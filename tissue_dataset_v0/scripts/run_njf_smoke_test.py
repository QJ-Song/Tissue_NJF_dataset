#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.njf import generate_mode_a, load_njf_plan, validate_njf_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate a tiny SOFA NJF Mode A smoke dataset.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "sofa_njf_dataset.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "sofa_njf_mode_a_smoke")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = load_njf_plan(args.config, output_override=args.output)
    root = generate_mode_a(plan, overwrite=args.overwrite)
    report = validate_njf_dataset(root)
    status = "PASS" if report.valid else "FAIL"
    print(f"NJF Mode A smoke: {status}")
    print(f"dataset={root}")
    print(f"samples={len(report.samples)} errors={len(report.errors)} warnings={len(report.warnings)}")
    for error in report.errors:
        print(f"- ERROR: {error}")
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
