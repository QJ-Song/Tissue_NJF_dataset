from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .basis import ResponseBasis, basis_key_from_metadata, coefficients_for_rows, load_basis_groups, reconstruct_from_coefficients
from .features import LocalPatchSpec, build_local_patch_spec, local_state_features
from .metrics import final_max_node_error_m, final_relative_l2, row_cosines, row_relative_l2, stats


@dataclass(frozen=True)
class FittedCoefficientConfig:
    ranks: tuple[int, ...] = (2, 3, 4)
    ridge_alpha: float = 1e-4
    prefix_train_steps: int = 5
    predictors: tuple[str, ...] = ("R1_non_autoregressive", "R2_autoregressive", "R3_state_local_ridge")
    local_patch_size: int = 64


@dataclass(frozen=True)
class TrajectoryData:
    trajectory_id: str
    trajectory_dir: Path
    dataset_root: Path
    metadata: dict[str, Any]
    states: np.ndarray
    responses: np.ndarray
    actions: np.ndarray
    contact_distances: np.ndarray | None
    contact_status: np.ndarray | None
    key: tuple[str, str, str]
    basis: ResponseBasis
    contact_points: np.ndarray
    local_patch: LocalPatchSpec

    @property
    def direction_id(self) -> str:
        return str(self.metadata.get("direction_id"))

    @property
    def group_id(self) -> str:
        return self.basis.group_id

    @property
    def step_count(self) -> int:
        return int(self.responses.shape[0])

    @property
    def node_count(self) -> int:
        return int(self.responses.shape[1])

    @property
    def flat_responses(self) -> np.ndarray:
        return self.responses.reshape(self.responses.shape[0], -1)


def evaluate_fitted_coefficient_predictor(
    *,
    basis_dataset: str | Path,
    rollout_datasets: list[str | Path],
    config: FittedCoefficientConfig,
) -> dict[str, Any]:
    basis_groups = load_basis_groups(basis_dataset)
    trajectories = load_trajectories(rollout_datasets, basis_groups, patch_size=config.local_patch_size)
    results: list[dict[str, Any]] = []
    per_step: list[dict[str, Any]] = []
    errors: list[str] = []

    for rank in config.ranks:
        rank = int(rank)
        try:
            prefix_results, prefix_steps = evaluate_prefix_split(trajectories, rank=rank, config=config)
            results.extend(prefix_results)
            per_step.extend(prefix_steps)
        except Exception as exc:
            errors.append(f"prefix_split rank={rank}: {exc}")
        try:
            heldout_results, heldout_steps = evaluate_heldout_direction_split(trajectories, rank=rank, config=config)
            results.extend(heldout_results)
            per_step.extend(heldout_steps)
        except Exception as exc:
            errors.append(f"heldout_direction rank={rank}: {exc}")

    return {
        "valid": not errors,
        "basis_dataset": str(basis_dataset),
        "rollout_datasets": [str(path) for path in rollout_datasets],
        "ranks": list(config.ranks),
        "ridge_alpha": float(config.ridge_alpha),
        "prefix_train_steps": int(config.prefix_train_steps),
        "local_patch_size": int(config.local_patch_size),
        "predictors": list(config.predictors),
        "trajectory_count": len(trajectories),
        "direction_ids": sorted({traj.direction_id for traj in trajectories}),
        "group_count": len({traj.group_id for traj in trajectories}),
        "result_count": len(results),
        "errors": errors,
        "aggregate": aggregate_results(results),
        "results": results,
        "per_step": per_step,
    }


def load_trajectories(
    rollout_datasets: list[str | Path],
    basis_groups: dict[tuple[str, str, str], ResponseBasis],
    *,
    patch_size: int,
) -> list[TrajectoryData]:
    trajectories: list[TrajectoryData] = []
    for dataset_root in rollout_datasets:
        root = Path(dataset_root)
        for trajectory_dir in discover_trajectory_dirs(root):
            metadata = load_json(trajectory_dir / "trajectory_metadata.json")
            key = basis_key_from_metadata(metadata)
            if key not in basis_groups:
                raise KeyError(f"{trajectory_dir}: no matched basis group for key={key}")
            states = np.load(trajectory_dir / "states.npy").astype(np.float64)
            responses = np.load(trajectory_dir / "responses.npy").astype(np.float64)
            actions = np.load(trajectory_dir / "actions.npy").astype(np.float64)
            contact_points = np.load(trajectory_dir / "contact_points.npy").astype(np.float64) if (trajectory_dir / "contact_points.npy").exists() else np.tile(np.asarray(metadata.get("contact_point_world", [0.0, 0.0, 0.0]), dtype=np.float64), (responses.shape[0], 1))
            contact_distances = np.load(trajectory_dir / "contact_distances.npy").astype(np.float64) if (trajectory_dir / "contact_distances.npy").exists() else None
            contact_status = np.load(trajectory_dir / "contact_status.npy").astype(bool) if (trajectory_dir / "contact_status.npy").exists() else None
            if responses.shape != states[1:].shape:
                raise ValueError(f"{trajectory_dir}: responses shape does not match states[1:]")
            contact_for_patch = contact_points[0] if contact_points.ndim == 2 and contact_points.shape[0] else np.asarray(metadata.get("contact_point_world", [0.0, 0.0, 0.0]), dtype=np.float64)
            local_patch = build_local_patch_spec(states[0], contact_for_patch, patch_size=patch_size)
            trajectories.append(
                TrajectoryData(
                    trajectory_id=trajectory_dir.name,
                    trajectory_dir=trajectory_dir,
                    dataset_root=root,
                    metadata=metadata,
                    states=states,
                    responses=responses,
                    actions=actions,
                    contact_distances=contact_distances,
                    contact_status=contact_status,
                    key=key,
                    basis=basis_groups[key],
                    contact_points=contact_points,
                    local_patch=local_patch,
                )
            )
    return trajectories


def evaluate_prefix_split(
    trajectories: list[TrajectoryData], *, rank: int, config: FittedCoefficientConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    per_step: list[dict[str, Any]] = []
    for traj in trajectories:
        train_steps = max(1, min(int(config.prefix_train_steps), traj.step_count - 1))
        train_idx = np.arange(0, train_steps, dtype=int)
        test_idx = np.arange(train_steps, traj.step_count, dtype=int)
        if test_idx.size == 0:
            continue
        for predictor_id in config.predictors:
            result, rows = fit_predict_for_indices(
                [traj],
                [traj],
                train_indices_by_traj={traj.trajectory_dir: train_idx},
                test_indices_by_traj={traj.trajectory_dir: test_idx},
                rank=rank,
                predictor_id=predictor_id,
                split_id="prefix_per_trajectory",
                config=config,
                heldout_direction=traj.direction_id,
            )
            results.extend(result)
            per_step.extend(rows)
    return results, per_step


def evaluate_heldout_direction_split(
    trajectories: list[TrajectoryData], *, rank: int, config: FittedCoefficientConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    per_step: list[dict[str, Any]] = []
    by_group: dict[tuple[str, str, str], list[TrajectoryData]] = {}
    for traj in trajectories:
        by_group.setdefault(traj.key, []).append(traj)
    for group_key, group_trajs in sorted(by_group.items(), key=lambda item: item[0]):
        directions = sorted({traj.direction_id for traj in group_trajs})
        if len(directions) < 2:
            continue
        for heldout in directions:
            train_trajs = [traj for traj in group_trajs if traj.direction_id != heldout]
            test_trajs = [traj for traj in group_trajs if traj.direction_id == heldout]
            if not train_trajs or not test_trajs:
                continue
            train_indices = {traj.trajectory_dir: np.arange(traj.step_count, dtype=int) for traj in train_trajs}
            test_indices = {traj.trajectory_dir: np.arange(traj.step_count, dtype=int) for traj in test_trajs}
            for predictor_id in config.predictors:
                result, rows = fit_predict_for_indices(
                    train_trajs,
                    test_trajs,
                    train_indices_by_traj=train_indices,
                    test_indices_by_traj=test_indices,
                    rank=rank,
                    predictor_id=predictor_id,
                    split_id="heldout_direction_within_group",
                    config=config,
                    heldout_direction=heldout,
                )
                results.extend(result)
                per_step.extend(rows)
    return results, per_step


def fit_predict_for_indices(
    train_trajs: list[TrajectoryData],
    test_trajs: list[TrajectoryData],
    *,
    train_indices_by_traj: dict[Path, np.ndarray],
    test_indices_by_traj: dict[Path, np.ndarray],
    rank: int,
    predictor_id: str,
    split_id: str,
    config: FittedCoefficientConfig,
    heldout_direction: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_features: list[np.ndarray] = []
    train_targets: list[np.ndarray] = []
    for traj in train_trajs:
        basis_rows = traj.basis.clipped_basis(rank)
        coeff = coefficients_for_rows(traj.flat_responses, basis_rows)
        idx = train_indices_by_traj[traj.trajectory_dir]
        for step in idx:
            train_features.append(build_features(traj, int(step), coeff, predictor_id=predictor_id, previous_override=None, config=config))
            train_targets.append(coeff[int(step)])
    if not train_features:
        return [], []
    x_train = np.stack(train_features, axis=0)
    y_train = np.stack(train_targets, axis=0)
    model = fit_ridge(x_train, y_train, alpha=config.ridge_alpha)

    results: list[dict[str, Any]] = []
    per_step: list[dict[str, Any]] = []
    for traj in test_trajs:
        basis_rows = traj.basis.clipped_basis(rank)
        true_coeff = coefficients_for_rows(traj.flat_responses, basis_rows)
        test_idx = test_indices_by_traj[traj.trajectory_dir]
        pred_coeff_by_step: dict[int, np.ndarray] = {}
        pred_flat: list[np.ndarray] = []
        target_flat: list[np.ndarray] = []
        step_rows: list[dict[str, Any]] = []
        for step in test_idx:
            step = int(step)
            prev_override = None
            if predictor_id == "R2_autoregressive":
                if step == 0:
                    prev_override = np.zeros(rank, dtype=np.float64)
                elif (step - 1) in pred_coeff_by_step:
                    prev_override = pred_coeff_by_step[step - 1]
                else:
                    prev_override = true_coeff[step - 1]
            feature = build_features(traj, step, true_coeff, predictor_id=predictor_id, previous_override=prev_override, config=config)
            predicted_coeff = predict_ridge(model, feature[None, :])[0]
            pred_coeff_by_step[step] = predicted_coeff
            predicted_flat = reconstruct_from_coefficients(predicted_coeff[None, :], basis_rows)[0]
            target = traj.flat_responses[step]
            pred_flat.append(predicted_flat)
            target_flat.append(target)
            coeff_rel = float(np.linalg.norm(predicted_coeff - true_coeff[step]) / max(np.linalg.norm(true_coeff[step]), 1e-12))
            step_rel = float(np.linalg.norm(predicted_flat - target) / max(np.linalg.norm(target), 1e-12))
            step_cos = float(np.dot(predicted_flat, target) / max(np.linalg.norm(predicted_flat) * np.linalg.norm(target), 1e-12))
            step_rows.append(
                {
                    "split_id": split_id,
                    "predictor_id": predictor_id,
                    "rank": int(rank),
                    "trajectory_id": traj.trajectory_id,
                    "trajectory_dir": str(traj.trajectory_dir),
                    "matched_group_id": traj.group_id,
                    "contact_point_id": traj.key[0],
                    "material_id": traj.key[1],
                    "boundary_id": traj.key[2],
                    "direction_id": traj.direction_id,
                    "heldout_direction": heldout_direction,
                    "step_id": step,
                    "step_relative_l2": step_rel,
                    "step_cosine": step_cos,
                    "coefficient_relative_l2": coeff_rel,
                }
            )
        if not pred_flat:
            continue
        pred_array = np.stack(pred_flat, axis=0)
        target_array = np.stack(target_flat, axis=0)
        step_rel_values = np.asarray([row["step_relative_l2"] for row in step_rows], dtype=np.float64)
        step_cos_values = np.asarray([row["step_cosine"] for row in step_rows], dtype=np.float64)
        coeff_rel_values = np.asarray([row["coefficient_relative_l2"] for row in step_rows], dtype=np.float64)
        results.append(
            {
                "split_id": split_id,
                "predictor_id": predictor_id,
                "rank": int(rank),
                "trajectory_id": traj.trajectory_id,
                "trajectory_dir": str(traj.trajectory_dir),
                "matched_group_id": traj.group_id,
                "contact_point_id": traj.key[0],
                "material_id": traj.key[1],
                "boundary_id": traj.key[2],
                "direction_id": traj.direction_id,
                "heldout_direction": heldout_direction,
                "train_sample_count": int(x_train.shape[0]),
                "test_step_count": int(len(step_rows)),
                "ridge_alpha": float(config.ridge_alpha),
                "step_relative_l2_mean": float(step_rel_values.mean()),
                "step_relative_l2_max": float(step_rel_values.max()),
                "step_cosine_mean": float(step_cos_values.mean()),
                "coefficient_relative_l2_mean": float(coeff_rel_values.mean()),
                "coefficient_relative_l2_max": float(coeff_rel_values.max()),
                "final_relative_l2": final_relative_l2(pred_array, target_array),
                "final_max_node_error_m": final_max_node_error_m(pred_array, target_array, node_count=traj.node_count),
                "interpretation": predictor_interpretation(predictor_id, split_id),
            }
        )
        per_step.extend(step_rows)
    return results, per_step


def build_features(
    traj: TrajectoryData,
    step: int,
    coefficients: np.ndarray,
    *,
    predictor_id: str,
    previous_override: np.ndarray | None,
    config: FittedCoefficientConfig,
) -> np.ndarray:
    action = traj.actions[step]
    metadata = traj.metadata
    material = metadata.get("material", {}) if isinstance(metadata.get("material"), dict) else {}
    step_count = max(traj.step_count, 1)
    cumulative_depth = float(np.sum(traj.actions[: step + 1, 5])) if traj.actions.ndim == 2 and traj.actions.shape[1] >= 6 else float(step + 1)
    total_depth = float(np.sum(traj.actions[:, 5])) if traj.actions.ndim == 2 and traj.actions.shape[1] >= 6 else float(step_count)
    contact_distance = 0.0 if traj.contact_distances is None else float(traj.contact_distances[step])
    contact_status = 1.0 if traj.contact_status is None else float(bool(traj.contact_status[step]))
    young = float(material.get("youngs_modulus", 0.0))
    poisson = float(material.get("poisson_ratio", 0.0))
    base = [
        float(step),
        float(step) / max(step_count - 1, 1),
        cumulative_depth,
        cumulative_depth / max(total_depth, 1e-12),
        float(action[2]),
        float(action[3]),
        float(action[4]),
        float(action[5]) if action.shape[0] >= 6 else 0.0,
        np.log10(max(young, 1e-12)),
        poisson,
        contact_distance,
        contact_status,
    ]
    if predictor_id == "R3_state_local_ridge":
        contact_point = traj.contact_points[step] if traj.contact_points.ndim == 2 and traj.contact_points.shape[0] > step else np.asarray(traj.metadata.get("contact_point_world", [0.0, 0.0, 0.0]), dtype=np.float64)
        base.extend(local_state_features(traj.states, step=step, contact_point=contact_point, patch=traj.local_patch).tolist())
    if predictor_id == "R2_autoregressive":
        if previous_override is not None:
            prev = np.asarray(previous_override, dtype=np.float64)
        elif step == 0:
            prev = np.zeros(coefficients.shape[1], dtype=np.float64)
        else:
            prev = coefficients[step - 1]
        base.extend(prev.tolist())
        base.append(float(np.linalg.norm(prev)))
    return np.asarray(base, dtype=np.float64)


@dataclass(frozen=True)
class RidgeModel:
    weights: np.ndarray
    feature_mean: np.ndarray
    feature_scale: np.ndarray


def fit_ridge(x: np.ndarray, y: np.ndarray, *, alpha: float) -> RidgeModel:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale = np.where(scale < 1e-12, 1.0, scale)
    z = (x - mean) / scale
    design = np.concatenate([np.ones((z.shape[0], 1), dtype=np.float64), z], axis=1)
    reg = np.eye(design.shape[1], dtype=np.float64) * float(alpha)
    reg[0, 0] = 0.0
    weights = np.linalg.solve(design.T @ design + reg, design.T @ y)
    return RidgeModel(weights=weights, feature_mean=mean, feature_scale=scale)


def predict_ridge(model: RidgeModel, x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    z = (x - model.feature_mean) / model.feature_scale
    design = np.concatenate([np.ones((z.shape[0], 1), dtype=np.float64), z], axis=1)
    return design @ model.weights


def predictor_interpretation(predictor_id: str, split_id: str) -> str:
    if predictor_id == "R1_non_autoregressive":
        base = "Estimates coefficients from step/depth/action/material/contact-distance features only."
    elif predictor_id == "R2_autoregressive":
        base = "Adds previous coefficient features; test rollout uses recursive estimated coefficients after the first test step."
    elif predictor_id == "R3_state_local_ridge":
        base = "Adds local patch state features from X_t around the contact point to scalar depth/action/material/contact features."
    else:
        base = "Unknown diagnostic variant."
    if split_id == "prefix_per_trajectory":
        return base + " Prefix split diagnoses within-trajectory extrapolation, not cross-trajectory generalization."
    return base + " Held-out direction split trains within the same contact/material basis group and tests action-direction generalization."


def discover_trajectory_dirs(dataset_root: Path) -> list[Path]:
    if dataset_root.is_dir() and dataset_root.name.startswith("traj_"):
        return [dataset_root]
    trajectories_root = dataset_root / "trajectories"
    if trajectories_root.is_dir():
        return sorted(path for path in trajectories_root.iterdir() if path.is_dir() and path.name.startswith("traj_"))
    if dataset_root.is_dir() and dataset_root.name == "trajectories":
        return sorted(path for path in dataset_root.iterdir() if path.is_dir() and path.name.startswith("traj_"))
    return []


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {}
    keys = sorted({(str(item["split_id"]), str(item["predictor_id"]), int(item["rank"])) for item in results})
    for split_id, predictor_id, rank in keys:
        subset = [
            item
            for item in results
            if str(item["split_id"]) == split_id and str(item["predictor_id"]) == predictor_id and int(item["rank"]) == rank
        ]
        aggregate[f"{split_id}|{predictor_id}|rank{rank}"] = {
            "split_id": split_id,
            "predictor_id": predictor_id,
            "rank": rank,
            "count": len(subset),
            "step_relative_l2_mean": stats(item["step_relative_l2_mean"] for item in subset),
            "step_relative_l2_max": stats(item["step_relative_l2_max"] for item in subset),
            "step_cosine_mean": stats(item["step_cosine_mean"] for item in subset),
            "coefficient_relative_l2_mean": stats(item["coefficient_relative_l2_mean"] for item in subset),
            "final_relative_l2": stats(item["final_relative_l2"] for item in subset),
            "final_max_node_error_m": stats(item["final_max_node_error_m"] for item in subset),
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
        return {str(key): jsonable(item) for key, item in value.items()}
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
