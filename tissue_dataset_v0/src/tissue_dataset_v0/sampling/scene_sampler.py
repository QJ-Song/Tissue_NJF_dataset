from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..config import default_sample_request
from ..schema import GeometryConfig, SampleRequest
from .action_sampler import ActionSampler, UniformPressActionSampler
from .geometry_sampler import FixedGeometrySampler, GeometrySampler
from .material_sampler import MaterialSampler, UniformMaterialSampler


class SceneSampler:
    def __init__(
        self,
        action_sampler: ActionSampler | None = None,
        material_sampler: MaterialSampler | None = None,
        geometry: GeometryConfig | None = None,
        geometry_sampler: GeometrySampler | None = None,
    ):
        self.action_sampler = action_sampler or UniformPressActionSampler()
        self.material_sampler = material_sampler or UniformMaterialSampler()
        self.geometry_sampler = geometry_sampler or FixedGeometrySampler(geometry or GeometryConfig())

    def sample(self, sample_id: int, rng: np.random.Generator) -> SampleRequest:
        request = default_sample_request(sample_id=sample_id)
        geometry = self.geometry_sampler.sample(rng)
        return replace(
            request,
            geometry=geometry,
            material=self.material_sampler.sample(rng),
            action=self.action_sampler.sample(geometry, rng),
        )
