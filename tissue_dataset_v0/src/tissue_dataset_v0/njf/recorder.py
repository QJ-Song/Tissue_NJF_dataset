from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from tissue_dataset_v0.trajectory import EpisodeTrajectoryReader

from .schema import ModeBGroupPlan, ModeCTrajectoryPlan, NJFDatasetPlan


def prepare_dataset_root(plan: NJFDatasetPlan, *, overwrite: bool = False) -> Path:
    root = plan.output_dir
    if root.exists() and any(root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"NJF dataset output directory exists and is not empty: {root}. Use --overwrite explicitly.")
        shutil.rmtree(root)
    (root / "samples").mkdir(parents=True, exist_ok=True)
    (root / "groups").mkdir(parents=True, exist_ok=True)
    (root / "trajectories").mkdir(parents=True, exist_ok=True)
    return root


def write_mode_b_group(root: Path, group: ModeBGroupPlan, sample_dirs: list[Path]) -> dict[str, Any]:
    if not sample_dirs:
        raise ValueError(f"Mode B group {group.group_id} has no sample directories")
    group_dir = root / "groups" / group.group_id
    group_dir.mkdir(parents=True, exist_ok=True)

    first = sample_dirs[0]
    state_initial = np.load(first / "vertices_0.npy")
    fixed_node_mask = np.load(first / "boundary_mask.npy").astype(bool)
    surface_points = state_initial.copy()
    contact_point = np.load(first / "contact_point.npy")
    actions = []
    responses = []
    sample_ids = []
    sample_paths = []
    action_directions = []
    action_magnitudes = []

    for sample_dir in sample_dirs:
        vertices_0 = np.load(sample_dir / "vertices_0.npy")
        if not np.allclose(vertices_0, state_initial, atol=1e-8):
            raise ValueError(f"{group.group_id}: state_initial differs for {sample_dir.name}")
        sample_contact = np.load(sample_dir / "contact_point.npy")
        if not np.allclose(sample_contact, contact_point, atol=1e-8):
            raise ValueError(f"{group.group_id}: contact_point differs for {sample_dir.name}")
        action = np.load(sample_dir / "action.npy")
        response = np.load(sample_dir / "displacement.npy")
        actions.append(action)
        responses.append(response)
        sample_ids.append(sample_dir.name)
        sample_paths.append(str(sample_dir.relative_to(root)))
        action_directions.append([float(v) for v in action[2:5]])
        action_magnitudes.append(float(action[5]))

    actions_array = np.stack(actions, axis=0)
    responses_array = np.stack(responses, axis=0)
    contact_normal = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)

    np.save(group_dir / "state_initial.npy", state_initial)
    np.save(group_dir / "fixed_node_mask.npy", fixed_node_mask)
    np.save(group_dir / "surface_points.npy", surface_points)
    np.save(group_dir / "actions.npy", actions_array)
    np.save(group_dir / "responses.npy", responses_array)
    np.save(group_dir / "contact_point.npy", contact_point)
    np.save(group_dir / "contact_normal.npy", contact_normal)

    material = _load_json(first / "material.json")
    boundary = _load_json(first / "boundary.json")
    solver = _load_json(first / "solver_summary.json")
    tool_geometry = _load_json(first / "tool_geometry.json")
    metadata = {
        "group_id": group.group_id,
        "group_type": "local_response_basis",
        "state_id": group.state_id,
        "material_id": group.material_id,
        "boundary_id": group.boundary_id,
        "contact_point_id": group.contact_point_id,
        "contact_point_world": [float(v) for v in contact_point.tolist()],
        "contact_normal": [float(v) for v in contact_normal.tolist()],
        "fixed_variables": ["state_id", "material_id", "boundary_id", "contact_point_id", "tool_geometry", "solver_config"],
        "varied_variables": ["action_direction", "action_magnitude"],
        "sample_ids": sample_ids,
        "sample_paths": sample_paths,
        "action_count": int(actions_array.shape[0]),
        "action_dim": int(actions_array.shape[1]),
        "response_shape": list(responses_array.shape),
        "action_directions": action_directions,
        "action_magnitudes_m": action_magnitudes,
        "material": material,
        "boundary": boundary,
        "solver_summary": solver,
        "tool_geometry": tool_geometry,
        "smoke_sized_group": int(actions_array.shape[0]) < 12,
    }
    _write_json(group_dir / "group_metadata.json", metadata)
    return {
        "group_id": group.group_id,
        "group_type": "local_response_basis",
        "path": str(group_dir.relative_to(root)),
        "sample_ids": sample_ids,
        "action_count": int(actions_array.shape[0]),
        "state_id": group.state_id,
        "material_id": group.material_id,
        "boundary_id": group.boundary_id,
        "contact_point_id": group.contact_point_id,
        "split": "train",
    }


def write_mode_c_trajectory(root: Path, trajectory: ModeCTrajectoryPlan, sample_dir: Path) -> dict[str, Any]:
    traj_dir = root / "trajectories" / trajectory.trajectory_id
    traj_dir.mkdir(parents=True, exist_ok=True)
    reader = EpisodeTrajectoryReader(sample_dir)
    frames = list(reader.iter_frames())
    if len(frames) < trajectory.num_steps + 1:
        raise ValueError(f"{trajectory.trajectory_id}: not enough logged frames for rollout")
    selected = _select_rollout_frames(frames, trajectory.num_steps)

    states = np.stack([np.asarray(frame.arrays["vertices"], dtype=np.float32) for frame in selected], axis=0)
    responses = states[1:] - states[:-1]
    action_template = np.asarray([*trajectory.contact_point[:2], *trajectory.direction, trajectory.step_size_m], dtype=np.float32)
    actions = np.stack([action_template.copy() for _ in range(trajectory.num_steps)], axis=0)
    fixed_node_mask = np.load(sample_dir / "boundary_mask.npy").astype(bool)
    contact_points = np.stack([_frame_contact_point(frame, trajectory.contact_point) for frame in selected[:-1]], axis=0).astype(np.float32)
    contact_normals = np.tile(np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32), (trajectory.num_steps, 1))
    tool_poses = np.stack([_frame_tool_pose(frame) for frame in selected], axis=0).astype(np.float32)
    contact_distances = np.asarray([float(frame.scalars.get("signed_gap", np.nan)) for frame in selected[:-1]], dtype=np.float32)
    contact_status = np.asarray([bool(frame.scalars.get("contact_active", False)) for frame in selected[:-1]], dtype=bool)

    np.save(traj_dir / "states.npy", states)
    np.save(traj_dir / "actions.npy", actions)
    np.save(traj_dir / "responses.npy", responses)
    np.save(traj_dir / "contact_points.npy", contact_points)
    np.save(traj_dir / "contact_normals.npy", contact_normals)
    np.save(traj_dir / "tool_poses.npy", tool_poses)
    np.save(traj_dir / "fixed_node_mask.npy", fixed_node_mask)
    np.save(traj_dir / "contact_distances.npy", contact_distances)
    np.save(traj_dir / "contact_status.npy", contact_status)

    solver_summary = _load_json(sample_dir / "solver_summary.json")
    solver_status = {
        "source_sample": str(sample_dir.relative_to(root)),
        "solver_summary": solver_summary,
        "per_step_valid": [bool(solver_summary.get("valid", False)) for _ in range(trajectory.num_steps)],
        "source_frame_steps": [int(frame.step_index) for frame in selected],
        "source_frame_progress": [float(frame.scalars.get("progress", 0.0)) for frame in selected],
    }
    _write_json(traj_dir / "solver_status.json", solver_status)

    metadata = {
        "trajectory_id": trajectory.trajectory_id,
        "trajectory_type": "multi_step_rollout",
        "source_sample_id": sample_dir.name,
        "source_sample_path": str(sample_dir.relative_to(root)),
        "state_id": trajectory.state_id,
        "material_id": trajectory.material_id,
        "boundary_id": trajectory.boundary_id,
        "contact_point_id": trajectory.contact_point_id,
        "contact_point_mode": "fixed_material_point",
        "contact_point_initial": [float(v) for v in trajectory.contact_point],
        "action_direction": [float(v) for v in trajectory.direction],
        "step_size_m": float(trajectory.step_size_m),
        "total_displacement_m": float(trajectory.total_displacement_m),
        "num_steps": int(trajectory.num_steps),
        "states_shape": list(states.shape),
        "actions_shape": list(actions.shape),
        "responses_shape": list(responses.shape),
        "tool_poses_shape": list(tool_poses.shape),
        "final_delta_x_max_m": float(np.linalg.norm(states[-1] - states[0], axis=1).max()),
        "source_frame_steps": [int(frame.step_index) for frame in selected],
        "source_frame_progress": [float(frame.scalars.get("progress", 0.0)) for frame in selected],
        "smoke_sized_trajectory": int(trajectory.num_steps) < 10,
    }
    _write_json(traj_dir / "trajectory_metadata.json", metadata)
    return {
        "trajectory_id": trajectory.trajectory_id,
        "trajectory_type": "multi_step_rollout",
        "path": str(traj_dir.relative_to(root)),
        "source_sample_id": sample_dir.name,
        "num_steps": int(trajectory.num_steps),
        "step_size_m": float(trajectory.step_size_m),
        "total_displacement_m": float(trajectory.total_displacement_m),
        "split": "test_rollout",
    }


def write_dataset_metadata(
    plan: NJFDatasetPlan,
    sample_records: list[dict[str, Any]],
    group_records: list[dict[str, Any]] | None = None,
    trajectory_records: list[dict[str, Any]] | None = None,
) -> None:
    root = plan.output_dir
    group_records = group_records or []
    trajectory_records = trajectory_records or []
    metadata = {
        **plan.metadata,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(root),
        "seed": plan.seed,
        "sample_count": len(sample_records),
        "group_count": len(group_records),
        "trajectory_count": len(trajectory_records),
        "modes": plan.modes,
        "samples": sample_records,
        "groups": group_records,
        "trajectories": trajectory_records,
        "geometry": {
            "size_x": plan.geometry.size_x,
            "size_y": plan.geometry.size_y,
            "thickness": plan.geometry.thickness,
            "nx": plan.geometry.nx,
            "ny": plan.geometry.ny,
            "layers": plan.geometry.layers,
        },
        "material": {
            "youngs_modulus": plan.material.youngs_modulus,
            "poisson_ratio": plan.material.poisson_ratio,
            "density": plan.material.density,
            "damping": plan.material.damping,
            "boundary_condition": plan.material.boundary_condition,
        },
        "required_sample_artifacts_mode_a_b_c": [
            "vertices_0", "vertices_1", "displacement", "action", "tool_pose_0", "tool_pose_1",
            "tool_geometry", "contact_summary", "boundary_mask", "fixed_node_indices", "free_node_indices",
            "boundary", "solver_summary",
        ],
        "required_group_artifacts_mode_b": [
            "group_metadata", "state_initial", "fixed_node_mask", "surface_points", "actions",
            "responses", "contact_point", "contact_normal",
        ],
        "required_trajectory_artifacts_mode_c": [
            "trajectory_metadata", "states", "actions", "responses", "contact_points", "contact_normals",
            "tool_poses", "fixed_node_mask", "solver_status",
        ],
    }
    _write_json(root / "metadata.json", metadata)
    splits = {
        "train": {
            "samples": [item["sample_id"] for item in sample_records if item.get("mode") != "rollout_trajectory"],
            "groups": [item["group_id"] for item in group_records],
            "trajectories": [],
        },
        "val": {"samples": [], "groups": [], "trajectories": []},
        "test_unseen_contact": {"samples": [], "groups": [], "trajectories": []},
        "test_unseen_material": {"samples": [], "groups": [], "trajectories": []},
        "test_rollout": {
            "samples": [item["sample_id"] for item in sample_records if item.get("mode") == "rollout_trajectory"],
            "groups": [],
            "trajectories": [item["trajectory_id"] for item in trajectory_records],
        },
    }
    _write_json(root / "splits.json", splits)
    copy_config(plan.config_path, root / "config.yaml")


def copy_config(src: Path, dst: Path) -> None:
    data = yaml.safe_load(src.read_text())
    with dst.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _select_rollout_frames(frames: list[Any], num_steps: int) -> list[Any]:
    targets = np.linspace(0.0, 1.0, num_steps + 1)
    selected = []
    last_index = -1
    for target in targets:
        candidates = [(idx, frame) for idx, frame in enumerate(frames) if idx > last_index]
        if not candidates:
            raise ValueError("Not enough monotonically increasing frames for rollout targets")
        idx, frame = min(candidates, key=lambda item: abs(float(item[1].scalars.get("progress", 0.0)) - float(target)))
        selected.append(frame)
        last_index = idx
    return selected


def _frame_contact_point(frame: Any, fallback: tuple[float, float, float]) -> np.ndarray:
    value = frame.scalars.get("contact_point", fallback)
    return np.asarray(value, dtype=np.float32).reshape(3)


def _frame_tool_pose(frame: Any) -> np.ndarray:
    pose = np.eye(4, dtype=np.float32)
    value = frame.scalars.get("tool_position", [0.0, 0.0, 0.0])
    pose[:3, 3] = np.asarray(value, dtype=np.float32).reshape(3)
    return pose


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
