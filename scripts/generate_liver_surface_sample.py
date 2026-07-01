#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TISSUE_SRC = ROOT / "tissue_dataset_v0" / "src"
for path in (ROOT, TISSUE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scenes.liver_surface_collision import (  # noqa: E402
    LiverSurfaceCollisionConfig,
    create_liver_surface_collision_scene,
    load_obj_vertices,
    object_positions,
    set_probe_position,
)
from tissue_dataset_v0.layout import default_layout  # noqa: E402
from tissue_dataset_v0.logger import DirectorySimulationLogger  # noqa: E402
from tissue_dataset_v0.schema import (  # noqa: E402
    ActionSpec,
    GeometryConfig,
    LoggingConfig,
    MaterialConfig,
    SampleConfig,
    SampleRequest,
    SampleResult,
)
from tissue_dataset_v0.trajectory import write_trajectory_summary  # noqa: E402
from tissue_dataset_v0.writer import FileSystemSampleWriter  # noqa: E402


DEFAULT_OUTPUT = ROOT / "tissue_dataset_v0" / "outputs" / "liver_surface_contact_sample"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dataset sample(s) from the standalone official-liver surface-collision scene."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-id", type=int, default=1)
    parser.add_argument("--layout", choices=("flat", "grouped"), default="flat", help="flat writes sample_* directly under output; grouped writes samples/ and groups/group_000001.")
    parser.add_argument("--group-id", default="group_000001")
    parser.add_argument("--contact-set", choices=("top_center", "top_three"), default="top_center")
    parser.add_argument("--direction-set", choices=("vertical", "basis_smoke", "basis_v1", "basis_v2"), default="vertical")
    parser.add_argument("--direction-id", default=None, help="Optional direction id selected from --direction-set; generates only that direction.")
    parser.add_argument("--material-set", choices=("single", "young_three"), default="single")
    parser.add_argument("--depth-mm", type=float, default=2.0)
    parser.add_argument("--depths-mm", nargs="+", type=float, default=None, help="Generate one sample per depth in mm. Overrides --depth-mm.")
    parser.add_argument("--target-long-axis-mm", type=float, default=150.0)
    parser.add_argument("--probe-radius-mm", type=float, default=10.0)
    parser.add_argument("--probe-clearance-mm", type=float, default=0.0)
    parser.add_argument("--contact-distance-mm", type=float, default=0.1, help="SOFA contact response threshold in mm.")
    parser.add_argument("--contact-observation-distance-mm", type=float, default=1.2, help="Vertex-gap observation threshold for contact_summary only.")
    parser.add_argument("--alarm-distance-mm", type=float, default=12.0)
    parser.add_argument("--preload-steps", type=int, default=60, help="Settle the initial contact pose before recording X_t.")
    parser.add_argument("--action-steps", type=int, default=40, help="Steps used to move the probe from tool_pose_0 to tool_pose_1.")
    parser.add_argument("--settle-steps", type=int, default=80, help="Steps to hold the final probe pose before recording X_next.")
    parser.add_argument("--total-steps", type=int, default=None, help="Deprecated alias for action+settle total when action/settle are not customized.")
    parser.add_argument("--log-every-n", type=int, default=10)
    parser.add_argument("--dt", type=float, default=0.005)
    parser.add_argument("--young-modulus", type=float, default=3000.0)
    parser.add_argument("--poisson-ratio", type=float, default=0.3)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    depths_mm = tuple(float(v) for v in (args.depths_mm if args.depths_mm is not None else [args.depth_mm]))
    if not depths_mm:
        raise ValueError("At least one depth must be provided.")
    for depth_mm in depths_mm:
        if depth_mm <= 0.0:
            raise ValueError("All depths must be positive.")
    if args.target_long_axis_mm <= 0.0:
        raise ValueError("--target-long-axis-mm must be positive.")

    Sofa, _ = load_sofa()
    calibration, mesh_info, surface_vertices_scene = load_calibration(Sofa, args)
    directions = filter_direction_specs(direction_specs(args.direction_set), args.direction_id)
    contacts = contact_point_specs(surface_vertices_scene, args.contact_set)
    materials = material_specs(args.material_set, args.young_modulus, args.poisson_ratio)
    writer = FileSystemSampleWriter(default_layout())
    records = []
    group_records = []
    offset = 0
    group_index = 0
    total_groups = len(contacts) * len(materials)
    for contact_id, contact_point_scene in contacts:
        for material_id, young_modulus, poisson_ratio in materials:
            group_index += 1
            group_id = args.group_id if total_groups == 1 else f"group_{group_index:06d}"
            sample_dirs: list[Path] = []
            for direction_id, direction in directions:
                for depth_mm in depths_mm:
                    sample_id = int(args.sample_id + offset)
                    sample_dir, summary = generate_one_sample(
                        Sofa=Sofa,
                        args=args,
                        sample_id=sample_id,
                        depth_mm=float(depth_mm),
                        direction_id=direction_id,
                        direction_dataset=direction,
                        calibration=calibration,
                        writer=writer,
                        contact_id=contact_id,
                        contact_point_scene=contact_point_scene,
                        material_id=material_id,
                        young_modulus=young_modulus,
                        poisson_ratio=poisson_ratio,
                        group_id=group_id,
                    )
                    sample_dirs.append(sample_dir)
                    records.append({"sample_id": sample_dir.name, "path": str(sample_dir.relative_to(args.output)), **summary})
                    print(f"Generated liver surface sample: {sample_dir}")
                    print(f"  contact: {contact_id}")
                    print(f"  material: {material_id} E={young_modulus:.1f} nu={poisson_ratio:.3f}")
                    print(f"  direction: {direction_id} {direction.tolist()}")
                    print(f"  depth: {depth_mm:.3f} mm")
                    print(f"  max displacement: {summary['max_displacement'] * 1000.0:.3f} mm")
                    print(f"  contact detected: {summary['contact_detected']}")
                    offset += 1
            if args.layout == "grouped":
                group_records.append(write_mode_b_group(args.output, group_id, sample_dirs, directions, contact_id=contact_id, material_id=material_id))
    write_bridge_metadata(args.output, args, depths_mm, calibration, mesh_info, records, group_records=group_records)
    return 0


def load_sofa() -> tuple[Any, Any]:
    try:
        import Sofa  # type: ignore
        import SofaRuntime  # type: ignore
    except ImportError as exc:
        raise RuntimeError("SOFA Python modules are unavailable. Run through scripts/run_sofa_python.sh.") from exc
    return Sofa, SofaRuntime


def load_calibration(Sofa: Any, args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, str], np.ndarray]:
    root = Sofa.Core.Node("root")
    temp = create_liver_surface_collision_scene(root, LiverSurfaceCollisionConfig(dt=args.dt))
    surface_vertices_scene = load_obj_vertices(temp.surface_mesh)
    calibration = calibrate_surface(surface_vertices_scene, args.target_long_axis_mm)
    mesh_info = {"volume_mesh": temp.liver_mesh.name, "surface_mesh": temp.surface_mesh.name}
    Sofa.Simulation.unload(root)
    return calibration, mesh_info, surface_vertices_scene


def action_and_settle_steps(args: argparse.Namespace) -> tuple[int, int, int]:
    action_steps = max(int(args.action_steps), 1)
    settle_steps = max(int(args.settle_steps), 0)
    if args.total_steps is not None and (args.action_steps, args.settle_steps) == (40, 80):
        total_steps = max(int(args.total_steps), 1)
        action_steps = min(action_steps, total_steps)
        settle_steps = max(total_steps - action_steps, 0)
    total_steps = action_steps + settle_steps
    return action_steps, settle_steps, total_steps


def filter_direction_specs(
    directions: tuple[tuple[str, np.ndarray], ...],
    direction_id: str | None,
) -> tuple[tuple[str, np.ndarray], ...]:
    if direction_id is None:
        return directions
    filtered = tuple((name, direction) for name, direction in directions if name == direction_id)
    if not filtered:
        available = ", ".join(name for name, _ in directions)
        raise ValueError(f"Unknown --direction-id {direction_id!r}; available: {available}")
    return filtered


def direction_specs(name: str) -> tuple[tuple[str, np.ndarray], ...]:
    if name == "vertical":
        return (("normal", np.asarray([0.0, 0.0, -1.0], dtype=np.float64)),)
    if name == "basis_smoke":
        tilt = np.deg2rad(12.0)
        sin_t = float(np.sin(tilt))
        cos_t = float(np.cos(tilt))
        return (
            ("normal", np.asarray([0.0, 0.0, -1.0], dtype=np.float64)),
            ("tilt_x", normalize_vector(np.asarray([sin_t, 0.0, -cos_t], dtype=np.float64))),
            ("tilt_y", normalize_vector(np.asarray([0.0, sin_t, -cos_t], dtype=np.float64))),
        )
    if name == "basis_v1":
        tilt = np.deg2rad(12.0)
        sin_t = float(np.sin(tilt))
        cos_t = float(np.cos(tilt))
        return (
            ("normal", np.asarray([0.0, 0.0, -1.0], dtype=np.float64)),
            ("tilt_pos_x", normalize_vector(np.asarray([sin_t, 0.0, -cos_t], dtype=np.float64))),
            ("tilt_neg_x", normalize_vector(np.asarray([-sin_t, 0.0, -cos_t], dtype=np.float64))),
            ("tilt_pos_y", normalize_vector(np.asarray([0.0, sin_t, -cos_t], dtype=np.float64))),
            ("tilt_neg_y", normalize_vector(np.asarray([0.0, -sin_t, -cos_t], dtype=np.float64))),
            ("tilt_diag_xy", normalize_vector(np.asarray([sin_t / np.sqrt(2.0), sin_t / np.sqrt(2.0), -cos_t], dtype=np.float64))),
        )
    if name == "basis_v2":
        return basis_v2_direction_specs()
    raise ValueError(f"Unsupported direction set: {name}")


def basis_v2_direction_specs() -> tuple[tuple[str, np.ndarray], ...]:
    """Single-contact action family beyond the basis_v1 small-cone press set.

    Pure tangential motion and retraction need additional contact-state handling.
    The shear-like directions below keep a substantial inward normal component
    so the current single-step surface-contact scene remains well defined.
    """

    directions: list[tuple[str, np.ndarray]] = [("normal", np.asarray([0.0, 0.0, -1.0], dtype=np.float64))]
    directions.extend(cardinal_tilt_directions("oblique15", 15.0))
    directions.extend(cardinal_tilt_directions("oblique30", 30.0))
    directions.extend(cardinal_tilt_directions("mixed40", 40.0))
    directions.extend(cardinal_tilt_directions("shear60", 60.0))
    return tuple(directions)


def cardinal_tilt_directions(prefix: str, tilt_deg: float) -> tuple[tuple[str, np.ndarray], ...]:
    tilt = np.deg2rad(float(tilt_deg))
    sin_t = float(np.sin(tilt))
    cos_t = float(np.cos(tilt))
    return (
        (f"{prefix}_pos_x", normalize_vector(np.asarray([sin_t, 0.0, -cos_t], dtype=np.float64))),
        (f"{prefix}_neg_x", normalize_vector(np.asarray([-sin_t, 0.0, -cos_t], dtype=np.float64))),
        (f"{prefix}_pos_y", normalize_vector(np.asarray([0.0, sin_t, -cos_t], dtype=np.float64))),
        (f"{prefix}_neg_y", normalize_vector(np.asarray([0.0, -sin_t, -cos_t], dtype=np.float64))),
    )


def probe_approach_direction(direction_set: str, direction_id: str, motion_direction: np.ndarray) -> np.ndarray:
    if direction_set == "basis_v2":
        return np.asarray([0.0, 0.0, -1.0], dtype=np.float64)
    return normalize_vector(np.asarray(motion_direction, dtype=np.float64))


def configure_probe_path(
    handles: Any,
    cfg: LiverSurfaceCollisionConfig,
    motion_direction_dataset: np.ndarray,
    approach_direction_dataset: np.ndarray,
) -> None:
    motion_scene = dataset_direction_to_sofa(motion_direction_dataset)
    approach_scene = dataset_direction_to_sofa(approach_direction_dataset)
    contact_point = np.asarray(handles.contact_point, dtype=np.float64)
    handles.probe_start = contact_point - approach_scene * (float(cfg.probe_radius) + float(cfg.probe_clearance))
    handles.probe_end = handles.probe_start + motion_scene * float(cfg.probe_depth)


def normalize_vector(value: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(value))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize near-zero vector")
    return np.asarray(value, dtype=np.float64) / norm


def dataset_direction_to_sofa(direction_dataset: np.ndarray) -> np.ndarray:
    direction = normalize_vector(np.asarray(direction_dataset, dtype=np.float64))
    return normalize_vector(np.asarray([direction[0], direction[2], direction[1]], dtype=np.float64))


def contact_point_specs(surface_vertices_scene: np.ndarray, name: str) -> tuple[tuple[str, np.ndarray], ...]:
    points = np.asarray(surface_vertices_scene, dtype=np.float64)
    max_y = float(points[:, 1].max())
    min_y = float(points[:, 1].min())
    band = max((max_y - min_y) * 0.08, 1e-6)
    top_points = points[points[:, 1] >= max_y - band]
    if top_points.size == 0:
        raise ValueError("No top-surface points available for contact sampling")

    def pick(label: str, x_fraction: float) -> tuple[str, np.ndarray]:
        x_min = float(top_points[:, 0].min())
        x_max = float(top_points[:, 0].max())
        target_x = x_min + (x_max - x_min) * x_fraction
        target_z = float(np.median(top_points[:, 2]))
        target = np.asarray([target_x, target_z], dtype=np.float64)
        distances = np.linalg.norm(top_points[:, [0, 2]] - target[None, :], axis=1)
        return label, top_points[int(np.argmin(distances))].astype(np.float64)

    if name == "top_center":
        return (pick("contact_top_center_000001", 0.5),)
    if name == "top_three":
        return (
            pick("contact_top_left_000001", 0.30),
            pick("contact_top_center_000001", 0.50),
            pick("contact_top_right_000001", 0.70),
        )
    raise ValueError(f"Unsupported contact set: {name}")


def material_specs(name: str, young_modulus: float, poisson_ratio: float) -> tuple[tuple[str, float, float], ...]:
    if name == "single":
        return (("material_000001", float(young_modulus), float(poisson_ratio)),)
    if name == "young_three":
        return (
            ("material_young_1000", 1000.0, float(poisson_ratio)),
            ("material_young_3000", 3000.0, float(poisson_ratio)),
            ("material_young_10000", 10000.0, float(poisson_ratio)),
        )
    raise ValueError(f"Unsupported material set: {name}")


def generate_one_sample(
    *,
    Sofa: Any,
    args: argparse.Namespace,
    sample_id: int,
    depth_mm: float,
    direction_id: str,
    direction_dataset: np.ndarray,
    calibration: dict[str, Any],
    writer: FileSystemSampleWriter,
    contact_id: str,
    contact_point_scene: np.ndarray,
    material_id: str,
    young_modulus: float,
    poisson_ratio: float,
    group_id: str | None,
) -> tuple[Path, dict[str, Any]]:
    scene_units_per_mm = float(calibration["scene_units_per_mm"])
    meters_per_scene_unit = float(calibration["mm_per_scene_unit"]) / 1000.0
    action_steps, settle_steps, total_steps = action_and_settle_steps(args)
    approach_direction_dataset = probe_approach_direction(args.direction_set, direction_id, direction_dataset)
    cfg = LiverSurfaceCollisionConfig(
        dt=args.dt,
        young_modulus=young_modulus,
        poisson_ratio=poisson_ratio,
        probe_radius=args.probe_radius_mm * scene_units_per_mm,
        probe_clearance=args.probe_clearance_mm * scene_units_per_mm,
        probe_depth=depth_mm * scene_units_per_mm,
        probe_direction=tuple(dataset_direction_to_sofa(approach_direction_dataset).tolist()),
        contact_point=tuple(np.asarray(contact_point_scene, dtype=np.float64).tolist()),
        alarm_distance=args.alarm_distance_mm * scene_units_per_mm,
        contact_distance=args.contact_distance_mm * scene_units_per_mm,
    )
    root = Sofa.Core.Node("root")
    handles = create_liver_surface_collision_scene(root, cfg)
    configure_probe_path(handles, cfg, direction_dataset, approach_direction_dataset)
    Sofa.Simulation.initRoot(root)
    set_probe_position(handles.probe_dofs, handles.probe_start)
    for _ in range(max(int(args.preload_steps), 0)):
        Sofa.Simulation.animate(root, root.dt.value)

    sample_root = args.output / "samples" if args.layout == "grouped" else args.output
    sample_dir = sample_root / f"sample_{sample_id:06d}"
    prepare_sample_dir(sample_dir, overwrite=args.overwrite)

    faces = load_obj_triangles(handles.surface_mesh)
    request = build_request(args, sample_id, depth_mm, direction_id, direction_dataset, approach_direction_dataset, calibration, handles, cfg, meters_per_scene_unit, contact_id=contact_id, material_id=material_id, young_modulus=young_modulus, poisson_ratio=poisson_ratio, group_id=group_id)
    logger = DirectorySimulationLogger(sample_dir / "logs")
    logger.begin(request)

    surface_0_scene = object_positions(handles.surface_dofs)
    surface_0 = to_dataset_meters(surface_0_scene, meters_per_scene_unit)
    contact_observations: list[dict[str, Any]] = []

    probe_scene = handles.probe_start.copy()
    observation = contact_observation(surface_0_scene, probe_scene, cfg, meters_per_scene_unit, args.contact_observation_distance_mm, 0, 0.0)
    contact_observations.append(observation)
    record_logged_frame(logger, request, surface_0_scene, probe_scene, observation, cfg, meters_per_scene_unit, step=0, progress=0.0)

    for step in range(1, total_steps + 1):
        if step <= action_steps:
            progress = step / max(action_steps, 1)
        else:
            progress = 1.0
        probe_scene = handles.probe_start + progress * (handles.probe_end - handles.probe_start)
        set_probe_position(handles.probe_dofs, probe_scene)
        Sofa.Simulation.animate(root, root.dt.value)
        surface_scene = object_positions(handles.surface_dofs)
        observation = contact_observation(surface_scene, probe_scene, cfg, meters_per_scene_unit, args.contact_observation_distance_mm, step, step * cfg.dt)
        contact_observations.append(observation)
        if step % max(args.log_every_n, 1) == 0 or step == total_steps:
            record_logged_frame(logger, request, surface_scene, probe_scene, observation, cfg, meters_per_scene_unit, step=step, progress=progress)

    surface_1_scene = object_positions(handles.surface_dofs)
    surface_1 = to_dataset_meters(surface_1_scene, meters_per_scene_unit)
    displacement = surface_1 - surface_0
    contact_summary = build_contact_summary(contact_observations)
    boundary_payload = surface_boundary_payload(surface_0)
    summary = {
        "backend": "official_liver_surface_collision_bridge",
        "sample_id": int(sample_id),
        "scene_id": "official_liver_surface_collision_v0",
        "simulator": "sofa",
        "vertex_count": int(surface_0.shape[0]),
        "face_count": int(faces.shape[0]),
        "action_type": request.action.action_type,
        "sofa_total_steps": int(total_steps),
        "sofa_action_steps": int(action_steps),
        "sofa_settle_steps": int(settle_steps),
        "sofa_preload_steps": int(args.preload_steps),
        "sofa_dt": float(cfg.dt),
        "depth_mm": float(depth_mm),
        "direction_id": direction_id,
        "direction": [float(v) for v in direction_dataset.tolist()],
        "approach_direction": [float(v) for v in approach_direction_dataset.tolist()],
        "contact_point_id": contact_id,
        "material_id": material_id,
        "young_modulus": float(young_modulus),
        "poisson_ratio": float(poisson_ratio),
        "group_id": group_id,
        "max_displacement": float(np.linalg.norm(displacement, axis=1).max()),
        "contact_detected": bool(contact_summary["contact_detected"]),
    }
    result = SampleResult(
        artifacts={
            "vertices_0": surface_0.astype(np.float32),
            "vertices_1": surface_1.astype(np.float32),
            "displacement": displacement.astype(np.float32),
            "faces": faces.astype(np.int32),
            "action": np.asarray(request.action.vector, dtype=np.float32),
            "contact_point": np.asarray(request.action.contact_point, dtype=np.float32),
            "material": material_payload(args, material_id=material_id, young_modulus=young_modulus, poisson_ratio=poisson_ratio),
            "meta": meta_payload(args, sample_id, depth_mm, direction_id, direction_dataset, approach_direction_dataset, calibration, handles, contact_id=contact_id, material_id=material_id, group_id=group_id),
            "tool_pose_0": pose_from_translation(to_dataset_meters(handles.probe_start[None, :], meters_per_scene_unit)[0]).astype(np.float32),
            "tool_pose_1": pose_from_translation(to_dataset_meters(handles.probe_end[None, :], meters_per_scene_unit)[0]).astype(np.float32),
            "tool_geometry": {
                "type": "sphere",
                "radius": float(cfg.probe_radius * meters_per_scene_unit),
                "unit": "meter",
                "frame": "tool_pose_center",
                "source": "official_liver_surface_collision",
            },
            "contact_summary": contact_summary,
            "fixed_node_indices": boundary_payload["fixed_node_indices"],
            "free_node_indices": boundary_payload["free_node_indices"],
            "boundary_mask": boundary_payload["boundary_mask"],
            "boundary": boundary_payload["boundary"],
            "solver_summary": solver_summary(args, cfg, calibration, displacement, contact_summary),
        },
        summary=summary,
    )
    writer.write_sample(sample_dir, result)
    logger.record_event(
        "sample_ready",
        {
            "sample_id": int(sample_id),
            "vertex_count": int(surface_0.shape[0]),
            "face_count": int(faces.shape[0]),
            "max_displacement": summary["max_displacement"],
        },
    )
    logger.finish(summary)
    write_trajectory_summary(sample_dir)
    Sofa.Simulation.unload(root)
    return sample_dir, summary


def record_logged_frame(
    logger: DirectorySimulationLogger,
    request: SampleRequest,
    surface_scene: np.ndarray,
    probe_scene: np.ndarray,
    observation: dict[str, Any],
    cfg: LiverSurfaceCollisionConfig,
    meters_per_scene_unit: float,
    *,
    step: int,
    progress: float,
) -> None:
    logger.record_frame(
        step,
        step * float(cfg.dt),
        arrays={"vertices": to_dataset_meters(surface_scene, meters_per_scene_unit).astype(np.float32)},
        scalars={
            "progress": float(progress),
            "action_type": request.action.action_type,
            "interaction_model": "official_liver_surface_collision",
            "contact_point": request.action.contact_point,
            "tool_position": to_dataset_meters(probe_scene[None, :], meters_per_scene_unit)[0].tolist(),
            "tool_radius": float(cfg.probe_radius * meters_per_scene_unit),
            "contact_active": bool(observation["contact_active"]),
            "signed_gap": float(observation["signed_gap"]),
            "contact_distance": float(observation["contact_distance"]),
            "penetration_depth": float(observation["penetration_depth"]),
            "contact_point_observed": observation["nearest_point"],
            "nearest_contact_vertex_index": int(observation["nearest_vertex_index"]),
        },
    )


def prepare_sample_dir(sample_dir: Path, *, overwrite: bool) -> None:
    if sample_dir.exists() and any(sample_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Sample directory is not empty: {sample_dir}. Use --overwrite to regenerate.")
        shutil.rmtree(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)


def calibrate_surface(surface_vertices: np.ndarray, target_long_axis_mm: float) -> dict[str, Any]:
    mins = surface_vertices.min(axis=0)
    maxs = surface_vertices.max(axis=0)
    extents = maxs - mins
    long_axis_index = int(np.argmax(extents))
    long_axis_scene_units = float(extents[long_axis_index])
    mm_per_scene_unit = float(target_long_axis_mm / long_axis_scene_units)
    return {
        "target_long_axis_mm": float(target_long_axis_mm),
        "bbox_min_scene_units": mins.tolist(),
        "bbox_max_scene_units": maxs.tolist(),
        "bbox_extent_scene_units": extents.tolist(),
        "long_axis_index": long_axis_index,
        "long_axis_scene_units": long_axis_scene_units,
        "mm_per_scene_unit": mm_per_scene_unit,
        "scene_units_per_mm": float(1.0 / mm_per_scene_unit),
    }


def load_obj_triangles(path: Path) -> np.ndarray:
    faces: list[list[int]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("f "):
                continue
            indices = []
            for token in line.split()[1:]:
                vertex_token = token.split("/")[0]
                if not vertex_token:
                    continue
                index = int(vertex_token)
                if index < 0:
                    raise ValueError(f"Negative OBJ face indices are not supported: {path}")
                indices.append(index - 1)
            if len(indices) == 3:
                faces.append(indices)
            elif len(indices) > 3:
                for i in range(1, len(indices) - 1):
                    faces.append([indices[0], indices[i], indices[i + 1]])
    if not faces:
        raise ValueError(f"OBJ file has no triangle faces: {path}")
    return np.asarray(faces, dtype=np.int32)


def to_dataset_meters(points_scene: np.ndarray, meters_per_scene_unit: float) -> np.ndarray:
    points = np.asarray(points_scene, dtype=np.float64)
    return points[..., [0, 2, 1]] * meters_per_scene_unit


def contact_observation(
    surface_scene: np.ndarray,
    probe_scene: np.ndarray,
    cfg: LiverSurfaceCollisionConfig,
    meters_per_scene_unit: float,
    contact_observation_distance_mm: float,
    step: int,
    time_code: float,
) -> dict[str, Any]:
    distances = np.linalg.norm(surface_scene - probe_scene[None, :], axis=1) - float(cfg.probe_radius)
    nearest_index = int(np.argmin(distances))
    signed_gap_scene = float(distances[nearest_index])
    sofa_contact_distance_scene = float(cfg.contact_distance)
    observation_distance = max(float(contact_observation_distance_mm) / 1000.0, sofa_contact_distance_scene * meters_per_scene_unit)
    return {
        "step": int(step),
        "time_code": float(time_code),
        "contact_active": bool(signed_gap_scene * meters_per_scene_unit <= observation_distance),
        "signed_gap": signed_gap_scene * meters_per_scene_unit,
        "contact_distance": observation_distance,
        "sofa_contact_distance": sofa_contact_distance_scene * meters_per_scene_unit,
        "contact_observation_distance": observation_distance,
        "penetration_depth": max(0.0, -signed_gap_scene) * meters_per_scene_unit,
        "nearest_point": to_dataset_meters(surface_scene[nearest_index][None, :], meters_per_scene_unit)[0].tolist(),
        "nearest_vertex_index": nearest_index,
    }


def build_contact_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    active = [obs for obs in observations if obs["contact_active"]]
    min_gap = min(float(obs["signed_gap"]) for obs in observations)
    max_penetration = max(float(obs["penetration_depth"]) for obs in observations)
    return {
        "contact_detected": bool(active),
        "first_contact_step": int(active[0]["step"]) if active else None,
        "contact_frame_count": len(active),
        "observation_count": len(observations),
        "min_signed_gap": min_gap,
        "max_penetration": max_penetration,
        "contact_distance": float(observations[0]["contact_distance"]) if observations else 0.0,
        "sofa_contact_distance": float(observations[0].get("sofa_contact_distance", 0.0)) if observations else 0.0,
        "contact_observation_distance": float(observations[0].get("contact_observation_distance", 0.0)) if observations else 0.0,
        "method": "surface_sphere_to_surface_vertex_gap_observation",
        "force_available": False,
        "contact_force_method": "unavailable",
    }


def surface_boundary_payload(surface_0: np.ndarray) -> dict[str, Any]:
    vertex_count = int(surface_0.shape[0])
    fixed = np.asarray([], dtype=np.int32)
    mask = np.zeros((vertex_count,), dtype=bool)
    free = np.arange(vertex_count, dtype=np.int32)
    mins = np.asarray(surface_0, dtype=np.float64).min(axis=0)
    maxs = np.asarray(surface_0, dtype=np.float64).max(axis=0)
    return {
        "fixed_node_indices": fixed,
        "free_node_indices": free,
        "boundary_mask": mask,
        "boundary": {
            "boundary_type": "official_liver_volume_fixed_indices_surface_unmapped",
            "surface_boundary_mask_semantics": "all_false_because_official_demo_fixed_constraint_is_on_volume_nodes_3_39_64",
            "volume_fixed_indices": [3, 39, 64],
            "fixed_node_count": 0,
            "free_node_count": vertex_count,
            "total_node_count": vertex_count,
            "boundary_box": {"min": mins.tolist(), "max": maxs.tolist(), "unit": "meter"},
            "unit": "meter",
        },
    }


def build_request(
    args: argparse.Namespace,
    sample_id: int,
    depth_mm: float,
    direction_id: str,
    direction_dataset: np.ndarray,
    approach_direction_dataset: np.ndarray,
    calibration: dict[str, Any],
    handles: Any,
    cfg: LiverSurfaceCollisionConfig,
    meters_per_scene_unit: float,
    contact_id: str,
    material_id: str,
    young_modulus: float,
    poisson_ratio: float,
    group_id: str | None,
) -> SampleRequest:
    contact = to_dataset_meters(handles.contact_point[None, :], meters_per_scene_unit)[0]
    action = ActionSpec(
        vector=(float(contact[0]), float(contact[1]), float(direction_dataset[0]), float(direction_dataset[1]), float(direction_dataset[2]), float(depth_mm / 1000.0)),
        action_type="surface_collision_directed_press",
        contact_point=tuple(float(v) for v in contact),
        extra={
            "depth_mm": float(depth_mm),
            "direction_id": direction_id,
            "approach_direction": [float(v) for v in approach_direction_dataset.tolist()],
            "target_long_axis_mm": float(args.target_long_axis_mm),
            "scene_units_per_mm": float(calibration["scene_units_per_mm"]),
            "contact_point_id": contact_id,
            "material_id": material_id,
            "young_modulus": float(young_modulus),
            "poisson_ratio": float(poisson_ratio),
            "group_id": group_id,
        },
    )
    action_steps, settle_steps, total_steps = action_and_settle_steps(args)
    extra = {
        "sofa_interaction_model": "official_liver_surface_collision",
        "sofa_tissue_shape": "official_liver",
        "sofa_total_steps": int(total_steps),
        "sofa_action_steps": int(action_steps),
        "sofa_settle_steps": int(settle_steps),
        "sofa_preload_steps": int(args.preload_steps),
        "sofa_dt": float(cfg.dt),
        "scene_units_per_mm": float(calibration["scene_units_per_mm"]),
        "mm_per_scene_unit": float(calibration["mm_per_scene_unit"]),
        "coordinate_transform": "dataset_xyz = sofa_xzy; dataset_z is SOFA y",
        "njf_mode": "response_basis_group" if args.layout == "grouped" else "local_perturbation",
        "group_id": group_id if args.layout == "grouped" else None,
        "direction_id": direction_id,
        "approach_direction": [float(v) for v in approach_direction_dataset.tolist()],
        "probe_approach_policy": "normal_approach_for_basis_v2" if args.direction_set == "basis_v2" else "action_aligned_approach",
        "state_id": "state_official_liver_000001",
        "material_id": material_id,
        "boundary_id": "boundary_official_liver_volume_fixed_indices",
        "contact_point_id": contact_id,
    }
    return SampleRequest(
        config=SampleConfig(
            sample_id=int(sample_id),
            scene_id="official_liver_surface_collision_v0",
            tissue_type="official_sofa_liver_surface",
            simulator="sofa",
            unit="meter",
            notes="SOFA official liver tetra FEM with mapped surface triangle collision sample",
            extra=extra,
        ),
        geometry=GeometryConfig(),
        material=MaterialConfig(
            youngs_modulus=float(young_modulus),
            poisson_ratio=float(poisson_ratio),
            density=1.0,
            damping=0.1,
            boundary_condition="official_liver_fixed_volume_indices",
            extra=extra,
        ),
        action=action,
        logging=LoggingConfig(enabled=True, log_every_n=max(int(args.log_every_n), 1), save_vertices=True),
    )


def material_payload(args: argparse.Namespace, *, material_id: str, young_modulus: float, poisson_ratio: float) -> dict[str, Any]:
    return {
        "material_id": material_id,
        "youngs_modulus": float(young_modulus),
        "poisson_ratio": float(poisson_ratio),
        "density": 1.0,
        "damping": 0.1,
        "boundary_condition": "official_liver_fixed_volume_indices",
        "model": "TetrahedralCorotationalFEMForceField",
        "collision_model": "mapped_surface_triangle_line_point",
    }


def meta_payload(args: argparse.Namespace, sample_id: int, depth_mm: float, direction_id: str, direction_dataset: np.ndarray, approach_direction_dataset: np.ndarray, calibration: dict[str, Any], handles: Any, *, contact_id: str, material_id: str, group_id: str | None) -> dict[str, Any]:
    return {
        "sample_id": int(sample_id),
        "scene_id": "official_liver_surface_collision_v0",
        "simulator": "sofa",
        "unit": "meter",
        "tissue_type": "official_sofa_liver_surface",
        "source_scene": "scenes/liver_surface_collision.py",
        "volume_mesh": handles.liver_mesh.name,
        "surface_mesh": handles.surface_mesh.name,
        "coordinate_transform": "dataset_xyz = sofa_xzy; dataset_z is SOFA y",
        "calibration": calibration,
        "depth_mm": float(depth_mm),
        "direction_id": direction_id,
        "direction": [float(v) for v in direction_dataset.tolist()],
        "approach_direction": [float(v) for v in approach_direction_dataset.tolist()],
        "probe_approach_policy": "normal_approach_for_basis_v2" if args.direction_set == "basis_v2" else "action_aligned_approach",
        "extra": {
            "njf_mode": "response_basis_group" if args.layout == "grouped" else "local_perturbation",
            "group_id": group_id if args.layout == "grouped" else None,
            "direction_id": direction_id,
            "approach_direction": [float(v) for v in approach_direction_dataset.tolist()],
            "probe_approach_policy": "normal_approach_for_basis_v2" if args.direction_set == "basis_v2" else "action_aligned_approach",
            "state_id": "state_official_liver_000001",
            "material_id": material_id,
            "boundary_id": "boundary_official_liver_volume_fixed_indices",
            "contact_point_id": contact_id,
        },
    }


def solver_summary(
    args: argparse.Namespace,
    cfg: LiverSurfaceCollisionConfig,
    calibration: dict[str, Any],
    displacement: np.ndarray,
    contact_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dt": float(cfg.dt),
        "total_steps": int(action_and_settle_steps(args)[2]),
        "action_steps": int(action_and_settle_steps(args)[0]),
        "settle_steps": int(action_and_settle_steps(args)[1]),
        "preload_steps": int(args.preload_steps),
        "settling_steps": int(action_and_settle_steps(args)[1]),
        "record_interval": int(args.log_every_n),
        "record_every_n": int(args.log_every_n),
        "solver_type": "EulerImplicitSolver",
        "ode_solver": "EulerImplicitSolver",
        "linear_solver_type": "CGLinearSolver",
        "linear_solver": "CGLinearSolver",
        "constraint_solver_type": "GenericConstraintSolver",
        "contact_pipeline": "surface_triangle_line_point_collision",
        "solver_status_method": "finite_state_check_only",
        "solver_converged": None,
        "solver_residual": None,
        "valid": bool(np.isfinite(displacement).all()),
        "finite": bool(np.isfinite(displacement).all()),
        "nan_or_inf_detected": bool(not np.isfinite(displacement).all()),
        "max_displacement": float(np.linalg.norm(displacement, axis=1).max()),
        "calibration": calibration,
        "contact_detected": bool(contact_summary["contact_detected"]),
    }


def pose_from_translation(translation: np.ndarray) -> np.ndarray:
    pose = np.eye(4, dtype=np.float64)
    pose[:3, 3] = np.asarray(translation, dtype=np.float64)
    return pose


def write_mode_b_group(output: Path, group_id: str, sample_dirs: list[Path], directions: tuple[tuple[str, np.ndarray], ...], *, contact_id: str, material_id: str) -> dict[str, Any]:
    if not sample_dirs:
        raise ValueError("Cannot write Mode B group with no samples")
    group_dir = output / "groups" / group_id
    group_dir.mkdir(parents=True, exist_ok=True)
    first = sample_dirs[0]
    state_initial = np.load(first / "vertices_0.npy")
    fixed_node_mask = np.load(first / "boundary_mask.npy").astype(bool)
    surface_points = state_initial.copy()
    contact_point = np.load(first / "contact_point.npy")
    actions = []
    responses = []
    sample_ids = []
    sample_paths = []
    action_directions = []
    action_magnitudes = []
    state_mismatch_max = 0.0
    for sample_dir in sample_dirs:
        vertices_0 = np.load(sample_dir / "vertices_0.npy")
        state_mismatch_max = max(state_mismatch_max, float(np.max(np.abs(vertices_0 - state_initial))))
        sample_contact = np.load(sample_dir / "contact_point.npy")
        if not np.allclose(sample_contact, contact_point, atol=1e-7):
            raise ValueError(f"{group_id}: contact_point differs for {sample_dir.name}")
        action = np.load(sample_dir / "action.npy")
        response = np.load(sample_dir / "displacement.npy")
        actions.append(action)
        responses.append(response)
        sample_ids.append(sample_dir.name)
        sample_paths.append(str(sample_dir.relative_to(output)))
        action_directions.append([float(v) for v in action[2:5]])
        action_magnitudes.append(float(action[5]))
    actions_array = np.stack(actions, axis=0)
    responses_array = np.stack(responses, axis=0)
    contact_normal = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    np.save(group_dir / "state_initial.npy", state_initial.astype(np.float32))
    np.save(group_dir / "fixed_node_mask.npy", fixed_node_mask)
    np.save(group_dir / "surface_points.npy", surface_points.astype(np.float32))
    np.save(group_dir / "actions.npy", actions_array.astype(np.float32))
    np.save(group_dir / "responses.npy", responses_array.astype(np.float32))
    np.save(group_dir / "contact_point.npy", contact_point.astype(np.float32))
    np.save(group_dir / "contact_normal.npy", contact_normal)
    material = load_json_file(first / "material.json")
    boundary = load_json_file(first / "boundary.json")
    solver = load_json_file(first / "solver_summary.json")
    tool_geometry = load_json_file(first / "tool_geometry.json")
    metadata = {
        "group_id": group_id,
        "group_type": "surface_collision_bridge_response_basis",
        "state_id": "state_official_liver_000001",
        "material_id": material_id,
        "boundary_id": "boundary_official_liver_volume_fixed_indices",
        "contact_point_id": contact_id,
        "contact_point_world": [float(v) for v in contact_point.tolist()],
        "contact_normal": [float(v) for v in contact_normal.tolist()],
        "fixed_variables": ["state_id", "material_id", "boundary_id", "contact_point_id", "tool_geometry", "solver_config"],
        "varied_variables": ["action_direction", "action_magnitude"],
        "direction_set": [{"direction_id": name, "direction": [float(v) for v in direction.tolist()]} for name, direction in directions],
        "sample_ids": sample_ids,
        "sample_paths": sample_paths,
        "action_count": int(actions_array.shape[0]),
        "action_dim": int(actions_array.shape[1]),
        "response_shape": list(responses_array.shape),
        "action_directions": action_directions,
        "action_magnitudes_m": action_magnitudes,
        "state_mismatch_max_m": state_mismatch_max,
        "material": material,
        "boundary": boundary,
        "solver_summary": solver,
        "tool_geometry": tool_geometry,
        "smoke_sized_group": int(actions_array.shape[0]) < 12,
    }
    write_json_file(group_dir / "group_metadata.json", metadata)
    return {
        "group_id": group_id,
        "group_type": metadata["group_type"],
        "path": str(group_dir.relative_to(output)),
        "sample_ids": sample_ids,
        "action_count": int(actions_array.shape[0]),
        "unique_action_directions": len({tuple(np.round(action[2:5], 6)) for action in actions_array}),
        "contact_point_id": contact_id,
        "material_id": material_id,
        "state_mismatch_max_m": state_mismatch_max,
    }


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_bridge_metadata(
    output: Path,
    args: argparse.Namespace,
    depths_mm: tuple[float, ...],
    calibration: dict[str, Any],
    mesh_info: dict[str, str],
    records: list[dict[str, Any]],
    group_records: list[dict[str, Any]] | None = None,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_type": "surface_collision_local_perturbation_bridge",
        "scene_id": "official_liver_surface_collision_v0",
        "source_scene": "scenes/liver_surface_collision.py",
        "generator": "scripts/generate_liver_surface_sample.py",
        "sample_count": len(records),
        "group_count": len(group_records or []),
        "layout": args.layout,
        "modes": {"response_basis_group": bool(args.layout == "grouped"), "local_perturbation": bool(args.layout == "flat")},
        "depths_mm": [float(v) for v in depths_mm],
        "direction_set": args.direction_set,
        "direction_id_filter": args.direction_id,
        "probe_approach_policy": "normal_approach_for_basis_v2" if args.direction_set == "basis_v2" else "action_aligned_approach",
        "contact_set": args.contact_set,
        "material_set": args.material_set,
        "target_long_axis_mm": float(args.target_long_axis_mm),
        "coordinate_transform": "dataset_xyz = sofa_xzy; dataset_z is SOFA y",
        "unit": "meter",
        "probe_radius_mm": float(args.probe_radius_mm),
        "probe_clearance_mm": float(args.probe_clearance_mm),
        "contact_distance_mm": float(args.contact_distance_mm),
        "contact_observation_distance_mm": float(args.contact_observation_distance_mm),
        "alarm_distance_mm": float(args.alarm_distance_mm),
        "preload_steps": int(args.preload_steps),
        "action_steps": int(action_and_settle_steps(args)[0]),
        "settle_steps": int(action_and_settle_steps(args)[1]),
        "young_modulus": float(args.young_modulus),
        "poisson_ratio": float(args.poisson_ratio),
        "calibration": calibration,
        "mesh": mesh_info,
        "samples": records,
        "groups": group_records or [],
    }
    with (output / "dataset_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
