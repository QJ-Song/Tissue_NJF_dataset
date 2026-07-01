from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
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
    "Sofa.Component.IO.Mesh",
    "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.Mapping.Linear",
    "Sofa.Component.Mass",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Constant",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.Visual",
    "Sofa.GL.Component.Rendering3D",
]


@dataclass(frozen=True)
class LiverSurfaceCollisionConfig:
    dt: float = 0.005
    young_modulus: float = 3000.0
    poisson_ratio: float = 0.3
    mass_density: float = 1.0
    rayleigh_stiffness: float = 0.1
    rayleigh_mass: float = 0.1
    probe_radius: float = 0.45
    probe_clearance: float = 0.20
    probe_depth: float = 0.45
    probe_direction: tuple[float, float, float] = (0.0, -1.0, 0.0)
    contact_point: tuple[float, float, float] | None = None
    alarm_distance: float = 0.50
    contact_distance: float = 0.05
    contact_friction: float = 0.0


@dataclass
class LiverSurfaceCollisionHandles:
    root: Any
    liver_node: Any
    liver_dofs: Any
    liver_collision_node: Any
    surface_dofs: Any
    probe_node: Any
    probe_dofs: Any
    contact_point: np.ndarray
    probe_start: np.ndarray
    probe_end: np.ndarray
    liver_mesh: Path
    surface_mesh: Path
    liver_collision_models: tuple[str, ...]
    liver_mapping: str


def createScene(root: Any) -> None:
    """SOFA entry point for runSofa GUI loading."""
    create_liver_surface_collision_scene(root, LiverSurfaceCollisionConfig())


def create_liver_surface_collision_scene(
    root: Any,
    cfg: LiverSurfaceCollisionConfig | None = None,
) -> LiverSurfaceCollisionHandles:
    cfg = cfg or LiverSurfaceCollisionConfig()
    liver_mesh, surface_mesh = find_liver_meshes()
    surface_points = load_obj_vertices(surface_mesh)
    if cfg.contact_point is None:
        contact_point = choose_top_contact_point(surface_points)
    else:
        contact_point = np.asarray(cfg.contact_point, dtype=np.float64)
        if contact_point.shape != (3,):
            raise ValueError(f"contact_point must have shape (3,), got {contact_point.shape}")
    direction = normalize_direction(np.asarray(cfg.probe_direction, dtype=np.float64))
    probe_start = contact_point - direction * (cfg.probe_radius + cfg.probe_clearance)
    probe_end = contact_point - direction * cfg.probe_radius + direction * cfg.probe_depth

    root.name = "liver_surface_collision_root"
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = cfg.dt
    root.addObject("RequiredPlugin", pluginName=SOFA_PLUGINS)
    root.addObject("VisualStyle", displayFlags="showVisual showCollisionModels")
    root.addObject("FreeMotionAnimationLoop")
    root.addObject("GenericConstraintSolver", tolerance=1e-6, maxIterations=100)
    root.addObject("CollisionPipeline", name="Pipeline", verbose=0)
    root.addObject("BruteForceBroadPhase", name="BroadPhase")
    root.addObject("BVHNarrowPhase", name="NarrowPhase")
    root.addObject("LocalMinDistance", name="Intersection", alarmDistance=cfg.alarm_distance, contactDistance=cfg.contact_distance, angleCone=0.0)
    root.addObject("CollisionResponse", name="ContactResponse", response="FrictionContactConstraint", responseParams=f"mu={cfg.contact_friction}")

    liver = root.addChild("Liver")
    liver.addObject("EulerImplicitSolver", name="odesolver", rayleighStiffness=cfg.rayleigh_stiffness, rayleighMass=cfg.rayleigh_mass)
    liver.addObject("CGLinearSolver", name="linear_solver", iterations=80, tolerance=1e-9, threshold=1e-9)
    liver.addObject("MeshGmshLoader", name="meshLoader", filename=str(liver_mesh))
    liver.addObject("TetrahedronSetTopologyContainer", name="topology", src="@meshLoader")
    liver_dofs = liver.addObject("MechanicalObject", name="dofs", src="@meshLoader")
    liver.addObject("TetrahedronSetGeometryAlgorithms", template="Vec3", name="geometry")
    liver.addObject("DiagonalMass", name="mass", massDensity=cfg.mass_density)
    liver.addObject(
        "TetrahedralCorotationalFEMForceField",
        template="Vec3",
        name="FEM",
        method="large",
        poissonRatio=cfg.poisson_ratio,
        youngModulus=cfg.young_modulus,
        computeGlobalMatrix=0,
    )
    liver.addObject("FixedProjectiveConstraint", name="FixedBoundary", indices="3 39 64")
    liver.addObject("UncoupledConstraintCorrection", defaultCompliance=1e-7)

    collision = liver.addChild("SurfaceCollision")
    collision.addObject("MeshOBJLoader", name="surfaceLoader", filename=str(surface_mesh), handleSeams=1)
    collision.addObject("MeshTopology", name="surfaceTopology", src="@surfaceLoader")
    surface_dofs = collision.addObject("MechanicalObject", name="surfaceDofs", src="@surfaceLoader")
    collision.addObject("TriangleCollisionModel", name="TriangleCollision", selfCollision=0)
    collision.addObject("LineCollisionModel", name="LineCollision", selfCollision=0)
    collision.addObject("PointCollisionModel", name="PointCollision", selfCollision=0)
    collision.addObject("BarycentricMapping", name="surfaceMapping", input="@..", output="@.")

    visual = liver.addChild("Visual")
    visual.addObject("MeshOBJLoader", name="visualLoader", filename=str(surface_mesh), handleSeams=1)
    visual.addObject("OglModel", name="VisualModel", src="@visualLoader", color="0.55 0.18 0.16 1.0")
    visual.addObject("BarycentricMapping", name="visualMapping", input="@../dofs", output="@VisualModel")

    probe = root.addChild("Probe")
    probe_dofs = probe.addObject("MechanicalObject", name="dofs", template="Vec3", position=[probe_start.tolist()])
    probe.addObject("SphereCollisionModel", name="ProbeCollision", radius=cfg.probe_radius)
    probe.addObject("FixedProjectiveConstraint", name="ProbeFixed", indices="0")

    return LiverSurfaceCollisionHandles(
        root=root,
        liver_node=liver,
        liver_dofs=liver_dofs,
        liver_collision_node=collision,
        surface_dofs=surface_dofs,
        probe_node=probe,
        probe_dofs=probe_dofs,
        contact_point=contact_point,
        probe_start=probe_start,
        probe_end=probe_end,
        liver_mesh=liver_mesh,
        surface_mesh=surface_mesh,
        liver_collision_models=("TriangleCollisionModel", "LineCollisionModel", "PointCollisionModel"),
        liver_mapping="BarycentricMapping",
    )


def find_liver_meshes() -> tuple[Path, Path]:
    mesh_dir = find_sofa_mesh_dir()
    liver_mesh = mesh_dir / "liver.msh"
    surface_mesh = mesh_dir / "liver-smooth.obj"
    missing = [str(path) for path in (liver_mesh, surface_mesh) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing SOFA liver mesh file(s): "
            + ", ".join(missing)
            + ". Set SOFA_MESH_DIR to a directory containing liver.msh and liver-smooth.obj."
        )
    return liver_mesh, surface_mesh


def find_sofa_mesh_dir() -> Path:
    candidates: list[Path] = []
    if os.environ.get("SOFA_MESH_DIR"):
        candidates.append(Path(os.environ["SOFA_MESH_DIR"]))
    if os.environ.get("SOFA_ROOT"):
        candidates.append(Path(os.environ["SOFA_ROOT"]) / "share" / "sofa" / "mesh")
        candidates.append(Path(os.environ["SOFA_ROOT"]) / "mesh")
    if os.environ.get("CONDA_PREFIX"):
        candidates.append(Path(os.environ["CONDA_PREFIX"]) / "share" / "sofa" / "mesh")
    candidates.append(Path(sys.prefix) / "share" / "sofa" / "mesh")

    for candidate in candidates:
        if (candidate / "liver.msh").exists() and (candidate / "liver-smooth.obj").exists():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "Could not locate SOFA liver meshes. Searched: "
        + searched
        + ". Set SOFA_MESH_DIR to a directory containing liver.msh and liver-smooth.obj."
    )



def normalize_direction(direction: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-12:
        raise ValueError(f"probe_direction must be nonzero, got {direction}")
    return np.asarray(direction, dtype=np.float64) / norm

def load_obj_vertices(path: Path) -> np.ndarray:
    points: list[list[float]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                points.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if not points:
        raise ValueError(f"OBJ file has no vertices: {path}")
    return np.asarray(points, dtype=np.float64)


def choose_top_contact_point(surface_points: np.ndarray) -> np.ndarray:
    max_y = float(surface_points[:, 1].max())
    min_y = float(surface_points[:, 1].min())
    band = max((max_y - min_y) * 0.08, 1e-6)
    top_points = surface_points[surface_points[:, 1] >= max_y - band]
    xz_center = np.median(surface_points[:, [0, 2]], axis=0)
    distances = np.linalg.norm(top_points[:, [0, 2]] - xz_center[None, :], axis=1)
    return top_points[int(np.argmin(distances))].astype(np.float64)


def set_probe_position(probe_dofs: Any, position: np.ndarray) -> None:
    probe_dofs.position.value = [np.asarray(position, dtype=np.float64).tolist()]


def object_positions(dofs: Any) -> np.ndarray:
    return np.asarray(dofs.position.array(), dtype=np.float64).copy()
