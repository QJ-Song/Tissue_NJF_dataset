from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .schema import NJFDatasetPlan


def prepare_dataset_root(plan: NJFDatasetPlan, *, overwrite: bool = False) -> Path:
    root = plan.output_dir
    if root.exists() and any(root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"NJF dataset output directory exists and is not empty: {root}. Use --overwrite explicitly.")
        shutil.rmtree(root)
    (root / "samples").mkdir(parents=True, exist_ok=True)
    (root / "groups").mkdir(parents=True, exist_ok=True)
    (root / "trajectories").mkdir(parents=True, exist_ok=True)
    return root


def write_dataset_metadata(plan: NJFDatasetPlan, sample_records: list[dict[str, Any]]) -> None:
    root = plan.output_dir
    metadata = {
        **plan.metadata,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(root),
        "seed": plan.seed,
        "sample_count": len(sample_records),
        "modes": plan.modes,
        "samples": sample_records,
        "geometry": {
            "size_x": plan.geometry.size_x,
            "size_y": plan.geometry.size_y,
            "thickness": plan.geometry.thickness,
            "nx": plan.geometry.nx,
            "ny": plan.geometry.ny,
            "layers": plan.geometry.layers,
        },
        "material": {
            "youngs_modulus": plan.material.youngs_modulus,
            "poisson_ratio": plan.material.poisson_ratio,
            "density": plan.material.density,
            "damping": plan.material.damping,
            "boundary_condition": plan.material.boundary_condition,
        },
        "required_sample_artifacts_mode_a": [
            "vertices_0",
            "vertices_1",
            "displacement",
            "action",
            "tool_pose_0",
            "tool_pose_1",
            "tool_geometry",
            "contact_summary",
            "boundary_mask",
            "fixed_node_indices",
            "free_node_indices",
            "boundary",
            "solver_summary",
        ],
    }
    _write_json(root / "metadata.json", metadata)
    splits = {"train": [item["sample_id"] for item in sample_records], "val": [], "test_unseen_contact": [], "test_unseen_material": [], "test_rollout": []}
    _write_json(root / "splits.json", splits)
    copy_config(plan.config_path, root / "config.yaml")


def copy_config(src: Path, dst: Path) -> None:
    data = yaml.safe_load(src.read_text())
    with dst.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
