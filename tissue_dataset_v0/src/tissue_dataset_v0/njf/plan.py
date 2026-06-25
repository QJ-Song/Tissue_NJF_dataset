from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from tissue_dataset_v0.config import default_sample_request
from tissue_dataset_v0.schema import ActionSpec, GeometryConfig, LoggingConfig, MaterialConfig, SampleConfig, SampleRequest

from .schema import ModeAActionPlan, NJFDatasetPlan, PlannedSample


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
    mode_a_actions = tuple(_build_mode_a_actions(data, geometry))

    metadata = {
        "dataset_type": "sofa_njf_dataset_v1",
        "implemented_modes": {"local_perturbation": bool(modes.get("local_perturbation", False)), "response_basis_group": False, "rollout_trajectory": False},
        "mode_status": {
            "local_perturbation": "implemented",
            "response_basis_group": "planned",
            "rollout_trajectory": "planned",
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
        metadata=metadata,
    )


def planned_sample_from_action(plan: NJFDatasetPlan, action_plan: ModeAActionPlan) -> PlannedSample:
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
        action_type="local_perturbation",
        contact_point=action_plan.contact_point,
        extra={
            "njf_mode": "local_perturbation",
            "action_id": action_plan.action_id,
            "delta_a_m": action_plan.magnitude_m,
        },
    )
    extra = dict(plan.backend_extra)
    extra.update(
        {
            "njf_mode": "local_perturbation",
            "state_id": "state_000001",
            "material_id": "material_000001",
            "boundary_id": "boundary_000001",
            "contact_point_id": "contact_000001",
            "action_id": action_plan.action_id,
            "step_id": 0,
            "delta_a_m": action_plan.magnitude_m,
            "action_direction": list(action_plan.direction),
            "contact_point_mode": "fixed_material_point",
        }
    )
    request = replace(
        base,
        config=SampleConfig(
            sample_id=action_plan.sample_id,
            scene_id="sofa_njf_mode_a_v1",
            tissue_type="sofa_tissue",
            simulator="sofa_fem",
            unit="meter",
            notes="SOFA NJF Mode A local perturbation sample",
            extra=extra,
        ),
        geometry=plan.geometry,
        material=plan.material,
        action=action,
        logging=plan.logging,
        enabled_artifacts=plan.enabled_artifacts,
        disabled_artifacts=plan.disabled_artifacts,
    )
    return PlannedSample(request=request, mode="local_perturbation", action_plan=action_plan)


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
    sampling = data.get("sampling", {}) or {}
    magnitudes = sampling.get("local_delta_magnitudes_mm", [0.05, 0.1, 0.2])
    max_depth_m = max(float(v) for v in magnitudes) / 1000.0
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


def _build_mode_a_actions(data: dict[str, Any], geometry: GeometryConfig) -> list[ModeAActionPlan]:
    sampling = data.get("sampling", {}) or {}
    magnitudes_mm = sampling.get("local_delta_magnitudes_mm", [0.05, 0.1, 0.2])
    contact_xy = sampling.get("contact_point_xy", [0.0, 0.0])
    direction = _normalize_direction(sampling.get("action_direction", [0.0, 0.0, -1.0]))
    contact_point = (float(contact_xy[0]), float(contact_xy[1]), float(geometry.thickness * 0.5))
    sample_start = int((data.get("dataset", {}) or {}).get("sample_id_start", 1))
    actions: list[ModeAActionPlan] = []
    for index, magnitude_mm in enumerate(magnitudes_mm):
        actions.append(
            ModeAActionPlan(
                action_id=f"action_{index + 1:06d}",
                direction=direction,
                magnitude_m=float(magnitude_mm) / 1000.0,
                contact_point=contact_point,
                sample_id=sample_start + index,
            )
        )
    return actions


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
