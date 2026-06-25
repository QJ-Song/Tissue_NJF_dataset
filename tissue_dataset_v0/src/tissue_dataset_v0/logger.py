from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .schema import SampleRequest


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return value.tolist()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return asdict(value)
        except Exception:
            return {k: _jsonable(v) for k, v in vars(value).items()}
    return value


class NullSimulationLogger:
    def begin(self, request: SampleRequest) -> None:
        return None

    def record_frame(
        self,
        step_index: int,
        time_code: float,
        *,
        arrays: Mapping[str, Any] | None = None,
        scalars: Mapping[str, Any] | None = None,
    ) -> None:
        return None

    def record_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        return None

    def finish(self, summary: Mapping[str, Any]) -> None:
        return None


class DirectorySimulationLogger:
    """Write simulation-time logs next to a sample output directory."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.frames_dir = self.root_dir / "frames"
        self.events_path = self.root_dir / "events.jsonl"
        self.timeline_path = self.root_dir / "timeline.jsonl"
        self.request_path = self.root_dir / "request.json"
        self.summary_path = self.root_dir / "summary.json"
        self._initialized = False
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    def begin(self, request: SampleRequest) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._write_json(
            self.request_path,
            {
                "config": request.config,
                "geometry": request.geometry,
                "material": request.material,
                "action": request.action,
                "logging": request.logging,
                "enabled_artifacts": list(request.enabled_artifacts) if request.enabled_artifacts is not None else None,
                "disabled_artifacts": list(request.disabled_artifacts),
            },
        )

    def record_frame(
        self,
        step_index: int,
        time_code: float,
        *,
        arrays: Mapping[str, Any] | None = None,
        scalars: Mapping[str, Any] | None = None,
    ) -> None:
        arrays = dict(arrays or {})
        scalars = dict(scalars or {})
        frame_base = f"frame_{step_index:06d}"
        frame_npz = self.frames_dir / f"{frame_base}.npz"
        frame_json = self.frames_dir / f"{frame_base}.json"
        if arrays:
            np.savez_compressed(frame_npz, **{k: np.asarray(v) for k, v in arrays.items()})
        if scalars:
            self._write_json(
                frame_json,
                {
                    "step_index": step_index,
                    "time_code": time_code,
                    **scalars,
                },
            )
        self._append_jsonl(
            self.timeline_path,
            {
                "step_index": step_index,
                "time_code": time_code,
                "frame_npz": frame_npz.name if arrays else None,
                "frame_json": frame_json.name if scalars else None,
                "scalar_keys": sorted(list(scalars.keys())),
                "array_keys": sorted(list(arrays.keys())),
            },
        )

    def record_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self._append_jsonl(
            self.events_path,
            {
                "event_type": event_type,
                "payload": _jsonable(payload),
            },
        )

    def finish(self, summary: Mapping[str, Any]) -> None:
        self._write_json(self.summary_path, summary)

    def _append_jsonl(self, path: Path, value: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_jsonable(value), sort_keys=True))
            f.write("\n")

    def _write_json(self, path: Path, value: Any) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(_jsonable(value), f, indent=2, sort_keys=True)
            f.write("\n")
