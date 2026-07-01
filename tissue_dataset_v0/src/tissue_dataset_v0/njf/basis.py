from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


BasisKey = tuple[str, str, str]


@dataclass(frozen=True)
class ResponseBasis:
    group_id: str
    group_dir: Path
    metadata: dict[str, Any]
    actions: np.ndarray
    responses: np.ndarray
    flat_responses: np.ndarray
    singular_values: np.ndarray
    basis_rows: np.ndarray

    @property
    def key(self) -> BasisKey:
        return basis_key_from_metadata(self.metadata)

    @property
    def max_rank(self) -> int:
        return int(self.basis_rows.shape[0])

    @property
    def action_count(self) -> int:
        return int(self.actions.shape[0])

    def clipped_basis(self, rank: int) -> np.ndarray:
        rank = max(1, min(int(rank), self.max_rank))
        return self.basis_rows[:rank]


def load_basis_groups(dataset_root: str | Path) -> dict[BasisKey, ResponseBasis]:
    root = Path(dataset_root)
    groups_root = root / "groups"
    if not groups_root.is_dir():
        raise FileNotFoundError(f"No groups directory found: {groups_root}")
    groups: dict[BasisKey, ResponseBasis] = {}
    for group_dir in sorted(groups_root.glob("group_*")):
        basis = load_basis_group(group_dir)
        groups[basis.key] = basis
    return groups


def load_basis_group(group_dir: str | Path) -> ResponseBasis:
    group_dir = Path(group_dir)
    metadata = load_json(group_dir / "group_metadata.json")
    responses = np.load(group_dir / "responses.npy").astype(np.float64)
    actions = np.load(group_dir / "actions.npy").astype(np.float64)
    if responses.ndim != 3 or responses.shape[2] != 3:
        raise ValueError(f"{group_dir}: responses.npy must have shape [K, N, 3]")
    flat = responses.reshape(responses.shape[0], -1)
    _, singular_values, vt = np.linalg.svd(flat, full_matrices=False)
    return ResponseBasis(
        group_id=group_dir.name,
        group_dir=group_dir,
        metadata=metadata,
        actions=actions,
        responses=responses,
        flat_responses=flat,
        singular_values=singular_values,
        basis_rows=vt,
    )


def basis_key_from_metadata(metadata: dict[str, Any]) -> BasisKey:
    return (
        str(metadata.get("contact_point_id")),
        str(metadata.get("material_id")),
        str(metadata.get("boundary_id")),
    )


def project_rows(rows: np.ndarray, basis_rows: np.ndarray) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.float64)
    basis_rows = np.asarray(basis_rows, dtype=np.float64)
    return coefficients_for_rows(rows, basis_rows) @ basis_rows


def coefficients_for_rows(rows: np.ndarray, basis_rows: np.ndarray) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.float64)
    basis_rows = np.asarray(basis_rows, dtype=np.float64)
    return rows @ basis_rows.T


def reconstruct_from_coefficients(coefficients: np.ndarray, basis_rows: np.ndarray) -> np.ndarray:
    coefficients = np.asarray(coefficients, dtype=np.float64)
    basis_rows = np.asarray(basis_rows, dtype=np.float64)
    return coefficients @ basis_rows


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data
