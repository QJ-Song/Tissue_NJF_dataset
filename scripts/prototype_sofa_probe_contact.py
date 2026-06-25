#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

import numpy as np


SOFA_PLUGINS = [
    "Sofa.Component.AnimationLoop",
    "Sofa.Component.Collision.Detection.Algorithm",
    "Sofa.Component.Collision.Detection.Intersection",
    "Sofa.Component.Collision.Geometry",
    "Sofa.Component.Collision.Response.Contact",
    "Sofa.Component.Constraint.Lagrangian.Correction",
    "Sofa.Component.Constraint.Lagrangian.Solver",
    "Sofa.Component.Constraint.Projective",
    "Sofa.Component.Engine.Select",
    "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.Mass",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.Topology.Container.Grid",
    "Sofa.Component.Topology.Mapping",
]


@dataclass(frozen=True)
class PrototypeConfig:
    steps: int
    dt: float
    size_x: float
    size_y: float
    thickness: float
    nx: int
    ny: int
    layers: int
    youngs_modulus: float
    poisson_ratio: float
    damping: float
    density: float
    probe_radius: float
    probe_clearance: float
    probe_depth: float
    alarm_distance: float
    contact_distance: float
    min_displacement_mm: float
    max_displacement_mm: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone SOFA probe/contact prototype for Stage D0.")
    parser.add_argument("--steps", type=int, default=160)
    parser.add_argument("--dt", type=float, default=0.005)
    parser.add_argument("--size-x", type=float, default=0.12)
    parser.add_argument("--size-y", type=float, default=0.085)
    parser.add_argument("--thickness", type=float, default=0.018)
    parser.add_argument("--nx", type=int, default=8)
    parser.add_argument("--ny", type=int, default=6)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--youngs-modulus", type=float, default=5000.0)
    parser.add_argument("--poisson-ratio", type=float, default=0.45)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--density", type=float, default=1000.0)
    parser.add_argument("--probe-radius", type=float, default=0.010)
    parser.add_argument("--probe-clearance", type=float, default=0.010)
    parser.add_argument("--probe-depth", type=float, default=0.0025)
    parser.add_argument("--alarm-distance", type=float, default=0.006)
    parser.add_argument("--contact-distance", type=float, default=0.002)
    parser.add_argument("--min-displacement-mm", type=float, default=0.5)
    parser.add_argument("--max-displacement-mm", type=float, default=5.0)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = PrototypeConfig(
        steps=args.steps,
        dt=args.dt,
        size_x=args.size_x,
        size_y=args.size_y,
        thickness=args.thickness,
        nx=args.nx,
        ny=args.ny,
        layers=args.layers,
        youngs_modulus=args.youngs_modulus,
        poisson_ratio=args.poisson_ratio,
        damping=args.damping,
        density=args.density,
        probe_radius=args.probe_radius,
        probe_clearance=args.probe_clearance,
        probe_depth=args.probe_depth,
        alarm_distance=args.alarm_distance,
        contact_distance=args.contact_distance,
        min_displacement_mm=args.min_displacement_mm,
        max_displacement_mm=args.max_displacement_mm,
    )
    payload = run_prototype(cfg)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if payload["valid"] else 1


def run_prototype(cfg: PrototypeConfig) -> dict[str, Any]:
    Sofa, SofaRuntime, SofaSimulation = sofa_modules()
    for plugin in SOFA_PLUGINS:
        SofaRuntime.importPlugin(plugin)

    root, tissue_dofs, probe_dofs = create_scene(Sofa, cfg)
    SofaSimulation.initRoot(root)
    try:
        vertices_0 = vertex_positions(tissue_dofs)
        top_z = float(vertices_0[:, 2].max())
        probe_start_z = top_z + cfg.probe_radius + cfg.probe_clearance
        probe_end_z = top_z + cfg.probe_radius - cfg.probe_depth

        min_gap = float("inf")
        first_contact_step: int | None = None
        contact_frame_count = 0
        probe_positions: list[float] = []
        frame_displacements: list[float] = []

        for step in range(cfg.steps + 1):
            progress = step / max(cfg.steps, 1)
            probe_z = probe_start_z + (probe_end_z - probe_start_z) * progress
            set_probe_position(probe_dofs, probe_z)
            if step < cfg.steps:
                SofaSimulation.animate(root, root.dt.value)

            vertices = vertex_positions(tissue_dofs)
            finite = bool(np.isfinite(vertices).all())
            if not finite:
                raise FloatingPointError(f"Non-finite tissue vertex state at step {step}")

            gap = signed_sphere_gap(vertices, np.asarray([0.0, 0.0, probe_z], dtype=np.float64), cfg.probe_radius)
            min_gap = min(min_gap, gap)
            if gap <= cfg.contact_distance + 1e-9:
                contact_frame_count += 1
                if first_contact_step is None:
                    first_contact_step = step
            probe_positions.append(float(probe_z))
            frame_displacements.append(float(np.linalg.norm(vertices - vertices_0, axis=1).max()))

        vertices_1 = vertex_positions(tissue_dofs)
        displacement = vertices_1 - vertices_0
        displacement_norms = np.linalg.norm(displacement, axis=1)
        max_index = int(displacement_norms.argmax())
        max_displacement_mm = float(displacement_norms[max_index] * 1000.0)
        max_downward_z_mm = float(abs(min(float(displacement[:, 2].min()), 0.0)) * 1000.0)
        max_upward_z_mm = float(max(float(displacement[:, 2].max()), 0.0) * 1000.0)
        probe_motion_down = bool(probe_positions[-1] < probe_positions[0])
        tissue_moves_down = bool(max_downward_z_mm > max_upward_z_mm)
        contact_detected = bool(first_contact_step is not None)

        checks = {
            "steps_completed": len(probe_positions) == cfg.steps + 1,
            "finite": bool(np.isfinite(vertices_1).all() and np.isfinite(displacement).all()),
            "contact_or_proximity_detected": contact_detected,
            "bounded_displacement": cfg.min_displacement_mm <= max_displacement_mm <= cfg.max_displacement_mm,
            "probe_motion_down": probe_motion_down,
            "tissue_deformation_direction_coherent": tissue_moves_down,
        }
        return {
            "valid": all(checks.values()),
            "checks": checks,
            "steps": cfg.steps,
            "dt": cfg.dt,
            "tissue": {
                "shape": "slab",
                "size": [cfg.size_x, cfg.size_y, cfg.thickness],
                "grid": [cfg.nx + 1, cfg.ny + 1, cfg.layers],
                "vertex_count": int(vertices_0.shape[0]),
                "youngs_modulus": cfg.youngs_modulus,
                "poisson_ratio": cfg.poisson_ratio,
            },
            "probe": {
                "geometry": "sphere",
                "radius_m": cfg.probe_radius,
                "start_z_m": probe_start_z,
                "end_z_m": probe_end_z,
                "depth_m": cfg.probe_depth,
            },
            "contact": {
                "alarm_distance_m": cfg.alarm_distance,
                "contact_distance_m": cfg.contact_distance,
                "contact_detected": contact_detected,
                "first_contact_step": first_contact_step,
                "contact_frame_count": contact_frame_count,
                "min_signed_gap_mm": float(min_gap * 1000.0),
            },
            "deformation": {
                "max_displacement_mm": max_displacement_mm,
                "max_downward_z_mm": max_downward_z_mm,
                "max_upward_z_mm": max_upward_z_mm,
                "max_displacement_vertex_index": max_index,
                "max_displacement_vertex_initial": vertices_0[max_index].astype(float).tolist(),
                "max_displacement_vertex_final": vertices_1[max_index].astype(float).tolist(),
            },
        }
    finally:
        SofaSimulation.unload(root)


def create_scene(Sofa, cfg: PrototypeConfig):
    root = Sofa.Core.Node("root")
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = cfg.dt
    root.addObject("RequiredPlugin", pluginName=SOFA_PLUGINS)
    root.addObject("FreeMotionAnimationLoop")
    root.addObject("GenericConstraintSolver", tolerance=1e-6, maxIterations=100)
    root.addObject("CollisionPipeline")
    root.addObject("BruteForceBroadPhase")
    root.addObject("BVHNarrowPhase")
    root.addObject("LocalMinDistance", alarmDistance=cfg.alarm_distance, contactDistance=cfg.contact_distance, angleCone=0.0)
    root.addObject("CollisionResponse", response="FrictionContactConstraint")

    nx = max(int(cfg.nx) + 1, 2)
    ny = max(int(cfg.ny) + 1, 2)
    nz = max(int(cfg.layers), 2)
    half_x = cfg.size_x * 0.5
    half_y = cfg.size_y * 0.5
    half_z = cfg.thickness * 0.5

    slab = root.addChild("Slab")
    slab.addObject("EulerImplicitSolver", rayleighStiffness=0.05, rayleighMass=max(cfg.damping, 0.0) * 0.02)
    slab.addObject("CGLinearSolver", iterations=80, tolerance=1e-9, threshold=1e-9)
    slab.addObject(
        "RegularGridTopology",
        name="grid",
        n=f"{nx} {ny} {nz}",
        min=f"{-half_x} {-half_y} {-half_z}",
        max=f"{half_x} {half_y} {half_z}",
    )
    tissue_dofs = slab.addObject("MechanicalObject", name="dofs", template="Vec3", position=regular_grid_positions(nx, ny, nz, cfg).tolist())
    total_mass = max(float(cfg.density) * cfg.size_x * cfg.size_y * cfg.thickness, 1e-6)
    slab.addObject("UniformMass", totalMass=total_mass)
    slab.addObject("FixedProjectiveConstraint", indices=bottom_indices(nx, ny))
    slab.addObject("UncoupledConstraintCorrection", defaultCompliance=1e-7)
    slab.addObject("PointCollisionModel")

    tetra = slab.addChild("Tetra")
    tetra.addObject("TetrahedronSetTopologyContainer", name="tetra_topology")
    tetra.addObject("TetrahedronSetTopologyModifier")
    tetra.addObject("TetrahedronSetGeometryAlgorithms", template="Vec3")
    tetra.addObject("Hexa2TetraTopologicalMapping", input="@../grid", output="@tetra_topology")
    tetra.addObject(
        "TetrahedronFEMForceField",
        template="Vec3",
        method="large",
        poissonRatio=float(cfg.poisson_ratio),
        youngModulus=float(cfg.youngs_modulus),
    )

    top_z = half_z
    probe = root.addChild("Probe")
    probe_dofs = probe.addObject(
        "MechanicalObject",
        name="dofs",
        template="Vec3",
        position=[[0.0, 0.0, top_z + cfg.probe_radius + cfg.probe_clearance]],
    )
    probe.addObject("SphereCollisionModel", radius=cfg.probe_radius)
    probe.addObject("FixedProjectiveConstraint", indices="0")
    return root, tissue_dofs, probe_dofs


def regular_grid_positions(nx: int, ny: int, nz: int, cfg: PrototypeConfig) -> np.ndarray:
    half_x = cfg.size_x * 0.5
    half_y = cfg.size_y * 0.5
    half_z = cfg.thickness * 0.5
    positions: list[list[float]] = []
    for k in range(nz):
        z = -half_z + cfg.thickness * k / max(nz - 1, 1)
        for j in range(ny):
            y = -half_y + cfg.size_y * j / max(ny - 1, 1)
            for i in range(nx):
                x = -half_x + cfg.size_x * i / max(nx - 1, 1)
                positions.append([x, y, z])
    return np.asarray(positions, dtype=np.float64)


def bottom_indices(nx: int, ny: int) -> str:
    return " ".join(str(j * nx + i) for j in range(ny) for i in range(nx))


def set_probe_position(probe_dofs: Any, z: float) -> None:
    probe_dofs.position.value = [[0.0, 0.0, float(z)]]


def vertex_positions(dofs: Any) -> np.ndarray:
    return np.asarray(dofs.position.array(), dtype=np.float64).copy()


def signed_sphere_gap(vertices: np.ndarray, center: np.ndarray, radius: float) -> float:
    return float(np.min(np.linalg.norm(vertices - center[None, :], axis=1) - radius))


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
    checks = payload["checks"]
    contact = payload["contact"]
    deformation = payload["deformation"]
    probe = payload["probe"]
    print(f"SOFA Stage D0 probe/contact prototype: {status}")
    print(
        f"steps={payload['steps']} dt={payload['dt']} "
        f"probe_z={probe['start_z_m']:.5f}->{probe['end_z_m']:.5f} m "
        f"radius={probe['radius_m']:.4f} m"
    )
    print(
        f"contact_detected={contact['contact_detected']} "
        f"first_contact_step={contact['first_contact_step']} "
        f"contact_frames={contact['contact_frame_count']} "
        f"min_gap={contact['min_signed_gap_mm']:.3f} mm"
    )
    print(
        f"max_disp={deformation['max_displacement_mm']:.3f} mm "
        f"down={deformation['max_downward_z_mm']:.3f} mm "
        f"up={deformation['max_upward_z_mm']:.3f} mm"
    )
    if not payload["valid"]:
        failed = [key for key, value in checks.items() if not value]
        print(f"failed_checks={failed}")


if __name__ == "__main__":
    raise SystemExit(main())
