from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..schema import ActionSpec, GeometryConfig


class ActionSampler(Protocol):
    def sample(self, geometry: GeometryConfig, rng: np.random.Generator) -> ActionSpec:
        raise NotImplementedError


@dataclass(frozen=True)
class UniformPressActionSampler:
    contact_margin: float = 0.03
    min_depth: float = 0.002
    max_depth: float = 0.010
    direction_mode: str = "vertical_down"
    max_tilt_deg: float = 45.0

    def sample(self, geometry: GeometryConfig, rng: np.random.Generator) -> ActionSpec:
        half_x = geometry.size_x / 2.0
        half_y = geometry.size_y / 2.0
        margin_x = min(self.contact_margin, half_x * 0.75)
        margin_y = min(self.contact_margin, half_y * 0.75)
        contact_x = float(rng.uniform(-margin_x, margin_x))
        contact_y = float(rng.uniform(-margin_y, margin_y))
        depth = float(rng.uniform(self.min_depth, self.max_depth))
        direction = self._sample_direction(rng)
        action_type = "vertical_press" if self.direction_mode == "vertical_down" else "directional_press"
        return ActionSpec(
            vector=(contact_x, contact_y, float(direction[0]), float(direction[1]), float(direction[2]), depth),
            action_type=action_type,
            contact_point=(contact_x, contact_y, geometry.thickness / 2.0),
            extra={
                "direction_mode": self.direction_mode,
                "max_tilt_deg": self.max_tilt_deg,
            },
        )

    def _sample_direction(self, rng: np.random.Generator) -> np.ndarray:
        mode = str(self.direction_mode)
        if mode == "vertical_down":
            return np.asarray([0.0, 0.0, -1.0], dtype=np.float64)
        if mode != "upper_hemisphere_cone":
            raise ValueError(f"Unsupported direction_mode: {mode}")

        max_tilt_deg = float(self.max_tilt_deg)
        if not 0.0 <= max_tilt_deg < 90.0:
            raise ValueError(f"max_tilt_deg must be in [0, 90), got {max_tilt_deg}")
        max_tilt_rad = np.deg2rad(max_tilt_deg)
        cos_theta = float(rng.uniform(np.cos(max_tilt_rad), 1.0))
        sin_theta = float(np.sqrt(max(0.0, 1.0 - cos_theta * cos_theta)))
        phi = float(rng.uniform(0.0, 2.0 * np.pi))
        return np.asarray(
            [
                sin_theta * np.cos(phi),
                sin_theta * np.sin(phi),
                -cos_theta,
            ],
            dtype=np.float64,
        )
