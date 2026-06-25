from __future__ import annotations

from pathlib import Path
from typing import Literal

from tissue_dataset_v0.backends import SofaFemBackend
from tissue_dataset_v0.layout import default_layout
from tissue_dataset_v0.pipeline import DatasetPipeline
from tissue_dataset_v0.writer import FileSystemSampleWriter

from .plan import planned_sample_from_action
from .recorder import prepare_dataset_root, write_dataset_metadata
from .schema import NJFDatasetPlan

ExistingPolicy = Literal["error", "overwrite"]


def generate_mode_a(plan: NJFDatasetPlan, *, overwrite: bool = False) -> Path:
    if not plan.modes.get("local_perturbation", False):
        raise ValueError("NJF plan has local_perturbation mode disabled.")
    root = prepare_dataset_root(plan, overwrite=overwrite)
    pipeline = DatasetPipeline(backend=SofaFemBackend(), writer=FileSystemSampleWriter(default_layout()))
    sample_root = root / "samples"
    records: list[dict] = []
    for action_plan in plan.mode_a_actions:
        planned = planned_sample_from_action(plan, action_plan)
        sample_dir = pipeline.generate(sample_root, planned.request, existing_policy="error")
        records.append(
            {
                "sample_id": sample_dir.name,
                "mode": planned.mode,
                "path": str(sample_dir.relative_to(root)),
                "state_id": "state_000001",
                "material_id": "material_000001",
                "boundary_id": "boundary_000001",
                "contact_point_id": "contact_000001",
                "action_id": action_plan.action_id,
                "step_id": 0,
                "delta_a_m": action_plan.magnitude_m,
                "action_direction": list(action_plan.direction),
                "contact_point": list(action_plan.contact_point),
                "split": "train",
            }
        )
    write_dataset_metadata(plan, records)
    return root
