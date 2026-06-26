#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tissue_dataset_v0.njf.dataset import NJFDataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-read SOFA NJF Mode A/B/C datasets without SOFA runtime.")
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--require-mode", action="append", default=[], choices=("local_perturbation", "response_basis_group", "rollout_trajectory"))
    parser.add_argument("--min-groups", type=int, default=0)
    parser.add_argument("--min-trajectories", type=int, default=0)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = NJFDataset(args.dataset_root)
    summary = dataset.summary()
    issues = dataset.validate_training_view()
    payload = summary.to_dict()
    for mode in args.require_mode:
        if payload["mode_counts"].get(mode, 0) <= 0:
            issues.append(f"Required mode has no samples: {mode}")
    if payload["group_count"] < args.min_groups:
        issues.append(f"group_count {payload['group_count']} < required {args.min_groups}")
    if payload["trajectory_count"] < args.min_trajectories:
        issues.append(f"trajectory_count {payload['trajectory_count']} < required {args.min_trajectories}")
    payload["valid"] = not issues
    payload["issues"] = issues
    payload["loader_features"] = inspect_features(dataset)
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if payload["valid"] else 1


def inspect_features(dataset: NJFDataset) -> dict[str, Any]:
    features: dict[str, Any] = {}
    first_local = next(dataset.iter_local_samples(modes=("local_perturbation", "response_basis_group")), None)
    if first_local is not None:
        features["local_record"] = {
            "x_t_shape": list(first_local.x_t.shape),
            "delta_x_shape": list(first_local.delta_x.shape),
            "action_shape": list(first_local.action.shape),
            "delta_a_shape": list(first_local.delta_a.shape),
            "fixed_node_mask_shape": list(first_local.fixed_node_mask.shape),
            "ids": first_local.ids,
        }
    first_group = next(dataset.iter_basis_groups(), None)
    if first_group is not None:
        features["basis_group"] = {
            "state_initial_shape": list(first_group.state_initial.shape),
            "actions_shape": list(first_group.actions.shape),
            "responses_shape": list(first_group.responses.shape),
            "response_matrix_shape": list(first_group.response_matrix.shape),
            "ids": first_group.ids,
        }
    first_traj = next(dataset.iter_rollout_trajectories(), None)
    if first_traj is not None:
        features["rollout_trajectory"] = {
            "states_shape": list(first_traj.states.shape),
            "actions_shape": list(first_traj.actions.shape),
            "responses_shape": list(first_traj.responses.shape),
            "step_count": first_traj.step_count,
            "first_step_keys": sorted(next(first_traj.iter_steps()).keys()) if first_traj.step_count else [],
        }
    return features


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"NJF dataset read: {status}")
    print(
        f"samples={payload['sample_count']} modes={payload['mode_counts']} "
        f"groups={payload['group_count']} trajectories={payload['trajectory_count']}"
    )
    print(f"action_dim={payload['action_dim']} materials={payload['material_ids']} contacts={payload['contact_point_ids']}")
    print(f"local_shape={payload['local_sample_shape']} group_response_shape={payload['group_response_shape']} trajectory_state_shape={payload['trajectory_state_shape']}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"- {issue}")
    print("loader_features:")
    for key, value in payload["loader_features"].items():
        print(f"- {key}: {value}")


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
