#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check optional tool motion artifacts for Stage D samples.")
    parser.add_argument("dataset_or_samples", nargs="+", type=Path)
    parser.add_argument("--min-samples", type=int, default=1)
    parser.add_argument("--min-z-drop-mm", type=float, default=0.5)
    parser.add_argument("--max-z-drop-mm", type=float, default=30.0)
    parser.add_argument("--max-log-pose-error-mm", type=float, default=1e-3)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sample_dirs = discover_samples(args.dataset_or_samples)
    issues: list[dict[str, str]] = []
    if len(sample_dirs) < args.min_samples:
        issues.append({"level": "error", "message": f"Expected at least {args.min_samples} samples, found {len(sample_dirs)}."})
    samples = []
    for sample_dir in sample_dirs:
        item, item_issues = check_sample(
            sample_dir,
            min_z_drop_mm=args.min_z_drop_mm,
            max_z_drop_mm=args.max_z_drop_mm,
            max_log_pose_error_mm=args.max_log_pose_error_mm,
        )
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


def check_sample(sample_dir: Path, *, min_z_drop_mm: float, max_z_drop_mm: float, max_log_pose_error_mm: float) -> tuple[dict[str, Any], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    sample_id = sample_dir.name
    pose_0_path = sample_dir / "tool_pose_0.npy"
    pose_1_path = sample_dir / "tool_pose_1.npy"
    geometry_path = sample_dir / "tool_geometry.json"
    if not pose_0_path.exists():
        issues.append(error(sample_id, "Missing tool_pose_0.npy."))
    if not pose_1_path.exists():
        issues.append(error(sample_id, "Missing tool_pose_1.npy."))
    if not geometry_path.exists():
        issues.append(error(sample_id, "Missing tool_geometry.json."))
    if issues:
        return {"sample_id": sample_id}, issues

    pose_0 = np.load(pose_0_path)
    pose_1 = np.load(pose_1_path)
    geometry = load_json(geometry_path)
    if pose_0.shape != (4, 4):
        issues.append(error(sample_id, f"tool_pose_0 shape is {list(pose_0.shape)}, expected [4, 4]."))
    if pose_1.shape != (4, 4):
        issues.append(error(sample_id, f"tool_pose_1 shape is {list(pose_1.shape)}, expected [4, 4]."))
    if not np.isfinite(pose_0).all() or not np.isfinite(pose_1).all():
        issues.append(error(sample_id, "Tool poses contain NaN or Inf."))
    if geometry.get("type") != "sphere":
        issues.append(error(sample_id, "tool_geometry.type must be sphere for D2."))
    radius = geometry.get("radius")
    if not isinstance(radius, (int, float)) or float(radius) <= 0.0:
        issues.append(error(sample_id, "tool_geometry.radius must be positive."))

    p0 = pose_0[:3, 3].astype(float)
    p1 = pose_1[:3, 3].astype(float)
    z_drop_mm = float((p0[2] - p1[2]) * 1000.0)
    if z_drop_mm < min_z_drop_mm:
        issues.append(error(sample_id, f"Tool z drop is {z_drop_mm:.3f} mm, below {min_z_drop_mm:.3f} mm."))
    if z_drop_mm > max_z_drop_mm:
        issues.append(error(sample_id, f"Tool z drop is {z_drop_mm:.3f} mm, above {max_z_drop_mm:.3f} mm."))

    first_log, last_log = load_first_last_tool_positions(sample_dir)
    max_log_error_mm = None
    if first_log is None or last_log is None:
        issues.append(error(sample_id, "Logged frames must include tool_position."))
    else:
        first_error = float(np.linalg.norm(np.asarray(first_log, dtype=float) - p0) * 1000.0)
        last_error = float(np.linalg.norm(np.asarray(last_log, dtype=float) - p1) * 1000.0)
        max_log_error_mm = max(first_error, last_error)
        if max_log_error_mm > max_log_pose_error_mm:
            issues.append(error(sample_id, f"Logged tool_position differs from tool poses by {max_log_error_mm:.6f} mm."))

    return {
        "sample_id": sample_id,
        "tool_pose_0_xyz": p0.tolist(),
        "tool_pose_1_xyz": p1.tolist(),
        "z_drop_mm": z_drop_mm,
        "tool_geometry": geometry,
        "max_log_pose_error_mm": max_log_error_mm,
    }, issues


def load_first_last_tool_positions(sample_dir: Path) -> tuple[list[float] | None, list[float] | None]:
    frame_paths = sorted((sample_dir / "logs" / "frames").glob("frame_*.json"))
    positions: list[list[float]] = []
    for path in frame_paths:
        data = load_json(path)
        value = data.get("tool_position")
        if isinstance(value, list) and len(value) == 3:
            positions.append([float(v) for v in value])
    if not positions:
        return None, None
    return positions[0], positions[-1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def error(sample_id: str, message: str) -> dict[str, str]:
    return {"level": "error", "sample": sample_id, "message": message}


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Tool motion check: {status}")
    print(f"samples={payload['sample_count']} errors={payload['error_count']} warnings={payload['warning_count']}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"- {issue['level'].upper()} {issue.get('sample', '')}: {issue['message']}")
    print("Samples:")
    for item in payload["samples"]:
        if "z_drop_mm" in item:
            print(
                f"- {item['sample_id']}: z_drop={item['z_drop_mm']:.3f} mm "
                f"radius={item['tool_geometry'].get('radius')} "
                f"log_error={item['max_log_pose_error_mm']} mm"
            )
        else:
            print(f"- {item.get('sample_id')}")


if __name__ == "__main__":
    raise SystemExit(main())
