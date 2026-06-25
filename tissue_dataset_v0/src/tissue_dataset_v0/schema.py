from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class MaterialConfig:
    youngs_modulus: float = 10_000.0
    poisson_ratio: float = 0.45
    density: float = 1000.0
    damping: float = 0.5
    boundary_condition: str = "bottom_fixed"
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeometryConfig:
    size_x: float = 0.10
    size_y: float = 0.10
    thickness: float = 0.01
    nx: int = 24
    ny: int = 24
    layers: int = 2
    fixed_border_ratio: float = 0.12


@dataclass(frozen=True)
class ActionSpec:
    """Compact action vector for action->deformation experiments."""

    vector: Sequence[float]
    action_type: str = "vertical_press"
    contact_point: Sequence[float] | None = None
    tool_pose_0: Sequence[Sequence[float]] | None = None
    tool_pose_1: Sequence[Sequence[float]] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_array(self) -> np.ndarray:
        return np.asarray(self.vector, dtype=np.float32)


@dataclass(frozen=True)
class LoggingConfig:
    enabled: bool = True
    log_dir_name: str = "logs"
    log_every_n: int = 1
    save_vertices: bool = True
    save_tool_pose: bool = True
    save_events: bool = True
    save_request: bool = True


@dataclass(frozen=True)
class SampleConfig:
    sample_id: int
    scene_id: str = "slab_v0"
    tissue_type: str = "toy_slab"
    simulator: str = "toy_backend"
    unit: str = "meter"
    notes: str = "synthetic tissue interaction sample"
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class SampleRequest:
    """One requested sample plus the artifact policy for that sample."""

    config: SampleConfig
    geometry: GeometryConfig
    material: MaterialConfig
    action: ActionSpec
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    enabled_artifacts: Optional[Sequence[str]] = None
    disabled_artifacts: Sequence[str] = field(default_factory=tuple)


@dataclass
class SampleResult:
    """Backend output before filesystem export."""

    artifacts: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, value: Any) -> None:
        self.artifacts[name] = value

    def remove(self, name: str) -> None:
        self.artifacts.pop(name, None)
