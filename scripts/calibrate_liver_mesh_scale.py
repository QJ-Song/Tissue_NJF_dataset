#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_LOCAL_LINEAR_SCENE_UNITS = [0.05, 0.1, 0.2, 0.3, 0.5]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate official SOFA liver mesh scene units to millimeters.")
    parser.add_argument(
        "--target-long-axis-mm",
        type=float,
        default=150.0,
        help="Assumed real liver long-axis length in mm. Default: 150 mm.",
    )
    parser.add_argument(
        "--mesh",
        type=Path,
        default=None,
        help="Optional mesh path. Defaults to the SOFA liver-smooth.obj found by scenes/liver_surface_collision.py.",
    )
    parser.add_argument(
        "--mesh-type",
        choices=("auto", "obj", "gmsh"),
        default="auto",
        help="Mesh parser to use when --mesh is supplied.",
    )
    parser.add_argument(
        "--local-linear-scene-units",
        nargs="+",
        type=float,
        default=DEFAULT_LOCAL_LINEAR_SCENE_UNITS,
        help="Scene-unit action depths to convert into calibrated mm.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tissue_dataset_v0/outputs/liver_surface_scale_calibration/summary.json"),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = calibrate(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload, args.output)
    return 0


def calibrate(args: argparse.Namespace) -> dict[str, Any]:
    mesh_path, mesh_type = resolve_mesh(args)
    points = load_mesh_vertices(mesh_path, mesh_type)
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    size = maximum - minimum
    long_axis_index = int(np.argmax(size))
    long_axis_scene_units = float(size[long_axis_index])
    if long_axis_scene_units <= 0.0:
        raise ValueError(f"Mesh long-axis size must be positive: {mesh_path}")

    target_long_axis_mm = float(args.target_long_axis_mm)
    if target_long_axis_mm <= 0.0:
        raise ValueError("--target-long-axis-mm must be positive.")
    mm_per_scene_unit = target_long_axis_mm / long_axis_scene_units
    scene_units_per_mm = 1.0 / mm_per_scene_unit
    converted_depths = [
        {
            "scene_units": float(depth),
            "mm": float(depth) * mm_per_scene_unit,
        }
        for depth in args.local_linear_scene_units
    ]
    return {
        "calibration_method": "bounding_box_long_axis",
        "mesh": {
            "path": str(mesh_path),
            "name": mesh_path.name,
            "type": mesh_type,
            "vertex_count": int(points.shape[0]),
            "min_xyz_scene_units": minimum.astype(float).tolist(),
            "max_xyz_scene_units": maximum.astype(float).tolist(),
            "size_xyz_scene_units": size.astype(float).tolist(),
            "long_axis": axis_name(long_axis_index),
            "long_axis_scene_units": long_axis_scene_units,
        },
        "target": {
            "long_axis_mm": target_long_axis_mm,
        },
        "scale": {
            "mm_per_scene_unit": float(mm_per_scene_unit),
            "scene_units_per_mm": float(scene_units_per_mm),
        },
        "converted_local_linear_depths": converted_depths,
        "notes": [
            "This is a first-pass scale calibration based on a target liver long-axis length.",
            "Use --target-long-axis-mm to test different anatomical assumptions.",
            "Use scale.scene_units_per_mm when a script expects conversion from requested mm to scene units.",
        ],
    }


def resolve_mesh(args: argparse.Namespace) -> tuple[Path, str]:
    if args.mesh is not None:
        mesh_path = args.mesh
        if not mesh_path.exists():
            raise FileNotFoundError(f"Mesh file does not exist: {mesh_path}")
        mesh_type = infer_mesh_type(mesh_path) if args.mesh_type == "auto" else args.mesh_type
        return mesh_path, mesh_type

    scene = load_scene_module()
    _, surface_mesh = scene.find_liver_meshes()
    return surface_mesh, "obj"


def load_scene_module():
    scene_path = Path(__file__).resolve().parents[1] / "scenes" / "liver_surface_collision.py"
    spec = importlib.util.spec_from_file_location("liver_surface_collision_scene", scene_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scene module from {scene_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def infer_mesh_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".obj":
        return "obj"
    if suffix == ".msh":
        return "gmsh"
    raise ValueError(f"Cannot infer mesh type from suffix {suffix!r}; pass --mesh-type.")


def load_mesh_vertices(path: Path, mesh_type: str) -> np.ndarray:
    if mesh_type == "obj":
        return load_obj_vertices(path)
    if mesh_type == "gmsh":
        return load_gmsh_vertices(path)
    raise ValueError(f"Unsupported mesh type: {mesh_type}")


def load_obj_vertices(path: Path) -> np.ndarray:
    points: list[list[float]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                points.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return vertices_array(points, path)


def load_gmsh_vertices(path: Path) -> np.ndarray:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    points: list[list[float]] = []
    for index, line in enumerate(lines):
        if line.strip() != "$Nodes":
            continue
        if index + 1 >= len(lines):
            break
        node_count = int(lines[index + 1].strip())
        for node_line in lines[index + 2 : index + 2 + node_count]:
            parts = node_line.split()
            if len(parts) < 4:
                continue
            points.append([float(parts[1]), float(parts[2]), float(parts[3])])
        break
    return vertices_array(points, path)


def vertices_array(points: list[list[float]], path: Path) -> np.ndarray:
    if not points:
        raise ValueError(f"Mesh file has no readable vertices: {path}")
    return np.asarray(points, dtype=np.float64)


def axis_name(index: int) -> str:
    return ("x", "y", "z")[index]


def jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def print_text(payload: dict[str, Any], output: Path) -> None:
    mesh = payload["mesh"]
    scale = payload["scale"]
    print("Liver mesh scale calibration: PASS")
    print(f"mesh={mesh['name']} type={mesh['type']} vertices={mesh['vertex_count']}")
    print(
        "bbox_scene_units="
        f"x={mesh['size_xyz_scene_units'][0]:.6f} "
        f"y={mesh['size_xyz_scene_units'][1]:.6f} "
        f"z={mesh['size_xyz_scene_units'][2]:.6f}"
    )
    print(
        f"long_axis={mesh['long_axis']} size={mesh['long_axis_scene_units']:.6f} scene units "
        f"target={payload['target']['long_axis_mm']:.3f} mm"
    )
    print(
        f"mm_per_scene_unit={scale['mm_per_scene_unit']:.6f} "
        f"scene_units_per_mm={scale['scene_units_per_mm']:.8f}"
    )
    print("Converted local-linear depths:")
    for item in payload["converted_local_linear_depths"]:
        print(f"- {item['scene_units']:.6f} scene units -> {item['mm']:.6f} mm")
    print(f"output={output}")


if __name__ == "__main__":
    raise SystemExit(main())
