from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LocalPatchSpec:
    node_indices: np.ndarray
    initial_distances: np.ndarray


def build_local_patch_spec(initial_state: np.ndarray, contact_point: np.ndarray, *, patch_size: int) -> LocalPatchSpec:
    points = np.asarray(initial_state, dtype=np.float64)
    contact = np.asarray(contact_point, dtype=np.float64)
    distances = np.linalg.norm(points - contact[None, :], axis=1)
    count = max(1, min(int(patch_size), points.shape[0]))
    indices = np.argsort(distances)[:count]
    return LocalPatchSpec(node_indices=indices.astype(np.int64), initial_distances=distances[indices].astype(np.float64))


def local_state_features(
    states: np.ndarray,
    *,
    step: int,
    contact_point: np.ndarray,
    patch: LocalPatchSpec,
) -> np.ndarray:
    states = np.asarray(states, dtype=np.float64)
    step = int(step)
    initial = states[0]
    current = states[step]
    indices = patch.node_indices
    initial_patch = initial[indices]
    current_patch = current[indices]
    displacement = current_patch - initial_patch
    norms = np.linalg.norm(displacement, axis=1)
    z_disp = displacement[:, 2]
    xy_norms = np.linalg.norm(displacement[:, :2], axis=1)
    weights = 1.0 / np.maximum(patch.initial_distances, 1e-9)
    weights = weights / max(float(weights.sum()), 1e-12)
    weighted_disp = weights @ displacement
    mean_disp = displacement.mean(axis=0)
    current_rel = current_patch - np.asarray(contact_point, dtype=np.float64)[None, :]
    initial_rel = initial_patch - np.asarray(contact_point, dtype=np.float64)[None, :]
    current_dist = np.linalg.norm(current_rel, axis=1)
    initial_dist = np.linalg.norm(initial_rel, axis=1)
    centered = current_patch - current_patch.mean(axis=0, keepdims=True)
    cov = centered.T @ centered / max(current_patch.shape[0], 1)
    eigvals = np.linalg.eigvalsh(cov)
    eigvals = np.sort(np.maximum(eigvals, 0.0))
    return np.asarray(
        [
            *mean_disp.tolist(),
            *weighted_disp.tolist(),
            float(norms.mean()),
            float(norms.max()),
            float(norms.std()),
            float(z_disp.mean()),
            float(z_disp.min()),
            float(z_disp.max()),
            float(xy_norms.mean()),
            float(xy_norms.max()),
            float(current_dist.mean()),
            float(current_dist.std()),
            float((current_dist - initial_dist).mean()),
            float((current_dist - initial_dist).std()),
            *eigvals.tolist(),
        ],
        dtype=np.float64,
    )
