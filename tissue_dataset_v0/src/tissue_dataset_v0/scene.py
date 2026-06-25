from __future__ import annotations

from typing import Protocol

from .backend import SimulationLogger
from .schema import SampleRequest, SampleResult


class SimulationScenePlugin(Protocol):
    name: str

    def simulate(self, request: SampleRequest, logger: SimulationLogger | None = None) -> SampleResult:
        raise NotImplementedError
