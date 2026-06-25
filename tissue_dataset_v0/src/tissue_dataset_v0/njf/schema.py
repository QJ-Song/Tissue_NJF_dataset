from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tissue_dataset_v0.schema import ActionSpec, GeometryConfig, LoggingConfig, MaterialConfig, SampleRequest


@dataclass(frozen=True)
class ModeAActionPlan:
    action_id: str
    direction: tuple[float, float, float]
    magnitude_m: float
    contact_point: tuple[float, float, float]
    sample_id: int


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
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannedSample:
    request: SampleRequest
    mode: str
    action_plan: ModeAActionPlan
