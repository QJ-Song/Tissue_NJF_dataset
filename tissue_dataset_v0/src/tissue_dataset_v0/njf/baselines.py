from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .basis import (
    ResponseBasis,
    basis_key_from_metadata,
    coefficients_for_rows,
    load_basis_groups,
    project_rows,
    reconstruct_from_coefficients,
)
from .metrics import final_max_node_error_m, final_relative_l2, row_cosines, row_relative_l2, stats


@dataclass(frozen=True)
class CoefficientBaselineConfig:
    ranks: tuple[int, ...] = (2, 3, 4)
    trend_degree: int = 1
    trend_train_steps: int = 3


def evaluate_coefficient_baselines(
    *,
    basis_dataset: str | Path,
    rollout_dataset: str | Path,
    config: CoefficientBaselineConfig,
) -> dict[str, Any]:
    basis_groups = load_basis_groups(basis_dataset)
    trajectory_dirs = discover_trajectory_dirs(rollout_dataset)
    results: list[dict[str, Any]] = []
    step_rows: list[dict[str, Any]] = []
    coefficient_payload: dict[str, np.ndarray] = {}
    errors: list[str] = []

    for trajectory_dir in trajectory_dirs:
        try:
            trajectory_results, trajectory_steps, trajectory_coefficients = evaluate_trajectory(
                trajectory_dir,
                basis_groups=basis_groups,
                config=config,
            )
            results.extend(trajectory_results)
            step_rows.extend(trajectory_steps)
            coefficient_payload.update(trajectory_coefficients)
        except Exception as exc:
            errors.append(f"{trajectory_dir.name}: {exc}")

    return {
        "valid": not errors,
        "basis_dataset": str(basis_dataset),
        "rollout_dataset": str(rollout_dataset),
        "ranks": list(config.ranks),
        "trend_degree": int(config.trend_degree),
        "trend_train_steps": int(config.trend_train_steps),
        "trajectory_count": len(trajectory_dirs),
        "result_count": len(results),
        "errors": errors,
        "aggregate": aggregate_results(results),
        "results": results,
        "per_step": step_rows,
        "coefficient_arrays": coefficient_payload,
    }


def evaluate_trajectory(
    trajectory_dir: Path,
    *,
    basis_groups: dict[tuple[str, str, str], ResponseBasis],
    config: CoefficientBaselineConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, np.ndarray]]:
    metadata = load_json(trajectory_dir / "trajectory_metadata.json")
    states = np.load(trajectory_dir / "states.npy").astype(np.float64)
    responses = np.load(trajectory_dir / "responses.npy").astype(np.float64)
    actions = np.load(trajectory_dir / "actions.npy").astype(np.float64)
    if states.ndim != 3 or responses.ndim != 3 or responses.shape != states[1:].shape:
        raise ValueError("states/responses shape mismatch")

    key = basis_key_from_metadata(metadata)
    if key not in basis_groups:
        raise KeyError(f"no matched basis group for key={key}")
    basis = basis_groups[key]
    flat = responses.reshape(responses.shape[0], -1)
    node_count = int(responses.shape[1])
    if flat.shape[1] != basis.flat_responses.shape[1]:
        raise ValueError("basis response dimension does not match rollout response dimension")

    trajectory_id = trajectory_dir.name
    base_fields = {
        "trajectory_id": trajectory_id,
        "trajectory_dir": str(trajectory_dir),
        "matched_group_id": basis.group_id,
        "matched_group_dir": str(basis.group_dir),
        "contact_point_id": key[0],
        "material_id": key[1],
        "boundary_id": key[2],
        "direction_id": metadata.get("direction_id"),
        "step_count": int(responses.shape[0]),
        "node_count": node_count,
        "action_magnitude_m": float(actions[0, 5]) if actions.ndim == 2 and actions.shape[1] >= 6 else None,
    }

    results: list[dict[str, Any]] = []
    step_rows: list[dict[str, Any]] = []
    coefficient_arrays: dict[str, np.ndarray] = {}

    b0_pred = np.repeat(flat[0:1], flat.shape[0], axis=0)
    result, rows = summarize_prediction(
        baseline_id="B0_repeat_first_response",
        rank=0,
        predicted_flat=b0_pred,
        target_flat=flat,
        node_count=node_count,
        base_fields=base_fields,
        interpretation="Fixed-response diagnostic: repeats the first observed step response for the full rollout.",
    )
    results.append(result)
    step_rows.extend(rows)

    for rank in config.ranks:
        clipped_rank = max(1, min(int(rank), basis.max_rank))
        basis_rows = basis.clipped_basis(clipped_rank)
        true_coefficients = coefficients_for_rows(flat, basis_rows)
        oracle_flat = project_rows(flat, basis_rows)
        fixed_coefficients = np.repeat(true_coefficients[0:1], true_coefficients.shape[0], axis=0)
        fixed_flat = reconstruct_from_coefficients(fixed_coefficients, basis_rows)
        trend_coefficients = fit_predict_coefficient_trend(
            true_coefficients,
            actions=actions,
            train_steps=config.trend_train_steps,
            degree=config.trend_degree,
        )
        trend_flat = reconstruct_from_coefficients(trend_coefficients, basis_rows)

        coefficient_arrays[f"rank{clipped_rank}_{trajectory_id}_true_coefficients"] = true_coefficients
        coefficient_arrays[f"rank{clipped_rank}_{trajectory_id}_fixed_first_coefficients"] = fixed_coefficients
        coefficient_arrays[f"rank{clipped_rank}_{trajectory_id}_trend_coefficients"] = trend_coefficients

        for baseline_id, predicted_flat, coeff_pred, interpretation in (
            (
                "B1_oracle_basis_projection",
                oracle_flat,
                true_coefficients,
                "Expression upper bound: projects each true rollout response into the matched Mode B basis.",
            ),
            (
                "B2_fixed_first_coefficient",
                fixed_flat,
                fixed_coefficients,
                "Tests whether fixed basis coefficients from step 0 remain valid through rollout.",
            ),
            (
                "B3_prefix_depth_trend_coefficient",
                trend_flat,
                trend_coefficients,
                "Diagnostic trend model: fits coefficients from early rollout steps as a polynomial of cumulative depth.",
            ),
        ):
            result, rows = summarize_prediction(
                baseline_id=baseline_id,
                rank=clipped_rank,
                predicted_flat=predicted_flat,
                target_flat=flat,
                node_count=node_count,
                base_fields=base_fields,
                interpretation=interpretation,
                true_coefficients=true_coefficients,
                predicted_coefficients=coeff_pred,
                trend_train_steps=config.trend_train_steps if baseline_id.startswith("B3") else None,
                trend_degree=config.trend_degree if baseline_id.startswith("B3") else None,
            )
            results.append(result)
            step_rows.extend(rows)

    return results, step_rows, coefficient_arrays


def summarize_prediction(
    *,
    baseline_id: str,
    rank: int,
    predicted_flat: np.ndarray,
    target_flat: np.ndarray,
    node_count: int,
    base_fields: dict[str, Any],
    interpretation: str,
    true_coefficients: np.ndarray | None = None,
    predicted_coefficients: np.ndarray | None = None,
    trend_train_steps: int | None = None,
    trend_degree: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    step_rel = row_relative_l2(predicted_flat, target_flat)
    step_cos = row_cosines(predicted_flat, target_flat)
    coeff_rel = None
    if true_coefficients is not None and predicted_coefficients is not None:
        coeff_rel = row_relative_l2(predicted_coefficients, true_coefficients)

    result = {
        **base_fields,
        "baseline_id": baseline_id,
        "rank": int(rank),
        "step_relative_l2_mean": float(step_rel.mean()),
        "step_relative_l2_max": float(step_rel.max()),
        "step_cosine_mean": float(step_cos.mean()),
        "final_relative_l2": final_relative_l2(predicted_flat, target_flat),
        "final_max_node_error_m": final_max_node_error_m(predicted_flat, target_flat, node_count=node_count),
        "coefficient_relative_l2_mean": None if coeff_rel is None else float(coeff_rel.mean()),
        "coefficient_relative_l2_max": None if coeff_rel is None else float(coeff_rel.max()),
        "trend_train_steps": trend_train_steps,
        "trend_degree": trend_degree,
        "interpretation": interpretation,
    }
    rows = []
    for step_id in range(target_flat.shape[0]):
        rows.append(
            {
                **{key: base_fields[key] for key in ("trajectory_id", "matched_group_id", "contact_point_id", "material_id", "boundary_id", "direction_id")},
                "baseline_id": baseline_id,
                "rank": int(rank),
                "step_id": int(step_id),
                "step_relative_l2": float(step_rel[step_id]),
                "step_cosine": float(step_cos[step_id]),
                "coefficient_relative_l2": None if coeff_rel is None else float(coeff_rel[step_id]),
            }
        )
    return result, rows


def fit_predict_coefficient_trend(
    coefficients: np.ndarray,
    *,
    actions: np.ndarray,
    train_steps: int,
    degree: int,
) -> np.ndarray:
    coefficients = np.asarray(coefficients, dtype=np.float64)
    step_count = coefficients.shape[0]
    if step_count == 0:
        return coefficients.copy()
    train_steps = max(1, min(int(train_steps), step_count))
    degree = max(0, min(int(degree), train_steps - 1))
    x = cumulative_depth_axis(actions, step_count)
    x_train = x[:train_steps]
    x_scale = max(float(np.max(np.abs(x_train))), 1e-12)
    design = polynomial_design(x / x_scale, degree)
    design_train = design[:train_steps]
    weights, *_ = np.linalg.lstsq(design_train, coefficients[:train_steps], rcond=None)
    return design @ weights


def cumulative_depth_axis(actions: np.ndarray, step_count: int) -> np.ndarray:
    if actions.ndim == 2 and actions.shape[0] >= step_count and actions.shape[1] >= 6:
        return np.cumsum(actions[:step_count, 5].astype(np.float64))
    return np.arange(1, step_count + 1, dtype=np.float64)


def polynomial_design(x: np.ndarray, degree: int) -> np.ndarray:
    columns = [np.ones_like(x)]
    for power in range(1, degree + 1):
        columns.append(x**power)
    return np.stack(columns, axis=1)


def discover_trajectory_dirs(dataset_root: str | Path) -> list[Path]:
    root = Path(dataset_root)
    if root.is_dir() and root.name.startswith("traj_"):
        return [root]
    trajectories_root = root / "trajectories"
    if trajectories_root.is_dir():
        return sorted(path for path in trajectories_root.iterdir() if path.is_dir() and path.name.startswith("traj_"))
    if root.is_dir() and root.name == "trajectories":
        return sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith("traj_"))
    return []


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {}
    keys = sorted({(str(item["baseline_id"]), int(item["rank"])) for item in results})
    for baseline_id, rank in keys:
        subset = [item for item in results if str(item["baseline_id"]) == baseline_id and int(item["rank"]) == rank]
        aggregate[f"{baseline_id}|rank{rank}"] = {
            "baseline_id": baseline_id,
            "rank": rank,
            "count": len(subset),
            "step_relative_l2_mean": stats(item["step_relative_l2_mean"] for item in subset),
            "step_relative_l2_max": stats(item["step_relative_l2_max"] for item in subset),
            "step_cosine_mean": stats(item["step_cosine_mean"] for item in subset),
            "final_relative_l2": stats(item["final_relative_l2"] for item in subset),
            "final_max_node_error_m": stats(item["final_max_node_error_m"] for item in subset),
            "coefficient_relative_l2_mean": stats(
                item["coefficient_relative_l2_mean"]
                for item in subset
                if item.get("coefficient_relative_l2_mean") is not None
            ),
        }
    return aggregate


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items() if key != "coefficient_arrays"}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value
