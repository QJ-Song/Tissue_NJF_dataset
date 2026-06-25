#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.config import load_generation_from_yaml
from tissue_dataset_v0.pipeline import DatasetPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate tissue dataset samples from YAML config.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="Delete existing non-empty sample directories before regenerating them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _, generation, sampler, backend, writer = load_generation_from_yaml(args.config)
    rng = np.random.default_rng(generation.seed)
    pipeline = DatasetPipeline(backend=backend, writer=writer)

    for offset in range(generation.num_samples):
        sample_id = generation.sample_id_start + offset
        request = sampler.sample(sample_id, rng)
        request = replace(
            request,
            config=replace(request.config, extra=dict(generation.backend_extra or {})),
            logging=generation.logging,
            enabled_artifacts=generation.enabled_artifacts,
            disabled_artifacts=generation.disabled_artifacts,
        )
        try:
            sample_dir = pipeline.generate(
                generation.output_dir,
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
