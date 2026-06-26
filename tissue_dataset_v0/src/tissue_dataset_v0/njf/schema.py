from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tissue_dataset_v0.schema import GeometryConfig, LoggingConfig, MaterialConfig, SampleRequest


@dataclass(frozen=True)
class ModeAActionPlan:
    action_id: str
    direction: tuple[float, float, float]
    magnitude_m: float
    contact_point: tuple[float, float, float]
    sample_id: int


@dataclass(frozen=True)
class ModeBGroupPlan:
    group_id: str
    state_id: str
    material_id: str
    boundary_id: str
    contact_point_id: str
    contact_point: tuple[float, float, float]
    material: MaterialConfig
    actions: tuple[ModeAActionPlan, ...]


@dataclass(frozen=True)
class ModeCTrajectoryPlan:
    trajectory_id: str
    state_id: str
    material_id: str
    boundary_id: str
    contact_point_id: str
    contact_point: tuple[float, float, float]
    direction: tuple[float, float, float]
    step_size_m: float
    total_displacement_m: float
    num_steps: int
    sample_id: int
    sofa_steps_per_rollout_step: int


@dataclass(frozen=True)
class NJFDatasetPlan:
    config_path: Path
    output_dir: Path
    seed: int
    modes: dict[str, bool]
    geometry: GeometryConfig
    material: MaterialConfig
    logging: LoggingConfig
    backend_extra: dict[str, Any]
    enabled_artifacts: tuple[str, ...] | None
    disabled_artifacts: tuple[str, ...]
    mode_a_actions: tuple[ModeAActionPlan, ...]
    mode_b_groups: tuple[ModeBGroupPlan, ...]
    mode_c_trajectories: tuple[ModeCTrajectoryPlan, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannedSample:
    request: SampleRequest
    mode: str
    action_plan: ModeAActionPlan
    group_id: str | None = None
    trajectory_id: str | None = None
