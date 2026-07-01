#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze SOFA NJF multi-step rollout trajectories.")
    parser.add_argument("dataset_or_trajectory", type=Path, help="Dataset root, trajectories/ directory, or one traj_* directory.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--min-steps", type=int, default=10, help="Minimum useful rollout length; default 10.")
    parser.add_argument("--max-tool-step-error-mm", type=float, default=0.01, help="Warn when tool step length error exceeds this many mm.")
    parser.add_argument("--max-tool-angle-error-deg", type=float, default=0.1, help="Warn when tool motion/action direction angle exceeds this many degrees.")
    parser.add_argument("--max-fixed-motion-mm", type=float, default=0.001, help="Warn when fixed-node motion exceeds this many mm.")
    parser.add_argument("--single-step-sample", type=Path, default=None, help="Optional matched sample_* directory or dataset root containing one sample for large-step comparison.")
    parser.add_argument("--csv-dir", type=Path, default=None, help="Optional directory for per-step CSV outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    traj_dirs = discover_trajectory_dirs(args.dataset_or_trajectory)
    if not traj_dirs:
        print(f"No traj_* directories found under {args.dataset_or_trajectory}", file=sys.stderr)
        return 2
    single_step_reference = args.single_step_sample
    trajectories = [
        analyze_trajectory(
            path,
            min_steps=args.min_steps,
            max_tool_step_error_m=args.max_tool_step_error_mm * 1e-3,
            max_tool_angle_error_deg=args.max_tool_angle_error_deg,
            max_fixed_motion_m=args.max_fixed_motion_mm * 1e-3,
            single_step_sample=single_step_reference,
        )
        for path in traj_dirs
    ]
    errors = [item for traj in trajectories for item in traj["errors"]]
    warnings = [item for traj in trajectories for item in traj["warnings"]]
    payload = {
        "valid": not errors,
        "trajectory_count": len(trajectories),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "trajectories": trajectories,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.csv_dir is not None:
        write_csv_outputs(args.csv_dir, trajectories)
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if not errors else 1


def discover_trajectory_dirs(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_dir() and path.name.startswith("traj_"):
        return [path]
    trajectories_dir = path / "trajectories"
    if trajectories_dir.is_dir():
        return sorted(item for item in trajectories_dir.iterdir() if item.is_dir() and item.name.startswith("traj_"))
    if path.is_dir() and path.name == "trajectories":
        return sorted(item for item in path.iterdir() if item.is_dir() and item.name.startswith("traj_"))
    return []


def analyze_trajectory(
    traj_dir: Path,
    *,
    min_steps: int,
    max_tool_step_error_m: float,
    max_tool_angle_error_deg: float,
    max_fixed_motion_m: float,
    single_step_sample: Path | None = None,
) -> dict[str, Any]:
    metadata = load_json(traj_dir / "trajectory_metadata.json")
    solver_status = load_json(traj_dir / "solver_status.json")
    states = np.load(traj_dir / "states.npy").astype(np.float64)
    actions = np.load(traj_dir / "actions.npy").astype(np.float64)
    responses = np.load(traj_dir / "responses.npy").astype(np.float64)
    contact_points = np.load(traj_dir / "contact_points.npy").astype(np.float64)
    contact_normals = np.load(traj_dir / "contact_normals.npy").astype(np.float64)
    tool_poses = np.load(traj_dir / "tool_poses.npy").astype(np.float64)
    fixed_mask = np.load(traj_dir / "fixed_node_mask.npy").astype(bool)
    contact_status = load_optional_array(traj_dir / "contact_status.npy")
    contact_distances = load_optional_array(traj_dir / "contact_distances.npy")

    errors: list[str] = []
    warnings: list[str] = []
    traj_id = traj_dir.name

    if states.ndim != 3 or states.shape[2] != 3:
        errors.append(f"{traj_id}: states.npy must have shape [T+1, N, 3]")
        step_count = 0
        vertex_count = 0
    else:
        step_count = states.shape[0] - 1
        vertex_count = states.shape[1]
    if actions.ndim != 2 or actions.shape[0] != step_count or actions.shape[1] < 6:
        errors.append(f"{traj_id}: actions.npy must have shape [T, action_dim>=6]")
    if responses.shape != (step_count, vertex_count, 3):
        errors.append(f"{traj_id}: responses.npy must have shape [T, N, 3]")
    if contact_points.shape != (step_count, 3):
        errors.append(f"{traj_id}: contact_points.npy must have shape [T, 3]")
    if contact_normals.shape != (step_count, 3):
        errors.append(f"{traj_id}: contact_normals.npy must have shape [T, 3]")
    if tool_poses.shape != (step_count + 1, 4, 4):
        errors.append(f"{traj_id}: tool_poses.npy must have shape [T+1, 4, 4]")
    if fixed_mask.shape != (vertex_count,):
        errors.append(f"{traj_id}: fixed_node_mask.npy must have shape [N]")
    if not all(np.isfinite(array).all() for array in (states, actions, responses, contact_points, contact_normals, tool_poses)):
        errors.append(f"{traj_id}: non-finite value found in trajectory arrays")

    response_consistency_max_m = 0.0
    if not errors and step_count > 0:
        residual = responses - (states[1:] - states[:-1])
        response_consistency_max_m = float(np.linalg.norm(residual.reshape(step_count, -1), axis=1).max())
        if response_consistency_max_m > 1e-7:
            errors.append(f"{traj_id}: responses do not match states[1:] - states[:-1]")

    response_node_norms = np.linalg.norm(responses, axis=2) if responses.ndim == 3 else np.zeros((0, 0))
    response_l2_per_step = np.linalg.norm(responses.reshape(step_count, -1), axis=1) if responses.ndim == 3 and step_count else np.asarray([])
    response_max_per_step = response_node_norms.max(axis=1) if response_node_norms.size else np.asarray([])
    cumulative = states[1:] - states[0:1] if states.ndim == 3 and step_count else np.zeros((0, 0, 3))
    cumulative_l2_per_step = np.linalg.norm(cumulative.reshape(step_count, -1), axis=1) if cumulative.size else np.asarray([])
    cumulative_max_per_step = np.linalg.norm(cumulative, axis=2).max(axis=1) if cumulative.size else np.asarray([])
    response_drift = analyze_response_drift(responses) if responses.ndim == 3 and step_count else empty_response_drift()
    constant_first_step = analyze_constant_first_step_rollout(responses, cumulative) if responses.ndim == 3 and cumulative.size else empty_constant_first_step()

    fixed_motion_max_m = 0.0
    if fixed_mask.shape == (vertex_count,) and fixed_mask.any() and states.ndim == 3:
        fixed_motion = np.linalg.norm(states[:, fixed_mask, :] - states[0:1, fixed_mask, :], axis=2)
        fixed_motion_max_m = float(fixed_motion.max())
        if fixed_motion_max_m > max_fixed_motion_m:
            warnings.append(f"{traj_id}: fixed-node motion {fixed_motion_max_m:.6g} m exceeds warning threshold")

    action_magnitudes = actions[:, 5] if actions.ndim == 2 and actions.shape[1] >= 6 else np.asarray([])
    action_dirs = actions[:, 2:5] if actions.ndim == 2 and actions.shape[1] >= 5 else np.zeros((0, 3))
    tool_translations = tool_poses[:, :3, 3] if tool_poses.ndim == 3 and tool_poses.shape[1:] == (4, 4) else np.zeros((0, 3))
    tool_deltas = tool_translations[1:] - tool_translations[:-1] if tool_translations.shape[0] == step_count + 1 else np.zeros((0, 3))
    tool_step_lengths = np.linalg.norm(tool_deltas, axis=1) if tool_deltas.size else np.asarray([])
    tool_step_length_error = np.abs(tool_step_lengths - action_magnitudes) if tool_step_lengths.size and action_magnitudes.size else np.asarray([])
    tool_direction_errors = angle_errors_deg(tool_deltas, action_dirs) if tool_deltas.size and action_dirs.size else np.asarray([])
    if tool_step_length_error.size and float(tool_step_length_error.max()) > max_tool_step_error_m:
        warnings.append(f"{traj_id}: max tool step length error {float(tool_step_length_error.max()):.6g} m exceeds warning threshold")
    if tool_direction_errors.size and float(tool_direction_errors.max()) > max_tool_angle_error_deg:
        warnings.append(f"{traj_id}: max tool/action angle error {float(tool_direction_errors.max()):.6g} deg exceeds warning threshold")

    contact_point_drift_max_m = 0.0
    if contact_points.shape == (step_count, 3) and step_count:
        contact_point_drift_max_m = float(np.linalg.norm(contact_points - contact_points[0:1], axis=1).max())
    normal_norm_errors = np.abs(np.linalg.norm(contact_normals, axis=1) - 1.0) if contact_normals.shape == (step_count, 3) else np.asarray([])
    contact_active_steps = int(np.count_nonzero(contact_status)) if contact_status is not None else None
    if contact_status is not None and contact_status.shape[0] != step_count:
        warnings.append(f"{traj_id}: contact_status length does not match step count")
    if contact_distances is not None and contact_distances.shape[0] != step_count:
        warnings.append(f"{traj_id}: contact_distances length does not match step count")
    if step_count < min_steps:
        warnings.append(f"{traj_id}: T={step_count} is shorter than requested useful rollout length {min_steps}")
    if not all(bool(v) for v in solver_status.get("per_step_valid", [])):
        errors.append(f"{traj_id}: solver_status.per_step_valid contains false")

    single_step_comparison = None
    if single_step_sample is not None and not errors:
        single_step_comparison = compare_single_large_step(
            single_step_sample,
            trajectory_metadata=metadata,
            states=states,
            cumulative=cumulative,
            action_magnitudes=action_magnitudes,
            errors=errors,
            warnings=warnings,
            traj_id=traj_id,
        )

    rollout_ready = not errors and step_count >= min_steps
    return {
        "trajectory_id": traj_id,
        "path": str(traj_dir),
        "valid": not errors,
        "rollout_ready": rollout_ready,
        "errors": errors,
        "warnings": warnings,
        "step_count": int(step_count),
        "vertex_count": int(vertex_count),
        "action_dim": int(actions.shape[1]) if actions.ndim == 2 else None,
        "step_size_min_m": float(action_magnitudes.min()) if action_magnitudes.size else None,
        "step_size_max_m": float(action_magnitudes.max()) if action_magnitudes.size else None,
        "total_displacement_m": float(metadata.get("total_displacement_m", float(action_magnitudes.sum()) if action_magnitudes.size else 0.0)),
        "response_l2_per_step_m": response_l2_per_step.tolist(),
        "response_l2_mean_m": float(response_l2_per_step.mean()) if response_l2_per_step.size else 0.0,
        "response_l2_max_m": float(response_l2_per_step.max()) if response_l2_per_step.size else 0.0,
        "response_node_max_per_step_m": response_max_per_step.tolist(),
        "response_node_max_m": float(response_max_per_step.max()) if response_max_per_step.size else 0.0,
        "cumulative_l2_per_step_m": cumulative_l2_per_step.tolist(),
        "cumulative_node_max_per_step_m": cumulative_max_per_step.tolist(),
        "final_delta_node_max_m": float(cumulative_max_per_step[-1]) if cumulative_max_per_step.size else 0.0,
        "response_drift": response_drift,
        "constant_first_step_baseline": constant_first_step,
        "single_large_step_comparison": single_step_comparison,
        "response_consistency_max_m": response_consistency_max_m,
        "fixed_node_motion_max_m": fixed_motion_max_m,
        "tool_step_length_min_m": float(tool_step_lengths.min()) if tool_step_lengths.size else None,
        "tool_step_length_max_m": float(tool_step_lengths.max()) if tool_step_lengths.size else None,
        "tool_step_length_error_max_m": float(tool_step_length_error.max()) if tool_step_length_error.size else None,
        "tool_action_angle_error_max_deg": float(tool_direction_errors.max()) if tool_direction_errors.size else None,
        "contact_active_steps": contact_active_steps,
        "contact_active_fraction": float(contact_active_steps / step_count) if contact_active_steps is not None and step_count else None,
        "contact_distance_min_m": float(np.nanmin(contact_distances)) if contact_distances is not None and contact_distances.size else None,
        "contact_distance_max_m": float(np.nanmax(contact_distances)) if contact_distances is not None and contact_distances.size else None,
        "contact_point_drift_max_m": contact_point_drift_max_m,
        "contact_normal_norm_error_max": float(normal_norm_errors.max()) if normal_norm_errors.size else None,
        "source_sample": solver_status.get("source_sample") or metadata.get("source_sample_path"),
        "smoke_sized_trajectory": bool(metadata.get("smoke_sized_trajectory", step_count < min_steps)),
        "future_model_metrics": {
            "rolling_njf_prediction_error": "not_computed_no_model_predictions",
            "single_step_large_action_error": "not_computed_no_model_predictions",
        },
    }


def analyze_response_drift(responses: np.ndarray) -> dict[str, Any]:
    flat = responses.reshape(responses.shape[0], -1).astype(np.float64)
    norms = np.linalg.norm(flat, axis=1)
    adjacent_cosines = []
    adjacent_relative_changes = []
    first_step_cosines = []
    first_step_relative_changes = []
    first = flat[0]
    first_norm = float(norms[0])
    for i in range(flat.shape[0] - 1):
        adjacent_cosines.append(cosine_similarity(flat[i], flat[i + 1]))
        denominator = max(float(norms[i]), 1e-12)
        adjacent_relative_changes.append(float(np.linalg.norm(flat[i + 1] - flat[i]) / denominator))
    for i in range(flat.shape[0]):
        first_step_cosines.append(cosine_similarity(first, flat[i]))
        denominator = max(first_norm, 1e-12)
        first_step_relative_changes.append(float(np.linalg.norm(flat[i] - first) / denominator))
    return {
        "adjacent_response_cosine": adjacent_cosines,
        "adjacent_response_cosine_mean": float(np.mean(adjacent_cosines)) if adjacent_cosines else None,
        "adjacent_response_cosine_min": float(np.min(adjacent_cosines)) if adjacent_cosines else None,
        "adjacent_relative_change": adjacent_relative_changes,
        "adjacent_relative_change_mean": float(np.mean(adjacent_relative_changes)) if adjacent_relative_changes else None,
        "adjacent_relative_change_max": float(np.max(adjacent_relative_changes)) if adjacent_relative_changes else None,
        "first_step_response_cosine": first_step_cosines,
        "first_step_response_cosine_final": float(first_step_cosines[-1]) if first_step_cosines else None,
        "first_step_relative_change": first_step_relative_changes,
        "first_step_relative_change_final": float(first_step_relative_changes[-1]) if first_step_relative_changes else None,
    }


def empty_response_drift() -> dict[str, Any]:
    return {
        "adjacent_response_cosine": [],
        "adjacent_response_cosine_mean": None,
        "adjacent_response_cosine_min": None,
        "adjacent_relative_change": [],
        "adjacent_relative_change_mean": None,
        "adjacent_relative_change_max": None,
        "first_step_response_cosine": [],
        "first_step_response_cosine_final": None,
        "first_step_relative_change": [],
        "first_step_relative_change_final": None,
    }


def analyze_constant_first_step_rollout(responses: np.ndarray, cumulative: np.ndarray) -> dict[str, Any]:
    first = responses[0].astype(np.float64)
    predicted = np.stack([(i + 1) * first for i in range(responses.shape[0])], axis=0)
    residual = predicted - cumulative
    residual_l2 = np.linalg.norm(residual.reshape(residual.shape[0], -1), axis=1)
    cumulative_l2 = np.linalg.norm(cumulative.reshape(cumulative.shape[0], -1), axis=1)
    relative_l2 = residual_l2 / np.maximum(cumulative_l2, 1e-12)
    node_error_max = np.linalg.norm(residual, axis=2).max(axis=1)
    return {
        "method": "repeat_first_step_response",
        "relative_l2_error_per_horizon": relative_l2.tolist(),
        "relative_l2_error_final": float(relative_l2[-1]) if relative_l2.size else None,
        "max_node_error_per_horizon_m": node_error_max.tolist(),
        "max_node_error_final_m": float(node_error_max[-1]) if node_error_max.size else None,
        "prediction_interpretation": "No-model baseline: assumes local Jacobian/response field stays equal to step 0 for the full rollout.",
    }


def empty_constant_first_step() -> dict[str, Any]:
    return {
        "method": "repeat_first_step_response",
        "relative_l2_error_per_horizon": [],
        "relative_l2_error_final": None,
        "max_node_error_per_horizon_m": [],
        "max_node_error_final_m": None,
    }


def compare_single_large_step(
    sample_dir: Path,
    *,
    trajectory_metadata: dict[str, Any],
    states: np.ndarray,
    cumulative: np.ndarray,
    action_magnitudes: np.ndarray,
    errors: list[str],
    warnings: list[str],
    traj_id: str,
) -> dict[str, Any] | None:
    sample_dir = resolve_single_step_sample(
        sample_dir,
        trajectory_metadata=trajectory_metadata,
        expected_total_action_m=float(np.sum(action_magnitudes)) if action_magnitudes.size else None,
    )
    required = ["vertices_0.npy", "vertices_1.npy", "displacement.npy", "action.npy"]
    missing = [name for name in required if not (sample_dir / name).exists()]
    if missing:
        errors.append(f"{traj_id}: single-step sample is missing files: {missing}")
        return None
    x0 = np.load(sample_dir / "vertices_0.npy").astype(np.float64)
    x1 = np.load(sample_dir / "vertices_1.npy").astype(np.float64)
    displacement = np.load(sample_dir / "displacement.npy").astype(np.float64)
    action = np.load(sample_dir / "action.npy").astype(np.float64)
    if x0.shape != states[0].shape or x1.shape != states[-1].shape:
        errors.append(f"{traj_id}: single-step sample shape does not match rollout states")
        return None
    initial_mismatch = float(np.linalg.norm((x0 - states[0]).reshape(-1)))
    if initial_mismatch > 1e-6:
        warnings.append(f"{traj_id}: single-step initial state mismatch {initial_mismatch:.6g} m")
    final_rollout_delta = cumulative[-1]
    residual = displacement - final_rollout_delta
    residual_norm = float(np.linalg.norm(residual.reshape(-1)))
    rollout_norm = float(np.linalg.norm(final_rollout_delta.reshape(-1)))
    single_norm = float(np.linalg.norm(displacement.reshape(-1)))
    total_rollout_action = float(np.sum(action_magnitudes)) if action_magnitudes.size else 0.0
    action_magnitude_error = abs(float(action[5]) - total_rollout_action) if action.shape[0] >= 6 else None
    return {
        "sample_dir": str(sample_dir),
        "match_mode": "metadata_contact_material_direction_action",
        "single_action_magnitude_m": float(action[5]) if action.shape[0] >= 6 else None,
        "rollout_total_action_magnitude_m": total_rollout_action,
        "action_magnitude_error_m": action_magnitude_error,
        "initial_state_l2_mismatch_m": initial_mismatch,
        "relative_l2_error": float(residual_norm / max(rollout_norm, 1e-12)),
        "rollout_final_l2_m": rollout_norm,
        "single_large_l2_m": single_norm,
        "pattern_cosine": cosine_similarity(displacement.reshape(-1), final_rollout_delta.reshape(-1)),
        "max_node_error_m": float(np.linalg.norm(residual, axis=1).max()),
        "rollout_final_node_max_m": float(np.linalg.norm(final_rollout_delta, axis=1).max()),
        "single_large_node_max_m": float(np.linalg.norm(displacement, axis=1).max()),
        "interpretation": "Compares quasi-static final state from one large tool motion against final state reached by multiple recorded small steps.",
    }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


def resolve_single_step_sample(
    path: Path | None,
    *,
    trajectory_metadata: dict[str, Any] | None = None,
    expected_total_action_m: float | None = None,
) -> Path:
    if path is None:
        raise ValueError("single-step sample path is required")
    path = Path(path)
    if path.is_dir() and path.name.startswith("sample_"):
        return path
    candidates = discover_sample_dirs(path)
    if not candidates:
        raise FileNotFoundError(f"Could not resolve sample_* directories from {path}")
    if trajectory_metadata is None:
        if len(candidates) == 1:
            return candidates[0]
        raise ValueError(f"Multiple sample_* directories found under {path}; trajectory metadata is required for matching")
    matches = [
        sample_dir
        for sample_dir in candidates
        if sample_matches_trajectory(sample_dir, trajectory_metadata, expected_total_action_m)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(
            "No single-step sample matched trajectory "
            f"contact={trajectory_metadata.get('contact_point_id')} "
            f"material={trajectory_metadata.get('material_id')} "
            f"direction={trajectory_metadata.get('direction_id')} "
            f"total_action={expected_total_action_m}"
        )
    raise ValueError(f"Multiple single-step samples matched trajectory metadata: {[str(item) for item in matches]}")


def discover_sample_dirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    direct_samples = sorted(item for item in path.iterdir() if item.is_dir() and item.name.startswith("sample_"))
    samples_dir = path / "samples"
    nested = sorted(item for item in samples_dir.iterdir() if item.is_dir() and item.name.startswith("sample_")) if samples_dir.is_dir() else []
    return direct_samples + nested


def sample_matches_trajectory(
    sample_dir: Path,
    trajectory_metadata: dict[str, Any],
    expected_total_action_m: float | None,
) -> bool:
    meta_path = sample_dir / "meta.json"
    action_path = sample_dir / "action.npy"
    if not meta_path.exists() or not action_path.exists():
        return False
    meta = load_json(meta_path)
    extra = meta.get("extra", {}) if isinstance(meta.get("extra"), dict) else {}
    if extra.get("contact_point_id") != trajectory_metadata.get("contact_point_id"):
        return False
    if extra.get("material_id") != trajectory_metadata.get("material_id"):
        return False
    if meta.get("direction_id") != trajectory_metadata.get("direction_id") and extra.get("direction_id") != trajectory_metadata.get("direction_id"):
        return False
    if expected_total_action_m is not None:
        action = np.load(action_path).astype(np.float64)
        if action.shape[0] < 6 or abs(float(action[5]) - float(expected_total_action_m)) > 1e-7:
            return False
    return True


def write_csv_outputs(csv_dir: Path, trajectories: list[dict[str, Any]]) -> None:
    csv_dir.mkdir(parents=True, exist_ok=True)
    for traj in trajectories:
        path = csv_dir / f"{traj['trajectory_id']}_per_step.csv"
        response_l2 = traj.get("response_l2_per_step_m", [])
        response_max = traj.get("response_node_max_per_step_m", [])
        cumulative_l2 = traj.get("cumulative_l2_per_step_m", [])
        cumulative_max = traj.get("cumulative_node_max_per_step_m", [])
        contact_distances = []
        if traj.get("contact_distance_min_m") is not None:
            # Per-step signed gaps are not included in the summary payload yet; keep CSV schema stable.
            contact_distances = [""] * len(response_l2)
        drift = traj.get("response_drift", {}) or {}
        first_cos = drift.get("first_step_response_cosine", []) or []
        first_rel = drift.get("first_step_relative_change", []) or []
        baseline = traj.get("constant_first_step_baseline", {}) or {}
        baseline_rel = baseline.get("relative_l2_error_per_horizon", []) or []
        baseline_max = baseline.get("max_node_error_per_horizon_m", []) or []
        rows = [
            "step,response_l2_m,response_node_max_m,cumulative_l2_m,cumulative_node_max_m,first_step_cosine,first_step_relative_change,constant_first_step_relative_l2_error,constant_first_step_max_node_error_m,contact_distance_m"
        ]
        for i in range(len(response_l2)):
            rows.append(
                ",".join(
                    str(value)
                    for value in [
                        i,
                        get_list_value(response_l2, i),
                        get_list_value(response_max, i),
                        get_list_value(cumulative_l2, i),
                        get_list_value(cumulative_max, i),
                        get_list_value(first_cos, i),
                        get_list_value(first_rel, i),
                        get_list_value(baseline_rel, i),
                        get_list_value(baseline_max, i),
                        get_list_value(contact_distances, i),
                    ]
                )
            )
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def get_list_value(values: list[Any], index: int) -> Any:
    return values[index] if index < len(values) else ""


def angle_errors_deg(vectors: np.ndarray, directions: np.ndarray) -> np.ndarray:
    count = min(vectors.shape[0], directions.shape[0])
    errors = []
    for vector, direction in zip(vectors[:count], directions[:count]):
        vector_norm = float(np.linalg.norm(vector))
        direction_norm = float(np.linalg.norm(direction))
        if vector_norm <= 0.0 or direction_norm <= 0.0:
            errors.append(0.0)
            continue
        cosine = float(np.dot(vector, direction) / (vector_norm * direction_norm))
        cosine = max(-1.0, min(1.0, cosine))
        errors.append(math.degrees(math.acos(cosine)))
    return np.asarray(errors, dtype=np.float64)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def load_optional_array(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.load(path)


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
    print(f"Rollout trajectory analysis: {status}")
    print(
        f"trajectories={payload['trajectory_count']} "
        f"errors={payload['error_count']} warnings={payload['warning_count']}"
    )
    for traj in payload["trajectories"]:
        print(
            f"- {traj['trajectory_id']}: T={traj['step_count']} "
            f"ready={traj['rollout_ready']} "
            f"step=[{format_optional_m(traj['step_size_min_m'])}, {format_optional_m(traj['step_size_max_m'])}] "
            f"final_max={traj['final_delta_node_max_m'] * 1e3:.3f} mm "
            f"step_response_max={traj['response_node_max_m'] * 1e3:.3f} mm"
        )
        print(
            f"  fixed_max={traj['fixed_node_motion_max_m'] * 1e3:.6f} mm "
            f"tool_step_error_max={format_optional_mm(traj['tool_step_length_error_max_m'])} "
            f"tool_angle_error_max={format_optional_deg(traj['tool_action_angle_error_max_deg'])}"
        )
        print(
            f"  contact_active={traj['contact_active_steps']}/{traj['step_count']} "
            f"contact_distance=[{format_optional_m(traj['contact_distance_min_m'])}, {format_optional_m(traj['contact_distance_max_m'])}] "
            f"contact_point_drift={traj['contact_point_drift_max_m'] * 1e3:.6f} mm"
        )
        drift = traj.get("response_drift", {}) or {}
        baseline = traj.get("constant_first_step_baseline", {}) or {}
        print(
            f"  response_drift adjacent_cos_mean={format_optional_float(drift.get('adjacent_response_cosine_mean'))} "
            f"adjacent_rel_change_mean={format_optional_float(drift.get('adjacent_relative_change_mean'))} "
            f"first_step_cos_final={format_optional_float(drift.get('first_step_response_cosine_final'))}"
        )
        print(
            f"  constant_first_step final_rel_l2={format_optional_float(baseline.get('relative_l2_error_final'))} "
            f"final_max_node_error={format_optional_m(baseline.get('max_node_error_final_m'))}"
        )
        comparison = traj.get("single_large_step_comparison")
        if comparison:
            print(
                f"  single_large_step rel_l2={comparison['relative_l2_error']:.6f} "
                f"pattern_cosine={comparison['pattern_cosine']:.6f} "
                f"max_node_error={comparison['max_node_error_m'] * 1e3:.3f} mm"
            )
        for warning in traj["warnings"]:
            print(f"  warning={warning}")
        for error in traj["errors"]:
            print(f"  error={error}")


def format_optional_m(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 1e3:.3f} mm"


def format_optional_mm(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 1e3:.6f} mm"


def format_optional_deg(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f} deg"


def format_optional_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
