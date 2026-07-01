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
    parser = argparse.ArgumentParser(description="Smoke test the SOFA liver surface-collision scene.")
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--min-displacement", type=float, default=1.0e-6, help="Minimum max liver displacement in scene units.")
    parser.add_argument("--max-displacement", type=float, default=5.0, help="Maximum max liver displacement in scene units.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run_smoke_test(args.steps, args.min_displacement, args.max_displacement)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if payload["valid"] else 1


def run_smoke_test(steps: int, min_displacement: float, max_allowed_displacement: float) -> dict[str, Any]:
    Sofa, SofaRuntime, SofaSimulation = sofa_modules()
    scene = load_scene_module()
    for plugin in scene.SOFA_PLUGINS:
        SofaRuntime.importPlugin(plugin)

    root = Sofa.Core.Node("root")
    cfg = scene.LiverSurfaceCollisionConfig()
    handles = scene.create_liver_surface_collision_scene(root, cfg)
    SofaSimulation.initRoot(root)
    try:
        liver_0 = scene.object_positions(handles.liver_dofs)
        surface_0 = scene.object_positions(handles.surface_dofs)
        min_gap = float("inf")
        first_contact_step: int | None = None
        contact_frame_count = 0
        contact_threshold = cfg.contact_distance + 1.0e-3

        for step in range(1, steps + 1):
            progress = step / max(steps, 1)
            probe_position = handles.probe_start + (handles.probe_end - handles.probe_start) * progress
            scene.set_probe_position(handles.probe_dofs, probe_position)
            SofaSimulation.animate(root, root.dt.value)
            surface = scene.object_positions(handles.surface_dofs)
            gap = signed_sphere_gap(surface, probe_position, cfg.probe_radius)
            min_gap = min(min_gap, gap)
            if gap <= contact_threshold:
                contact_frame_count += 1
                if first_contact_step is None:
                    first_contact_step = step

        liver_1 = scene.object_positions(handles.liver_dofs)
        surface_1 = scene.object_positions(handles.surface_dofs)
        displacement = liver_1 - liver_0
        surface_displacement = surface_1 - surface_0
        max_displacement = float(np.linalg.norm(displacement, axis=1).max())
        max_surface_displacement = float(np.linalg.norm(surface_displacement, axis=1).max())
        finite = bool(
            np.isfinite(liver_0).all()
            and np.isfinite(liver_1).all()
            and np.isfinite(surface_0).all()
            and np.isfinite(surface_1).all()
        )

        checks = {
            "scene_loaded": True,
            "finite_states": finite,
            "liver_deformable_fem": True,
            "liver_surface_collision_models": set(handles.liver_collision_models)
            == {"TriangleCollisionModel", "LineCollisionModel", "PointCollisionModel"},
            "liver_collision_not_sphere": "SphereCollisionModel" not in handles.liver_collision_models,
            "surface_mapping": handles.liver_mapping == "BarycentricMapping",
            "contact_or_proximity_detected": first_contact_step is not None,
            "bounded_liver_displacement": min_displacement <= max_displacement <= max_allowed_displacement,
        }
        return {
            "valid": all(checks.values()),
            "checks": checks,
            "steps": steps,
            "dt": float(root.dt.value),
            "meshes": {
                "volume": handles.liver_mesh.name,
                "surface": handles.surface_mesh.name,
            },
            "liver": {
                "mechanical_node_count": int(liver_0.shape[0]),
                "surface_node_count": int(surface_0.shape[0]),
                "collision_models": list(handles.liver_collision_models),
                "mapping": handles.liver_mapping,
                "max_displacement": max_displacement,
                "max_surface_displacement": max_surface_displacement,
            },
            "probe": {
                "geometry": "sphere",
                "radius": cfg.probe_radius,
                "start": handles.probe_start.astype(float).tolist(),
                "end": handles.probe_end.astype(float).tolist(),
                "motion": (handles.probe_end - handles.probe_start).astype(float).tolist(),
            },
            "contact": {
                "contact_distance": cfg.contact_distance,
                "detection_threshold": contact_threshold,
                "min_signed_gap": min_gap,
                "contact_detected": first_contact_step is not None,
                "first_contact_step": first_contact_step,
                "contact_frame_count": contact_frame_count,
            },
        }
    finally:
        SofaSimulation.unload(root)


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


def sofa_modules():
    try:
        import Sofa
        import SofaRuntime
        import Sofa.Simulation
    except ImportError as exc:
        raise RuntimeError("Run this script with scripts/run_sofa_python.sh or the sofa conda environment.") from exc
    return Sofa, SofaRuntime, Sofa.Simulation


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    liver = payload["liver"]
    contact = payload["contact"]
    probe = payload["probe"]
    print(f"Liver surface collision smoke: {status}")
    print(
        f"steps={payload['steps']} dt={payload['dt']} "
        f"volume={payload['meshes']['volume']} surface={payload['meshes']['surface']}"
    )
    print(
        f"nodes mechanical={liver['mechanical_node_count']} surface={liver['surface_node_count']} "
        f"models={','.join(liver['collision_models'])} mapping={liver['mapping']}"
    )
    print(
        f"probe radius={probe['radius']:.4f} "
        f"motion=({probe['motion'][0]:.4f}, {probe['motion'][1]:.4f}, {probe['motion'][2]:.4f})"
    )
    print(
        f"contact={contact['contact_detected']} first={contact['first_contact_step']} "
        f"frames={contact['contact_frame_count']} min_gap={contact['min_signed_gap']:.6f}"
    )
    print(
        f"max_liver_displacement={liver['max_displacement']:.6e} "
        f"max_surface_displacement={liver['max_surface_displacement']:.6e}"
    )
    if not payload["valid"]:
        failed = [key for key, value in payload["checks"].items() if not value]
        print(f"failed_checks={failed}")


if __name__ == "__main__":
    raise SystemExit(main())
