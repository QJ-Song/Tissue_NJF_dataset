#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check optional contact summary/log fields for Stage D contact samples.")
    parser.add_argument("dataset_or_samples", nargs="+", type=Path)
    parser.add_argument("--min-samples", type=int, default=1)
    parser.add_argument("--allow-missing", action="store_true", help="Warn instead of fail when contact_summary.json is absent.")
    parser.add_argument("--allow-no-contact", action="store_true", help="Do not fail when contact_detected is false.")
    parser.add_argument("--max-min-gap-mm", type=float, default=5.0, help="Maximum allowed min signed gap for detected/nonpenetrating proximity.")
    parser.add_argument("--max-penetration-mm", type=float, default=5.0)
    parser.add_argument("--no-require-logs", action="store_true")
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
        item, sample_issues = check_sample(
            sample_dir,
            allow_missing=args.allow_missing,
            allow_no_contact=args.allow_no_contact,
            max_min_gap_mm=args.max_min_gap_mm,
            max_penetration_mm=args.max_penetration_mm,
            require_logs=not args.no_require_logs,
        )
        samples.append(item)
        issues.extend(sample_issues)
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


def check_sample(
    sample_dir: Path,
    *,
    allow_missing: bool,
    allow_no_contact: bool,
    max_min_gap_mm: float,
    max_penetration_mm: float,
    require_logs: bool,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    sample_id = sample_dir.name
    issues: list[dict[str, str]] = []
    summary_path = sample_dir / "contact_summary.json"
    if not summary_path.exists():
        item = {"sample_id": sample_id, "contact_summary_present": False}
        issue = warning(sample_id, "Missing contact_summary.json.") if allow_missing else error(sample_id, "Missing contact_summary.json.")
        return item, [issue]

    summary = load_json(summary_path)
    manifest_issue = check_manifest(sample_dir)
    if manifest_issue is not None:
        issues.append(manifest_issue)

    required_fields = [
        "contact_detected",
        "first_contact_step",
        "contact_frame_count",
        "observation_count",
        "min_signed_gap",
        "max_penetration",
        "contact_distance",
        "method",
        "force_available",
    ]
    for field in required_fields:
        if field not in summary:
            issues.append(error(sample_id, f"contact_summary missing field: {field}."))

    numeric_fields = ["min_signed_gap", "max_penetration", "contact_distance"]
    for field in numeric_fields:
        if field in summary and not np.isfinite(float(summary[field])):
            issues.append(error(sample_id, f"contact_summary.{field} is not finite."))

    contact_detected = bool(summary.get("contact_detected", False))
    if not contact_detected and not allow_no_contact:
        issues.append(error(sample_id, "contact_detected is false."))
    if contact_detected:
        if summary.get("first_contact_step") is None:
            issues.append(error(sample_id, "first_contact_step must be set when contact is detected."))
        if int(summary.get("contact_frame_count", 0)) <= 0:
            issues.append(error(sample_id, "contact_frame_count must be positive when contact is detected."))

    min_gap_mm = float(summary.get("min_signed_gap", float("inf"))) * 1000.0
    max_penetration_value_mm = float(summary.get("max_penetration", 0.0)) * 1000.0
    if min_gap_mm > max_min_gap_mm:
        issues.append(error(sample_id, f"min_signed_gap is {min_gap_mm:.3f} mm, above {max_min_gap_mm:.3f} mm."))
    if max_penetration_value_mm > max_penetration_mm:
        issues.append(error(sample_id, f"max_penetration is {max_penetration_value_mm:.3f} mm, above {max_penetration_mm:.3f} mm."))

    log_summary = check_frame_logs(sample_dir, require_logs=require_logs)
    issues.extend(log_summary.pop("issues"))

    return {
        "sample_id": sample_id,
        "contact_summary_present": True,
        "contact_detected": contact_detected,
        "first_contact_step": summary.get("first_contact_step"),
        "contact_frame_count": summary.get("contact_frame_count"),
        "observation_count": summary.get("observation_count"),
        "min_signed_gap_mm": min_gap_mm,
        "max_penetration_mm": max_penetration_value_mm,
        "force_available": bool(summary.get("force_available", False)),
        **log_summary,
    }, issues


def check_manifest(sample_dir: Path) -> dict[str, str] | None:
    manifest_path = sample_dir / "sample_manifest.json"
    if not manifest_path.exists():
        return warning(sample_dir.name, "sample_manifest.json is absent; cannot verify contact_summary manifest entry.")
    manifest = load_json(manifest_path)
    artifacts = manifest.get("artifacts", [])
    for artifact in artifacts:
        if artifact.get("name") == "contact_summary":
            if not artifact.get("present", False):
                return error(sample_dir.name, "sample_manifest marks contact_summary present=false.")
            return None
    return error(sample_dir.name, "sample_manifest has no contact_summary artifact entry.")


def check_frame_logs(sample_dir: Path, *, require_logs: bool) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    frame_paths = sorted((sample_dir / "logs" / "frames").glob("frame_*.json"))
    if not frame_paths:
        if require_logs:
            issues.append(error(sample_dir.name, "No frame JSON logs found."))
        return {"logged_frame_count": 0, "logged_contact_active_count": 0, "issues": issues}

    active_count = 0
    checked_count = 0
    for path in frame_paths:
        data = load_json(path)
        if "contact_active" not in data or "signed_gap" not in data or "contact_distance" not in data:
            issues.append(error(sample_dir.name, f"Frame log missing contact scalar(s): {path.name}."))
            continue
        checked_count += 1
        if bool(data.get("contact_active", False)):
            active_count += 1
        for key in ("signed_gap", "contact_distance"):
            if not np.isfinite(float(data[key])):
                issues.append(error(sample_dir.name, f"Frame log {path.name} has non-finite {key}."))
    return {"logged_frame_count": checked_count, "logged_contact_active_count": active_count, "issues": issues}


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
    print(f"Contact check: {status}")
    print(f"samples={payload['sample_count']} errors={payload['error_count']} warnings={payload['warning_count']}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"- {issue['level'].upper()} {issue.get('sample', '')}: {issue['message']}")
    print("Samples:")
    for item in payload["samples"]:
        if item.get("contact_summary_present"):
            print(
                f"- {item['sample_id']}: contact={item['contact_detected']} "
                f"first={item['first_contact_step']} frames={item['contact_frame_count']} "
                f"min_gap={item['min_signed_gap_mm']:.3f} mm "
                f"max_pen={item['max_penetration_mm']:.3f} mm "
                f"logged_active={item['logged_contact_active_count']}"
            )
        else:
            print(f"- {item['sample_id']}: missing contact_summary")


if __name__ == "__main__":
    raise SystemExit(main())
