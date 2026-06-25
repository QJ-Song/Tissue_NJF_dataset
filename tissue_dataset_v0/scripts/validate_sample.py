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

from tissue_dataset_v0.validation import build_default_validator, load_rule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate tissue dataset sample directories.")
    parser.add_argument("sample_dirs", nargs="+", type=Path, help="One or more sample directories to validate.")
    parser.add_argument("--log-dir-name", default="logs")
    parser.add_argument("--rule", action="append", default=[], help="Extra validation rule as module:ClassName.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--no-require-logs", action="store_true", help="Do not fail when logs are absent.")
    parser.add_argument("--warnings-as-errors", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    extra_rules = [load_rule(spec) for spec in args.rule]
    validator = build_default_validator(extra_rules=extra_rules)
    options = {"require_logs": False} if args.no_require_logs else {}
    reports = [
        validator.validate(sample_dir, log_dir_name=args.log_dir_name, options=options)
        for sample_dir in args.sample_dirs
    ]

    if args.format == "json":
        payload = [report.to_dict() for report in reports]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2, sort_keys=True))
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            print(report.format_text())

    failed = any(not report.is_valid for report in reports)
    if args.warnings_as_errors:
        failed = failed or any(report.warning_count > 0 for report in reports)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
