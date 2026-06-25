#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check D5 boundary and solver metadata artifacts.")
    parser.add_argument("dataset_or_samples", nargs="+", type=Path)
    parser.add_argument("--min-samples", type=int, default=1)
    parser.add_argument("--fixed-displacement-tol-mm", type=float, default=1e-3)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sample_dirs = discover_samples(args.dataset_or_samples)
    issues: list[dict[str, str]] = []
    if len(sample_dirs) < args.min_samples:
        issues.append(error("dataset", f"Expected at least {args.min_samples} samples, found {len(sample_dirs)}."))
    samples = []
    for sample_dir in sample_dirs:
        item, item_issues = check_sample(sample_dir, fixed_displacement_tol_mm=args.fixed_displacement_tol_mm, allow_missing=args.allow_missing)
        samples.append(item)
        issues.extend(item_issues)
    valid = not any(issue["level"] == "error" for issue in issues)
    payload = {
        "valid": valid,
        "sample_count": len(sample_dirs),
        "error_count": sum(1 for issue in issues if issue["level"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["level"] == "warning"),
        "issues": issues,
        "samples": samples,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if valid else 1


def discover_samples(paths: list[Path]) -> list[Path]:
    sample_dirs: list[Path] = []
    for path in paths:
        if path.name.startswith("sample_") and path.is_dir():
            sample_dirs.append(path)
        elif path.is_dir():
            sample_dirs.extend(sorted(child for child in path.iterdir() if child.is_dir() and child.name.startswith("sample_")))
    return sorted(set(sample_dirs))


def check_sample(sample_dir: Path, *, fixed_displacement_tol_mm: float, allow_missing: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
    sample_id = sample_dir.name
    issues: list[dict[str, str]] = []
    required = {
        "fixed_node_indices": sample_dir / "fixed_node_indices.npy",
        "free_node_indices": sample_dir / "free_node_indices.npy",
        "boundary_mask": sample_dir / "boundary_mask.npy",
        "boundary": sample_dir / "boundary.json",
        "solver_summary": sample_dir / "solver_summary.json",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        issue_fn = warning if allow_missing else error
        return {"sample_id": sample_id, "present": False, "missing": missing}, [issue_fn(sample_id, f"Missing D5 artifact(s): {', '.join(missing)}.")]

    fixed = np.load(required["fixed_node_indices"])
    free = np.load(required["free_node_indices"])
    mask = np.load(required["boundary_mask"])
    boundary = load_json(required["boundary"])
    solver = load_json(required["solver_summary"])
    vertices_0 = np.load(sample_dir / "vertices_0.npy")
    vertices_1 = np.load(sample_dir / "vertices_1.npy")

    vertex_count = int(vertices_0.shape[0])
    if mask.shape != (vertex_count,):
        issues.append(error(sample_id, f"boundary_mask shape {list(mask.shape)} does not match vertex_count {vertex_count}."))
    if mask.dtype != np.bool_:
        issues.append(error(sample_id, f"boundary_mask dtype is {mask.dtype}, expected bool."))
    if fixed.ndim != 1 or free.ndim != 1:
        issues.append(error(sample_id, "fixed_node_indices and free_node_indices must be 1D."))
    if not np.issubdtype(fixed.dtype, np.integer) or not np.issubdtype(free.dtype, np.integer):
        issues.append(error(sample_id, "fixed/free indices must be integer arrays."))
    if np.intersect1d(fixed, free).size:
        issues.append(error(sample_id, "fixed and free node indices overlap."))
    if fixed.size + free.size != vertex_count:
        issues.append(error(sample_id, "fixed/free index counts do not sum to vertex_count."))
    if mask.shape == (vertex_count,):
        if not np.array_equal(np.nonzero(mask)[0], np.sort(fixed.astype(int))):
            issues.append(error(sample_id, "boundary_mask true indices do not match fixed_node_indices."))

    if fixed.size:
        fixed_disp_mm = np.linalg.norm(vertices_1[fixed.astype(int)] - vertices_0[fixed.astype(int)], axis=1) * 1000.0
        max_fixed_disp_mm = float(fixed_disp_mm.max())
    else:
        max_fixed_disp_mm = 0.0
        issues.append(error(sample_id, "No fixed nodes recorded."))
    if max_fixed_disp_mm > fixed_displacement_tol_mm:
        issues.append(error(sample_id, f"Max fixed-node displacement {max_fixed_disp_mm:.6f} mm exceeds {fixed_displacement_tol_mm:.6f} mm."))

    if boundary.get("boundary_type") != "fixed_bottom":
        issues.append(error(sample_id, "boundary.boundary_type must be fixed_bottom for current D5 samples."))
    for key in ("fixed_node_count", "free_node_count", "total_node_count", "boundary_box"):
        if key not in boundary:
            issues.append(error(sample_id, f"boundary.json missing field: {key}."))
    if int(boundary.get("fixed_node_count", -1)) != int(fixed.size):
        issues.append(error(sample_id, "boundary.fixed_node_count does not match fixed_node_indices."))
    if int(boundary.get("free_node_count", -1)) != int(free.size):
        issues.append(error(sample_id, "boundary.free_node_count does not match free_node_indices."))

    solver_required = ["valid", "finite", "dt", "total_steps", "settling_steps", "record_every_n", "ode_solver", "linear_solver", "nan_or_inf_detected"]
    for key in solver_required:
        if key not in solver:
            issues.append(error(sample_id, f"solver_summary missing field: {key}."))
    if not bool(solver.get("finite", False)) or bool(solver.get("nan_or_inf_detected", True)):
        issues.append(error(sample_id, "solver_summary reports non-finite state."))
    if float(solver.get("dt", 0.0)) <= 0.0:
        issues.append(error(sample_id, "solver_summary.dt must be positive."))
    if int(solver.get("total_steps", 0)) <= 0:
        issues.append(error(sample_id, "solver_summary.total_steps must be positive."))

    manifest_issue = check_manifest(sample_dir, required_names=set(required))
    if manifest_issue is not None:
        issues.append(manifest_issue)

    return {
        "sample_id": sample_id,
        "present": True,
        "vertex_count": vertex_count,
        "fixed_node_count": int(fixed.size),
        "free_node_count": int(free.size),
        "max_fixed_displacement_mm": max_fixed_disp_mm,
        "dt": solver.get("dt"),
        "total_steps": solver.get("total_steps"),
        "solver_valid": solver.get("valid"),
    }, issues


def check_manifest(sample_dir: Path, *, required_names: set[str]) -> dict[str, str] | None:
    manifest_path = sample_dir / "sample_manifest.json"
    if not manifest_path.exists():
        return warning(sample_dir.name, "sample_manifest.json is absent; cannot verify D5 artifact entries.")
    manifest = load_json(manifest_path)
    present = {item.get("name") for item in manifest.get("artifacts", []) if item.get("present", False)}
    missing = sorted(required_names - present)
    if missing:
        return error(sample_dir.name, f"sample_manifest missing present D5 artifact(s): {', '.join(missing)}.")
    return None


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def error(sample_id: str, message: str) -> dict[str, str]:
    return {"level": "error", "sample": sample_id, "message": message}


def warning(sample_id: str, message: str) -> dict[str, str]:
    return {"level": "warning", "sample": sample_id, "message": message}


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Boundary/solver check: {status}")
    print(f"samples={payload['sample_count']} errors={payload['error_count']} warnings={payload['warning_count']}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"- {issue['level'].upper()} {issue.get('sample', '')}: {issue['message']}")
    print("Samples:")
    for item in payload["samples"]:
        if item.get("present"):
            print(
                f"- {item['sample_id']}: fixed={item['fixed_node_count']} free={item['free_node_count']} "
                f"max_fixed_disp={item['max_fixed_displacement_mm']:.6f} mm "
                f"dt={item['dt']} steps={item['total_steps']} valid={item['solver_valid']}"
            )
        else:
            print(f"- {item['sample_id']}: missing {item.get('missing')}")


if __name__ == "__main__":
    raise SystemExit(main())
