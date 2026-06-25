from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .layout import DatasetLayout, default_layout
from .schema import ActionSpec, GeometryConfig, LoggingConfig, MaterialConfig, SampleConfig, SampleRequest


@dataclass(frozen=True)
class DatasetConfig:
    root_dir: Path
    name: str = "dataset_v0"
    layout: DatasetLayout = field(default_factory=default_layout)


def default_sample_request(sample_id: int = 1) -> SampleRequest:
    geometry = GeometryConfig()
    material = MaterialConfig()
    action = ActionSpec(
        vector=(0.0, 0.0, 0.0, 0.0, -1.0, 0.008),
        action_type="vertical_press",
        contact_point=(0.0, 0.0, 0.0),
    )
    logging = LoggingConfig()
    config = SampleConfig(sample_id=sample_id)
    return SampleRequest(config=config, geometry=geometry, material=material, action=action, logging=logging)
