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

from tissue_dataset_v0.trajectory import load_trajectory_reader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or refresh a trajectory summary for a logged sample.")
    parser.add_argument("sample_dir", type=Path)
    parser.add_argument("--log-dir-name", default="logs")
    parser.add_argument("--reader", default="default", help="default or module:ClassName")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--print", action="store_true", help="Print the summary JSON after writing it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = load_trajectory_reader(args.reader, args.sample_dir, log_dir_name=args.log_dir_name)
    output_path = reader.write_summary(args.output)
    print(f"Wrote trajectory summary: {output_path}")
    if args.print:
        print(json.dumps(reader.build_summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
