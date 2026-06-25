from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class NJFValidationReport:
    dataset_root: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_root": str(self.dataset_root),
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "samples": self.samples,
        }


def validate_njf_dataset(dataset_root: Path) -> NJFValidationReport:
    root = Path(dataset_root)
    report = NJFValidationReport(dataset_root=root)
    metadata_path = root / "metadata.json"
    if not metadata_path.exists():
        report.errors.append("Missing metadata.json")
        return report
    metadata = _load_json(metadata_path)
    samples_dir = root / "samples"
    if not samples_dir.is_dir():
        report.errors.append("Missing samples/ directory")
        return report
    sample_dirs = sorted(path for path in samples_dir.iterdir() if path.is_dir() and path.name.startswith("sample_"))
    if not sample_dirs:
        report.errors.append("No sample_* directories found under samples/")
    expected = {item.get("sample_id") for item in metadata.get("samples", []) if isinstance(item, dict)}
    actual = {path.name for path in sample_dirs}
    if expected and expected != actual:
        report.errors.append(f"metadata samples {sorted(expected)} do not match samples directory {sorted(actual)}")
    for sample_dir in sample_dirs:
        report.samples.append(_validate_mode_a_sample(sample_dir, report))
    return report


def _validate_mode_a_sample(sample_dir: Path, report: NJFValidationReport) -> dict[str, Any]:
    sample_id = sample_dir.name
    required = [
        "vertices_0.npy",
        "vertices_1.npy",
        "displacement.npy",
        "action.npy",
        "tool_pose_0.npy",
        "tool_pose_1.npy",
        "tool_geometry.json",
        "contact_summary.json",
        "boundary_mask.npy",
        "fixed_node_indices.npy",
        "free_node_indices.npy",
        "boundary.json",
        "solver_summary.json",
        "meta.json",
        "sample_manifest.json",
    ]
    missing = [name for name in required if not (sample_dir / name).exists()]
    if missing:
        report.errors.append(f"{sample_id}: missing required Mode A artifact(s): {', '.join(missing)}")
        return {"sample_id": sample_id, "valid": False, "missing": missing}

    vertices_0 = np.load(sample_dir / "vertices_0.npy")
    vertices_1 = np.load(sample_dir / "vertices_1.npy")
    displacement = np.load(sample_dir / "displacement.npy")
    action = np.load(sample_dir / "action.npy")
    mask = np.load(sample_dir / "boundary_mask.npy")
    fixed = np.load(sample_dir / "fixed_node_indices.npy")
    contact = _load_json(sample_dir / "contact_summary.json")
    solver = _load_json(sample_dir / "solver_summary.json")
    meta = _load_json(sample_dir / "meta.json")

    if vertices_0.shape != vertices_1.shape or vertices_0.shape != displacement.shape:
        report.errors.append(f"{sample_id}: vertices/displacement shapes do not match")
    if not np.allclose(displacement, vertices_1 - vertices_0, atol=1e-7):
        report.errors.append(f"{sample_id}: displacement != vertices_1 - vertices_0")
    if not np.isfinite(vertices_0).all() or not np.isfinite(vertices_1).all() or not np.isfinite(displacement).all():
        report.errors.append(f"{sample_id}: non-finite vertex/displacement value")
    if action.shape[0] < 6:
        report.errors.append(f"{sample_id}: action must have at least 6 values")
        magnitude_m = float("nan")
    else:
        magnitude_m = float(action[5])
        if magnitude_m <= 0.0 or magnitude_m > 0.00025:
            report.errors.append(f"{sample_id}: local action magnitude {magnitude_m} m is outside Mode A smoke bounds")
    if mask.shape != (vertices_0.shape[0],):
        report.errors.append(f"{sample_id}: boundary_mask shape does not match vertex count")
    if fixed.size and mask.shape == (vertices_0.shape[0],):
        fixed_disp = np.linalg.norm(vertices_1[fixed.astype(int)] - vertices_0[fixed.astype(int)], axis=1)
        max_fixed = float(fixed_disp.max())
        if max_fixed > 1e-6:
            report.errors.append(f"{sample_id}: fixed node displacement {max_fixed} m exceeds tolerance")
    else:
        max_fixed = 0.0
    if not bool(contact.get("contact_detected", False)):
        report.errors.append(f"{sample_id}: contact_summary.contact_detected is false")
    if not bool(solver.get("valid", False)):
        report.errors.append(f"{sample_id}: solver_summary.valid is false")
    extra = meta.get("extra", {}) if isinstance(meta.get("extra"), dict) else {}
    if extra.get("njf_mode") != "local_perturbation":
        report.errors.append(f"{sample_id}: meta.extra.njf_mode is not local_perturbation")

    return {
        "sample_id": sample_id,
        "valid": True,
        "vertex_count": int(vertices_0.shape[0]),
        "action_magnitude_m": magnitude_m,
        "max_displacement_m": float(np.linalg.norm(displacement, axis=1).max()),
        "max_fixed_displacement_m": max_fixed,
        "contact_detected": bool(contact.get("contact_detected", False)),
        "solver_valid": bool(solver.get("valid", False)),
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data
