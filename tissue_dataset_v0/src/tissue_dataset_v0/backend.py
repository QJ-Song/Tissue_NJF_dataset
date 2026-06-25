from __future__ import annotations

from typing import Any, Mapping, Protocol

from .schema import SampleRequest, SampleResult


class SimulationLogger(Protocol):
    def begin(self, request: SampleRequest) -> None:
        raise NotImplementedError

    def record_frame(
        self,
        step_index: int,
        time_code: float,
        *,
        arrays: Mapping[str, Any] | None = None,
        scalars: Mapping[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError

    def record_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def finish(self, summary: Mapping[str, Any]) -> None:
        raise NotImplementedError


class SimulationBackend(Protocol):
    name: str

    def simulate(self, request: SampleRequest, logger: SimulationLogger | None = None) -> SampleResult:
        raise NotImplementedError
