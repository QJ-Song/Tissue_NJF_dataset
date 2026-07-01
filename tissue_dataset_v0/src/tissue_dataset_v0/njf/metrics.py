from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def row_norms(rows: np.ndarray) -> np.ndarray:
    return np.linalg.norm(rows, axis=1)


def row_relative_l2(predicted: np.ndarray, target: np.ndarray) -> np.ndarray:
    predicted = np.asarray(predicted, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    return row_norms(predicted - target) / np.maximum(row_norms(target), 1e-12)


def row_cosines(predicted: np.ndarray, target: np.ndarray) -> np.ndarray:
    predicted = np.asarray(predicted, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    denom = row_norms(predicted) * row_norms(target)
    denom = np.maximum(denom, 1e-12)
    return np.sum(predicted * target, axis=1) / denom


def final_relative_l2(predicted_steps: np.ndarray, target_steps: np.ndarray) -> float:
    predicted_final = np.asarray(predicted_steps, dtype=np.float64).sum(axis=0)
    target_final = np.asarray(target_steps, dtype=np.float64).sum(axis=0)
    return float(np.linalg.norm(predicted_final - target_final) / max(np.linalg.norm(target_final), 1e-12))


def final_max_node_error_m(predicted_steps: np.ndarray, target_steps: np.ndarray, *, node_count: int) -> float:
    predicted_final = np.asarray(predicted_steps, dtype=np.float64).sum(axis=0).reshape(node_count, 3)
    target_final = np.asarray(target_steps, dtype=np.float64).sum(axis=0).reshape(node_count, 3)
    return float(np.linalg.norm(predicted_final - target_final, axis=1).max())


def stats(values: Iterable[float]) -> dict[str, float]:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        return {"min": 0.0, "mean": 0.0, "max": 0.0}
    return {"min": float(array.min()), "mean": float(array.mean()), "max": float(array.max())}
