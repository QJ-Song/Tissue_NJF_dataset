from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class NJFValidationReport:
    dataset_root: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    groups: list[dict[str, Any]] = field(default_factory=list)
    trajectories: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_root": str(self.dataset_root),
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "samples": self.samples,
            "groups": self.groups,
            "trajectories": self.trajectories,
        }


def validate_njf_dataset(dataset_root: Path) -> NJFValidationReport:
    root = Path(dataset_root)
    report = NJFValidationReport(dataset_root=root)
    metadata_path = root / "metadata.json"
    if not metadata_path.exists():
        report.errors.append("Missing metadata.json")
        return report
    metadata = _load_json(metadata_path)

    samples_dir = root / "samples"
    if not samples_dir.is_dir():
        report.errors.append("Missing samples/ directory")
        return report
    sample_dirs = sorted(path for path in samples_dir.iterdir() if path.is_dir() and path.name.startswith("sample_"))
    if not sample_dirs:
        report.errors.append("No sample_* directories found under samples/")
    expected = {item.get("sample_id") for item in metadata.get("samples", []) if isinstance(item, dict)}
    actual = {path.name for path in sample_dirs}
    if expected and expected != actual:
        report.errors.append(f"metadata samples {sorted(expected)} do not match samples directory {sorted(actual)}")
    for sample_dir in sample_dirs:
        report.samples.append(_validate_local_step_sample(sample_dir, report))

    groups_dir = root / "groups"
    group_dirs = sorted(path for path in groups_dir.iterdir() if path.is_dir() and path.name.startswith("group_")) if groups_dir.is_dir() else []
    expected_groups = {item.get("group_id") for item in metadata.get("groups", []) if isinstance(item, dict)}
    actual_groups = {path.name for path in group_dirs}
    if expected_groups and expected_groups != actual_groups:
        report.errors.append(f"metadata groups {sorted(expected_groups)} do not match groups directory {sorted(actual_groups)}")
    if metadata.get("modes", {}).get("response_basis_group") and not group_dirs:
        report.errors.append("response_basis_group mode is enabled but no group_* directories were found")
    for group_dir in group_dirs:
        report.groups.append(_validate_mode_b_group(root, group_dir, report))

    trajectories_dir = root / "trajectories"
    traj_dirs = sorted(path for path in trajectories_dir.iterdir() if path.is_dir() and path.name.startswith("traj_")) if trajectories_dir.is_dir() else []
    expected_traj = {item.get("trajectory_id") for item in metadata.get("trajectories", []) if isinstance(item, dict)}
    actual_traj = {path.name for path in traj_dirs}
    if expected_traj and expected_traj != actual_traj:
        report.errors.append(f"metadata trajectories {sorted(expected_traj)} do not match trajectories directory {sorted(actual_traj)}")
    if metadata.get("modes", {}).get("rollout_trajectory") and not traj_dirs:
        report.errors.append("rollout_trajectory mode is enabled but no traj_* directories were found")
    for traj_dir in traj_dirs:
        report.trajectories.append(_validate_mode_c_trajectory(root, traj_dir, report))
    return report


def _validate_local_step_sample(sample_dir: Path, report: NJFValidationReport) -> dict[str, Any]:
    sample_id = sample_dir.name
    required = [
        "vertices_0.npy", "vertices_1.npy", "displacement.npy", "action.npy", "tool_pose_0.npy",
        "tool_pose_1.npy", "tool_geometry.json", "contact_summary.json", "boundary_mask.npy",
        "fixed_node_indices.npy", "free_node_indices.npy", "boundary.json", "solver_summary.json",
        "meta.json", "sample_manifest.json",
    ]
    missing = [name for name in required if not (sample_dir / name).exists()]
    if missing:
        report.errors.append(f"{sample_id}: missing required NJF sample artifact(s): {', '.join(missing)}")
        return {"sample_id": sample_id, "valid": False, "missing": missing}

    vertices_0 = np.load(sample_dir / "vertices_0.npy")
    vertices_1 = np.load(sample_dir / "vertices_1.npy")
    displacement = np.load(sample_dir / "displacement.npy")
    action = np.load(sample_dir / "action.npy")
    mask = np.load(sample_dir / "boundary_mask.npy")
    fixed = np.load(sample_dir / "fixed_node_indices.npy")
    contact = _load_json(sample_dir / "contact_summary.json")
    solver = _load_json(sample_dir / "solver_summary.json")
    meta = _load_json(sample_dir / "meta.json")
    extra = meta.get("extra", {}) if isinstance(meta.get("extra"), dict) else {}
    mode = extra.get("njf_mode")

    if vertices_0.shape != vertices_1.shape or vertices_0.shape != displacement.shape:
        report.errors.append(f"{sample_id}: vertices/displacement shapes do not match")
    if not np.allclose(displacement, vertices_1 - vertices_0, atol=1e-7):
        report.errors.append(f"{sample_id}: displacement != vertices_1 - vertices_0")
    if not np.isfinite(vertices_0).all() or not np.isfinite(vertices_1).all() or not np.isfinite(displacement).all():
        report.errors.append(f"{sample_id}: non-finite vertex/displacement value")
    if action.shape[0] < 6:
        report.errors.append(f"{sample_id}: action must have at least 6 values")
        magnitude_m = float("nan")
    else:
        magnitude_m = float(action[5])
        max_allowed = 0.005 if mode == "rollout_trajectory" else 0.00025
        if magnitude_m <= 0.0 or magnitude_m > max_allowed:
            report.errors.append(f"{sample_id}: action magnitude {magnitude_m} m is outside bounds for mode {mode}")
        direction_norm = float(np.linalg.norm(action[2:5]))
        if not np.isclose(direction_norm, 1.0, atol=1e-3):
            report.errors.append(f"{sample_id}: action direction is not unit length")
    if mask.shape != (vertices_0.shape[0],):
        report.errors.append(f"{sample_id}: boundary_mask shape does not match vertex count")
    if fixed.size and mask.shape == (vertices_0.shape[0],):
        fixed_disp = np.linalg.norm(vertices_1[fixed.astype(int)] - vertices_0[fixed.astype(int)], axis=1)
        max_fixed = float(fixed_disp.max())
        if max_fixed > 1e-6:
            report.errors.append(f"{sample_id}: fixed node displacement {max_fixed} m exceeds tolerance")
    else:
        max_fixed = 0.0
    if not bool(contact.get("contact_detected", False)):
        report.errors.append(f"{sample_id}: contact_summary.contact_detected is false")
    if not bool(solver.get("valid", False)):
        report.errors.append(f"{sample_id}: solver_summary.valid is false")
    if mode not in {"local_perturbation", "response_basis_group", "rollout_trajectory"}:
        report.errors.append(f"{sample_id}: meta.extra.njf_mode is not a supported NJF mode")

    return {
        "sample_id": sample_id,
        "valid": True,
        "mode": mode,
        "group_id": extra.get("group_id"),
        "trajectory_id": extra.get("trajectory_id"),
        "vertex_count": int(vertices_0.shape[0]),
        "action_magnitude_m": magnitude_m,
        "max_displacement_m": float(np.linalg.norm(displacement, axis=1).max()),
        "max_fixed_displacement_m": max_fixed,
        "contact_detected": bool(contact.get("contact_detected", False)),
        "solver_valid": bool(solver.get("valid", False)),
    }


def _validate_mode_b_group(root: Path, group_dir: Path, report: NJFValidationReport) -> dict[str, Any]:
    group_id = group_dir.name
    required = ["group_metadata.json", "state_initial.npy", "fixed_node_mask.npy", "surface_points.npy", "actions.npy", "responses.npy", "contact_point.npy", "contact_normal.npy"]
    missing = [name for name in required if not (group_dir / name).exists()]
    if missing:
        report.errors.append(f"{group_id}: missing required Mode B artifact(s): {', '.join(missing)}")
        return {"group_id": group_id, "valid": False, "missing": missing}

    metadata = _load_json(group_dir / "group_metadata.json")
    state_initial = np.load(group_dir / "state_initial.npy")
    fixed_mask = np.load(group_dir / "fixed_node_mask.npy")
    surface_points = np.load(group_dir / "surface_points.npy")
    actions = np.load(group_dir / "actions.npy")
    responses = np.load(group_dir / "responses.npy")
    contact_point = np.load(group_dir / "contact_point.npy")
    contact_normal = np.load(group_dir / "contact_normal.npy")

    if state_initial.ndim != 2 or state_initial.shape[1] != 3:
        report.errors.append(f"{group_id}: state_initial must have shape [N, 3]")
    if fixed_mask.shape != (state_initial.shape[0],):
        report.errors.append(f"{group_id}: fixed_node_mask shape does not match state_initial")
    if surface_points.shape != state_initial.shape:
        report.errors.append(f"{group_id}: surface_points shape must match state_initial for current fixed-topology smoke")
    if actions.ndim != 2 or actions.shape[1] < 6:
        report.errors.append(f"{group_id}: actions must have shape [K, action_dim>=6]")
    if responses.ndim != 3 or responses.shape[1:] != state_initial.shape:
        report.errors.append(f"{group_id}: responses must have shape [K, N, 3]")
    if actions.shape[0] != responses.shape[0]:
        report.errors.append(f"{group_id}: action count does not match response count")
    if contact_point.shape != (3,):
        report.errors.append(f"{group_id}: contact_point must have shape [3]")
    if contact_normal.shape != (3,):
        report.errors.append(f"{group_id}: contact_normal must have shape [3]")
    if not np.isfinite(state_initial).all() or not np.isfinite(actions).all() or not np.isfinite(responses).all():
        report.errors.append(f"{group_id}: non-finite value in group arrays")
    if actions.shape[0] < 3:
        report.errors.append(f"{group_id}: smoke response basis group needs at least 3 actions")
    elif actions.shape[0] < 12:
        report.warnings.append(f"{group_id}: K={actions.shape[0]} is smoke-sized; basis analysis should use K>=12")
    unique_dirs = np.unique(np.round(actions[:, 2:5], decimals=4), axis=0) if actions.ndim == 2 and actions.shape[1] >= 5 else np.empty((0, 3))
    if unique_dirs.shape[0] < 2:
        report.warnings.append(f"{group_id}: group has only one unique action direction; complete Mode B should vary direction")

    sample_paths = metadata.get("sample_paths", [])
    state_ids: set[str] = set()
    material_ids: set[str] = set()
    boundary_ids: set[str] = set()
    contact_point_ids: set[str] = set()
    for index, rel_path in enumerate(sample_paths):
        sample_dir = root / rel_path
        if not sample_dir.is_dir():
            report.errors.append(f"{group_id}: missing referenced sample {rel_path}")
            continue
        sample_state = np.load(sample_dir / "vertices_0.npy")
        sample_response = np.load(sample_dir / "displacement.npy")
        sample_action = np.load(sample_dir / "action.npy")
        sample_contact = np.load(sample_dir / "contact_point.npy")
        if not np.allclose(sample_state, state_initial, atol=1e-8):
            report.errors.append(f"{group_id}: referenced sample {sample_dir.name} has different X_t")
        if index < responses.shape[0] and not np.allclose(sample_response, responses[index], atol=1e-7):
            report.errors.append(f"{group_id}: response[{index}] does not match {sample_dir.name}/displacement.npy")
        if index < actions.shape[0] and not np.allclose(sample_action, actions[index], atol=1e-8):
            report.errors.append(f"{group_id}: action[{index}] does not match {sample_dir.name}/action.npy")
        if not np.allclose(sample_contact, contact_point, atol=1e-8):
            report.errors.append(f"{group_id}: referenced sample {sample_dir.name} has different contact_point")
        meta = _load_json(sample_dir / "meta.json")
        extra = meta.get("extra", {}) if isinstance(meta.get("extra"), dict) else {}
        state_ids.add(str(extra.get("state_id")))
        material_ids.add(str(extra.get("material_id")))
        boundary_ids.add(str(extra.get("boundary_id")))
        contact_point_ids.add(str(extra.get("contact_point_id")))
    for name, values in (("state_id", state_ids), ("material_id", material_ids), ("boundary_id", boundary_ids), ("contact_point_id", contact_point_ids)):
        if len(values) > 1:
            report.errors.append(f"{group_id}: {name} is not fixed across group samples: {sorted(values)}")

    return {
        "group_id": group_id,
        "valid": True,
        "action_count": int(actions.shape[0]),
        "vertex_count": int(state_initial.shape[0]),
        "unique_action_directions": int(unique_dirs.shape[0]),
        "max_response_m": float(np.linalg.norm(responses, axis=2).max()),
        "sample_count": len(sample_paths),
    }


def _validate_mode_c_trajectory(root: Path, traj_dir: Path, report: NJFValidationReport) -> dict[str, Any]:
    traj_id = traj_dir.name
    required = [
        "trajectory_metadata.json", "states.npy", "actions.npy", "responses.npy", "contact_points.npy",
        "contact_normals.npy", "tool_poses.npy", "fixed_node_mask.npy", "solver_status.json",
    ]
    missing = [name for name in required if not (traj_dir / name).exists()]
    if missing:
        report.errors.append(f"{traj_id}: missing required Mode C artifact(s): {', '.join(missing)}")
        return {"trajectory_id": traj_id, "valid": False, "missing": missing}

    metadata = _load_json(traj_dir / "trajectory_metadata.json")
    solver_status = _load_json(traj_dir / "solver_status.json")
    states = np.load(traj_dir / "states.npy")
    actions = np.load(traj_dir / "actions.npy")
    responses = np.load(traj_dir / "responses.npy")
    contact_points = np.load(traj_dir / "contact_points.npy")
    contact_normals = np.load(traj_dir / "contact_normals.npy")
    tool_poses = np.load(traj_dir / "tool_poses.npy")
    fixed_mask = np.load(traj_dir / "fixed_node_mask.npy")

    if states.ndim != 3 or states.shape[2] != 3:
        report.errors.append(f"{traj_id}: states must have shape [T+1, N, 3]")
    step_count = max(int(states.shape[0]) - 1, 0) if states.ndim == 3 else 0
    if actions.shape[0] != step_count:
        report.errors.append(f"{traj_id}: actions count must equal states count - 1")
    if responses.shape != (step_count, states.shape[1], 3):
        report.errors.append(f"{traj_id}: responses shape must be [T, N, 3]")
    elif not np.allclose(responses, states[1:] - states[:-1], atol=1e-7):
        report.errors.append(f"{traj_id}: responses != states[1:] - states[:-1]")
    if contact_points.shape != (step_count, 3):
        report.errors.append(f"{traj_id}: contact_points must have shape [T, 3]")
    if contact_normals.shape != (step_count, 3):
        report.errors.append(f"{traj_id}: contact_normals must have shape [T, 3]")
    if tool_poses.shape != (step_count + 1, 4, 4):
        report.errors.append(f"{traj_id}: tool_poses must have shape [T+1, 4, 4]")
    if fixed_mask.shape != (states.shape[1],):
        report.errors.append(f"{traj_id}: fixed_node_mask shape must match vertex count")
    if not np.isfinite(states).all() or not np.isfinite(actions).all() or not np.isfinite(responses).all():
        report.errors.append(f"{traj_id}: non-finite value in trajectory arrays")
    if actions.ndim == 2 and actions.shape[1] >= 6:
        max_step = float(np.max(actions[:, 5]))
        if np.any(actions[:, 5] <= 0.0) or max_step > 0.00025:
            report.errors.append(f"{traj_id}: per-step action magnitude exceeds small-step bound")
    else:
        max_step = float("nan")
        report.errors.append(f"{traj_id}: actions must have shape [T, action_dim>=6]")
    if fixed_mask.size and states.ndim == 3:
        fixed = np.nonzero(fixed_mask.astype(bool))[0]
        if fixed.size:
            fixed_motion = np.linalg.norm(states[:, fixed, :] - states[0:1, fixed, :], axis=2)
            max_fixed = float(fixed_motion.max())
            if max_fixed > 1e-6:
                report.errors.append(f"{traj_id}: fixed node trajectory displacement {max_fixed} m exceeds tolerance")
        else:
            max_fixed = 0.0
    else:
        max_fixed = 0.0
    if step_count < 3:
        report.errors.append(f"{traj_id}: smoke rollout needs at least 3 steps")
    elif step_count < 10:
        report.warnings.append(f"{traj_id}: T={step_count} is smoke-sized; rollout validation should use T>=10")
    if not all(bool(v) for v in solver_status.get("per_step_valid", [])):
        report.errors.append(f"{traj_id}: solver_status.per_step_valid contains false")
    source_path = solver_status.get("source_sample") or metadata.get("source_sample_path")
    if source_path and not (root / source_path).is_dir():
        report.errors.append(f"{traj_id}: source sample does not exist: {source_path}")

    return {
        "trajectory_id": traj_id,
        "valid": True,
        "step_count": int(step_count),
        "vertex_count": int(states.shape[1]) if states.ndim == 3 else 0,
        "max_step_action_m": max_step,
        "max_response_m": float(np.linalg.norm(responses, axis=2).max()) if responses.ndim == 3 else 0.0,
        "max_fixed_displacement_m": max_fixed,
        "source_sample": source_path,
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data
