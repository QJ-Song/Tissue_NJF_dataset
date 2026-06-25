#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.replay import ReplayReader, ReplayRunner, SummaryReplayViewer, load_viewer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a logged tissue dataset sample.")
    parser.add_argument("sample_dir", type=Path)
    parser.add_argument("--viewer", default="summary", help="summary or module:ClassName")
    parser.add_argument("--log-dir-name", default="logs")
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--stop", type=int, default=None)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--max-print", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = ReplayReader(args.sample_dir, log_dir_name=args.log_dir_name)
    if args.viewer == "summary":
        viewer = SummaryReplayViewer(max_frames=args.max_print)
    else:
        viewer = load_viewer(args.viewer)
    runner = ReplayRunner(reader, viewer)
    runner.run(start=args.start, stop=args.stop, stride=args.stride)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
