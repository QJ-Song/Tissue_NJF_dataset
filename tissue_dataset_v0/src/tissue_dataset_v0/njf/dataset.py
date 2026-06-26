from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np


@dataclass(frozen=True)
class LocalPerturbationRecord:
    """One Mode A/local small-step sample loaded as model-agnostic numpy fields."""

    sample_id: str
    sample_dir: Path
    metadata: dict[str, Any]
    material: dict[str, Any]
    boundary: dict[str, Any]
    solver_summary: dict[str, Any]
    contact_summary: dict[str, Any]
    tool_geometry: dict[str, Any]
    x_t: np.ndarray
    x_next: np.ndarray
    delta_x: np.ndarray
    action: np.ndarray
    contact_point: np.ndarray
    fixed_node_mask: np.ndarray
    tool_pose_t: np.ndarray
    tool_pose_next: np.ndarray

    @property
    def delta_a(self) -> np.ndarray:
        return self.action_direction * self.action_magnitude_m

    @property
    def action_direction(self) -> np.ndarray:
        return self.action[2:5].copy()

    @property
    def action_magnitude_m(self) -> float:
        return float(self.action[5])

    @property
    def ids(self) -> dict[str, str | None]:
        extra = self.metadata.get("extra", {}) if isinstance(self.metadata.get("extra"), dict) else {}
        return {
            "sample_id": self.sample_id,
            "state_id": extra.get("state_id"),
            "material_id": extra.get("material_id"),
            "boundary_id": extra.get("boundary_id"),
            "contact_point_id": extra.get("contact_point_id"),
            "group_id": extra.get("group_id"),
            "trajectory_id": extra.get("trajectory_id"),
            "action_id": extra.get("action_id"),
        }


@dataclass(frozen=True)
class ResponseBasisGroupRecord:
    """One Mode B fixed-contact response-basis group."""

    group_id: str
    group_dir: Path
    metadata: dict[str, Any]
    state_initial: np.ndarray
    fixed_node_mask: np.ndarray
    surface_points: np.ndarray
    actions: np.ndarray
    responses: np.ndarray
    contact_point: np.ndarray
    contact_normal: np.ndarray

    @property
    def action_count(self) -> int:
        return int(self.actions.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.state_initial.shape[0])

    @property
    def response_matrix(self) -> np.ndarray:
        return self.responses.reshape(self.responses.shape[0], -1)

    @property
    def action_directions(self) -> np.ndarray:
        return self.actions[:, 2:5]

    @property
    def action_magnitudes_m(self) -> np.ndarray:
        return self.actions[:, 5]

    @property
    def ids(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "state_id": self.metadata.get("state_id"),
            "material_id": self.metadata.get("material_id"),
            "boundary_id": self.metadata.get("boundary_id"),
            "contact_point_id": self.metadata.get("contact_point_id"),
        }


@dataclass(frozen=True)
class RolloutTrajectoryRecord:
    """One Mode C multi-step trajectory loaded from trajectories/traj_*."""

    trajectory_id: str
    trajectory_dir: Path
    metadata: dict[str, Any]
    solver_status: dict[str, Any]
    states: np.ndarray
    actions: np.ndarray
    responses: np.ndarray
    contact_points: np.ndarray
    contact_normals: np.ndarray
    tool_poses: np.ndarray
    fixed_node_mask: np.ndarray
    contact_status: np.ndarray | None = None
    contact_distances: np.ndarray | None = None

    @property
    def step_count(self) -> int:
        return int(self.actions.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.states.shape[1])

    def iter_steps(self) -> Iterator[dict[str, Any]]:
        for step in range(self.step_count):
            yield {
                "trajectory_id": self.trajectory_id,
                "step_id": step,
                "x_t": self.states[step],
                "x_next": self.states[step + 1],
                "delta_x": self.responses[step],
                "action": self.actions[step],
                "contact_point": self.contact_points[step],
                "contact_normal": self.contact_normals[step],
                "tool_pose_t": self.tool_poses[step],
                "tool_pose_next": self.tool_poses[step + 1],
                "contact_status": None if self.contact_status is None else bool(self.contact_status[step]),
                "contact_distance": None if self.contact_distances is None else float(self.contact_distances[step]),
            }


@dataclass(frozen=True)
class NJFDatasetSummary:
    dataset_root: Path
    sample_count: int
    mode_counts: dict[str, int]
    group_count: int
    trajectory_count: int
    local_sample_shape: tuple[int, ...] | None
    group_response_shape: tuple[int, ...] | None
    trajectory_state_shape: tuple[int, ...] | None
    action_dim: int | None
    split_counts: dict[str, dict[str, int]]
    material_ids: list[str]
    contact_point_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_root": str(self.dataset_root),
            "sample_count": self.sample_count,
            "mode_counts": self.mode_counts,
            "group_count": self.group_count,
            "trajectory_count": self.trajectory_count,
            "local_sample_shape": list(self.local_sample_shape) if self.local_sample_shape is not None else None,
            "group_response_shape": list(self.group_response_shape) if self.group_response_shape is not None else None,
            "trajectory_state_shape": list(self.trajectory_state_shape) if self.trajectory_state_shape is not None else None,
            "action_dim": self.action_dim,
            "split_counts": self.split_counts,
            "material_ids": self.material_ids,
            "contact_point_ids": self.contact_point_ids,
        }


class NJFDataset:
    """SOFA-free reader for Mode A/B/C NJF dataset roots.

    The reader intentionally returns numpy arrays and metadata dictionaries. It
    does not import SOFA, Isaac Sim, torch, or any backend module, so training
    and evaluation code can depend on saved data only.
    """

    def __init__(self, dataset_root: str | Path):
        self.root = Path(dataset_root)
        self.metadata = load_json(self.root / "metadata.json")
        self.splits = load_json(self.root / "splits.json") if (self.root / "splits.json").exists() else {}
        self.sample_dirs = discover_dirs(self.root / "samples", "sample_")
        self.group_dirs = discover_dirs(self.root / "groups", "group_")
        self.trajectory_dirs = discover_dirs(self.root / "trajectories", "traj_")

    def iter_local_samples(self, *, modes: Iterable[str] = ("local_perturbation",)) -> Iterator[LocalPerturbationRecord]:
        wanted = set(modes)
        for sample_dir in self.sample_dirs:
            meta = load_json(sample_dir / "meta.json")
            extra = meta.get("extra", {}) if isinstance(meta.get("extra"), dict) else {}
            if extra.get("njf_mode") not in wanted:
                continue
            yield load_local_sample(sample_dir, metadata=meta)

    def iter_basis_groups(self) -> Iterator[ResponseBasisGroupRecord]:
        for group_dir in self.group_dirs:
            yield load_basis_group(group_dir)

    def iter_rollout_trajectories(self) -> Iterator[RolloutTrajectoryRecord]:
        for trajectory_dir in self.trajectory_dirs:
            yield load_rollout_trajectory(trajectory_dir)

    def iter_rollout_steps(self) -> Iterator[dict[str, Any]]:
        for trajectory in self.iter_rollout_trajectories():
            yield from trajectory.iter_steps()

    def summary(self) -> NJFDatasetSummary:
        mode_counts: dict[str, int] = {}
        material_ids: set[str] = set()
        contact_ids: set[str] = set()
        local_shape: tuple[int, ...] | None = None
        action_dim: int | None = None
        for sample_dir in self.sample_dirs:
            meta = load_json(sample_dir / "meta.json")
            extra = meta.get("extra", {}) if isinstance(meta.get("extra"), dict) else {}
            mode = str(extra.get("njf_mode", "unknown"))
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            if extra.get("material_id") is not None:
                material_ids.add(str(extra.get("material_id")))
            if extra.get("contact_point_id") is not None:
                contact_ids.add(str(extra.get("contact_point_id")))
            if local_shape is None and mode == "local_perturbation":
                local_shape = tuple(int(dim) for dim in np.load(sample_dir / "vertices_0.npy").shape)
            if action_dim is None:
                action_dim = int(np.load(sample_dir / "action.npy").shape[0])
        group_shape = None
        if self.group_dirs:
            group_shape = tuple(int(dim) for dim in np.load(self.group_dirs[0] / "responses.npy").shape)
        traj_shape = None
        if self.trajectory_dirs:
            traj_shape = tuple(int(dim) for dim in np.load(self.trajectory_dirs[0] / "states.npy").shape)
        return NJFDatasetSummary(
            dataset_root=self.root,
            sample_count=len(self.sample_dirs),
            mode_counts=mode_counts,
            group_count=len(self.group_dirs),
            trajectory_count=len(self.trajectory_dirs),
            local_sample_shape=local_shape,
            group_response_shape=group_shape,
            trajectory_state_shape=traj_shape,
            action_dim=action_dim,
            split_counts=summarize_splits(self.splits),
            material_ids=sorted(material_ids),
            contact_point_ids=sorted(contact_ids),
        )

    def validate_training_view(self) -> list[str]:
        issues: list[str] = []
        for record in self.iter_local_samples(modes=("local_perturbation", "response_basis_group")):
            if record.x_t.shape != record.x_next.shape or record.x_t.shape != record.delta_x.shape:
                issues.append(f"{record.sample_id}: local sample shapes do not match")
            elif not np.allclose(record.delta_x, record.x_next - record.x_t, atol=1e-7):
                issues.append(f"{record.sample_id}: delta_x != x_next - x_t")
            if record.action.shape[0] < 6:
                issues.append(f"{record.sample_id}: action_dim < 6")
            if record.fixed_node_mask.shape != (record.x_t.shape[0],):
                issues.append(f"{record.sample_id}: fixed_node_mask shape mismatch")
        for group in self.iter_basis_groups():
            if group.responses.shape != (group.actions.shape[0], group.state_initial.shape[0], 3):
                issues.append(f"{group.group_id}: responses shape mismatch")
            if group.fixed_node_mask.shape != (group.state_initial.shape[0],):
                issues.append(f"{group.group_id}: fixed_node_mask shape mismatch")
            if not np.isfinite(group.responses).all() or not np.isfinite(group.actions).all():
                issues.append(f"{group.group_id}: non-finite group arrays")
        for trajectory in self.iter_rollout_trajectories():
            if trajectory.states.shape[0] != trajectory.actions.shape[0] + 1:
                issues.append(f"{trajectory.trajectory_id}: states count must equal actions + 1")
            if trajectory.responses.shape != trajectory.states[1:].shape:
                issues.append(f"{trajectory.trajectory_id}: response shape mismatch")
            elif not np.allclose(trajectory.responses, trajectory.states[1:] - trajectory.states[:-1], atol=1e-7):
                issues.append(f"{trajectory.trajectory_id}: responses != states[1:] - states[:-1]")
            if trajectory.fixed_node_mask.shape != (trajectory.states.shape[1],):
                issues.append(f"{trajectory.trajectory_id}: fixed_node_mask shape mismatch")
        return issues


def load_local_sample(sample_dir: Path, *, metadata: dict[str, Any] | None = None) -> LocalPerturbationRecord:
    meta = metadata if metadata is not None else load_json(sample_dir / "meta.json")
    return LocalPerturbationRecord(
        sample_id=sample_dir.name,
        sample_dir=sample_dir,
        metadata=meta,
        material=load_json(sample_dir / "material.json"),
        boundary=load_json(sample_dir / "boundary.json"),
        solver_summary=load_json(sample_dir / "solver_summary.json"),
        contact_summary=load_json(sample_dir / "contact_summary.json"),
        tool_geometry=load_json(sample_dir / "tool_geometry.json"),
        x_t=np.load(sample_dir / "vertices_0.npy"),
        x_next=np.load(sample_dir / "vertices_1.npy"),
        delta_x=np.load(sample_dir / "displacement.npy"),
        action=np.load(sample_dir / "action.npy"),
        contact_point=np.load(sample_dir / "contact_point.npy"),
        fixed_node_mask=np.load(sample_dir / "boundary_mask.npy").astype(bool),
        tool_pose_t=np.load(sample_dir / "tool_pose_0.npy"),
        tool_pose_next=np.load(sample_dir / "tool_pose_1.npy"),
    )


def load_basis_group(group_dir: Path) -> ResponseBasisGroupRecord:
    return ResponseBasisGroupRecord(
        group_id=group_dir.name,
        group_dir=group_dir,
        metadata=load_json(group_dir / "group_metadata.json"),
        state_initial=np.load(group_dir / "state_initial.npy"),
        fixed_node_mask=np.load(group_dir / "fixed_node_mask.npy").astype(bool),
        surface_points=np.load(group_dir / "surface_points.npy"),
        actions=np.load(group_dir / "actions.npy"),
        responses=np.load(group_dir / "responses.npy"),
        contact_point=np.load(group_dir / "contact_point.npy"),
        contact_normal=np.load(group_dir / "contact_normal.npy"),
    )


def load_rollout_trajectory(trajectory_dir: Path) -> RolloutTrajectoryRecord:
    return RolloutTrajectoryRecord(
        trajectory_id=trajectory_dir.name,
        trajectory_dir=trajectory_dir,
        metadata=load_json(trajectory_dir / "trajectory_metadata.json"),
        solver_status=load_json(trajectory_dir / "solver_status.json"),
        states=np.load(trajectory_dir / "states.npy"),
        actions=np.load(trajectory_dir / "actions.npy"),
        responses=np.load(trajectory_dir / "responses.npy"),
        contact_points=np.load(trajectory_dir / "contact_points.npy"),
        contact_normals=np.load(trajectory_dir / "contact_normals.npy"),
        tool_poses=np.load(trajectory_dir / "tool_poses.npy"),
        fixed_node_mask=np.load(trajectory_dir / "fixed_node_mask.npy").astype(bool),
        contact_status=load_optional_array(trajectory_dir / "contact_status.npy"),
        contact_distances=load_optional_array(trajectory_dir / "contact_distances.npy"),
    )


def discover_dirs(root: Path, prefix: str) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith(prefix))


def summarize_splits(splits: dict[str, Any]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for split_name, split_payload in splits.items():
        if not isinstance(split_payload, dict):
            continue
        result[str(split_name)] = {
            "samples": len(split_payload.get("samples", []) or []),
            "groups": len(split_payload.get("groups", []) or []),
            "trajectories": len(split_payload.get("trajectories", []) or []),
        }
    return result


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def load_optional_array(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.load(path)
