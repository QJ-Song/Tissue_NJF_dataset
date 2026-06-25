from __future__ import annotations

import importlib
from typing import Protocol

from ..trajectory import EpisodeTrajectoryReader, TrajectoryFrame

ReplayFrame = TrajectoryFrame


class ReplayViewer(Protocol):
    name: str

    def setup(self, reader: "ReplayReader") -> None:
        raise NotImplementedError

    def show_frame(self, frame: ReplayFrame) -> None:
        raise NotImplementedError

    def finish(self) -> None:
        raise NotImplementedError


class ReplayReader(EpisodeTrajectoryReader):
    """Compatibility wrapper around the trajectory reader.

    New code should prefer `EpisodeTrajectoryReader`; replay keeps this class
    so existing viewers and scripts do not need to change their public API.
    """


class SummaryReplayViewer:
    """Default viewer for validating replay plumbing without graphics."""

    name = "summary"

    def __init__(self, max_frames: int | None = None):
        self.max_frames = max_frames
        self.reader: ReplayReader | None = None
        self.frame_count = 0
        self.array_keys: set[str] = set()
        self.first_step: int | None = None
        self.last_step: int | None = None

    def setup(self, reader: ReplayReader) -> None:
        self.reader = reader
        summary = reader.load_summary()
        print(f"Replay sample: {reader.sample_dir}")
        if summary:
            print(f"Summary: {summary}")

    def show_frame(self, frame: ReplayFrame) -> None:
        if self.frame_count == 0:
            self.first_step = frame.step_index
        self.last_step = frame.step_index
        self.frame_count += 1
        self.array_keys.update(frame.arrays.keys())
        if self.max_frames is None or self.frame_count <= self.max_frames:
            shapes = {key: list(value.shape) for key, value in frame.arrays.items()}
            print(
                f"frame={frame.step_index} time={frame.time_code:.4f} "
                f"arrays={shapes} scalars={sorted(frame.scalars.keys())}"
            )

    def finish(self) -> None:
        print(
            f"Replay complete: frames={self.frame_count} "
            f"first_step={self.first_step} last_step={self.last_step} "
            f"array_keys={sorted(self.array_keys)}"
        )


class ReplayRunner:
    def __init__(self, reader: ReplayReader, viewer: ReplayViewer):
        self.reader = reader
        self.viewer = viewer

    def run(self, start: int | None = None, stop: int | None = None, stride: int = 1) -> int:
        self.viewer.setup(self.reader)
        count = 0
        for frame in self.reader.iter_frames(start=start, stop=stop, stride=stride):
            self.viewer.show_frame(frame)
            count += 1
        self.viewer.finish()
        return count


def load_viewer(spec: str) -> ReplayViewer:
    if spec == "summary":
        return SummaryReplayViewer()
    module_name, sep, attr_name = spec.partition(":")
    if not sep:
        raise ValueError("viewer spec must be 'summary' or 'module:ClassName'")
    module = importlib.import_module(module_name)
    viewer_cls = getattr(module, attr_name)
    return viewer_cls()
