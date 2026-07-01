#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose small-depth response linearity on the standalone SOFA liver surface-collision scene."
    )
    parser.add_argument("--depths-mm", nargs="+", type=float, default=[0.05, 0.1, 0.2])
    parser.add_argument(
        "--scene-units-per-mm",
        type=float,
        default=1.0,
        help="Scene units per requested millimeter. Default 1.0 is uncalibrated; use calibrate_liver_mesh_scale.py output scale.scene_units_per_mm for physical mm.",
    )
    parser.add_argument("--preload-steps", type=int, default=80)
    parser.add_argument("--action-steps", type=int, default=40)
    parser.add_argument("--settle-steps", type=int, default=80)
    parser.add_argument("--probe-radius", type=float, default=0.45)
    parser.add_argument("--probe-clearance", type=float, default=0.0)
    parser.add_argument("--contact-distance", type=float, default=0.05)
    parser.add_argument("--contact-tolerance", type=float, default=1.0e-3)
    parser.add_argument("--linearity-threshold", type=float, default=0.10)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary.json"),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run_diagnostic(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload, args.output)
    return 0 if payload["valid"] else 1


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    Sofa, SofaRuntime, SofaSimulation = sofa_modules()
    scene = load_scene_module()
    for plugin in scene.SOFA_PLUGINS:
        SofaRuntime.importPlugin(plugin)

    depths_mm = sorted(float(item) for item in args.depths_mm)
    depth_scene_units = [depth * float(args.scene_units_per_mm) for depth in depths_mm]
    cases = []
    for depth_mm, depth_scene in zip(depths_mm, depth_scene_units, strict=True):
        cases.append(
            run_case(
                Sofa,
                SofaSimulation,
                scene,
                depth_mm=depth_mm,
                depth_scene_units=depth_scene,
                args=args,
            )
        )

    linearity_rows = analyze_linearity(cases, threshold=float(args.linearity_threshold))
    valid_cases = all(case["valid"] for case in cases)
    valid_linearity = all(row["relative_scale_error"] <= args.linearity_threshold for row in linearity_rows)
    return {
        "valid": bool(valid_cases and valid_linearity),
        "analysis_type": "liver_surface_linearity_diagnostic",
        "depths_mm": depths_mm,
        "scene_units_per_mm": float(args.scene_units_per_mm),
        "preload_steps": int(args.preload_steps),
        "action_steps": int(args.action_steps),
        "settle_steps": int(args.settle_steps),
        "contact_distance_scene_units": float(args.contact_distance),
        "contact_detection_threshold_scene_units": float(args.contact_distance + args.contact_tolerance),
        "linearity_threshold": float(args.linearity_threshold),
        "cases": cases,
        "linearity": linearity_rows,
        "notes": [
            "Each depth is simulated in a fresh scene from the same official liver mesh and contact point.",
            "The baseline state X_t is recorded after preload with the probe at zero incremental depth.",
            "Responses are final liver mechanical-node positions minus the preloaded baseline state.",
            "Use --scene-units-per-mm from scale calibration when depths should be interpreted as physical millimeters.",
        ],
    }


def run_case(
    Sofa: Any,
    SofaSimulation: Any,
    scene: Any,
    *,
    depth_mm: float,
    depth_scene_units: float,
    args: argparse.Namespace,
) -> dict[str, Any]:
    root = Sofa.Core.Node("root")
    cfg = scene.LiverSurfaceCollisionConfig(
        probe_radius=float(args.probe_radius),
        probe_clearance=float(args.probe_clearance),
        probe_depth=float(max(depth_scene_units, 1.0e-12)),
        contact_distance=float(args.contact_distance),
    )
    handles = scene.create_liver_surface_collision_scene(root, cfg)
    SofaSimulation.initRoot(root)
    try:
        start_position = handles.probe_start.astype(np.float64)
        if depth_scene_units > 0:
            direction = normalize(handles.probe_end - handles.probe_start)
        else:
            direction = np.asarray([0.0, -1.0, 0.0], dtype=np.float64)
        end_position = start_position + direction * float(depth_scene_units)
        contact_threshold = float(args.contact_distance + args.contact_tolerance)

        for _ in range(int(args.preload_steps)):
            scene.set_probe_position(handles.probe_dofs, start_position)
            SofaSimulation.animate(root, root.dt.value)
        baseline_liver = scene.object_positions(handles.liver_dofs)
        baseline_surface = scene.object_positions(handles.surface_dofs)

        min_gap = float("inf")
        first_contact_step: int | None = None
        contact_frame_count = 0
        total_motion_steps = int(args.action_steps) + int(args.settle_steps)
        for step in range(1, total_motion_steps + 1):
            if step <= int(args.action_steps):
                progress = step / max(int(args.action_steps), 1)
                probe_position = start_position + (end_position - start_position) * progress
            else:
                probe_position = end_position
            scene.set_probe_position(handles.probe_dofs, probe_position)
            SofaSimulation.animate(root, root.dt.value)
            surface = scene.object_positions(handles.surface_dofs)
            gap = signed_sphere_gap(surface, probe_position, cfg.probe_radius)
            min_gap = min(min_gap, gap)
            if gap <= contact_threshold:
                contact_frame_count += 1
                if first_contact_step is None:
                    first_contact_step = step

        final_liver = scene.object_positions(handles.liver_dofs)
        final_surface = scene.object_positions(handles.surface_dofs)
        response = final_liver - baseline_liver
        surface_response = final_surface - baseline_surface
        response_norm = float(np.linalg.norm(response.reshape(-1)))
        max_displacement = float(np.linalg.norm(response, axis=1).max())
        max_surface_displacement = float(np.linalg.norm(surface_response, axis=1).max())
        finite = bool(np.isfinite(response).all() and np.isfinite(surface_response).all())
        return {
            "valid": bool(finite and first_contact_step is not None and response_norm > 0.0),
            "depth_mm": float(depth_mm),
            "depth_scene_units": float(depth_scene_units),
            "response_norm": response_norm,
            "max_liver_displacement": max_displacement,
            "max_surface_displacement": max_surface_displacement,
            "contact_detected": first_contact_step is not None,
            "first_contact_step": first_contact_step,
            "contact_frame_count": int(contact_frame_count),
            "min_signed_gap": float(min_gap),
            "probe_start": start_position.astype(float).tolist(),
            "probe_end": end_position.astype(float).tolist(),
            "response": response.reshape(-1).astype(float).tolist(),
        }
    finally:
        SofaSimulation.unload(root)


def analyze_linearity(cases: list[dict[str, Any]], *, threshold: float) -> list[dict[str, Any]]:
    positive = [case for case in cases if case["depth_scene_units"] > 0.0 and case["valid"]]
    if len(positive) < 2:
        return []
    reference = positive[0]
    reference_response = np.asarray(reference["response"], dtype=np.float64)
    rows = []
    for case in positive[1:]:
        response = np.asarray(case["response"], dtype=np.float64)
        scale = float(case["depth_scene_units"] / reference["depth_scene_units"])
        predicted = reference_response * scale
        absolute_error = float(np.linalg.norm(response - predicted))
        response_norm = float(np.linalg.norm(response))
        relative_error = absolute_error / max(response_norm, 1.0e-12)
        rows.append(
            {
                "reference_depth_mm": reference["depth_mm"],
                "depth_mm": case["depth_mm"],
                "scale_factor": scale,
                "response_norm": response_norm,
                "scaled_reference_norm": float(np.linalg.norm(predicted)),
                "absolute_scale_error": absolute_error,
                "relative_scale_error": relative_error,
                "cosine_with_scaled_reference": cosine_similarity(response, predicted),
                "recommendation": "keep" if relative_error <= threshold else "reject_or_retest",
            }
        )
    return rows


def load_scene_module():
    scene_path = Path(__file__).resolve().parents[1] / "scenes" / "liver_surface_collision.py"
    spec = importlib.util.spec_from_file_location("liver_surface_collision_scene", scene_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scene module from {scene_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def signed_sphere_gap(points: np.ndarray, center: np.ndarray, radius: float) -> float:
    return float(np.min(np.linalg.norm(points - center[None, :], axis=1) - radius))


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return np.asarray([0.0, -1.0, 0.0], dtype=np.float64)
    return np.asarray(vector, dtype=np.float64) / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items() if key != "response"}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def sofa_modules():
    try:
        import Sofa
        import SofaRuntime
        import Sofa.Simulation
    except ImportError as exc:
        raise RuntimeError("Run this script with scripts/run_sofa_python.sh or the sofa conda environment.") from exc
    return Sofa, SofaRuntime, Sofa.Simulation


def print_text(payload: dict[str, Any], output: Path) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Liver surface action-linearity diagnostic: {status}")
    print(
        f"depths_mm={payload['depths_mm']} scene_units_per_mm={payload['scene_units_per_mm']} "
        f"output={output}"
    )
    print("Cases:")
    for case in payload["cases"]:
        print(
            f"- depth={case['depth_mm']:.4f} mm ({case['depth_scene_units']:.6f} scene units): "
            f"valid={case['valid']} contact={case['contact_detected']} "
            f"frames={case['contact_frame_count']} min_gap={case['min_signed_gap']:.6f} "
            f"norm={case['response_norm']:.6e} max_disp={case['max_liver_displacement']:.6e}"
        )
    print("Linearity:")
    if not payload["linearity"]:
        print("- not enough valid positive-depth cases")
    for row in payload["linearity"]:
        print(
            f"- {row['reference_depth_mm']:.4f}->{row['depth_mm']:.4f} mm "
            f"scale={row['scale_factor']:.3f} rel_err={row['relative_scale_error']:.6f} "
            f"cos={row['cosine_with_scaled_reference']:.6f} {row['recommendation']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
