from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol, Sequence

import numpy as np


@dataclass(frozen=True)
class TrajectoryFrame:
    frame_id: int
    step_index: int
    time_code: float
    arrays: Mapping[str, np.ndarray] = field(default_factory=dict)
    scalars: Mapping[str, Any] = field(default_factory=dict)
    source_npz: Path | None = None
    source_json: Path | None = None


@dataclass(frozen=True)
class TrajectoryTransition:
    frame_t: TrajectoryFrame
    frame_t_plus_1: TrajectoryFrame

    @property
    def dt(self) -> float:
        return float(self.frame_t_plus_1.time_code - self.frame_t.time_code)


class TrajectoryReader(Protocol):
    sample_dir: Path
    log_dir: Path

    def iter_frames(self, start: int | None = None, stop: int | None = None, stride: int = 1) -> Iterator[TrajectoryFrame]:
        raise NotImplementedError

    def build_summary(self) -> dict[str, Any]:
        raise NotImplementedError


class EpisodeTrajectoryReader:
    """Read an episode trajectory from saved logs without simulator dependencies.

    This is the semantic layer above the current JSONL/NPZ log layout. Replay,
    validation, and future training loaders should depend on this interface
    instead of parsing frame files directly.
    """

    def __init__(self, sample_dir: Path, log_dir_name: str = "logs"):
        self.sample_dir = Path(sample_dir)
        self.log_dir_name = log_dir_name
        self.log_dir = self.sample_dir / log_dir_name
        self.frames_dir = self.log_dir / "frames"
        self.timeline_path = self.log_dir / "timeline.jsonl"
        self.events_path = self.log_dir / "events.jsonl"
        self.request_path = self.log_dir / "request.json"
        self.log_summary_path = self.log_dir / "summary.json"
        self.trajectory_summary_path = self.log_dir / "trajectory_summary.json"
        self.manifest_path = self.sample_dir / "sample_manifest.json"
        self._validate()

    def _validate(self) -> None:
        if not self.sample_dir.is_dir():
            raise FileNotFoundError(f"sample_dir does not exist: {self.sample_dir}")
        if not self.timeline_path.is_file():
            raise FileNotFoundError(f"timeline log does not exist: {self.timeline_path}")
        if not self.frames_dir.is_dir():
            raise FileNotFoundError(f"frames dir does not exist: {self.frames_dir}")

    def load_request(self) -> dict[str, Any]:
        return self._read_json(self.request_path) if self.request_path.exists() else {}

    def load_log_summary(self) -> dict[str, Any]:
        return self._read_json(self.log_summary_path) if self.log_summary_path.exists() else {}

    def load_summary(self) -> dict[str, Any]:
        if self.trajectory_summary_path.exists():
            return self._read_json(self.trajectory_summary_path)
        return self.load_log_summary()

    def load_manifest(self) -> dict[str, Any]:
        return self._read_json(self.manifest_path) if self.manifest_path.exists() else {}

    def iter_events(self) -> Iterator[dict[str, Any]]:
        if not self.events_path.exists():
            return
        with self.events_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def iter_timeline(self) -> Iterator[dict[str, Any]]:
        with self.timeline_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def iter_frames(self, start: int | None = None, stop: int | None = None, stride: int = 1) -> Iterator[TrajectoryFrame]:
        stride = max(int(stride), 1)
        for frame_id, row in enumerate(self.iter_timeline()):
            if start is not None and frame_id < start:
                continue
            if stop is not None and frame_id >= stop:
                break
            if (frame_id - (start or 0)) % stride != 0:
                continue
            yield self._load_frame(frame_id, row)

    def iter_transitions(self, stride: int = 1) -> Iterator[TrajectoryTransition]:
        previous: TrajectoryFrame | None = None
        for frame in self.iter_frames(stride=stride):
            if previous is not None:
                yield TrajectoryTransition(frame_t=previous, frame_t_plus_1=frame)
            previous = frame

    def build_summary(self) -> dict[str, Any]:
        request = self.load_request()
        manifest = self.load_manifest()
        log_summary = self.load_log_summary()
        rows = list(self.iter_timeline())

        array_keys: set[str] = set()
        scalar_keys: set[str] = set()
        frame_npz_count = 0
        frame_json_count = 0
        for row in rows:
            array_keys.update(str(key) for key in row.get("array_keys", []) if key is not None)
            scalar_keys.update(str(key) for key in row.get("scalar_keys", []) if key is not None)
            if row.get("frame_npz"):
                frame_npz_count += 1
            if row.get("frame_json"):
                frame_json_count += 1

        config = request.get("config", {}) if isinstance(request, dict) else {}
        material = request.get("material", {}) if isinstance(request, dict) else {}
        action = request.get("action", {}) if isinstance(request, dict) else {}
        logging = request.get("logging", {}) if isinstance(request, dict) else {}
        first = rows[0] if rows else {}
        last = rows[-1] if rows else {}

        return {
            "schema_version": "trajectory_summary_v1",
            "sample_dir": str(self.sample_dir),
            "log_dir_name": self.log_dir_name,
            "sample_id": config.get("sample_id", log_summary.get("sample_id")),
            "scene_id": config.get("scene_id"),
            "simulator": config.get("simulator"),
            "backend": log_summary.get("backend"),
            "action_type": action.get("action_type", log_summary.get("action_type")),
            "material": material,
            "logging": logging,
            "frame_count": len(rows),
            "frame_npz_count": frame_npz_count,
            "frame_json_count": frame_json_count,
            "first_step": first.get("step_index"),
            "last_step": last.get("step_index"),
            "first_time_code": first.get("time_code"),
            "last_time_code": last.get("time_code"),
            "array_keys": sorted(array_keys),
            "scalar_keys": sorted(scalar_keys),
            "artifact_names": _manifest_artifact_names(manifest),
            "source_files": {
                "manifest": str(self.manifest_path) if self.manifest_path.exists() else None,
                "request": str(self.request_path) if self.request_path.exists() else None,
                "log_summary": str(self.log_summary_path) if self.log_summary_path.exists() else None,
                "timeline": str(self.timeline_path),
                "frames_dir": str(self.frames_dir),
            },
        }

    def write_summary(self, path: Path | None = None) -> Path:
        output_path = path or self.trajectory_summary_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(_jsonable(self.build_summary()), f, indent=2, sort_keys=True)
            f.write("\n")
        return output_path

    def _load_frame(self, frame_id: int, row: Mapping[str, Any]) -> TrajectoryFrame:
        arrays: dict[str, np.ndarray] = {}
        scalars: dict[str, Any] = {}
        npz_path = None
        json_path = None

        frame_npz = row.get("frame_npz")
        if frame_npz:
            npz_path = self.frames_dir / str(frame_npz)
            with np.load(npz_path) as data:
                arrays = {key: data[key] for key in data.files}

        frame_json = row.get("frame_json")
        if frame_json:
            json_path = self.frames_dir / str(frame_json)
            scalars = self._read_json(json_path)

        return TrajectoryFrame(
            frame_id=frame_id,
            step_index=int(row["step_index"]),
            time_code=float(row["time_code"]),
            arrays=arrays,
            scalars=scalars,
            source_npz=npz_path,
            source_json=json_path,
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)


def write_trajectory_summary(sample_dir: Path, log_dir_name: str = "logs", output_path: Path | None = None) -> Path:
    return EpisodeTrajectoryReader(sample_dir, log_dir_name=log_dir_name).write_summary(output_path)


def load_trajectory_reader(spec: str, sample_dir: Path, *, log_dir_name: str = "logs") -> TrajectoryReader:
    if spec in ("default", "episode", "logs"):
        return EpisodeTrajectoryReader(sample_dir, log_dir_name=log_dir_name)
    module_name, sep, attr_name = spec.partition(":")
    if not sep:
        raise ValueError("trajectory reader spec must be 'default' or 'module:ClassName'")
    module = importlib.import_module(module_name)
    reader_cls = getattr(module, attr_name)
    return reader_cls(sample_dir, log_dir_name=log_dir_name)


def _manifest_artifact_names(manifest: Mapping[str, Any]) -> list[str]:
    artifacts = manifest.get("artifacts", []) if isinstance(manifest, Mapping) else []
    if not isinstance(artifacts, list):
        return []
    names = [item.get("name") for item in artifacts if isinstance(item, dict)]
    return sorted(str(name) for name in names if name)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value
