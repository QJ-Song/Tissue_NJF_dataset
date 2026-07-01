#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.njf.fitted import (  # noqa: E402
    FittedCoefficientConfig,
    evaluate_fitted_coefficient_predictor,
    jsonable,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit/evaluate NumPy ridge coefficient diagnostics on Mode C rollouts.")
    parser.add_argument("--basis-dataset", type=Path, required=True)
    parser.add_argument("--rollout-datasets", nargs="+", type=Path, required=True)
    parser.add_argument("--ranks", nargs="+", type=int, default=[2, 3, 4])
    parser.add_argument("--ridge-alpha", type=float, default=1e-4)
    parser.add_argument("--prefix-train-steps", type=int, default=5)
    parser.add_argument("--local-patch-size", type=int, default=64)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = FittedCoefficientConfig(
        ranks=tuple(sorted(set(args.ranks))),
        ridge_alpha=float(args.ridge_alpha),
        prefix_train_steps=int(args.prefix_train_steps),
        local_patch_size=int(args.local_patch_size),
    )
    payload = evaluate_fitted_coefficient_predictor(
        basis_dataset=args.basis_dataset,
        rollout_datasets=list(args.rollout_datasets),
        config=config,
    )
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(output / "per_evaluation_metrics.csv", payload["results"])
    write_csv(output / "per_step_metrics.csv", payload["per_step"])
    write_report(output / "report.md", payload)
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if payload["valid"] else 1


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({field for row in rows for field in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Fitted Coefficient Diagnostic v1",
        "",
        f"Basis dataset: `{payload['basis_dataset']}`",
        "",
        "Rollout datasets:",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["rollout_datasets"])
    lines.extend(
        [
            "",
            f"Directions: `{', '.join(payload['direction_ids'])}`",
            "",
            f"Trajectory count: `{payload['trajectory_count']}`",
            "",
            f"Ridge alpha: `{payload['ridge_alpha']}`",
            "",
            f"Prefix train steps: `{payload['prefix_train_steps']}`",
            "",
            f"Local patch size: `{payload.get('local_patch_size', 'n/a')}`",
            "",
            "## Aggregate Metrics",
            "",
            "| split | diagnostic | rank | count | final rel L2 mean | step rel L2 mean | coeff rel L2 mean | final max error mean (mm) |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for key in sorted(payload["aggregate"]):
        item = payload["aggregate"][key]
        lines.append(
            "| {split} | {predictor} | {rank} | {count} | {final:.6f} | {step:.6f} | {coeff:.6f} | {maxerr:.3f} |".format(
                split=item["split_id"],
                predictor=item["predictor_id"],
                rank=item["rank"],
                count=item["count"],
                final=item["final_relative_l2"]["mean"],
                step=item["step_relative_l2_mean"]["mean"],
                coeff=item["coefficient_relative_l2_mean"]["mean"],
                maxerr=item["final_max_node_error_m"]["mean"] * 1000.0,
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "`R1_non_autoregressive` uses depth/action/material/contact-distance features and does not use coefficient history.",
            "",
            "`R2_autoregressive` adds previous coefficient features. In test rollout, coefficients are estimated recursively after the first test step, so this is not teacher-forced except for the last observed prefix coefficient.",
            "",
            "`R3_state_local_ridge` adds local patch state features from `X_t` around the contact point.",
            "",
            "`prefix_per_trajectory` diagnoses within-trajectory extrapolation from early steps to later steps.",
            "",
            "`heldout_direction_within_group` trains within each matched contact/material basis group on other action directions and tests the held-out direction. It avoids mixing coefficient coordinates across different basis groups.",
            "",
        ]
    )
    if payload["errors"]:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {error}" for error in payload["errors"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Fitted coefficient diagnostic v1: {status}")
    print(
        f"trajectories={payload['trajectory_count']} groups={payload['group_count']} "
        f"directions={payload['direction_ids']} results={payload['result_count']} errors={len(payload['errors'])}"
    )
    for key in sorted(payload["aggregate"]):
        item = payload["aggregate"][key]
        print(
            f"- {item['split_id']} {item['predictor_id']} rank={item['rank']}: "
            f"final_rel_l2_mean={item['final_relative_l2']['mean']:.6f} "
            f"step_rel_l2_mean={item['step_relative_l2_mean']['mean']:.6f} "
            f"coeff_rel_l2_mean={item['coefficient_relative_l2_mean']['mean']:.6f}"
        )
    for error in payload["errors"]:
        print(f"error={error}")


if __name__ == "__main__":
    raise SystemExit(main())
