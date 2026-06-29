from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from ..backend import SimulationLogger
from ..schema import SampleRequest, SampleResult


class SofaFemBackend:
    """Minimal SofaPython3 FEM slab backend.

    This implementation keeps the original localized probe-force mode for
    regression and adds an incremental probe_contact mode for Stage D. Contact
    mode can emit optional tool motion and geometric contact/proximity summary
    fields while preserving the same required core artifacts.
    """

    name = "sofa_fem"

    def simulate(self, request: SampleRequest, logger: SimulationLogger | None = None) -> SampleResult:
        sofa_request = self._request_with_sofa_meta(request)
        if logger is not None:
            logger.begin(sofa_request)

        scene = self._create_sofa_scene(sofa_request)
        root = scene["root"]
        dofs = scene["dofs"]
        self._sofa_simulation().initRoot(root)

        probe_reference_vertices = self._vertex_positions(dofs)
        scene["probe_reference_vertices"] = probe_reference_vertices.copy()
        self._run_probe_preload(scene, sofa_request, probe_reference_vertices)
        vertices_0 = self._vertex_positions(dofs)
        faces = self._build_surface_faces(sofa_request.geometry)

        total_steps = int(sofa_request.config.extra.get("sofa_total_steps", 180))
        log_every_n = max(int(sofa_request.logging.log_every_n), 1)
        dt = float(root.dt.value)
        last_logged = False
        contact_observations: list[dict[str, Any]] = []

        for step in range(total_steps + 1):
            progress = step / max(total_steps, 1)
            self._update_probe_motion(scene, sofa_request, progress, vertices_0)
            vertices = self._vertex_positions(dofs)
            contact_observation = self._contact_observation(scene, sofa_request, vertices, step, step * dt)
            if contact_observation is not None:
                contact_observations.append(contact_observation)
            if step % log_every_n == 0 or step == total_steps:
                arrays = {}
                if sofa_request.logging.save_vertices:
                    arrays["vertices"] = vertices.astype(np.float32)
                if logger is not None and sofa_request.logging.enabled:
                    scalars = {
                        "progress": progress,
                        "action_type": sofa_request.action.action_type,
                        "contact_point": sofa_request.action.contact_point or (0.0, 0.0, 0.0),
                        "interaction_model": self._interaction_model(sofa_request),
                        "load_type": sofa_request.config.extra.get("sofa_load_model", self._interaction_model(sofa_request)),
                    }
                    tool_position = self._scene_tool_position(scene, sofa_request)
                    if tool_position is not None:
                        scalars["tool_position"] = tool_position.astype(float).tolist()
                        scalars["tool_radius"] = float(sofa_request.config.extra.get("sofa_probe_radius", 0.010))
                    if contact_observation is not None:
                        scalars.update(
                            {
                                "contact_active": bool(contact_observation["contact_active"]),
                                "signed_gap": float(contact_observation["signed_gap"]),
                                "contact_distance": float(contact_observation["contact_distance"]),
                                "penetration_depth": float(contact_observation["penetration_depth"]),
                                "contact_point_observed": contact_observation["nearest_point"],
                                "nearest_contact_vertex_index": int(contact_observation["nearest_vertex_index"]),
                            }
                        )
                    logger.record_frame(
                        step,
                        step * dt,
                        arrays=arrays,
                        scalars=scalars,
                    )
                last_logged = step == total_steps
            if step < total_steps:
                self._sofa_simulation().animate(root, root.dt.value)

        vertices_1 = self._vertex_positions(dofs)
        displacement = vertices_1 - vertices_0

        result = SampleResult()
        result.add("vertices_0", vertices_0.astype(np.float32))
        result.add("vertices_1", vertices_1.astype(np.float32))
        result.add("displacement", displacement.astype(np.float32))
        result.add("faces", faces.astype(np.int32))
        result.add("action", np.asarray(sofa_request.action.vector, dtype=np.float32))
        result.add("contact_point", np.asarray(sofa_request.action.contact_point or (0.0, 0.0, 0.0), dtype=np.float32))
        result.add("material", self._material_payload(sofa_request))
        result.add("meta", self._meta_payload(sofa_request))
        record_boundary_solver = bool(sofa_request.config.extra.get("sofa_record_boundary_solver", True))
        boundary_payload = self._boundary_payload(sofa_request, vertices_0) if record_boundary_solver else None
        if boundary_payload is not None:
            result.add("fixed_node_indices", boundary_payload["fixed_node_indices"].astype(np.int32))
            result.add("free_node_indices", boundary_payload["free_node_indices"].astype(np.int32))
            result.add("boundary_mask", boundary_payload["boundary_mask"].astype(bool))
            result.add("boundary", boundary_payload["boundary"])
        tool_payload = self._tool_payload(scene, sofa_request, vertices_0)
        if tool_payload is not None:
            result.add("tool_pose_0", tool_payload["tool_pose_0"].astype(np.float32))
            result.add("tool_pose_1", tool_payload["tool_pose_1"].astype(np.float32))
            result.add("tool_geometry", tool_payload["tool_geometry"])
        contact_summary = self._contact_summary(contact_observations, sofa_request)
        if contact_summary is not None:
            result.add("contact_summary", contact_summary)
        solver_summary = None
        if record_boundary_solver:
            solver_summary = self._solver_summary(sofa_request, total_steps, dt, vertices_0, vertices_1, contact_summary=contact_summary)
            result.add("solver_summary", solver_summary)
        result.summary = {
            "backend": self.name,
            "sample_id": sofa_request.config.sample_id,
            "vertex_count": int(vertices_0.shape[0]),
            "face_count": int(faces.shape[0]),
            "action_type": sofa_request.action.action_type,
            "log_dir": sofa_request.logging.log_dir_name,
            "sofa_total_steps": total_steps,
            "sofa_dt": dt,
            "max_displacement": float(np.linalg.norm(displacement, axis=1).max()),
            "last_frame_logged": last_logged,
            "sofa_interaction_model": self._interaction_model(sofa_request),
            "tool_pose_recorded": tool_payload is not None,
            "contact_summary_recorded": contact_summary is not None,
            "contact_detected": bool(contact_summary.get("contact_detected", False)) if contact_summary else False,
            "boundary_solver_recorded": bool(record_boundary_solver),
        }

        if logger is not None:
            logger.record_event(
                "sample_ready",
                {
                    "sample_id": sofa_request.config.sample_id,
                    "vertex_count": int(vertices_0.shape[0]),
                    "face_count": int(faces.shape[0]),
                    "max_displacement": result.summary["max_displacement"],
                },
            )
            logger.finish(result.summary)

        self._sofa_simulation().unload(root)
        return result

    def _request_with_sofa_meta(self, request: SampleRequest) -> SampleRequest:
        cfg = request.config
        extra = dict(cfg.extra)
        extra.setdefault("sofa_total_steps", 180)
        extra.setdefault("sofa_dt", 0.01)
        if "sofa_load_model" not in extra:
            extra["sofa_load_model"] = str(extra.get("sofa_interaction_model", "localized_probe_force"))
        extra.setdefault("sofa_interaction_model", str(extra.get("sofa_load_model", "localized_probe_force")))
        extra.setdefault("sofa_probe_radius", 0.024)
        extra.setdefault("sofa_probe_force_scale", 4.0)
        extra.setdefault("sofa_probe_max_force", 6.0)
        extra.setdefault("sofa_probe_clearance", 0.010)
        extra.setdefault("sofa_probe_contact_distance", 0.002)
        extra.setdefault("sofa_probe_alarm_distance", 0.006)
        extra.setdefault("sofa_record_tool_motion", False)
        extra.setdefault("sofa_record_contact_summary", True)
        extra.setdefault("sofa_record_boundary_solver", True)
        extra.setdefault("sofa_solver_tolerance", 1e-9)
        extra.setdefault("sofa_solver_threshold", 1e-9)
        extra.setdefault("sofa_constraint_solver_tolerance", 1e-6)
        extra.setdefault("sofa_constraint_solver_max_iterations", 100)
        extra.setdefault("sofa_probe_force_material_scaling", True)
        extra.setdefault("sofa_tissue_shape", "slab")
        tissue_shape = str(extra.get("sofa_tissue_shape", "slab"))
        return replace(
            request,
            config=replace(
                cfg,
                simulator="sofa_fem",
                tissue_type=f"sofa_{tissue_shape}",
                notes=f"SOFA FEM {tissue_shape} {extra.get('sofa_interaction_model')} sample",
                extra=extra,
            ),
        )

    def _create_sofa_scene(self, request: SampleRequest) -> dict[str, Any]:
        Sofa, SofaRuntime = self._sofa_modules()
        plugins = self._required_plugins(request)
        for plugin in plugins:
            SofaRuntime.importPlugin(plugin)

        geometry = request.geometry
        material = request.material
        cfg = request.config.extra
        interaction_model = self._interaction_model(request)
        root = Sofa.Core.Node("root")
        root.gravity = [0.0, 0.0, 0.0]
        root.dt = float(cfg.get("sofa_dt", 0.01))
        root.addObject("RequiredPlugin", pluginName=plugins)
        if interaction_model == "probe_contact":
            root.addObject("FreeMotionAnimationLoop")
            root.addObject(
                "GenericConstraintSolver",
                tolerance=float(cfg.get("sofa_constraint_solver_tolerance", 1e-6)),
                maxIterations=int(cfg.get("sofa_constraint_solver_max_iterations", 100)),
            )
            root.addObject("CollisionPipeline")
            root.addObject("BruteForceBroadPhase")
            root.addObject("BVHNarrowPhase")
            root.addObject(
                "LocalMinDistance",
                alarmDistance=float(cfg.get("sofa_probe_alarm_distance", 0.006)),
                contactDistance=float(cfg.get("sofa_probe_contact_distance", 0.002)),
                angleCone=0.0,
            )
            root.addObject("CollisionResponse", response="FrictionContactConstraint")
        elif interaction_model == "localized_probe_force":
            root.addObject("DefaultAnimationLoop")
        else:
            raise ValueError(f"Unsupported sofa_interaction_model: {interaction_model}")

        half_x = geometry.size_x * 0.5
        half_y = geometry.size_y * 0.5
        half_z = geometry.thickness * 0.5
        nx = max(int(geometry.nx) + 1, 2)
        ny = max(int(geometry.ny) + 1, 2)
        nz = max(int(geometry.layers), 2)

        slab = root.addChild("Slab")
        slab.addObject("EulerImplicitSolver", name="ode", rayleighStiffness=0.05, rayleighMass=max(material.damping, 0.0) * 0.02)
        slab.addObject(
            "CGLinearSolver",
            name="linear_solver",
            iterations=80 if interaction_model == "probe_contact" else 50,
            tolerance=float(cfg.get("sofa_solver_tolerance", 1e-9)),
            threshold=float(cfg.get("sofa_solver_threshold", 1e-9)),
        )
        slab.addObject(
            "RegularGridTopology",
            name="grid",
            n=f"{nx} {ny} {nz}",
            min=f"{-half_x} {-half_y} {-half_z}",
            max=f"{half_x} {half_y} {half_z}",
        )
        positions = self._initial_positions(geometry, str(cfg.get("sofa_tissue_shape", "slab")))
        dofs = slab.addObject("MechanicalObject", name="dofs", template="Vec3", position=positions.tolist())
        slab.addObject("UniformMass", name="mass", totalMass=max(float(material.density) * geometry.size_x * geometry.size_y * geometry.thickness, 1e-6))
        slab.addObject("FixedProjectiveConstraint", name="fixed_bottom", indices=self._bottom_indices(geometry))
        if interaction_model == "probe_contact":
            slab.addObject("UncoupledConstraintCorrection", defaultCompliance=1e-7)
            slab.addObject("PointCollisionModel")
        else:
            probe_box = self._probe_roi_box(request, half_z)
            slab.addObject(
                "BoxROI",
                name="probe_roi",
                box=probe_box,
                position="@dofs.position",
            )
            force_vector = self._force_vector_from_action(request)
            slab.addObject(
                "ConstantForceField",
                name="probe_load",
                indices="@probe_roi.indices",
                totalForce=f"{force_vector[0]} {force_vector[1]} {force_vector[2]}",
            )

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
            poissonRatio=float(material.poisson_ratio),
            youngModulus=float(material.youngs_modulus),
        )

        scene: dict[str, Any] = {"root": root, "dofs": dofs, "interaction_model": interaction_model}
        if interaction_model == "probe_contact":
            contact = request.action.contact_point or (0.0, 0.0, half_z)
            probe = root.addChild("Probe")
            probe_dofs = probe.addObject(
                "MechanicalObject",
                name="dofs",
                template="Vec3",
                position=[[float(contact[0]), float(contact[1]), half_z + float(cfg.get("sofa_probe_radius", 0.010)) + float(cfg.get("sofa_probe_clearance", 0.010))]],
            )
            probe.addObject("SphereCollisionModel", radius=float(cfg.get("sofa_probe_radius", 0.010)))
            probe.addObject("FixedProjectiveConstraint", indices="0")
            scene["probe_dofs"] = probe_dofs
        return scene

    def _interaction_model(self, request: SampleRequest) -> str:
        extra = request.config.extra
        return str(extra.get("sofa_interaction_model", extra.get("sofa_load_model", "localized_probe_force")))

    def _update_probe_motion(self, scene: dict[str, Any], request: SampleRequest, progress: float, vertices_0: np.ndarray) -> None:
        if scene.get("interaction_model") != "probe_contact":
            return
        probe_dofs = scene.get("probe_dofs")
        if probe_dofs is None:
            return
        reference_vertices = scene.get("probe_reference_vertices", vertices_0)
        start_position, end_position = self._tool_start_end_positions(request, np.asarray(reference_vertices, dtype=np.float64))
        position = start_position + (end_position - start_position) * float(progress)
        probe_dofs.position.value = [position.astype(float).tolist()]

    def _scene_tool_position(self, scene: dict[str, Any], request: SampleRequest) -> np.ndarray | None:
        if scene.get("interaction_model") != "probe_contact" or not bool(request.config.extra.get("sofa_record_tool_motion", False)):
            return None
        return self._probe_position(scene)

    def _probe_position(self, scene: dict[str, Any]) -> np.ndarray | None:
        probe_dofs = scene.get("probe_dofs")
        if probe_dofs is None:
            return None
        return np.asarray(probe_dofs.position.array(), dtype=np.float64).reshape(-1, 3)[0].copy()

    def _tool_payload(self, scene: dict[str, Any], request: SampleRequest, vertices_0: np.ndarray) -> dict[str, Any] | None:
        if scene.get("interaction_model") != "probe_contact" or not bool(request.config.extra.get("sofa_record_tool_motion", False)):
            return None
        reference_vertices = scene.get("probe_reference_vertices", vertices_0)
        start_position, end_position = self._tool_start_end_positions(request, np.asarray(reference_vertices, dtype=np.float64))
        radius = float(request.config.extra.get("sofa_probe_radius", 0.010))
        return {
            "tool_pose_0": self._pose_matrix(start_position),
            "tool_pose_1": self._pose_matrix(end_position),
            "tool_geometry": {
                "type": "sphere",
                "radius": radius,
                "frame": "tool_pose_center",
                "unit": "meter",
                "source": "sofa_probe_contact",
                "motion_direction_source": "action_vector_2_4",
            },
        }

    def _tool_start_end_positions(self, request: SampleRequest, vertices_0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cfg = request.config.extra
        action = np.asarray(request.action.vector, dtype=np.float64)
        depth = float(action[5]) if action.shape[0] >= 6 else 0.0025
        preload_depth = float(cfg.get("sofa_probe_preload_depth", 0.0))
        clearance = float(cfg.get("sofa_probe_clearance", 0.010))
        max_depth = float(cfg.get("sofa_probe_contact_max_depth", 0.0025))
        incremental = bool(cfg.get("sofa_probe_incremental_after_preload", preload_depth > 0.0))
        depth = max(depth, 0.0)
        if incremental:
            start_depth = min(max(preload_depth, 0.0), max_depth)
            increment_depth = min(depth, max(max_depth - start_depth, 0.0))
            preload_direction = self._preload_direction(request)
            start_position = self._tool_position_for_depth(
                request, vertices_0, start_depth, clearance=0.0, direction=preload_direction
            )
            end_position = start_position + self._action_direction(request) * increment_depth
        else:
            start_depth = 0.0
            end_depth = min(depth, max_depth)
            start_position = self._tool_position_for_depth(request, vertices_0, start_depth, clearance=clearance)
            end_position = self._tool_position_for_depth(request, vertices_0, end_depth, clearance=0.0)
        return start_position, end_position

    def _tool_position_for_depth(
        self,
        request: SampleRequest,
        vertices_0: np.ndarray,
        depth: float,
        *,
        clearance: float,
        direction: np.ndarray | None = None,
    ) -> np.ndarray:
        cfg = request.config.extra
        radius = float(cfg.get("sofa_probe_radius", 0.010))
        if direction is None:
            direction = self._action_direction(request)
        contact = request.action.contact_point or (0.0, 0.0, float(vertices_0[:, 2].max()))
        top_z = float(vertices_0[:, 2].max())
        contact_anchor = np.asarray([float(contact[0]), float(contact[1]), top_z], dtype=np.float64)
        return contact_anchor - direction * (radius + max(clearance, 0.0)) + direction * max(depth, 0.0)

    def _run_probe_preload(self, scene: dict[str, Any], request: SampleRequest, vertices_ref: np.ndarray) -> None:
        if scene.get("interaction_model") != "probe_contact":
            return
        preload_depth = float(request.config.extra.get("sofa_probe_preload_depth", 0.0))
        if preload_depth <= 0.0:
            return
        probe_dofs = scene.get("probe_dofs")
        if probe_dofs is None:
            return
        max_depth = float(request.config.extra.get("sofa_probe_contact_max_depth", preload_depth))
        preload_depth = min(preload_depth, max_depth)
        preload_direction = self._preload_direction(request)
        start_position = self._tool_position_for_depth(
            request,
            vertices_ref,
            0.0,
            clearance=float(request.config.extra.get("sofa_probe_clearance", 0.010)),
            direction=preload_direction,
        )
        preload_position = self._tool_position_for_depth(
            request, vertices_ref, preload_depth, clearance=0.0, direction=preload_direction
        )
        motion_steps = max(int(request.config.extra.get("sofa_probe_preload_motion_steps", 40)), 1)
        settle_steps = max(int(request.config.extra.get("sofa_probe_preload_settle_steps", 80)), 0)
        for step in range(motion_steps):
            progress = (step + 1) / motion_steps
            position = start_position + (preload_position - start_position) * progress
            probe_dofs.position.value = [position.astype(float).tolist()]
            self._sofa_simulation().animate(scene["root"], scene["root"].dt.value)
        for _ in range(settle_steps):
            probe_dofs.position.value = [preload_position.astype(float).tolist()]
            self._sofa_simulation().animate(scene["root"], scene["root"].dt.value)

    def _preload_direction(self, request: SampleRequest) -> np.ndarray:
        value = request.config.extra.get("sofa_probe_preload_direction", [0.0, 0.0, -1.0])
        direction = np.asarray(value, dtype=np.float64).reshape(3)
        norm = float(np.linalg.norm(direction))
        if norm <= 0.0:
            return np.asarray([0.0, 0.0, -1.0], dtype=np.float64)
        return direction / norm

    def _pose_matrix(self, position: np.ndarray) -> np.ndarray:
        pose = np.eye(4, dtype=np.float64)
        pose[:3, 3] = np.asarray(position, dtype=np.float64)[:3]
        return pose

    def _contact_observation(
        self,
        scene: dict[str, Any],
        request: SampleRequest,
        vertices: np.ndarray,
        step_index: int,
        time_code: float,
    ) -> dict[str, Any] | None:
        if scene.get("interaction_model") != "probe_contact" or not bool(request.config.extra.get("sofa_record_contact_summary", True)):
            return None
        center = self._probe_position(scene)
        if center is None:
            return None
        radius = float(request.config.extra.get("sofa_probe_radius", 0.010))
        contact_distance = float(request.config.extra.get("sofa_probe_contact_distance", 0.002))
        signed_gap, nearest_index, nearest_point = self._signed_sphere_gap(vertices, center, radius)
        return {
            "step_index": int(step_index),
            "time_code": float(time_code),
            "contact_active": bool(signed_gap <= contact_distance + 1e-9),
            "signed_gap": float(signed_gap),
            "contact_distance": contact_distance,
            "penetration_depth": float(max(-signed_gap, 0.0)),
            "probe_center": center.astype(float).tolist(),
            "probe_radius": radius,
            "nearest_vertex_index": int(nearest_index),
            "nearest_point": nearest_point.astype(float).tolist(),
        }

    def _contact_summary(self, observations: list[dict[str, Any]], request: SampleRequest) -> dict[str, Any] | None:
        if not observations:
            return None
        active = [item for item in observations if bool(item["contact_active"])]
        min_gap_item = min(observations, key=lambda item: float(item["signed_gap"]))
        max_penetration_item = max(observations, key=lambda item: float(item["penetration_depth"]))
        first_active = active[0] if active else None
        return {
            "contact_detected": bool(active),
            "first_contact_step": int(first_active["step_index"]) if first_active is not None else None,
            "first_contact_time": float(first_active["time_code"]) if first_active is not None else None,
            "contact_frame_count": int(len(active)),
            "observation_count": int(len(observations)),
            "min_signed_gap": float(min_gap_item["signed_gap"]),
            "min_signed_gap_step": int(min_gap_item["step_index"]),
            "max_penetration": float(max_penetration_item["penetration_depth"]),
            "max_penetration_step": int(max_penetration_item["step_index"]),
            "final_signed_gap": float(observations[-1]["signed_gap"]),
            "contact_distance": float(request.config.extra.get("sofa_probe_contact_distance", 0.002)),
            "alarm_distance": float(request.config.extra.get("sofa_probe_alarm_distance", 0.006)),
            "method": "sphere_to_vertex_gap",
            "force_available": False,
            "contact_force_method": "unavailable",
            "unit": "meter",
            "nearest_vertex_index_at_min_gap": int(min_gap_item["nearest_vertex_index"]),
            "nearest_point_at_min_gap": list(min_gap_item["nearest_point"]),
            "probe_center_at_min_gap": list(min_gap_item["probe_center"]),
            "probe_radius": float(min_gap_item["probe_radius"]),
        }

    def _signed_sphere_gap(self, vertices: np.ndarray, center: np.ndarray, radius: float) -> tuple[float, int, np.ndarray]:
        distances = np.linalg.norm(vertices - center[None, :], axis=1) - float(radius)
        nearest_index = int(np.argmin(distances))
        return float(distances[nearest_index]), nearest_index, vertices[nearest_index].copy()

    def _force_vector_from_action(self, request: SampleRequest) -> np.ndarray:
        action = np.asarray(request.action.vector, dtype=np.float64)
        depth = float(action[5]) if action.shape[0] >= 6 else 0.008
        youngs = max(float(request.material.youngs_modulus), 1.0)
        stiffness_scale = youngs / 5000.0 if bool(request.config.extra.get("sofa_probe_force_material_scaling", True)) else 1.0
        force_scale = float(request.config.extra.get("sofa_probe_force_scale", 4.0))
        max_force = float(request.config.extra.get("sofa_probe_max_force", 6.0))
        magnitude = min(force_scale * (depth / 0.008) * stiffness_scale, max_force)
        return self._action_direction(request) * magnitude

    def _action_direction(self, request: SampleRequest) -> np.ndarray:
        action = np.asarray(request.action.vector, dtype=np.float64)
        if action.shape[0] >= 5:
            direction = action[2:5]
        else:
            direction = np.asarray([0.0, 0.0, -1.0], dtype=np.float64)
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-12:
            direction = np.asarray([0.0, 0.0, -1.0], dtype=np.float64)
        else:
            direction = direction / norm
        if float(direction[2]) >= 0.0:
            raise ValueError(f"Press action direction must point downward, got {direction.tolist()}")
        return direction

    def _probe_roi_box(self, request: SampleRequest, half_z: float) -> str:
        geometry = request.geometry
        contact = request.action.contact_point or (0.0, 0.0, half_z)
        radius = float(request.config.extra.get("sofa_probe_radius", 0.024))
        radius = max(radius, min(geometry.size_x, geometry.size_y) * 0.08)
        z_band = max(geometry.thickness * 0.35, 1e-6)
        x = float(contact[0])
        y = float(contact[1])
        return (
            f"{x - radius} {y - radius} {half_z - z_band} "
            f"{x + radius} {y + radius} {half_z + 1e-6}"
        )

    def _initial_positions(self, geometry, tissue_shape: str) -> np.ndarray:
        nx = max(int(geometry.nx) + 1, 2)
        ny = max(int(geometry.ny) + 1, 2)
        nz = max(int(geometry.layers), 2)
        half_x = geometry.size_x * 0.5
        half_y = geometry.size_y * 0.5
        half_z = geometry.thickness * 0.5
        positions: list[list[float]] = []
        for k in range(nz):
            zn = -1.0 + 2.0 * k / max(nz - 1, 1)
            for j in range(ny):
                yn = -1.0 + 2.0 * j / max(ny - 1, 1)
                for i in range(nx):
                    xn = -1.0 + 2.0 * i / max(nx - 1, 1)
                    if tissue_shape == "liver_like":
                        positions.append(self._liver_like_position(xn, yn, zn, half_x, half_y, half_z))
                    else:
                        positions.append([half_x * xn, half_y * yn, half_z * zn])
        return np.asarray(positions, dtype=np.float64)

    def _liver_like_position(self, xn: float, yn: float, zn: float, half_x: float, half_y: float, half_z: float) -> list[float]:
        right_lobe = 0.86 + 0.18 / (1.0 + np.exp(-3.0 * (xn + 0.10)))
        edge_round = max(0.40, 1.0 - 0.30 * abs(xn) ** 1.7)
        y_scale = right_lobe * edge_round
        dome = max(0.35, 1.0 - 0.42 * abs(xn) ** 1.8 - 0.34 * abs(yn) ** 1.8)
        asym_shift = 0.07 * (1.0 - yn * yn) * (1.0 - 0.35 * abs(zn))
        notch = 0.05 * np.exp(-((xn + 0.18) ** 2 / 0.08 + (yn - 0.85) ** 2 / 0.05))
        x = half_x * (0.94 * xn + asym_shift - notch)
        y = half_y * yn * y_scale
        z = half_z * zn * dome
        return [float(x), float(y), float(z)]

    def _bottom_indices(self, geometry) -> str:
        nx = max(int(geometry.nx) + 1, 2)
        ny = max(int(geometry.ny) + 1, 2)
        return " ".join(str(j * nx + i) for j in range(ny) for i in range(nx))

    def _vertex_positions(self, dofs: Any) -> np.ndarray:
        return np.asarray(dofs.position.array(), dtype=np.float64).copy()

    def _build_surface_faces(self, geometry) -> np.ndarray:
        nx = max(int(geometry.nx) + 1, 2)
        ny = max(int(geometry.ny) + 1, 2)
        nz = max(int(geometry.layers), 2)

        def idx(i: int, j: int, k: int) -> int:
            return k * nx * ny + j * nx + i

        faces: list[list[int]] = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                faces.append([idx(i, j, nz - 1), idx(i + 1, j, nz - 1), idx(i + 1, j + 1, nz - 1), idx(i, j + 1, nz - 1)])
                faces.append([idx(i + 1, j, 0), idx(i, j, 0), idx(i, j + 1, 0), idx(i + 1, j + 1, 0)])
        for k in range(nz - 1):
            for i in range(nx - 1):
                faces.append([idx(i, 0, k), idx(i + 1, 0, k), idx(i + 1, 0, k + 1), idx(i, 0, k + 1)])
                faces.append([idx(i + 1, ny - 1, k), idx(i, ny - 1, k), idx(i, ny - 1, k + 1), idx(i + 1, ny - 1, k + 1)])
            for j in range(ny - 1):
                faces.append([idx(0, j + 1, k), idx(0, j, k), idx(0, j, k + 1), idx(0, j + 1, k + 1)])
                faces.append([idx(nx - 1, j, k), idx(nx - 1, j + 1, k), idx(nx - 1, j + 1, k + 1), idx(nx - 1, j, k + 1)])
        return np.asarray(faces, dtype=np.int32)

    def _bottom_index_array(self, geometry) -> np.ndarray:
        nx = max(int(geometry.nx) + 1, 2)
        ny = max(int(geometry.ny) + 1, 2)
        return np.asarray([j * nx + i for j in range(ny) for i in range(nx)], dtype=np.int32)

    def _boundary_payload(self, request: SampleRequest, vertices_0: np.ndarray) -> dict[str, Any]:
        fixed = self._bottom_index_array(request.geometry)
        vertex_count = int(vertices_0.shape[0])
        mask = np.zeros(vertex_count, dtype=bool)
        mask[fixed] = True
        free = np.nonzero(~mask)[0].astype(np.int32)
        fixed_points = vertices_0[fixed]
        bbox_min = fixed_points.min(axis=0).astype(float).tolist()
        bbox_max = fixed_points.max(axis=0).astype(float).tolist()
        boundary = {
            "boundary_type": "fixed_bottom",
            "constraint_object": "FixedProjectiveConstraint",
            "selection_method": "regular_grid_bottom_layer",
            "fixed_node_count": int(fixed.shape[0]),
            "free_node_count": int(free.shape[0]),
            "total_node_count": vertex_count,
            "fixed_z": float(fixed_points[:, 2].mean()) if fixed_points.size else None,
            "boundary_box": {
                "min": bbox_min,
                "max": bbox_max,
                "unit": "meter",
            },
            "mask_artifact": "boundary_mask.npy",
            "fixed_indices_artifact": "fixed_node_indices.npy",
            "free_indices_artifact": "free_node_indices.npy",
        }
        return {
            "fixed_node_indices": fixed,
            "free_node_indices": free,
            "boundary_mask": mask,
            "boundary": boundary,
        }

    def _solver_summary(
        self,
        request: SampleRequest,
        total_steps: int,
        dt: float,
        vertices_0: np.ndarray,
        vertices_1: np.ndarray,
        *,
        contact_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        cfg = request.config.extra
        interaction_model = self._interaction_model(request)
        finite = bool(np.isfinite(vertices_0).all() and np.isfinite(vertices_1).all())
        displacement = vertices_1 - vertices_0
        return {
            "valid": finite,
            "finite": finite,
            "solver_converged": None,
            "solver_residual": None,
            "solver_status_method": "finite_state_check_only",
            "dt": float(dt),
            "total_steps": int(total_steps),
            "settling_steps": int(total_steps),
            "record_every_n": int(request.logging.log_every_n),
            "interaction_model": interaction_model,
            "ode_solver": "EulerImplicitSolver",
            "linear_solver": "CGLinearSolver",
            "linear_solver_iterations": 80 if interaction_model == "probe_contact" else 50,
            "linear_solver_tolerance": float(cfg.get("sofa_solver_tolerance", 1e-9)),
            "linear_solver_threshold": float(cfg.get("sofa_solver_threshold", 1e-9)),
            "animation_loop": "FreeMotionAnimationLoop" if interaction_model == "probe_contact" else "DefaultAnimationLoop",
            "constraint_solver": "GenericConstraintSolver" if interaction_model == "probe_contact" else None,
            "constraint_solver_tolerance": float(cfg.get("sofa_constraint_solver_tolerance", 1e-6)) if interaction_model == "probe_contact" else None,
            "constraint_solver_max_iterations": int(cfg.get("sofa_constraint_solver_max_iterations", 100)) if interaction_model == "probe_contact" else None,
            "collision_pipeline": "CollisionPipeline" if interaction_model == "probe_contact" else None,
            "collision_response": "FrictionContactConstraint" if interaction_model == "probe_contact" else None,
            "contact_method": contact_summary.get("method") if contact_summary else None,
            "contact_detected": bool(contact_summary.get("contact_detected", False)) if contact_summary else False,
            "max_displacement": float(np.linalg.norm(displacement, axis=1).max()) if displacement.size else 0.0,
            "nan_or_inf_detected": not finite,
            "unit": "meter",
        }

    def _material_payload(self, request: SampleRequest) -> dict:
        material = request.material
        return {
            "youngs_modulus": material.youngs_modulus,
            "poisson_ratio": material.poisson_ratio,
            "density": material.density,
            "damping": material.damping,
            "boundary_condition": material.boundary_condition,
            "extra": dict(material.extra),
        }

    def _meta_payload(self, request: SampleRequest) -> dict:
        cfg = request.config
        return {
            "sample_id": cfg.sample_id,
            "scene_id": cfg.scene_id,
            "simulator": cfg.simulator,
            "tissue_type": cfg.tissue_type,
            "action_type": request.action.action_type,
            "unit": cfg.unit,
            "notes": cfg.notes,
            "extra": dict(cfg.extra),
            "geometry": {
                "size_x": request.geometry.size_x,
                "size_y": request.geometry.size_y,
                "thickness": request.geometry.thickness,
                "nx": request.geometry.nx,
                "ny": request.geometry.ny,
                "layers": request.geometry.layers,
                "fixed_border_ratio": request.geometry.fixed_border_ratio,
            },
            "logging": {
                "enabled": request.logging.enabled,
                "log_dir_name": request.logging.log_dir_name,
                "log_every_n": request.logging.log_every_n,
                "save_vertices": request.logging.save_vertices,
                "save_tool_pose": request.logging.save_tool_pose,
                "save_events": request.logging.save_events,
            },
        }

    def _required_plugins(self, request: SampleRequest | None = None) -> list[str]:
        plugins = [
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
        if request is not None and self._interaction_model(request) == "probe_contact":
            plugins.extend(
                [
                    "Sofa.Component.AnimationLoop",
                    "Sofa.Component.Collision.Detection.Algorithm",
                    "Sofa.Component.Collision.Detection.Intersection",
                    "Sofa.Component.Collision.Geometry",
                    "Sofa.Component.Collision.Response.Contact",
                    "Sofa.Component.Constraint.Lagrangian.Correction",
                    "Sofa.Component.Constraint.Lagrangian.Solver",
                ]
            )
        return plugins

    def _sofa_modules(self):
        try:
            import Sofa
            import SofaRuntime
        except ImportError as exc:
            raise RuntimeError(
                "SofaFemBackend requires the SOFA conda environment. "
                "Use scripts/run_sofa_python.sh or activate $HOME/conda/envs/sofa."
            ) from exc
        return Sofa, SofaRuntime

    def _sofa_simulation(self):
        try:
            import Sofa.Simulation
        except ImportError as exc:
            raise RuntimeError(
                "SofaFemBackend requires Sofa.Simulation from SofaPython3. "
                "Use scripts/run_sofa_python.sh or activate $HOME/conda/envs/sofa."
            ) from exc
        return Sofa.Simulation
