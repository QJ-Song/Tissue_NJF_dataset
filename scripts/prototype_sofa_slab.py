"""Minimal SOFA slab smoke test.

This script verifies the local SofaPython3 environment can:

- create a small FEM slab from a regular grid;
- apply a simple downward load while fixing the bottom surface;
- advance the simulation headlessly;
- read vertex positions back into NumPy.

It is intentionally outside the dataset pipeline. Once this works, the scene
construction and state extraction logic can be moved into SofaFemBackend.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np
import Sofa
import SofaRuntime


REQUIRED_PLUGINS = [
    "Sofa.Component.Constraint.Projective",
    "Sofa.Component.Engine.Select",
    "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.Mass",
    "Sofa.Component.MechanicalLoad",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.Topology.Container.Grid",
    "Sofa.Component.Topology.Mapping",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--dt", type=float, default=0.01)
    parser.add_argument("--size-x", type=float, default=0.10)
    parser.add_argument("--size-y", type=float, default=0.10)
    parser.add_argument("--thickness", type=float, default=0.01)
    parser.add_argument("--nx", type=int, default=5)
    parser.add_argument("--ny", type=int, default=5)
    parser.add_argument("--nz", type=int, default=3)
    parser.add_argument("--youngs-modulus", type=float, default=5000.0)
    parser.add_argument("--poisson-ratio", type=float, default=0.45)
    parser.add_argument("--force-z", type=float, default=-0.1)
    return parser.parse_args()


def create_scene(root: Any, args: argparse.Namespace) -> None:
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = args.dt
    root.addObject("RequiredPlugin", pluginName=REQUIRED_PLUGINS)
    root.addObject("DefaultAnimationLoop")

    half_x = args.size_x * 0.5
    half_y = args.size_y * 0.5
    half_z = args.thickness * 0.5

    slab = root.addChild("Slab")
    slab.addObject("EulerImplicitSolver", name="ode", rayleighStiffness=0.05, rayleighMass=0.05)
    slab.addObject("CGLinearSolver", name="linear_solver", iterations=50, tolerance=1e-9, threshold=1e-9)
    slab.addObject(
        "RegularGridTopology",
        name="grid",
        n=f"{args.nx} {args.ny} {args.nz}",
        min=f"{-half_x} {-half_y} {-half_z}",
        max=f"{half_x} {half_y} {half_z}",
    )
    slab.addObject("MechanicalObject", name="dofs", template="Vec3", position="@grid.position")
    slab.addObject("UniformMass", name="mass", totalMass=0.01)
    slab.addObject("ConstantForceField", name="downward_load", totalForce=f"0 0 {args.force_z}")
    slab.addObject(
        "BoxROI",
        name="fixed_roi",
        box=f"{-half_x - 1e-6} {-half_y - 1e-6} {-half_z - 1e-6} "
        f"{half_x + 1e-6} {half_y + 1e-6} {-half_z + 1e-6}",
        position="@dofs.position",
    )
    slab.addObject("FixedProjectiveConstraint", name="fixed_bottom", indices="@fixed_roi.indices")

    tetra = slab.addChild("Tetra")
    tetra.addObject("TetrahedronSetTopologyContainer", name="tetra_topology")
    tetra.addObject("TetrahedronSetTopologyModifier")
    tetra.addObject("TetrahedronSetGeometryAlgorithms", template="Vec3")
    tetra.addObject("Hexa2TetraTopologicalMapping", input="@../grid", output="@tetra_topology")
    tetra.addObject(
        "TetrahedronFEMForceField",
        name="fem",
        template="Vec3",
        method="large",
        poissonRatio=args.poisson_ratio,
        youngModulus=args.youngs_modulus,
    )



def vertex_positions(root: Any) -> np.ndarray:
    dofs = root.getChild("Slab").getObject("dofs")
    return np.asarray(dofs.position.array(), dtype=np.float64).copy()


def main() -> None:
    args = parse_args()
    for plugin in REQUIRED_PLUGINS:
        SofaRuntime.importPlugin(plugin)

    root = Sofa.Core.Node("root")
    create_scene(root, args)
    Sofa.Simulation.initRoot(root)

    vertices_0 = vertex_positions(root)
    for _ in range(args.steps):
        Sofa.Simulation.animate(root, root.dt.value)
    vertices_1 = vertex_positions(root)

    displacement = vertices_1 - vertices_0
    displacement_norm = np.linalg.norm(displacement, axis=1)
    summary = {
        "steps": int(args.steps),
        "dt": float(args.dt),
        "vertex_count": int(vertices_0.shape[0]),
        "initial_bounds": {
            "min": vertices_0.min(axis=0).tolist(),
            "max": vertices_0.max(axis=0).tolist(),
        },
        "final_bounds": {
            "min": vertices_1.min(axis=0).tolist(),
            "max": vertices_1.max(axis=0).tolist(),
        },
        "max_displacement": float(displacement_norm.max()),
        "mean_displacement": float(displacement_norm.mean()),
        "max_z_displacement": float(displacement[:, 2].max()),
        "min_z_displacement": float(displacement[:, 2].min()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
