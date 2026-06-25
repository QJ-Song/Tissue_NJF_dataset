#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.config import default_sample_request
from tissue_dataset_v0.layout import default_layout
from tissue_dataset_v0.pipeline import DatasetPipeline
from tissue_dataset_v0.toy_backend import ToyPressBackend
from tissue_dataset_v0.writer import FileSystemSampleWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a tissue dataset V0 sample.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "dataset_v0")
    parser.add_argument("--sample-id", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true", help="Delete an existing non-empty sample directory before regenerating it.")
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="Only export the named artifact. Repeatable.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Skip the named artifact. Repeatable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    layout = default_layout()
    backend = ToyPressBackend()
    writer = FileSystemSampleWriter(layout)
    pipeline = DatasetPipeline(backend=backend, writer=writer)
    request = default_sample_request(sample_id=args.sample_id)
    request = replace(
        request,
        enabled_artifacts=args.include,
        disabled_artifacts=tuple(args.exclude or ()),
    )
    try:
        sample_dir = pipeline.generate(
            args.output_dir,
            request,
            existing_policy="overwrite" if args.overwrite else "error",
        )
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Generated sample: {sample_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
