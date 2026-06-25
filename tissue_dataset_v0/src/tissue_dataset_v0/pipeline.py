from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from .backend import SimulationBackend
from .logger import DirectorySimulationLogger, NullSimulationLogger
from .schema import SampleRequest
from .trajectory import write_trajectory_summary
from .writer import FileSystemSampleWriter

ExistingSamplePolicy = Literal["error", "overwrite"]


class DatasetPipeline:
    """Coordinates backend simulation, data logging, and filesystem export."""

    def __init__(self, backend: SimulationBackend, writer: FileSystemSampleWriter, logger_factory=None):
        self.backend = backend
        self.writer = writer
        self.logger_factory = logger_factory or DirectorySimulationLogger

    def generate(
        self,
        sample_root: Path,
        request: SampleRequest,
        *,
        existing_policy: ExistingSamplePolicy = "error",
    ) -> Path:
        sample_root = Path(sample_root)
        sample_dir = sample_root / f"sample_{request.config.sample_id:06d}"
        self._prepare_sample_dir(sample_dir, existing_policy=existing_policy)

        if request.logging.enabled:
            logger = self.logger_factory(sample_dir / request.logging.log_dir_name)
        else:
            logger = NullSimulationLogger()

        result = self.backend.simulate(request, logger=logger)
        self.writer.write_sample(
            sample_dir,
            result,
            include_artifacts=request.enabled_artifacts,
            exclude_artifacts=request.disabled_artifacts,
        )
        if request.logging.enabled:
            write_trajectory_summary(sample_dir, log_dir_name=request.logging.log_dir_name)
        return sample_dir

    def _prepare_sample_dir(self, sample_dir: Path, *, existing_policy: ExistingSamplePolicy) -> None:
        if existing_policy not in ("error", "overwrite"):
            raise ValueError(f"Unsupported existing sample policy: {existing_policy}")
        if sample_dir.exists() and not sample_dir.is_dir():
            raise NotADirectoryError(f"Sample path exists and is not a directory: {sample_dir}")
        if sample_dir.exists() and any(sample_dir.iterdir()):
            if existing_policy == "error":
                raise FileExistsError(
                    f"Sample directory already exists and is not empty: {sample_dir}. "
                    "Use --overwrite to delete and regenerate it explicitly."
                )
            shutil.rmtree(sample_dir)
        sample_dir.mkdir(parents=True, exist_ok=True)
