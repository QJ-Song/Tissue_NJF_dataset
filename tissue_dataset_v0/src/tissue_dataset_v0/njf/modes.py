from __future__ import annotations

from pathlib import Path
from typing import Literal

from tissue_dataset_v0.backends import SofaFemBackend
from tissue_dataset_v0.layout import default_layout
from tissue_dataset_v0.pipeline import DatasetPipeline
from tissue_dataset_v0.writer import FileSystemSampleWriter

from .plan import planned_sample_from_action, planned_sample_from_trajectory
from .recorder import prepare_dataset_root, write_dataset_metadata, write_mode_b_group, write_mode_c_trajectory
from .schema import NJFDatasetPlan, PlannedSample

ExistingPolicy = Literal["error", "overwrite"]


def generate_njf_dataset(plan: NJFDatasetPlan, *, overwrite: bool = False) -> Path:
    root = prepare_dataset_root(plan, overwrite=overwrite)
    pipeline = DatasetPipeline(backend=SofaFemBackend(), writer=FileSystemSampleWriter(default_layout()))
    sample_root = root / "samples"
    sample_records: list[dict] = []
    group_records: list[dict] = []
    trajectory_records: list[dict] = []

    if plan.modes.get("local_perturbation", False):
        for action_plan in plan.mode_a_actions:
            planned = planned_sample_from_action(plan, action_plan, mode="local_perturbation")
            sample_dir = pipeline.generate(sample_root, planned.request, existing_policy="error")
            sample_records.append(_sample_record(root, sample_dir, planned, split="train"))

    if plan.modes.get("response_basis_group", False):
        for group in plan.mode_b_groups:
            group_sample_dirs: list[Path] = []
            for action_plan in group.actions:
                planned = planned_sample_from_action(
                    plan,
                    action_plan,
                    mode="response_basis_group",
                    group_id=group.group_id,
                )
                sample_dir = pipeline.generate(sample_root, planned.request, existing_policy="error")
                group_sample_dirs.append(sample_dir)
                sample_records.append(_sample_record(root, sample_dir, planned, split="train"))
            group_records.append(write_mode_b_group(root, group, group_sample_dirs))

    if plan.modes.get("rollout_trajectory", False):
        for trajectory in plan.mode_c_trajectories:
            planned = planned_sample_from_trajectory(plan, trajectory)
            sample_dir = pipeline.generate(sample_root, planned.request, existing_policy="error")
            sample_records.append(_sample_record(root, sample_dir, planned, split="test_rollout"))
            trajectory_records.append(write_mode_c_trajectory(root, trajectory, sample_dir))

    if not sample_records:
        raise ValueError("NJF plan did not enable any implemented sample-generating modes")
    write_dataset_metadata(plan, sample_records, group_records, trajectory_records)
    return root


def generate_mode_a(plan: NJFDatasetPlan, *, overwrite: bool = False) -> Path:
    return generate_njf_dataset(plan, overwrite=overwrite)


def _sample_record(root: Path, sample_dir: Path, planned: PlannedSample, *, split: str) -> dict:
    action_plan = planned.action_plan
    return {
        "sample_id": sample_dir.name,
        "mode": planned.mode,
        "group_id": planned.group_id,
        "trajectory_id": planned.trajectory_id,
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
        "split": split,
    }
