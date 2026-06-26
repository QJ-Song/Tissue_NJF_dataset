#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.njf import generate_njf_dataset, load_njf_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SOFA NJF dataset modes from YAML config.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "sofa_njf_dataset.yaml")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = load_njf_plan(args.config, output_override=args.output)
    root = generate_njf_dataset(plan, overwrite=args.overwrite)
    print(f"Generated NJF dataset: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
