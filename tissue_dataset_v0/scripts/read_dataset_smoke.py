#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.dataset import TissueSampleDataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-read generated tissue dataset samples.")
    parser.add_argument("dataset_or_samples", nargs="+", type=Path)
    parser.add_argument("--artifact", action="append", default=None, help="Only load this artifact name; repeatable.")
    parser.add_argument("--require", action="append", default=[], help="Require this artifact name; repeatable.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = TissueSampleDataset(
        args.dataset_or_samples,
        artifact_names=args.artifact,
        require_artifacts=args.require,
        load_all_present=args.artifact is None,
    )
    summary = dataset.summary()
    issues = validate_summary(summary, required_artifacts=default_required_artifacts(args))
    payload = {
        "valid": not issues,
        "issues": issues,
        **summary,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if payload["valid"] else 1


def default_required_artifacts(args: argparse.Namespace) -> tuple[str, ...]:
    if args.artifact is not None:
        return tuple(args.require)
    return ("vertices_0", "vertices_1", "displacement", "action", "material", "meta")


def validate_summary(summary: dict, *, required_artifacts: tuple[str, ...]) -> list[str]:
    issues: list[str] = []
    if summary["sample_count"] == 0:
        issues.append("No sample directories found.")
    for required in required_artifacts:
        if required not in summary["loaded_artifacts"]:
            issues.append(f"Required smoke artifact was not loaded: {required}")
    return issues


def print_text(payload: dict) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Dataset read smoke: {status}")
    print(f"samples={payload['sample_count']}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"- {issue}")
    print(f"loaded_artifacts={payload['loaded_artifacts']}")
    print("array_shapes:")
    for name, shapes in payload["array_shapes"].items():
        fixed = payload["fixed_array_shapes"].get(name)
        print(f"- {name}: shapes={shapes} fixed={fixed}")
    print(f"material_keys={payload['material_keys']}")


if __name__ == "__main__":
    raise SystemExit(main())
