from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..schema import MaterialConfig


class MaterialSampler(Protocol):
    def sample(self, rng: np.random.Generator) -> MaterialConfig:
        raise NotImplementedError


@dataclass(frozen=True)
class UniformMaterialSampler:
    youngs_modulus_range: tuple[float, float] = (5_000.0, 50_000.0)
    poisson_ratio_range: tuple[float, float] = (0.40, 0.49)
    damping_range: tuple[float, float] = (0.1, 2.0)
    density: float = 1000.0
    boundary_condition: str = "bottom_fixed"

    def sample(self, rng: np.random.Generator) -> MaterialConfig:
        return MaterialConfig(
            youngs_modulus=float(rng.uniform(*self.youngs_modulus_range)),
            poisson_ratio=float(rng.uniform(*self.poisson_ratio_range)),
            density=self.density,
            damping=float(rng.uniform(*self.damping_range)),
            boundary_condition=self.boundary_condition,
        )
