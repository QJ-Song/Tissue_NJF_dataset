#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.njf.baselines import (  # noqa: E402
    CoefficientBaselineConfig,
    evaluate_coefficient_baselines,
    jsonable,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate coefficient diagnostics on matched Mode B basis and Mode C rollout data.")
    parser.add_argument("--basis-dataset", type=Path, required=True)
    parser.add_argument("--rollout-dataset", type=Path, required=True)
    parser.add_argument("--ranks", nargs="+", type=int, default=[2, 3, 4])
    parser.add_argument("--trend-degree", type=int, default=1)
    parser.add_argument("--trend-train-steps", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True, help="Output directory.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = CoefficientBaselineConfig(
        ranks=tuple(sorted(set(args.ranks))),
        trend_degree=args.trend_degree,
        trend_train_steps=args.trend_train_steps,
    )
    payload = evaluate_coefficient_baselines(
        basis_dataset=args.basis_dataset,
        rollout_dataset=args.rollout_dataset,
        config=config,
    )
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    coefficient_arrays = payload.pop("coefficient_arrays")
    (output / "summary.json").write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(output / "per_trajectory_metrics.csv", payload["results"])
    write_csv(output / "per_step_metrics.csv", payload["per_step"])
    if coefficient_arrays:
        np.savez_compressed(output / "coefficient_trajectories.npz", **coefficient_arrays)
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
        "# Coefficient Diagnostics v1",
        "",
        f"Basis dataset: `{payload['basis_dataset']}`",
        "",
        f"Rollout dataset: `{payload['rollout_dataset']}`",
        "",
        f"Trajectories: {payload['trajectory_count']}",
        "",
        f"Trend model: polynomial degree `{payload['trend_degree']}` fit on first `{payload['trend_train_steps']}` steps.",
        "",
        "## Aggregate Metrics",
        "",
        "| diagnostic | rank | final rel L2 mean | step rel L2 mean | final max error mean (mm) | coeff rel L2 mean |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in sorted(payload["aggregate"]):
        item = payload["aggregate"][key]
        coeff_stats = item["coefficient_relative_l2_mean"]
        coeff_text = "n/a" if item["baseline_id"] == "B0_repeat_first_response" else f"{coeff_stats['mean']:.6f}"
        lines.append(
            "| {baseline} | {rank} | {final:.6f} | {step:.6f} | {maxerr:.3f} | {coeff} |".format(
                baseline=item["baseline_id"],
                rank=item["rank"],
                final=item["final_relative_l2"]["mean"],
                step=item["step_relative_l2_mean"]["mean"],
                maxerr=item["final_max_node_error_m"]["mean"] * 1000.0,
                coeff=coeff_text,
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "`B0_repeat_first_response` tests whether one observed local response can be reused through rollout.",
            "",
            "`B1_oracle_basis_projection` is an expression upper bound, not a predictive model. It tests whether rollout responses are representable in the matched Mode B basis.",
            "",
            "`B2_fixed_first_coefficient` tests whether the basis coefficients from the first step stay valid as tissue state changes.",
            "",
            "`B3_prefix_depth_trend_coefficient` is fit from early rollout steps. It tests whether coefficient evolution is smooth with cumulative depth, but it is not a cross-group generalization result or final model benchmark.",
            "",
        ]
    )
    if payload["errors"]:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {error}" for error in payload["errors"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Coefficient diagnostics v1: {status}")
    print(
        f"trajectories={payload['trajectory_count']} results={payload['result_count']} "
        f"errors={len(payload['errors'])}"
    )
    for key in sorted(payload["aggregate"]):
        item = payload["aggregate"][key]
        print(
            f"- {item['baseline_id']} rank={item['rank']}: "
            f"final_rel_l2_mean={item['final_relative_l2']['mean']:.6f} "
            f"step_rel_l2_mean={item['step_relative_l2_mean']['mean']:.6f} "
            f"final_max_mm_mean={item['final_max_node_error_m']['mean'] * 1000.0:.3f}"
        )
    for error in payload["errors"]:
        print(f"error={error}")


if __name__ == "__main__":
    raise SystemExit(main())
