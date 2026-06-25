#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check D4 tool pose displacement direction against saved action direction.")
    parser.add_argument("dataset_or_samples", nargs="+", type=Path)
    parser.add_argument("--min-samples", type=int, default=1)
    parser.add_argument("--max-angle-error-deg", type=float, default=0.1)
    parser.add_argument("--require-nonvertical", action="store_true")
    parser.add_argument("--min-max-tilt-deg", type=float, default=2.0, help="Required maximum action tilt from vertical when --require-nonvertical is set.")
    parser.add_argument("--min-motion-mm", type=float, default=0.1)
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
        item, item_issues = check_sample(sample_dir, max_angle_error_deg=args.max_angle_error_deg, min_motion_mm=args.min_motion_mm)
        samples.append(item)
        issues.extend(item_issues)
    if args.require_nonvertical:
        max_tilt = max((float(item.get("action_tilt_deg", 0.0)) for item in samples), default=0.0)
        if max_tilt < args.min_max_tilt_deg:
            issues.append(error("dataset", f"Maximum action tilt {max_tilt:.3f} deg is below required {args.min_max_tilt_deg:.3f} deg."))
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


def check_sample(sample_dir: Path, *, max_angle_error_deg: float, min_motion_mm: float) -> tuple[dict[str, Any], list[dict[str, str]]]:
    sample_id = sample_dir.name
    issues: list[dict[str, str]] = []
    required = [sample_dir / "tool_pose_0.npy", sample_dir / "tool_pose_1.npy", sample_dir / "action.npy"]
    for path in required:
        if not path.exists():
            issues.append(error(sample_id, f"Missing required artifact: {path.name}."))
    if issues:
        return {"sample_id": sample_id}, issues

    pose0 = np.load(sample_dir / "tool_pose_0.npy")
    pose1 = np.load(sample_dir / "tool_pose_1.npy")
    action = np.load(sample_dir / "action.npy")
    if pose0.shape != (4, 4) or pose1.shape != (4, 4):
        issues.append(error(sample_id, "tool poses must have shape [4, 4]."))
        return {"sample_id": sample_id}, issues
    if action.shape[0] < 5:
        issues.append(error(sample_id, "action must contain direction components at indices 2:5."))
        return {"sample_id": sample_id}, issues

    p0 = pose0[:3, 3].astype(float)
    p1 = pose1[:3, 3].astype(float)
    motion = p1 - p0
    motion_norm = float(np.linalg.norm(motion))
    motion_mm = motion_norm * 1000.0
    if motion_mm < min_motion_mm:
        issues.append(error(sample_id, f"Tool motion is {motion_mm:.6f} mm, below {min_motion_mm:.6f} mm."))
    motion_dir = normalize(motion)
    action_dir = normalize(action[2:5].astype(float))
    angle_error = angle_deg(motion_dir, action_dir)
    if angle_error > max_angle_error_deg:
        issues.append(error(sample_id, f"Tool motion/action direction angle error {angle_error:.6f} deg exceeds {max_angle_error_deg:.6f} deg."))
    if action_dir[2] >= 0.0:
        issues.append(error(sample_id, f"Action direction must point downward, got z={action_dir[2]:.6f}."))
    action_tilt = angle_deg(action_dir, np.asarray([0.0, 0.0, -1.0], dtype=float))
    xy_motion_mm = float(np.linalg.norm(motion[:2]) * 1000.0)
    z_drop_mm = float((p0[2] - p1[2]) * 1000.0)
    return {
        "sample_id": sample_id,
        "angle_error_deg": angle_error,
        "action_tilt_deg": action_tilt,
        "motion_mm": motion_mm,
        "xy_motion_mm": xy_motion_mm,
        "z_drop_mm": z_drop_mm,
        "action_direction": action_dir.tolist(),
        "motion_direction": motion_dir.tolist(),
    }, issues


def normalize(value: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(value))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize near-zero vector.")
    return value / norm


def angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
    return float(math.degrees(math.acos(dot)))


def error(sample_id: str, message: str) -> dict[str, str]:
    return {"level": "error", "sample": sample_id, "message": message}


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Tool direction check: {status}")
    print(f"samples={payload['sample_count']} errors={payload['error_count']} warnings={payload['warning_count']}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"- {issue['level'].upper()} {issue.get('sample', '')}: {issue['message']}")
    print("Samples:")
    for item in payload["samples"]:
        if "angle_error_deg" in item:
            print(
                f"- {item['sample_id']}: angle_error={item['angle_error_deg']:.6f} deg "
                f"tilt={item['action_tilt_deg']:.3f} deg motion={item['motion_mm']:.3f} mm "
                f"xy={item['xy_motion_mm']:.3f} mm z_drop={item['z_drop_mm']:.3f} mm"
            )
        else:
            print(f"- {item.get('sample_id')}")


if __name__ == "__main__":
    raise SystemExit(main())
