from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..schema import GeometryConfig


class GeometrySampler(Protocol):
    def sample(self, rng: np.random.Generator) -> GeometryConfig:
        raise NotImplementedError


@dataclass(frozen=True)
class FixedGeometrySampler:
    geometry: GeometryConfig

    def sample(self, rng: np.random.Generator) -> GeometryConfig:
        return self.geometry


@dataclass(frozen=True)
class UniformGeometrySampler:
    size_x_range: tuple[float, float]
    size_y_range: tuple[float, float]
    thickness_range: tuple[float, float]
    nx: int
    ny: int
    layers: int
    fixed_border_ratio: float = 0.12

    def sample(self, rng: np.random.Generator) -> GeometryConfig:
        return GeometryConfig(
            size_x=float(rng.uniform(*self.size_x_range)),
            size_y=float(rng.uniform(*self.size_y_range)),
            thickness=float(rng.uniform(*self.thickness_range)),
            nx=int(self.nx),
            ny=int(self.ny),
            layers=int(self.layers),
            fixed_border_ratio=float(self.fixed_border_ratio),
        )
