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

from tissue_dataset_v0.njf import validate_njf_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a SOFA NJF dataset root.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_njf_dataset(args.dataset)
    payload = report.to_dict()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "PASS" if report.valid else "FAIL"
        print(f"NJF dataset validation: {status}")
        print(f"samples={len(report.samples)} errors={len(report.errors)} warnings={len(report.warnings)}")
        for error in report.errors:
            print(f"- ERROR: {error}")
        for warning in report.warnings:
            print(f"- WARNING: {warning}")
        for sample in report.samples:
            print(f"- {sample.get('sample_id')}: action={sample.get('action_magnitude_m')} max_disp={sample.get('max_displacement_m')} contact={sample.get('contact_detected')}")
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
