#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_STATE_DIR = Path("tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/state")
DEFAULT_OUTPUT = Path("tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/isaacsim_liver_surface_deformation.usda")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export SOFA liver surface deformation state to an Isaac Sim USDA replay.")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--deformation-scale", type=float, default=1.0)
    parser.add_argument("--meters-per-unit", type=float, default=1.0)
    parser.add_argument("--show-baseline-ghost", action="store_true", help="Overlay the initial surface as a translucent debug mesh.")
    parser.add_argument("--show-displacement-vectors", action="store_true", help="Show high-displacement debug vectors.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    export_usd(args)
    print(f"Isaac Sim liver deformation USDA: {args.output}")
    return 0


def export_usd(args: argparse.Namespace) -> None:
    Usd, UsdGeom, UsdLux, UsdShade, Sdf, Gf = pxr_modules()
    state_path = args.state_dir / "surface_deformation_state.npz"
    metadata_path = args.state_dir / "metadata.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Missing state file: {state_path}")
    data = np.load(state_path)
    metadata = load_json(metadata_path)
    baseline = data["baseline_surface"].astype(np.float32)
    final = data["final_surface"].astype(np.float32)
    faces = data["faces"].astype(np.int32)
    contact_point = data["contact_point"].astype(np.float32)
    probe_start = data["probe_start"].astype(np.float32)
    probe_end = data["probe_end"].astype(np.float32)
    display_final = baseline + (final - baseline) * float(args.deformation_scale)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    stage = Usd.Stage.CreateNew(str(args.output))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, float(args.meters_per_unit))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(100)
    stage.SetFramesPerSecond(24)
    stage.SetTimeCodesPerSecond(24)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())

    materials = {
        "liver": define_material(stage, "/World/Materials/LiverTissue", (0.47, 0.09, 0.08), 0.72),
        "ghost": define_material(stage, "/World/Materials/GhostInitial", (0.18, 0.18, 0.18), 0.9, opacity=0.16),
        "tool": define_material(stage, "/World/Materials/Tool", (0.54, 0.60, 0.68), 0.25),
        "contact": define_material(stage, "/World/Materials/Contact", (0.92, 0.80, 0.18), 0.35),
    }

    animated = UsdGeom.Mesh.Define(stage, "/World/LiverSurface")
    set_mesh_topology(animated, faces)
    animated.CreateDisplayColorAttr([Gf.Vec3f(0.47, 0.09, 0.08)])
    points_attr = animated.GetPointsAttr()
    points_attr.Set(vec3f_list(Gf, baseline), Usd.TimeCode(0))
    points_attr.Set(vec3f_list(Gf, display_final), Usd.TimeCode(100))
    UsdShade.MaterialBindingAPI(animated.GetPrim()).Bind(materials["liver"])

    if args.show_baseline_ghost:
        ghost = UsdGeom.Mesh.Define(stage, "/World/BaselineGhost")
        set_mesh_topology(ghost, faces)
        ghost.GetPointsAttr().Set(vec3f_list(Gf, baseline))
        UsdShade.MaterialBindingAPI(ghost.GetPrim()).Bind(materials["ghost"])

    add_probe(stage, Gf, Usd, UsdGeom, UsdShade, materials["tool"], metadata, probe_start, probe_end)
    add_contact_marker(stage, Gf, UsdGeom, UsdShade, materials["contact"], contact_point)
    if args.show_displacement_vectors:
        add_displacement_vectors(stage, Gf, UsdGeom, baseline, display_final)
    add_lighting_and_camera(stage, Gf, UsdGeom, UsdLux, baseline, display_final)
    add_metadata(stage, metadata, args)
    stage.GetRootLayer().Export(str(args.output))


def pxr_modules():
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

    return Usd, UsdGeom, UsdLux, UsdShade, Sdf, Gf


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def set_mesh_topology(mesh: Any, faces: np.ndarray) -> None:
    mesh.CreateFaceVertexCountsAttr([3] * int(faces.shape[0]))
    mesh.CreateFaceVertexIndicesAttr([int(v) for v in faces.reshape(-1)])
    mesh.CreateSubdivisionSchemeAttr("none")


def define_material(stage: Any, path: str, color: tuple[float, float, float], roughness: float, opacity: float = 1.0):
    from pxr import Gf, Sdf, UsdShade

    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def add_probe(stage: Any, Gf: Any, Usd: Any, UsdGeom: Any, UsdShade: Any, material: Any, metadata: dict[str, Any], start: np.ndarray, end: np.ndarray) -> None:
    sphere = UsdGeom.Sphere.Define(stage, "/World/Probe")
    sphere.CreateRadiusAttr(float(metadata.get("probe_radius_scene_units", 0.45)))
    op = UsdGeom.Xformable(sphere).AddTranslateOp()
    op.Set(Gf.Vec3d(float(start[0]), float(start[1]), float(start[2])), Usd.TimeCode(0))
    op.Set(Gf.Vec3d(float(end[0]), float(end[1]), float(end[2])), Usd.TimeCode(100))
    UsdShade.MaterialBindingAPI(sphere.GetPrim()).Bind(material)


def add_contact_marker(stage: Any, Gf: Any, UsdGeom: Any, UsdShade: Any, material: Any, contact_point: np.ndarray) -> None:
    marker = UsdGeom.Sphere.Define(stage, "/World/ContactPoint")
    marker.CreateRadiusAttr(0.045)
    UsdGeom.Xformable(marker).AddTranslateOp().Set(
        Gf.Vec3d(float(contact_point[0]), float(contact_point[1]), float(contact_point[2]))
    )
    UsdShade.MaterialBindingAPI(marker.GetPrim()).Bind(material)


def add_displacement_vectors(stage: Any, Gf: Any, UsdGeom: Any, baseline: np.ndarray, final: np.ndarray) -> None:
    displacement = final - baseline
    norms = np.linalg.norm(displacement, axis=1)
    if not norms.size:
        return
    top_indices = np.argsort(norms)[-12:]
    points: list[Any] = []
    widths: list[float] = []
    for index in top_indices:
        start = baseline[index]
        end = final[index]
        points.extend([Gf.Vec3f(float(start[0]), float(start[1]), float(start[2])), Gf.Vec3f(float(end[0]), float(end[1]), float(end[2]))])
        widths.append(0.012)
    curves = UsdGeom.BasisCurves.Define(stage, "/World/DisplacementVectors")
    curves.CreateTypeAttr("linear")
    curves.CreateCurveVertexCountsAttr([2] * len(top_indices))
    curves.CreatePointsAttr(points)
    curves.CreateWidthsAttr(widths)
    curves.CreateDisplayColorAttr([Gf.Vec3f(0.05, 0.62, 0.95)])


def add_lighting_and_camera(stage: Any, Gf: Any, UsdGeom: Any, UsdLux: Any, baseline: np.ndarray, final: np.ndarray) -> None:
    all_points = np.concatenate([baseline, final], axis=0)
    min_xyz = all_points.min(axis=0)
    max_xyz = all_points.max(axis=0)
    center = (min_xyz + max_xyz) * 0.5
    extent = float(np.linalg.norm(max_xyz - min_xyz))

    key = UsdLux.SphereLight.Define(stage, "/World/KeyLight")
    key.CreateIntensityAttr(4500)
    key.CreateRadiusAttr(1.5)
    UsdGeom.Xformable(key).AddTranslateOp().Set(
        Gf.Vec3d(float(center[0] + extent * 0.4), float(center[1] - extent * 0.8), float(center[2] + extent * 0.55))
    )
    dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
    dome.CreateIntensityAttr(260)

    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    xform = UsdGeom.Xformable(camera)
    xform.AddTranslateOp().Set(
        Gf.Vec3d(float(center[0] + extent * 0.95), float(center[1] - extent * 1.35), float(center[2] + extent * 0.72))
    )
    xform.AddRotateXYZOp().Set(Gf.Vec3f(62, 0, 36))
    camera.CreateFocalLengthAttr(42)


def add_metadata(stage: Any, metadata: dict[str, Any], args: argparse.Namespace) -> None:
    world = stage.GetPrimAtPath("/World")
    world.SetCustomDataByKey("liver_surface_deformation", {
        "depth_mm": metadata.get("depth_mm"),
        "depth_scene_units": metadata.get("depth_scene_units"),
        "scene_units_per_mm": metadata.get("scene_units_per_mm"),
        "deformation_scale": float(args.deformation_scale),
        "show_baseline_ghost": bool(args.show_baseline_ghost),
        "show_displacement_vectors": bool(args.show_displacement_vectors),
        "source_state_dir": str(args.state_dir),
    })


def vec3f_list(Gf: Any, vertices: np.ndarray):
    return [Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in np.asarray(vertices, dtype=np.float32)]


if __name__ == "__main__":
    raise SystemExit(main())
