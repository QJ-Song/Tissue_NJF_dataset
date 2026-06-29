#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose how requested action depth maps to tool motion, contact gap, and tissue response."
    )
    parser.add_argument("dataset_or_samples", type=Path, help="Dataset root, samples/ directory, or one sample_* directory.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: DATASET_ROOT/analysis/probe_depth.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sample_dirs = discover_sample_dirs(args.dataset_or_samples)
    if not sample_dirs:
        print(f"No sample_* directories found under {args.dataset_or_samples}", file=sys.stderr)
        return 2
    rows = [diagnose_sample(sample_dir) for sample_dir in sample_dirs]
    summary = build_summary(rows)
    payload = {
        "valid": True,
        "analysis_type": "probe_depth",
        "sample_count": len(rows),
        "summary": summary,
        "rows": rows,
        "notes": [
            "requested_depth_m is action[5].",
            "tool_motion_m is norm(tool_pose_1.xyz - tool_pose_0.xyz).",
            "final_signed_gap and max_penetration come from contact_summary.json.",
            "If contact_distance is much larger than requested depth, LocalMinDistance can activate before actual penetration.",
        ],
    }
    output_dir = args.output_dir or default_output_dir(args.dataset_or_samples)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "probe_depth_samples.csv", rows)
    write_csv(output_dir / "probe_depth_by_requested_depth.csv", summary["by_requested_depth_mm"])
    write_json(output_dir / "summary.json", payload)
    (output_dir / "decision_summary.md").write_text(build_report(payload), encoding="utf-8")
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload, output_dir)
    return 0


def discover_sample_dirs(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_dir() and path.name.startswith("sample_"):
        return [path]
    if path.is_dir() and path.name == "samples":
        return sorted(item for item in path.iterdir() if item.is_dir() and item.name.startswith("sample_"))
    samples_dir = path / "samples"
    if samples_dir.is_dir():
        return sorted(item for item in samples_dir.iterdir() if item.is_dir() and item.name.startswith("sample_"))
    return []


def default_output_dir(path: Path) -> Path:
    path = Path(path)
    if path.name.startswith("sample_"):
        return path / "analysis" / "probe_depth"
    if path.name == "samples":
        return path.parent / "analysis" / "probe_depth"
    return path / "analysis" / "probe_depth"


def diagnose_sample(sample_dir: Path) -> dict[str, Any]:
    action = np.load(sample_dir / "action.npy").astype(np.float64)
    vertices_0 = np.load(sample_dir / "vertices_0.npy").astype(np.float64)
    displacement = np.load(sample_dir / "displacement.npy").astype(np.float64)
    contact_point = np.load(sample_dir / "contact_point.npy").astype(np.float64)
    contact_summary = load_json(sample_dir / "contact_summary.json")
    tool_pose_0 = load_optional_pose(sample_dir / "tool_pose_0.npy")
    tool_pose_1 = load_optional_pose(sample_dir / "tool_pose_1.npy")

    requested_depth = float(action[5]) if action.shape[0] >= 6 else 0.0
    direction = action[2:5] if action.shape[0] >= 5 else np.asarray([0.0, 0.0, -1.0])
    direction_norm = float(np.linalg.norm(direction))
    if direction_norm > 0.0:
        direction = direction / direction_norm
    p0 = tool_pose_0[:3, 3] if tool_pose_0 is not None else np.full(3, np.nan)
    p1 = tool_pose_1[:3, 3] if tool_pose_1 is not None else np.full(3, np.nan)
    tool_delta = p1 - p0
    tool_motion = float(np.linalg.norm(tool_delta)) if np.isfinite(tool_delta).all() else None
    tool_along_action = float(np.dot(tool_delta, direction)) if np.isfinite(tool_delta).all() else None
    nearest = np.asarray(contact_summary.get("nearest_point_at_min_gap", [np.nan, np.nan, np.nan]), dtype=np.float64)
    nearest_xy_distance = float(np.linalg.norm(nearest[:2] - contact_point[:2])) if np.isfinite(nearest[:2]).all() else None
    response_norm = float(np.linalg.norm(displacement.reshape(1, -1)))
    response_node_norms = np.linalg.norm(displacement, axis=1)
    return {
        "sample_id": sample_dir.name,
        "requested_depth_mm": requested_depth * 1e3,
        "action_direction": json.dumps([float(v) for v in direction]),
        "tool_motion_mm": None if tool_motion is None else tool_motion * 1e3,
        "tool_motion_along_action_mm": None if tool_along_action is None else tool_along_action * 1e3,
        "tool_motion_minus_depth_mm": None if tool_motion is None else (tool_motion - requested_depth) * 1e3,
        "contact_distance_mm": float(contact_summary.get("contact_distance", 0.0)) * 1e3,
        "contact_detected": bool(contact_summary.get("contact_detected", False)),
        "first_contact_step": contact_summary.get("first_contact_step"),
        "contact_frame_count": int(contact_summary.get("contact_frame_count", 0)),
        "observation_count": int(contact_summary.get("observation_count", 0)),
        "min_signed_gap_mm": float(contact_summary.get("min_signed_gap", 0.0)) * 1e3,
        "final_signed_gap_mm": float(contact_summary.get("final_signed_gap", 0.0)) * 1e3,
        "max_penetration_mm": float(contact_summary.get("max_penetration", 0.0)) * 1e3,
        "nearest_xy_distance_at_min_gap_mm": nearest_xy_distance * 1e3 if nearest_xy_distance is not None else None,
        "contact_point_x": float(contact_point[0]),
        "contact_point_y": float(contact_point[1]),
        "nearest_point_x": float(nearest[0]) if np.isfinite(nearest[0]) else None,
        "nearest_point_y": float(nearest[1]) if np.isfinite(nearest[1]) else None,
        "response_l2_norm_m": response_norm,
        "response_node_max_m": float(response_node_norms.max()) if response_node_norms.size else 0.0,
        "top_z_m": float(vertices_0[:, 2].max()),
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": summarize_numeric(rows),
        "by_requested_depth_mm": summarize_by_key(rows, "requested_depth_mm"),
        "diagnosis": diagnose_overall(rows),
    }


def summarize_by_key(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[float, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(round(float(row[key]), 8), []).append(row)
    output = []
    for value, bucket in sorted(buckets.items()):
        summary = summarize_numeric(bucket)
        summary[key] = value
        output.append(summary)
    return output


def summarize_numeric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "tool_motion_minus_depth_mm",
        "contact_distance_mm",
        "min_signed_gap_mm",
        "final_signed_gap_mm",
        "max_penetration_mm",
        "nearest_xy_distance_at_min_gap_mm",
        "response_l2_norm_m",
        "response_node_max_m",
    ]
    summary: dict[str, Any] = {"count": len(rows)}
    for field in fields:
        values = np.asarray([float(row[field]) for row in rows if row.get(field) is not None], dtype=np.float64)
        if values.size:
            summary[f"{field}_mean"] = float(values.mean())
            summary[f"{field}_min"] = float(values.min())
            summary[f"{field}_max"] = float(values.max())
        else:
            summary[f"{field}_mean"] = None
            summary[f"{field}_min"] = None
            summary[f"{field}_max"] = None
    return summary


def diagnose_overall(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "not_answered"
    contact_distances = np.asarray([float(row["contact_distance_mm"]) for row in rows], dtype=np.float64)
    depths = np.asarray([float(row["requested_depth_mm"]) for row in rows], dtype=np.float64)
    nearest_xy = np.asarray(
        [float(row["nearest_xy_distance_at_min_gap_mm"]) for row in rows if row.get("nearest_xy_distance_at_min_gap_mm") is not None],
        dtype=np.float64,
    )
    penetrations = np.asarray([float(row["max_penetration_mm"]) for row in rows], dtype=np.float64)
    if contact_distances.size and depths.size and float(contact_distances.mean()) > float(depths.max()):
        return "contact_distance_larger_than_depth; proximity constraints can dominate small-depth tests"
    if nearest_xy.size and depths.size and float(nearest_xy.mean()) > float(depths.max()):
        return "nearest_collision_vertex_offset_larger_than_depth; align contact point to a top collision vertex or use surface collision"
    if penetrations.size and np.all(penetrations <= 1e-9):
        return "no_penetration_recorded; requested depth is not producing geometric penetration"
    return "depth_parameterization_looks_geometrically_plausible"


def build_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    overall = summary["overall"]
    lines = [
        "# Probe Depth Diagnosis",
        "",
        f"Samples analyzed: {payload['sample_count']}",
        f"Diagnosis: {summary['diagnosis']}",
        "",
        "## Key Means",
        "",
        f"- contact distance mean: {format_optional(overall.get('contact_distance_mm_mean'))} mm",
        f"- nearest xy offset mean: {format_optional(overall.get('nearest_xy_distance_at_min_gap_mm_mean'))} mm",
        f"- final signed gap mean: {format_optional(overall.get('final_signed_gap_mm_mean'))} mm",
        f"- max penetration mean: {format_optional(overall.get('max_penetration_mm_mean'))} mm",
        f"- tool motion minus depth mean: {format_optional(overall.get('tool_motion_minus_depth_mm_mean'))} mm",
        "",
    ]
    return "\n".join(lines)


def print_text(payload: dict[str, Any], output_dir: Path) -> None:
    summary = payload["summary"]
    overall = summary["overall"]
    print("Probe depth diagnosis: PASS")
    print(f"samples={payload['sample_count']}")
    print(f"diagnosis={summary['diagnosis']}")
    print(
        "summary="
        f"contact_distance_mean={format_optional(overall.get('contact_distance_mm_mean'))}mm "
        f"nearest_xy_offset_mean={format_optional(overall.get('nearest_xy_distance_at_min_gap_mm_mean'))}mm "
        f"final_gap_mean={format_optional(overall.get('final_signed_gap_mm_mean'))}mm "
        f"max_penetration_mean={format_optional(overall.get('max_penetration_mm_mean'))}mm"
    )
    print(f"outputs={output_dir}")


def load_optional_pose(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    pose = np.load(path).astype(np.float64)
    if pose.shape != (4, 4):
        return None
    return pose


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(jsonable(value), sort_keys=True)
    return value


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def format_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
