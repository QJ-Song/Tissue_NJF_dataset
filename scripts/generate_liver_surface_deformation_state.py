#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_OUTPUT = Path("tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/state")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SOFA liver surface deformation state for Isaac Sim replay.")
    parser.add_argument("--depth-mm", type=float, default=2.0)
    parser.add_argument(
        "--scene-units-per-mm",
        type=float,
        default=0.0425757,
        help="Scale from calibrated physical millimeters to official liver scene units.",
    )
    parser.add_argument("--preload-steps", type=int, default=80)
    parser.add_argument("--action-steps", type=int, default=40)
    parser.add_argument("--settle-steps", type=int, default=80)
    parser.add_argument("--probe-radius", type=float, default=0.45)
    parser.add_argument("--probe-clearance", type=float, default=0.0)
    parser.add_argument("--contact-distance", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = generate_state(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(payload["metadata"], indent=2, sort_keys=True), encoding="utf-8")
    np.savez_compressed(
        args.output_dir / "surface_deformation_state.npz",
        rest_surface=payload["rest_surface"],
        baseline_surface=payload["baseline_surface"],
        final_surface=payload["final_surface"],
        faces=payload["faces"],
        contact_point=payload["contact_point"],
        probe_start=payload["probe_start"],
        probe_end=payload["probe_end"],
    )
    result = {
        "valid": payload["metadata"]["valid"],
        "output_dir": str(args.output_dir),
        "state_npz": str(args.output_dir / "surface_deformation_state.npz"),
        "metadata": payload["metadata"],
    }
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0 if result["valid"] else 1


def generate_state(args: argparse.Namespace) -> dict[str, Any]:
    Sofa, SofaRuntime, SofaSimulation = sofa_modules()
    scene = load_scene_module()
    for plugin in scene.SOFA_PLUGINS:
        SofaRuntime.importPlugin(plugin)

    root = Sofa.Core.Node("root")
    depth_scene_units = float(args.depth_mm) * float(args.scene_units_per_mm)
    cfg = scene.LiverSurfaceCollisionConfig(
        probe_radius=float(args.probe_radius),
        probe_clearance=float(args.probe_clearance),
        probe_depth=max(depth_scene_units, 1.0e-12),
        contact_distance=float(args.contact_distance),
    )
    handles = scene.create_liver_surface_collision_scene(root, cfg)
    faces = load_obj_triangles(handles.surface_mesh)
    SofaSimulation.initRoot(root)
    try:
        rest_surface = scene.object_positions(handles.surface_dofs)
        start_position = handles.probe_start.astype(np.float64)
        direction = normalize(handles.probe_end - handles.probe_start)
        end_position = start_position + direction * depth_scene_units

        for _ in range(int(args.preload_steps)):
            scene.set_probe_position(handles.probe_dofs, start_position)
            SofaSimulation.animate(root, root.dt.value)
        baseline_surface = scene.object_positions(handles.surface_dofs)

        min_gap = float("inf")
        first_contact_step: int | None = None
        contact_frame_count = 0
        contact_threshold = cfg.contact_distance + 1.0e-3
        total_steps = int(args.action_steps) + int(args.settle_steps)
        for step in range(1, total_steps + 1):
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

        final_surface = scene.object_positions(handles.surface_dofs)
        displacement = final_surface - baseline_surface
        norms = np.linalg.norm(displacement, axis=1)
        valid = bool(np.isfinite(final_surface).all() and first_contact_step is not None and float(norms.max()) > 0.0)
        metadata = {
            "valid": valid,
            "source": "scenes/liver_surface_collision.py",
            "surface_mesh": handles.surface_mesh.name,
            "volume_mesh": handles.liver_mesh.name,
            "depth_mm": float(args.depth_mm),
            "scene_units_per_mm": float(args.scene_units_per_mm),
            "depth_scene_units": depth_scene_units,
            "probe_radius_scene_units": float(args.probe_radius),
            "probe_clearance_scene_units": float(args.probe_clearance),
            "contact_distance_scene_units": float(args.contact_distance),
            "preload_steps": int(args.preload_steps),
            "action_steps": int(args.action_steps),
            "settle_steps": int(args.settle_steps),
            "surface_node_count": int(final_surface.shape[0]),
            "face_count": int(faces.shape[0]),
            "first_contact_step": first_contact_step,
            "contact_frame_count": int(contact_frame_count),
            "min_signed_gap_scene_units": float(min_gap),
            "max_surface_displacement_scene_units": float(norms.max()),
            "mean_surface_displacement_scene_units": float(norms.mean()),
        }
        return {
            "metadata": metadata,
            "rest_surface": rest_surface.astype(np.float32),
            "baseline_surface": baseline_surface.astype(np.float32),
            "final_surface": final_surface.astype(np.float32),
            "faces": faces.astype(np.int32),
            "contact_point": handles.contact_point.astype(np.float32),
            "probe_start": start_position.astype(np.float32),
            "probe_end": end_position.astype(np.float32),
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


def load_obj_triangles(path: Path) -> np.ndarray:
    triangles: list[list[int]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("f "):
                continue
            indices = [parse_obj_index(part) for part in line.split()[1:]]
            if len(indices) < 3:
                continue
            for i in range(1, len(indices) - 1):
                triangles.append([indices[0], indices[i], indices[i + 1]])
    if not triangles:
        raise ValueError(f"No triangles found in OBJ mesh: {path}")
    return np.asarray(triangles, dtype=np.int32)


def parse_obj_index(token: str) -> int:
    return int(token.split("/")[0]) - 1


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return np.asarray([0.0, -1.0, 0.0], dtype=np.float64)
    return np.asarray(vector, dtype=np.float64) / norm


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


def print_text(result: dict[str, Any]) -> None:
    metadata = result["metadata"]
    status = "PASS" if result["valid"] else "FAIL"
    print(f"Liver surface deformation state: {status}")
    print(f"output_dir={result['output_dir']}")
    print(f"state_npz={result['state_npz']}")
    print(
        f"depth={metadata['depth_mm']:.3f} mm "
        f"({metadata['depth_scene_units']:.6f} scene units) "
        f"surface_nodes={metadata['surface_node_count']} faces={metadata['face_count']}"
    )
    print(
        f"contact_first={metadata['first_contact_step']} frames={metadata['contact_frame_count']} "
        f"max_surface_displacement={metadata['max_surface_displacement_scene_units']:.6f} scene units"
    )


if __name__ == "__main__":
    raise SystemExit(main())
