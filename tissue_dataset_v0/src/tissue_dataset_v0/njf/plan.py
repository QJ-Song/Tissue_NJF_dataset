from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from tissue_dataset_v0.config import default_sample_request
from tissue_dataset_v0.schema import ActionSpec, GeometryConfig, LoggingConfig, MaterialConfig, SampleConfig

from .schema import ModeAActionPlan, ModeBGroupPlan, ModeCTrajectoryPlan, NJFDatasetPlan, PlannedSample

STATE_ID = "state_000001"
MATERIAL_ID = "material_000001"
BOUNDARY_ID = "boundary_000001"
CONTACT_POINT_ID = "contact_000001"


def load_njf_plan(path: Path, *, output_override: Path | None = None) -> NJFDatasetPlan:
    path = Path(path)
    data = _load_yaml(path)
    dataset = data.get("dataset", {})
    modes = dict(dataset.get("modes", {}) or {})
    modes.setdefault("local_perturbation", True)
    modes.setdefault("response_basis_group", False)
    modes.setdefault("rollout_trajectory", False)

    output_dir = Path(output_override or dataset.get("output_root", dataset.get("output_dir", "../outputs/sofa_njf_dataset")))
    if not output_dir.is_absolute():
        output_dir = path.parent / output_dir

    geometry = _build_geometry(data.get("tissue", data.get("geometry", {})))
    material = _build_material(data.get("material", data.get("material_sampler", {})))
    logging = _build_logging(data.get("logging", {}))
    backend_extra = _build_backend_extra(data, geometry)
    artifacts = data.get("artifacts", {}) or {}
    enabled = artifacts.get("include")
    disabled = artifacts.get("exclude", ()) or ()
    seed = int(dataset.get("random_seed", dataset.get("seed", 0)))
    sample_start = int(dataset.get("sample_id_start", 1))
    mode_a_actions = tuple(_build_mode_a_actions(data, geometry, sample_start=sample_start))
    mode_b_start = int(dataset.get("basis_sample_id_start", sample_start + len(mode_a_actions)))
    mode_b_groups = tuple(_build_mode_b_groups(data, geometry, sample_start=mode_b_start))
    mode_b_sample_count = sum(len(group.actions) for group in mode_b_groups)
    mode_c_start = int(dataset.get("rollout_sample_id_start", mode_b_start + mode_b_sample_count))
    mode_c_trajectories = tuple(_build_mode_c_trajectories(data, geometry, sample_start=mode_c_start))

    metadata = {
        "dataset_type": "sofa_njf_dataset_v1",
        "implemented_modes": {
            "local_perturbation": bool(modes.get("local_perturbation", False)),
            "response_basis_group": bool(modes.get("response_basis_group", False)),
            "rollout_trajectory": bool(modes.get("rollout_trajectory", False)),
        },
        "mode_status": {
            "local_perturbation": "implemented",
            "response_basis_group": "implemented",
            "rollout_trajectory": "implemented",
        },
        "source_config": str(path),
    }
    return NJFDatasetPlan(
        config_path=path,
        output_dir=output_dir,
        seed=seed,
        modes=modes,
        geometry=geometry,
        material=material,
        logging=logging,
        backend_extra=backend_extra,
        enabled_artifacts=tuple(enabled) if enabled is not None else None,
        disabled_artifacts=tuple(disabled),
        mode_a_actions=mode_a_actions,
        mode_b_groups=mode_b_groups,
        mode_c_trajectories=mode_c_trajectories,
        metadata=metadata,
    )


def planned_sample_from_action(
    plan: NJFDatasetPlan,
    action_plan: ModeAActionPlan,
    *,
    mode: str = "local_perturbation",
    group_id: str | None = None,
    trajectory_id: str | None = None,
    extra_updates: dict[str, Any] | None = None,
) -> PlannedSample:
    base = default_sample_request(sample_id=action_plan.sample_id)
    action = ActionSpec(
        vector=(
            float(action_plan.contact_point[0]),
            float(action_plan.contact_point[1]),
            float(action_plan.direction[0]),
            float(action_plan.direction[1]),
            float(action_plan.direction[2]),
            float(action_plan.magnitude_m),
        ),
        action_type=mode,
        contact_point=action_plan.contact_point,
        extra={
            "njf_mode": mode,
            "group_id": group_id,
            "trajectory_id": trajectory_id,
            "action_id": action_plan.action_id,
            "delta_a_m": action_plan.magnitude_m,
        },
    )
    extra = dict(plan.backend_extra)
    extra.update(
        {
            "njf_mode": mode,
            "group_id": group_id,
            "trajectory_id": trajectory_id,
            "state_id": STATE_ID,
            "material_id": MATERIAL_ID,
            "boundary_id": BOUNDARY_ID,
            "contact_point_id": CONTACT_POINT_ID,
            "action_id": action_plan.action_id,
            "step_id": 0,
            "delta_a_m": action_plan.magnitude_m,
            "action_direction": list(action_plan.direction),
            "contact_point_mode": "fixed_material_point",
        }
    )
    if extra_updates:
        extra.update(extra_updates)
    request = replace(
        base,
        config=SampleConfig(
            sample_id=action_plan.sample_id,
            scene_id=f"sofa_njf_{mode}_v1",
            tissue_type="sofa_tissue",
            simulator="sofa_fem",
            unit="meter",
            notes=f"SOFA NJF {mode} sample",
            extra=extra,
        ),
        geometry=plan.geometry,
        material=plan.material,
        action=action,
        logging=plan.logging,
        enabled_artifacts=plan.enabled_artifacts,
        disabled_artifacts=plan.disabled_artifacts,
    )
    return PlannedSample(request=request, mode=mode, action_plan=action_plan, group_id=group_id, trajectory_id=trajectory_id)


def planned_sample_from_trajectory(plan: NJFDatasetPlan, trajectory: ModeCTrajectoryPlan) -> PlannedSample:
    action_plan = ModeAActionPlan(
        action_id=f"{trajectory.trajectory_id}_total_action",
        direction=trajectory.direction,
        magnitude_m=trajectory.total_displacement_m,
        contact_point=trajectory.contact_point,
        sample_id=trajectory.sample_id,
    )
    extra_updates = {
        "rollout_step_size_m": trajectory.step_size_m,
        "rollout_total_displacement_m": trajectory.total_displacement_m,
        "rollout_num_steps": trajectory.num_steps,
        "sofa_total_steps": trajectory.num_steps * trajectory.sofa_steps_per_rollout_step,
        "sofa_rollout_steps_per_step": trajectory.sofa_steps_per_rollout_step,
    }
    return planned_sample_from_action(
        plan,
        action_plan,
        mode="rollout_trajectory",
        trajectory_id=trajectory.trajectory_id,
        extra_updates=extra_updates,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _build_geometry(cfg: dict[str, Any]) -> GeometryConfig:
    size = cfg.get("size", None)
    if isinstance(size, (list, tuple)) and len(size) == 3:
        size_x, size_y, thickness = size
    else:
        size_x = cfg.get("size_x", 0.12)
        size_y = cfg.get("size_y", 0.085)
        thickness = cfg.get("thickness", 0.018)
    grid = cfg.get("grid", None)
    if isinstance(grid, (list, tuple)) and len(grid) == 3:
        nx, ny, layers = int(grid[0]), int(grid[1]), int(grid[2])
        nx = max(nx - 1, 1)
        ny = max(ny - 1, 1)
    else:
        nx = int(cfg.get("nx", 8))
        ny = int(cfg.get("ny", 6))
        layers = int(cfg.get("layers", 4))
    return GeometryConfig(
        size_x=float(size_x),
        size_y=float(size_y),
        thickness=float(thickness),
        nx=nx,
        ny=ny,
        layers=int(layers),
        fixed_border_ratio=float(cfg.get("fixed_border_ratio", 0.12)),
    )


def _build_material(cfg: dict[str, Any]) -> MaterialConfig:
    young = cfg.get("young_modulus", cfg.get("youngs_modulus", 5000.0))
    if isinstance(young, (list, tuple)):
        young = young[0]
    poisson = cfg.get("poisson_ratio", 0.45)
    if isinstance(poisson, (list, tuple)):
        poisson = poisson[0]
    damping = cfg.get("damping", 0.5)
    if isinstance(damping, (list, tuple)):
        damping = damping[0]
    density = cfg.get("density", 1000.0)
    if isinstance(density, str):
        density = 1000.0
    return MaterialConfig(
        youngs_modulus=float(young),
        poisson_ratio=float(poisson),
        density=float(density),
        damping=float(damping),
        boundary_condition=str(cfg.get("boundary_condition", "bottom_fixed")),
    )


def _build_logging(cfg: dict[str, Any]) -> LoggingConfig:
    return LoggingConfig(
        enabled=bool(cfg.get("enabled", True)),
        log_dir_name=str(cfg.get("log_dir_name", "logs")),
        log_every_n=int(cfg.get("log_every_n", 10)),
        save_vertices=bool(cfg.get("save_vertices", True)),
        save_tool_pose=bool(cfg.get("save_tool_pose", True)),
        save_events=bool(cfg.get("save_events", True)),
        save_request=bool(cfg.get("save_request", True)),
    )


def _build_backend_extra(data: dict[str, Any], geometry: GeometryConfig) -> dict[str, Any]:
    backend = data.get("backend", {}) or {}
    extra = dict(backend.get("extra", {}) or {})
    tissue = data.get("tissue", {}) or {}
    tool = data.get("tool", {}) or {}
    contact = data.get("contact", {}) or {}
    solver = data.get("solver", {}) or {}
    extra.setdefault("sofa_tissue_shape", str(tissue.get("shape", tissue.get("geometry_type", "liver_like"))))
    extra.setdefault("sofa_interaction_model", "probe_contact")
    extra.setdefault("sofa_total_steps", int(solver.get("settling_steps", 80)))
    extra.setdefault("sofa_dt", float(solver.get("dt", 0.005)))
    radius_mm = float(tool.get("radius_mm", 10.0))
    extra.setdefault("sofa_probe_radius", radius_mm / 1000.0)
    extra.setdefault("sofa_probe_clearance", float(tool.get("clearance_mm", 0.0)) / 1000.0)
    max_depth_m = _max_configured_magnitude_m(data)
    extra.setdefault("sofa_probe_contact_max_depth", max_depth_m)
    extra.setdefault("sofa_probe_contact_distance", float(contact.get("contact_distance_mm", 2.0)) / 1000.0)
    extra.setdefault("sofa_probe_alarm_distance", float(contact.get("alarm_distance_mm", 6.0)) / 1000.0)
    extra.setdefault("sofa_record_tool_motion", True)
    extra.setdefault("sofa_record_contact_summary", True)
    extra.setdefault("sofa_record_boundary_solver", True)
    extra.setdefault("sofa_constraint_solver_tolerance", float(solver.get("constraint_solver_tolerance", 1e-6)))
    extra.setdefault("sofa_constraint_solver_max_iterations", int(solver.get("constraint_solver_max_iterations", 100)))
    extra.setdefault("sofa_solver_tolerance", float(solver.get("linear_solver_tolerance", 1e-9)))
    extra.setdefault("sofa_solver_threshold", float(solver.get("linear_solver_threshold", 1e-9)))
    return extra


def _max_configured_magnitude_m(data: dict[str, Any]) -> float:
    sampling = data.get("sampling", {}) or {}
    values: list[float] = [float(v) for v in sampling.get("local_delta_magnitudes_mm", [0.05, 0.1, 0.2])]
    basis = sampling.get("response_basis", {}) or {}
    values.extend(float(v) for v in basis.get("local_delta_magnitudes_mm", []))
    rollout = sampling.get("rollout", {}) or {}
    if rollout:
        if "total_displacement_mm" in rollout:
            values.append(float(rollout["total_displacement_mm"]))
        if "total_displacements_mm" in rollout:
            values.extend(float(v) for v in rollout["total_displacements_mm"])
        if "step_size_mm" in rollout and "num_steps" in rollout:
            values.append(float(rollout["step_size_mm"]) * int(rollout["num_steps"]))
    return max(values) / 1000.0


def _build_mode_a_actions(data: dict[str, Any], geometry: GeometryConfig, *, sample_start: int) -> list[ModeAActionPlan]:
    sampling = data.get("sampling", {}) or {}
    magnitudes_mm = sampling.get("local_delta_magnitudes_mm", [0.05, 0.1, 0.2])
    contact_xy = sampling.get("contact_point_xy", [0.0, 0.0])
    direction = _normalize_direction(sampling.get("action_direction", [0.0, 0.0, -1.0]))
    contact_point = _contact_point_from_xy(contact_xy, geometry)
    actions: list[ModeAActionPlan] = []
    for index, magnitude_mm in enumerate(magnitudes_mm):
        actions.append(
            ModeAActionPlan(
                action_id=f"mode_a_action_{index + 1:06d}",
                direction=direction,
                magnitude_m=float(magnitude_mm) / 1000.0,
                contact_point=contact_point,
                sample_id=sample_start + index,
            )
        )
    return actions


def _build_mode_b_groups(data: dict[str, Any], geometry: GeometryConfig, *, sample_start: int) -> list[ModeBGroupPlan]:
    sampling = data.get("sampling", {}) or {}
    basis = sampling.get("response_basis", {}) or {}
    contact_xy = basis.get("contact_point_xy", sampling.get("contact_point_xy", [0.0, 0.0]))
    contact_point = _contact_point_from_xy(contact_xy, geometry)
    directions = basis.get(
        "action_directions",
        [
            [0.0, 0.0, -1.0],
            [0.0872, 0.0, -0.9962],
            [0.0, 0.0872, -0.9962],
        ],
    )
    magnitudes_mm = basis.get("local_delta_magnitudes_mm", [0.1])
    group_id = str(basis.get("group_id", "group_000001"))
    actions: list[ModeAActionPlan] = []
    index = 0
    for direction_value in directions:
        direction = _normalize_direction(direction_value)
        for magnitude_mm in magnitudes_mm:
            actions.append(
                ModeAActionPlan(
                    action_id=f"{group_id}_action_{index + 1:06d}",
                    direction=direction,
                    magnitude_m=float(magnitude_mm) / 1000.0,
                    contact_point=contact_point,
                    sample_id=sample_start + index,
                )
            )
            index += 1
    return [
        ModeBGroupPlan(
            group_id=group_id,
            state_id=STATE_ID,
            material_id=MATERIAL_ID,
            boundary_id=BOUNDARY_ID,
            contact_point_id=CONTACT_POINT_ID,
            contact_point=contact_point,
            actions=tuple(actions),
        )
    ]


def _build_mode_c_trajectories(data: dict[str, Any], geometry: GeometryConfig, *, sample_start: int) -> list[ModeCTrajectoryPlan]:
    sampling = data.get("sampling", {}) or {}
    rollout = sampling.get("rollout", {}) or {}
    contact_xy = rollout.get("contact_point_xy", sampling.get("contact_point_xy", [0.0, 0.0]))
    contact_point = _contact_point_from_xy(contact_xy, geometry)
    direction = _normalize_direction(rollout.get("action_direction", sampling.get("action_direction", [0.0, 0.0, -1.0])))
    step_size_mm = float(rollout.get("step_size_mm", 0.1))
    num_steps = int(rollout.get("num_steps", 3))
    if num_steps <= 0:
        raise ValueError("rollout.num_steps must be positive")
    total_mm = float(rollout.get("total_displacement_mm", step_size_mm * num_steps))
    steps_per_rollout_step = int(rollout.get("sofa_steps_per_rollout_step", 30))
    return [
        ModeCTrajectoryPlan(
            trajectory_id=str(rollout.get("trajectory_id", "traj_000001")),
            state_id=STATE_ID,
            material_id=MATERIAL_ID,
            boundary_id=BOUNDARY_ID,
            contact_point_id=CONTACT_POINT_ID,
            contact_point=contact_point,
            direction=direction,
            step_size_m=step_size_mm / 1000.0,
            total_displacement_m=total_mm / 1000.0,
            num_steps=num_steps,
            sample_id=sample_start,
            sofa_steps_per_rollout_step=steps_per_rollout_step,
        )
    ]


def _contact_point_from_xy(contact_xy: Any, geometry: GeometryConfig) -> tuple[float, float, float]:
    return (float(contact_xy[0]), float(contact_xy[1]), float(geometry.thickness * 0.5))


def _normalize_direction(value: Any) -> tuple[float, float, float]:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3,):
        raise ValueError(f"Expected action_direction [x, y, z], got: {value}")
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-12:
        raise ValueError("action_direction must be non-zero")
    arr = arr / norm
    if arr[2] >= 0.0:
        raise ValueError(f"action_direction must point downward for current probe_contact mode, got {arr.tolist()}")
    return (float(arr[0]), float(arr[1]), float(arr[2]))
