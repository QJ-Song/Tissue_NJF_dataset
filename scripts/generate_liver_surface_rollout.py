#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TISSUE_SRC = ROOT / "tissue_dataset_v0" / "src"
for path in (ROOT, SCRIPTS, TISSUE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generate_liver_surface_sample import (  # noqa: E402
    contact_observation,
    configure_probe_path,
    contact_point_specs,
    dataset_direction_to_sofa,
    direction_specs,
    load_calibration,
    load_sofa,
    material_payload,
    material_specs,
    pose_from_translation,
    probe_approach_direction,
    surface_boundary_payload,
    to_dataset_meters,
    write_json_file,
)
from scenes.liver_surface_collision import (  # noqa: E402
    LiverSurfaceCollisionConfig,
    create_liver_surface_collision_scene,
    object_positions,
    set_probe_position,
)


DEFAULT_OUTPUT = ROOT / "tissue_dataset_v0" / "outputs" / "liver_surface_mode_c_rollout_smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Mode C rollout trajectories from the official-liver surface-collision scene."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trajectory-id", type=int, default=1)
    parser.add_argument("--contact-set", choices=("top_center", "top_three"), default="top_center")
    parser.add_argument("--material-set", choices=("single", "young_three"), default="single")
    parser.add_argument("--direction-set", choices=("vertical", "basis_smoke", "basis_v1", "basis_v2"), default="vertical")
    parser.add_argument("--direction-id", default="normal", help="Direction id selected from --direction-set.")
    parser.add_argument("--step-size-mm", type=float, default=1.17)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--target-long-axis-mm", type=float, default=150.0)
    parser.add_argument("--probe-radius-mm", type=float, default=10.0)
    parser.add_argument("--probe-clearance-mm", type=float, default=0.0)
    parser.add_argument("--contact-distance-mm", type=float, default=0.1)
    parser.add_argument("--contact-observation-distance-mm", type=float, default=1.2)
    parser.add_argument("--alarm-distance-mm", type=float, default=12.0)
    parser.add_argument("--preload-steps", type=int, default=0)
    parser.add_argument("--action-substeps", type=int, default=40)
    parser.add_argument("--settle-steps-per-step", type=int, default=20)
    parser.add_argument("--dt", type=float, default=0.005)
    parser.add_argument("--young-modulus", type=float, default=3000.0)
    parser.add_argument("--poisson-ratio", type=float, default=0.3)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.step_size_mm <= 0.0:
        raise ValueError("--step-size-mm must be positive")
    if args.steps <= 0:
        raise ValueError("--steps must be positive")
    if args.action_substeps <= 0:
        raise ValueError("--action-substeps must be positive")
    if args.target_long_axis_mm <= 0.0:
        raise ValueError("--target-long-axis-mm must be positive")

    Sofa, _ = load_sofa()
    calibration, mesh_info, surface_vertices_scene = load_calibration(Sofa, args)
    directions = dict(direction_specs(args.direction_set))
    if args.direction_id not in directions:
        available = ", ".join(sorted(directions))
        raise ValueError(f"Unknown --direction-id {args.direction_id!r}; available: {available}")
    direction_dataset = directions[args.direction_id]
    contacts = contact_point_specs(surface_vertices_scene, args.contact_set)
    materials = material_specs(args.material_set, args.young_modulus, args.poisson_ratio)

    prepare_output(args.output, overwrite=args.overwrite)
    trajectory_records: list[dict[str, Any]] = []
    trajectory_index = int(args.trajectory_id)
    for contact_id, contact_point_scene in contacts:
        for material_id, young_modulus, poisson_ratio in materials:
            traj_id = f"traj_{trajectory_index:06d}"
            traj_dir = args.output / "trajectories" / traj_id
            summary = generate_one_trajectory(
                Sofa=Sofa,
                args=args,
                traj_dir=traj_dir,
                traj_id=traj_id,
                direction_dataset=direction_dataset,
                calibration=calibration,
                contact_id=contact_id,
                contact_point_scene=contact_point_scene,
                material_id=material_id,
                young_modulus=young_modulus,
                poisson_ratio=poisson_ratio,
            )
            trajectory_records.append(summary)
            print(f"Generated liver surface rollout: {traj_dir}")
            print(f"  contact: {contact_id}")
            print(f"  material: {material_id} E={young_modulus:.1f} nu={poisson_ratio:.3f}")
            print(f"  direction: {args.direction_id} {direction_dataset.tolist()}")
            print(f"  steps: {args.steps} step_size={args.step_size_mm:.3f} mm")
            print(f"  final max deformation: {summary['final_delta_node_max_m'] * 1000.0:.3f} mm")
            print(f"  contact active: {summary['contact_active_steps']}/{args.steps}")
            trajectory_index += 1

    write_dataset_metadata(args.output, args, calibration, mesh_info, trajectory_records)
    return 0


def generate_one_trajectory(
    *,
    Sofa: Any,
    args: argparse.Namespace,
    traj_dir: Path,
    traj_id: str,
    direction_dataset: np.ndarray,
    calibration: dict[str, Any],
    contact_id: str,
    contact_point_scene: np.ndarray,
    material_id: str,
    young_modulus: float,
    poisson_ratio: float,
) -> dict[str, Any]:
    scene_units_per_mm = float(calibration["scene_units_per_mm"])
    meters_per_scene_unit = float(calibration["mm_per_scene_unit"]) / 1000.0
    step_size_scene = float(args.step_size_mm) * scene_units_per_mm
    total_depth_scene = step_size_scene * int(args.steps)
    approach_direction_dataset = probe_approach_direction(args.direction_set, args.direction_id, direction_dataset)
    direction_sofa = dataset_direction_to_sofa(direction_dataset)
    approach_direction_sofa = dataset_direction_to_sofa(approach_direction_dataset)

    cfg = LiverSurfaceCollisionConfig(
        dt=args.dt,
        young_modulus=float(young_modulus),
        poisson_ratio=float(poisson_ratio),
        probe_radius=float(args.probe_radius_mm) * scene_units_per_mm,
        probe_clearance=float(args.probe_clearance_mm) * scene_units_per_mm,
        probe_depth=total_depth_scene,
        probe_direction=tuple(approach_direction_sofa.tolist()),
        contact_point=tuple(np.asarray(contact_point_scene, dtype=np.float64).tolist()),
        alarm_distance=float(args.alarm_distance_mm) * scene_units_per_mm,
        contact_distance=float(args.contact_distance_mm) * scene_units_per_mm,
    )
    root = Sofa.Core.Node("root")
    handles = create_liver_surface_collision_scene(root, cfg)
    configure_probe_path(handles, cfg, direction_dataset, approach_direction_dataset)
    Sofa.Simulation.initRoot(root)
    set_probe_position(handles.probe_dofs, handles.probe_start)
    for _ in range(max(int(args.preload_steps), 0)):
        Sofa.Simulation.animate(root, root.dt.value)

    traj_dir.mkdir(parents=True, exist_ok=True)
    states_scene = [object_positions(handles.surface_dofs)]
    probe_positions_scene = [handles.probe_start.copy()]
    contact_observations: list[dict[str, Any]] = []
    per_step_valid: list[bool] = []

    current_probe = handles.probe_start.copy()
    for step_index in range(int(args.steps)):
        next_probe = handles.probe_start + direction_sofa * step_size_scene * float(step_index + 1)
        for substep in range(1, int(args.action_substeps) + 1):
            alpha = substep / float(args.action_substeps)
            probe = current_probe + alpha * (next_probe - current_probe)
            set_probe_position(handles.probe_dofs, probe)
            Sofa.Simulation.animate(root, root.dt.value)
        set_probe_position(handles.probe_dofs, next_probe)
        for _ in range(max(int(args.settle_steps_per_step), 0)):
            Sofa.Simulation.animate(root, root.dt.value)
        surface_scene = object_positions(handles.surface_dofs)
        observation = contact_observation(
            surface_scene,
            next_probe,
            cfg,
            meters_per_scene_unit,
            args.contact_observation_distance_mm,
            step_index + 1,
            float(step_index + 1) * (args.action_substeps + args.settle_steps_per_step) * cfg.dt,
        )
        states_scene.append(surface_scene)
        probe_positions_scene.append(next_probe.copy())
        contact_observations.append(observation)
        per_step_valid.append(bool(np.isfinite(surface_scene).all()))
        current_probe = next_probe

    states = to_dataset_meters(np.stack(states_scene, axis=0), meters_per_scene_unit).astype(np.float32)
    responses = (states[1:] - states[:-1]).astype(np.float32)
    contact_point_dataset = to_dataset_meters(handles.contact_point[None, :], meters_per_scene_unit)[0]
    actions = np.tile(
        np.asarray(
            [
                float(contact_point_dataset[0]),
                float(contact_point_dataset[1]),
                float(direction_dataset[0]),
                float(direction_dataset[1]),
                float(direction_dataset[2]),
                float(args.step_size_mm / 1000.0),
            ],
            dtype=np.float64,
        ),
        (int(args.steps), 1),
    )
    contact_points = np.tile(contact_point_dataset.astype(np.float64), (int(args.steps), 1))
    contact_normals = np.tile(np.asarray([0.0, 0.0, 1.0], dtype=np.float64), (int(args.steps), 1))
    probe_positions = to_dataset_meters(np.stack(probe_positions_scene, axis=0), meters_per_scene_unit)
    tool_poses = np.stack([pose_from_translation(position) for position in probe_positions], axis=0)
    boundary_payload = surface_boundary_payload(states[0])
    contact_status = np.asarray([bool(item["contact_active"]) for item in contact_observations], dtype=bool)
    contact_distances = np.asarray([float(item["signed_gap"]) for item in contact_observations], dtype=np.float64)
    final_delta = states[-1] - states[0]
    final_delta_node_max = float(np.linalg.norm(final_delta, axis=1).max())
    response_node_max = float(np.linalg.norm(responses, axis=2).max()) if responses.size else 0.0
    contact_active_steps = int(np.count_nonzero(contact_status))

    np.save(traj_dir / "states.npy", states)
    np.save(traj_dir / "actions.npy", actions.astype(np.float32))
    np.save(traj_dir / "responses.npy", responses)
    np.save(traj_dir / "contact_points.npy", contact_points.astype(np.float32))
    np.save(traj_dir / "contact_normals.npy", contact_normals.astype(np.float32))
    np.save(traj_dir / "tool_poses.npy", tool_poses.astype(np.float32))
    np.save(traj_dir / "fixed_node_mask.npy", boundary_payload["boundary_mask"])
    np.save(traj_dir / "contact_status.npy", contact_status)
    np.save(traj_dir / "contact_distances.npy", contact_distances.astype(np.float32))

    metadata = {
        "trajectory_id": traj_id,
        "trajectory_type": "surface_collision_bridge_rollout",
        "mode": "rollout_trajectory",
        "state_id": "state_official_liver_000001",
        "material_id": material_id,
        "boundary_id": "boundary_official_liver_volume_fixed_indices",
        "contact_point_id": contact_id,
        "contact_point_mode": "fixed_material_point",
        "contact_point_world": [float(v) for v in contact_point_dataset.tolist()],
        "contact_normal": [0.0, 0.0, 1.0],
        "direction_id": args.direction_id,
        "action_direction": [float(v) for v in direction_dataset.tolist()],
        "approach_direction": [float(v) for v in approach_direction_dataset.tolist()],
        "probe_approach_policy": "normal_approach_for_basis_v2" if args.direction_set == "basis_v2" else "action_aligned_approach",
        "step_size_m": float(args.step_size_mm / 1000.0),
        "step_size_mm": float(args.step_size_mm),
        "step_count": int(args.steps),
        "total_displacement_m": float(args.step_size_mm * args.steps / 1000.0),
        "total_displacement_mm": float(args.step_size_mm * args.steps),
        "states_shape": list(states.shape),
        "actions_shape": list(actions.shape),
        "responses_shape": list(responses.shape),
        "tool_poses_shape": list(tool_poses.shape),
        "material": material_payload(args, material_id=material_id, young_modulus=young_modulus, poisson_ratio=poisson_ratio),
        "boundary": boundary_payload["boundary"],
        "tool_geometry": {
            "type": "sphere",
            "radius": float(cfg.probe_radius * meters_per_scene_unit),
            "unit": "meter",
            "frame": "tool_pose_center",
            "source": "official_liver_surface_collision",
        },
        "solver_config": rollout_solver_config(args, cfg),
        "calibration": calibration,
        "coordinate_transform": "dataset_xyz = sofa_xzy; dataset_z is SOFA y",
        "source_scene": "scenes/liver_surface_collision.py",
        "smoke_sized_trajectory": int(args.steps) < 10,
    }
    solver_status = {
        "trajectory_id": traj_id,
        "source_sample": None,
        "solver_status_method": "finite_state_check_only",
        "per_step_valid": per_step_valid,
        "valid": bool(all(per_step_valid) and np.isfinite(responses).all()),
        "finite": bool(np.isfinite(states).all() and np.isfinite(responses).all()),
        "nan_or_inf_detected": bool(not (np.isfinite(states).all() and np.isfinite(responses).all())),
        "dt": float(cfg.dt),
        "action_substeps": int(args.action_substeps),
        "settle_steps_per_step": int(args.settle_steps_per_step),
        "preload_steps": int(args.preload_steps),
        "contact_active_steps": contact_active_steps,
        "contact_distance_min_m": float(np.min(contact_distances)) if contact_distances.size else None,
        "contact_distance_max_m": float(np.max(contact_distances)) if contact_distances.size else None,
        "final_delta_node_max_m": final_delta_node_max,
        "response_node_max_m": response_node_max,
    }
    write_json_file(traj_dir / "trajectory_metadata.json", metadata)
    write_json_file(traj_dir / "solver_status.json", solver_status)
    Sofa.Simulation.unload(root)
    return {
        "trajectory_id": traj_id,
        "path": str(traj_dir.relative_to(args.output)),
        "contact_point_id": contact_id,
        "material_id": material_id,
        "step_count": int(args.steps),
        "step_size_mm": float(args.step_size_mm),
        "total_displacement_mm": float(args.step_size_mm * args.steps),
        "final_delta_node_max_m": final_delta_node_max,
        "response_node_max_m": response_node_max,
        "contact_active_steps": contact_active_steps,
    }


def rollout_solver_config(args: argparse.Namespace, cfg: LiverSurfaceCollisionConfig) -> dict[str, Any]:
    return {
        "dt": float(cfg.dt),
        "ode_solver": "EulerImplicitSolver",
        "solver_type": "EulerImplicitSolver",
        "linear_solver": "CGLinearSolver",
        "linear_solver_type": "CGLinearSolver",
        "constraint_solver": "GenericConstraintSolver",
        "constraint_solver_type": "GenericConstraintSolver",
        "contact_pipeline": "surface_triangle_line_point_collision",
        "action_substeps": int(args.action_substeps),
        "settle_steps_per_step": int(args.settle_steps_per_step),
        "preload_steps": int(args.preload_steps),
        "contact_distance_mm": float(args.contact_distance_mm),
        "contact_observation_distance_mm": float(args.contact_observation_distance_mm),
        "alarm_distance_mm": float(args.alarm_distance_mm),
    }


def prepare_output(output: Path, *, overwrite: bool) -> None:
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output}. Use --overwrite to regenerate.")
        shutil.rmtree(output)
    (output / "trajectories").mkdir(parents=True, exist_ok=True)


def write_dataset_metadata(
    output: Path,
    args: argparse.Namespace,
    calibration: dict[str, Any],
    mesh_info: dict[str, str],
    trajectories: list[dict[str, Any]],
) -> None:
    payload = {
        "dataset_type": "surface_collision_rollout_bridge",
        "scene_id": "official_liver_surface_collision_v0",
        "source_scene": "scenes/liver_surface_collision.py",
        "generator": "scripts/generate_liver_surface_rollout.py",
        "trajectory_count": len(trajectories),
        "sample_count": 0,
        "group_count": 0,
        "modes": {"rollout_trajectory": True, "local_perturbation": False, "response_basis_group": False},
        "contact_set": args.contact_set,
        "material_set": args.material_set,
        "direction_set": args.direction_set,
        "direction_id": args.direction_id,
        "probe_approach_policy": "normal_approach_for_basis_v2" if args.direction_set == "basis_v2" else "action_aligned_approach",
        "step_size_mm": float(args.step_size_mm),
        "steps": int(args.steps),
        "target_long_axis_mm": float(args.target_long_axis_mm),
        "coordinate_transform": "dataset_xyz = sofa_xzy; dataset_z is SOFA y",
        "unit": "meter",
        "probe_radius_mm": float(args.probe_radius_mm),
        "probe_clearance_mm": float(args.probe_clearance_mm),
        "contact_distance_mm": float(args.contact_distance_mm),
        "contact_observation_distance_mm": float(args.contact_observation_distance_mm),
        "alarm_distance_mm": float(args.alarm_distance_mm),
        "preload_steps": int(args.preload_steps),
        "action_substeps": int(args.action_substeps),
        "settle_steps_per_step": int(args.settle_steps_per_step),
        "young_modulus": float(args.young_modulus),
        "poisson_ratio": float(args.poisson_ratio),
        "calibration": calibration,
        "mesh": mesh_info,
        "trajectories": trajectories,
    }
    write_json_file(output / "dataset_metadata.json", payload)
    write_json_file(output / "metadata.json", payload)


if __name__ == "__main__":
    raise SystemExit(main())
