#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project Mode C rollout step responses onto matched Mode B response-basis groups."
    )
    parser.add_argument("--rollout-dataset", type=Path, required=True)
    parser.add_argument("--basis-dataset", type=Path, required=True)
    parser.add_argument("--ranks", nargs="+", type=int, default=[2], help="Basis ranks to evaluate.")
    parser.add_argument("--output", type=Path, required=True, help="JSON summary output path.")
    parser.add_argument("--csv-output", type=Path, default=None)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ranks = sorted(set(int(rank) for rank in args.ranks))
    if not ranks or any(rank <= 0 for rank in ranks):
        raise ValueError("--ranks must contain positive integers")

    basis_groups = load_basis_groups(args.basis_dataset)
    trajectories = discover_trajectory_dirs(args.rollout_dataset)
    if not trajectories:
        print(f"No traj_* directories found under {args.rollout_dataset}", file=sys.stderr)
        return 2
    if not basis_groups:
        print(f"No basis groups found under {args.basis_dataset}", file=sys.stderr)
        return 2

    results = []
    errors: list[str] = []
    warnings: list[str] = []
    for traj_dir in trajectories:
        try:
            results.extend(analyze_trajectory(traj_dir, basis_groups=basis_groups, ranks=ranks))
        except Exception as exc:  # keep processing visible in JSON/text output
            errors.append(f"{traj_dir.name}: {exc}")

    aggregate = aggregate_results(results, ranks)
    payload = {
        "valid": not errors,
        "rollout_dataset": str(args.rollout_dataset),
        "basis_dataset": str(args.basis_dataset),
        "trajectory_count": len(trajectories),
        "basis_group_count": len(basis_groups),
        "ranks": ranks,
        "result_count": len(results),
        "errors": errors,
        "warnings": warnings,
        "aggregate_by_rank": aggregate,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.csv_output is not None:
        write_csv(args.csv_output, results)
    if args.report_output is not None:
        write_report(args.report_output, payload)
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if not errors else 1


def load_basis_groups(dataset_root: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    groups_root = dataset_root / "groups"
    groups = {}
    for group_dir in sorted(groups_root.glob("group_*")):
        metadata = load_json(group_dir / "group_metadata.json")
        key = (
            str(metadata.get("contact_point_id")),
            str(metadata.get("material_id")),
            str(metadata.get("boundary_id")),
        )
        responses = np.load(group_dir / "responses.npy").astype(np.float64)
        actions = np.load(group_dir / "actions.npy").astype(np.float64)
        if responses.ndim != 3 or responses.shape[2] != 3:
            raise ValueError(f"{group_dir}: responses.npy must have shape [K, N, 3]")
        flat = responses.reshape(responses.shape[0], -1)
        _, singular_values, vt = np.linalg.svd(flat, full_matrices=False)
        groups[key] = {
            "group_dir": group_dir,
            "group_id": group_dir.name,
            "metadata": metadata,
            "responses": responses,
            "actions": actions,
            "flat_responses": flat,
            "singular_values": singular_values,
            "basis_rows": vt,
            "max_rank": int(vt.shape[0]),
        }
    return groups


def discover_trajectory_dirs(dataset_root: Path) -> list[Path]:
    if dataset_root.is_dir() and dataset_root.name.startswith("traj_"):
        return [dataset_root]
    trajectories_root = dataset_root / "trajectories"
    if trajectories_root.is_dir():
        return sorted(path for path in trajectories_root.iterdir() if path.is_dir() and path.name.startswith("traj_"))
    if dataset_root.is_dir() and dataset_root.name == "trajectories":
        return sorted(path for path in dataset_root.iterdir() if path.is_dir() and path.name.startswith("traj_"))
    return []


def analyze_trajectory(
    traj_dir: Path,
    *,
    basis_groups: dict[tuple[str, str, str], dict[str, Any]],
    ranks: list[int],
) -> list[dict[str, Any]]:
    metadata = load_json(traj_dir / "trajectory_metadata.json")
    states = np.load(traj_dir / "states.npy").astype(np.float64)
    responses = np.load(traj_dir / "responses.npy").astype(np.float64)
    actions = np.load(traj_dir / "actions.npy").astype(np.float64)
    if states.ndim != 3 or responses.ndim != 3:
        raise ValueError("states/responses must be rank-3 arrays")
    if responses.shape != states[1:].shape:
        raise ValueError("responses shape does not match states[1:]")

    key = (
        str(metadata.get("contact_point_id")),
        str(metadata.get("material_id")),
        str(metadata.get("boundary_id")),
    )
    if key not in basis_groups:
        raise KeyError(f"no matched basis group for key={key}")
    group = basis_groups[key]
    if group["flat_responses"].shape[1] != responses.reshape(responses.shape[0], -1).shape[1]:
        raise ValueError("basis response dimension does not match rollout response dimension")

    flat = responses.reshape(responses.shape[0], -1)
    true_final = states[-1] - states[0]
    true_final_flat = true_final.reshape(-1)
    constant = constant_first_step_metrics(responses, true_final)

    results = []
    for rank in ranks:
        rank = min(rank, group["max_rank"])
        basis_rows = group["basis_rows"][:rank]
        projected_flat = project_rows(flat, basis_rows)
        projected = projected_flat.reshape(responses.shape)
        residual = flat - projected_flat
        step_relative = row_norms(residual) / np.maximum(row_norms(flat), 1e-12)
        step_cosines = row_cosines(projected_flat, flat)
        predicted_final = projected.sum(axis=0)
        final_residual = predicted_final - true_final
        basis_train_error = basis_group_train_error(group["flat_responses"], basis_rows)
        results.append(
            {
                "trajectory_id": traj_dir.name,
                "trajectory_dir": str(traj_dir),
                "matched_group_id": group["group_id"],
                "matched_group_dir": str(group["group_dir"]),
                "contact_point_id": key[0],
                "material_id": key[1],
                "boundary_id": key[2],
                "direction_id": metadata.get("direction_id"),
                "rank": int(rank),
                "basis_max_rank": int(group["max_rank"]),
                "basis_action_count": int(group["actions"].shape[0]),
                "rollout_step_count": int(responses.shape[0]),
                "rollout_step_size_m": float(actions[0, 5]) if actions.ndim == 2 and actions.shape[1] >= 6 else None,
                "step_relative_error": step_relative.tolist(),
                "step_relative_error_mean": float(step_relative.mean()),
                "step_relative_error_max": float(step_relative.max()),
                "step_projection_cosine": step_cosines.tolist(),
                "step_projection_cosine_mean": float(step_cosines.mean()),
                "final_accumulated_relative_l2_error": float(
                    np.linalg.norm(final_residual.reshape(-1)) / max(np.linalg.norm(true_final_flat), 1e-12)
                ),
                "final_accumulated_max_node_error_m": float(np.linalg.norm(final_residual, axis=1).max()),
                "basis_train_relative_error_mean": float(basis_train_error.mean()),
                "basis_train_relative_error_max": float(basis_train_error.max()),
                "constant_first_step_final_relative_l2_error": constant["final_relative_l2_error"],
                "constant_first_step_final_max_node_error_m": constant["final_max_node_error_m"],
                "constant_first_step_step_relative_error_mean": constant["step_relative_error_mean"],
                "improvement_vs_constant_final_l2": float(
                    constant["final_relative_l2_error"]
                    - np.linalg.norm(final_residual.reshape(-1)) / max(np.linalg.norm(true_final_flat), 1e-12)
                ),
                "interpretation": "Projects each rollout delta_X_k onto the fixed initial-state Mode B response basis matched by contact/material/boundary.",
            }
        )
    return results


def project_rows(rows: np.ndarray, basis_rows: np.ndarray) -> np.ndarray:
    return (rows @ basis_rows.T) @ basis_rows


def row_norms(rows: np.ndarray) -> np.ndarray:
    return np.linalg.norm(rows, axis=1)


def row_cosines(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    denom = np.maximum(denom, 1e-12)
    return np.sum(a * b, axis=1) / denom


def basis_group_train_error(group_rows: np.ndarray, basis_rows: np.ndarray) -> np.ndarray:
    projected = project_rows(group_rows, basis_rows)
    return row_norms(group_rows - projected) / np.maximum(row_norms(group_rows), 1e-12)


def constant_first_step_metrics(responses: np.ndarray, true_final: np.ndarray) -> dict[str, float]:
    first = responses[0]
    per_step_residual = responses - first[None, :, :]
    per_step_relative = np.linalg.norm(per_step_residual.reshape(responses.shape[0], -1), axis=1) / np.maximum(
        np.linalg.norm(responses.reshape(responses.shape[0], -1), axis=1), 1e-12
    )
    predicted_final = first * responses.shape[0]
    final_residual = predicted_final - true_final
    return {
        "step_relative_error_mean": float(per_step_relative.mean()),
        "step_relative_error_max": float(per_step_relative.max()),
        "final_relative_l2_error": float(
            np.linalg.norm(final_residual.reshape(-1)) / max(np.linalg.norm(true_final.reshape(-1)), 1e-12)
        ),
        "final_max_node_error_m": float(np.linalg.norm(final_residual, axis=1).max()),
    }


def aggregate_results(results: list[dict[str, Any]], ranks: list[int]) -> dict[str, Any]:
    aggregate = {}
    for rank in ranks:
        subset = [item for item in results if int(item["rank"]) == int(rank)]
        if not subset:
            continue
        aggregate[str(rank)] = {
            "count": len(subset),
            "step_relative_error_mean": stats(item["step_relative_error_mean"] for item in subset),
            "step_relative_error_max": stats(item["step_relative_error_max"] for item in subset),
            "step_projection_cosine_mean": stats(item["step_projection_cosine_mean"] for item in subset),
            "final_accumulated_relative_l2_error": stats(item["final_accumulated_relative_l2_error"] for item in subset),
            "final_accumulated_max_node_error_m": stats(item["final_accumulated_max_node_error_m"] for item in subset),
            "basis_train_relative_error_mean": stats(item["basis_train_relative_error_mean"] for item in subset),
            "constant_first_step_final_relative_l2_error": stats(
                item["constant_first_step_final_relative_l2_error"] for item in subset
            ),
            "improvement_vs_constant_final_l2": stats(item["improvement_vs_constant_final_l2"] for item in subset),
        }
    return aggregate


def stats(values: Any) -> dict[str, float]:
    array = np.asarray(list(values), dtype=np.float64)
    return {
        "min": float(array.min()),
        "mean": float(array.mean()),
        "max": float(array.max()),
    }


def write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "trajectory_id",
        "matched_group_id",
        "contact_point_id",
        "material_id",
        "boundary_id",
        "direction_id",
        "rank",
        "step_relative_error_mean",
        "step_relative_error_max",
        "step_projection_cosine_mean",
        "final_accumulated_relative_l2_error",
        "final_accumulated_max_node_error_m",
        "basis_train_relative_error_mean",
        "basis_train_relative_error_max",
        "constant_first_step_final_relative_l2_error",
        "constant_first_step_final_max_node_error_m",
        "improvement_vs_constant_final_l2",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in results:
            writer.writerow({field: item.get(field) for field in fields})


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Rollout Basis Projection Analysis",
        "",
        f"Rollout dataset: `{payload['rollout_dataset']}`",
        "",
        f"Basis dataset: `{payload['basis_dataset']}`",
        "",
        f"Trajectories: {payload['trajectory_count']}",
        "",
        f"Basis groups: {payload['basis_group_count']}",
        "",
        "## Aggregate By Rank",
        "",
    ]
    for rank, stats_payload in payload["aggregate_by_rank"].items():
        lines.extend(
            [
                f"### Rank {rank}",
                "",
                f"- step relative error mean: {stats_payload['step_relative_error_mean']['mean']:.6f}",
                f"- final accumulated relative L2 error mean: {stats_payload['final_accumulated_relative_l2_error']['mean']:.6f}",
                f"- final accumulated relative L2 error max: {stats_payload['final_accumulated_relative_l2_error']['max']:.6f}",
                f"- constant-first-step final relative L2 mean: {stats_payload['constant_first_step_final_relative_l2_error']['mean']:.6f}",
                f"- improvement vs constant final L2 mean: {stats_payload['improvement_vs_constant_final_l2']['mean']:.6f}",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "This baseline keeps the Mode B response basis fixed for each matched contact/material/boundary condition and only projects each rollout step response into that fixed subspace. Low projection error means the response subspace is stable across rollout state changes. High projection error means the basis itself likely needs to be state-conditioned or the Mode B action family is incomplete.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Rollout basis projection analysis: {status}")
    print(
        f"trajectories={payload['trajectory_count']} basis_groups={payload['basis_group_count']} "
        f"results={payload['result_count']} errors={len(payload['errors'])}"
    )
    for rank, stats_payload in payload["aggregate_by_rank"].items():
        print(
            f"- rank {rank}: step_err_mean={stats_payload['step_relative_error_mean']['mean']:.6f} "
            f"final_err_mean={stats_payload['final_accumulated_relative_l2_error']['mean']:.6f} "
            f"final_err_max={stats_payload['final_accumulated_relative_l2_error']['max']:.6f} "
            f"constant_final_mean={stats_payload['constant_first_step_final_relative_l2_error']['mean']:.6f}"
        )
    for error in payload["errors"]:
        print(f"error={error}")


if __name__ == "__main__":
    raise SystemExit(main())
