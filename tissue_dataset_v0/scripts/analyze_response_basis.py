#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze SOFA NJF response-basis groups with SVD/PCA metrics.")
    parser.add_argument("dataset_or_group", type=Path, help="Dataset root, groups/ directory, or one group_* directory.")
    parser.add_argument("--rank", type=int, default=None, help="Rank for reconstruction error; default uses effective ceil rank.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    group_dirs = discover_group_dirs(args.dataset_or_group)
    if not group_dirs:
        print(f"No group_* directories found under {args.dataset_or_group}", file=sys.stderr)
        return 2
    groups = [analyze_group(path, rank=args.rank) for path in group_dirs]
    payload = {"valid": True, "group_count": len(groups), "summary": summarize_groups(groups), "groups": groups}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0


def discover_group_dirs(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_dir() and path.name.startswith("group_"):
        return [path]
    groups_dir = path / "groups"
    if groups_dir.is_dir():
        return sorted(item for item in groups_dir.iterdir() if item.is_dir() and item.name.startswith("group_"))
    if path.is_dir() and path.name == "groups":
        return sorted(item for item in path.iterdir() if item.is_dir() and item.name.startswith("group_"))
    return []


def analyze_group(group_dir: Path, *, rank: int | None) -> dict[str, Any]:
    metadata = load_json(group_dir / "group_metadata.json")
    actions = np.load(group_dir / "actions.npy")
    responses = np.load(group_dir / "responses.npy")
    if responses.ndim != 3:
        raise ValueError(f"responses.npy must have shape [K, N, 3]: {group_dir}")
    matrix = responses.reshape(responses.shape[0], -1).astype(np.float64)
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    _, singular_values, vh = np.linalg.svd(centered, full_matrices=False)
    energy = singular_values**2
    total_energy = float(energy.sum())
    explained = energy / total_energy if total_energy > 0.0 else np.zeros_like(energy)
    cumulative = np.cumsum(explained)
    effective_rank = entropy_effective_rank(explained)
    chosen_rank = rank if rank is not None else max(1, min(int(np.ceil(effective_rank)), max(len(singular_values) - 1, 1)))
    chosen_rank = max(1, min(chosen_rank, max(len(singular_values) - 1, 1)))
    loo = leave_one_out_error(matrix, chosen_rank)
    action_magnitudes = actions[:, 5] if actions.ndim == 2 and actions.shape[1] >= 6 else np.asarray([])
    unique_dirs = np.unique(np.round(actions[:, 2:5], decimals=4), axis=0) if actions.ndim == 2 and actions.shape[1] >= 5 else np.empty((0, 3))
    response_norms = np.linalg.norm(matrix, axis=1)
    return {
        "group_id": group_dir.name,
        "path": str(group_dir),
        "action_count": int(matrix.shape[0]),
        "vertex_count": int(responses.shape[1]),
        "action_dim": int(actions.shape[1]) if actions.ndim == 2 else None,
        "unique_action_directions": int(unique_dirs.shape[0]),
        "action_magnitude_min_m": float(action_magnitudes.min()) if action_magnitudes.size else None,
        "action_magnitude_max_m": float(action_magnitudes.max()) if action_magnitudes.size else None,
        "response_norm_min_m": float(response_norms.min()) if response_norms.size else 0.0,
        "response_norm_max_m": float(response_norms.max()) if response_norms.size else 0.0,
        "singular_values": singular_values.tolist(),
        "explained_variance_ratio": explained.tolist(),
        "cumulative_explained_variance": cumulative.tolist(),
        "effective_rank": float(effective_rank),
        "rank_for_reconstruction": int(chosen_rank),
        "leave_one_out_relative_error_mean": float(loo["mean_relative_error"]),
        "leave_one_out_relative_error_max": float(loo["max_relative_error"]),
        "leave_one_out_relative_errors": loo["relative_errors"],
        "smoke_sized_group": bool(metadata.get("smoke_sized_group", matrix.shape[0] < 12)),
        "fixed_variables": metadata.get("fixed_variables", []),
        "varied_variables": metadata.get("varied_variables", []),
    }


def summarize_groups(groups: list[dict[str, Any]]) -> dict[str, Any]:
    if not groups:
        return {}
    effective_ranks = np.asarray([float(group["effective_rank"]) for group in groups], dtype=np.float64)
    loo_mean = np.asarray([float(group["leave_one_out_relative_error_mean"]) for group in groups], dtype=np.float64)
    loo_max = np.asarray([float(group["leave_one_out_relative_error_max"]) for group in groups], dtype=np.float64)
    top1 = np.asarray([_cumulative_at(group, 0) for group in groups], dtype=np.float64)
    top2 = np.asarray([_cumulative_at(group, 1) for group in groups], dtype=np.float64)
    top3 = np.asarray([_cumulative_at(group, 2) for group in groups], dtype=np.float64)
    return {
        "effective_rank": stat_summary(effective_ranks),
        "loo_mean_relative_error": stat_summary(loo_mean),
        "loo_max_relative_error": stat_summary(loo_max),
        "top1_cumulative_explained": stat_summary(top1),
        "top2_cumulative_explained": stat_summary(top2),
        "top3_cumulative_explained": stat_summary(top3),
        "smoke_sized_group_count": int(sum(bool(group.get("smoke_sized_group", False)) for group in groups)),
        "groups_with_k_ge_12": int(sum(int(group.get("action_count", 0)) >= 12 for group in groups)),
    }


def _cumulative_at(group: dict[str, Any], index: int) -> float:
    values = group.get("cumulative_explained_variance", [])
    if not values:
        return 0.0
    return float(values[min(index, len(values) - 1)])


def stat_summary(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
    }


def entropy_effective_rank(explained: np.ndarray) -> float:
    probs = explained[np.asarray(explained) > 0.0]
    if probs.size == 0:
        return 0.0
    entropy = -float(np.sum(probs * np.log(probs)))
    return float(np.exp(entropy))


def leave_one_out_error(matrix: np.ndarray, rank: int) -> dict[str, Any]:
    errors: list[float] = []
    for holdout in range(matrix.shape[0]):
        train = np.delete(matrix, holdout, axis=0)
        mean = train.mean(axis=0, keepdims=True)
        centered_train = train - mean
        if centered_train.shape[0] <= 1 or np.linalg.norm(matrix[holdout]) <= 0.0:
            errors.append(0.0)
            continue
        _, _, vh = np.linalg.svd(centered_train, full_matrices=False)
        basis = vh[: max(1, min(rank, vh.shape[0]))]
        target = matrix[holdout : holdout + 1] - mean
        reconstruction = mean + (target @ basis.T) @ basis
        numerator = float(np.linalg.norm(matrix[holdout : holdout + 1] - reconstruction))
        denominator = float(np.linalg.norm(matrix[holdout : holdout + 1]))
        errors.append(numerator / max(denominator, 1e-12))
    return {
        "relative_errors": errors,
        "mean_relative_error": float(np.mean(errors)) if errors else 0.0,
        "max_relative_error": float(np.max(errors)) if errors else 0.0,
    }


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
    print("Response basis analysis: PASS")
    print(f"groups={payload['group_count']}")
    summary = payload.get("summary") or {}
    if summary:
        rank = summary["effective_rank"]
        loo = summary["loo_mean_relative_error"]
        top2 = summary["top2_cumulative_explained"]
        print(
            "summary="
            f"eff_rank_mean={rank['mean']:.3f} eff_rank_range=[{rank['min']:.3f}, {rank['max']:.3f}] "
            f"loo_mean={loo['mean']:.6f} top2_mean={top2['mean']:.6f}"
        )
    for group in payload["groups"]:
        print(
            f"- {group['group_id']}: K={group['action_count']} "
            f"dirs={group['unique_action_directions']} "
            f"eff_rank={group['effective_rank']:.3f} "
            f"loo_mean={group['leave_one_out_relative_error_mean']:.6f} "
            f"loo_max={group['leave_one_out_relative_error_max']:.6f}"
        )
        top = group["cumulative_explained_variance"][: min(5, len(group["cumulative_explained_variance"]))]
        print(f"  cumulative_explained_top={top}")
        if group["smoke_sized_group"]:
            print("  warning=smoke-sized group; use K>=12 for meaningful basis analysis")


if __name__ == "__main__":
    raise SystemExit(main())
