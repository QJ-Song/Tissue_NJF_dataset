from __future__ import annotations

from typing import Tuple

import numpy as np

from ..backend import SimulationBackend, SimulationLogger
from ..schema import SampleRequest, SampleResult


class ToyPressBackend:
    """Deterministic toy backend for module validation.

    The implementation is intentionally backend-agnostic in data shape. It can
    be replaced by Isaac Sim or SOFA later as long as the returned artifacts
    follow the same layout.
    """

    name = "toy_press"

    def simulate(self, request: SampleRequest, logger: SimulationLogger | None = None) -> SampleResult:
        if logger is not None:
            logger.begin(request)

        geometry = request.geometry
        material = request.material
        action = request.action

        vertices_0, faces = self._build_slab_mesh(geometry)
        vertices_1 = self._deform(vertices_0, geometry, material, action)
        displacement = vertices_1 - vertices_0

        self._log_trajectory(vertices_0, geometry, material, action, logger, request)

        result = SampleResult()
        result.add("vertices_0", vertices_0)
        result.add("vertices_1", vertices_1)
        result.add("displacement", displacement)
        result.add("faces", faces)
        result.add("action", np.asarray(action.vector, dtype=np.float32))
        result.add("contact_point", np.asarray(action.contact_point or (0.0, 0.0, 0.0), dtype=np.float32))
        result.add("material", self._material_payload(request))
        result.add("meta", self._meta_payload(request))
        if action.tool_pose_0 is not None:
            result.add("tool_pose_0", np.asarray(action.tool_pose_0, dtype=np.float32))
        if action.tool_pose_1 is not None:
            result.add("tool_pose_1", np.asarray(action.tool_pose_1, dtype=np.float32))
        result.summary = {
            "backend": self.name,
            "sample_id": request.config.sample_id,
            "vertex_count": int(vertices_0.shape[0]),
            "face_count": int(faces.shape[0]),
            "action_type": action.action_type,
            "log_dir": request.logging.log_dir_name,
        }

        if logger is not None:
            logger.record_event(
                "sample_ready",
                {
                    "sample_id": request.config.sample_id,
                    "vertex_count": int(vertices_0.shape[0]),
                    "face_count": int(faces.shape[0]),
                },
            )
            logger.finish(result.summary)

        return result

    def _log_trajectory(self, vertices_0, geometry, material, action, logger, request: SampleRequest) -> None:
        if logger is None or not request.logging.enabled:
            return

        total_steps = 180
        log_every_n = max(int(request.logging.log_every_n), 1)
        for step in range(total_steps + 1):
            if step % log_every_n != 0 and step != total_steps:
                continue
            progress = self._progress_at_step(step, total_steps)
            current = self._deform_with_progress(vertices_0, geometry, material, action, progress)
            arrays = {}
            if request.logging.save_vertices:
                arrays["vertices"] = current.astype(np.float32)
            if request.logging.save_tool_pose and action.tool_pose_0 is not None and action.tool_pose_1 is not None:
                tool_pose = self._interpolate_pose(action.tool_pose_0, action.tool_pose_1, progress)
                arrays["tool_pose"] = tool_pose.astype(np.float32)
            logger.record_frame(
                step,
                step / 60.0,
                arrays=arrays,
                scalars={
                    "progress": progress,
                    "action_type": action.action_type,
                    "contact_point": action.contact_point or (0.0, 0.0, 0.0),
                },
            )

    def _progress_at_step(self, step: int, total_steps: int) -> float:
        if step < 25:
            return 0.0
        if step < 70:
            return (step - 25) / 45.0
        if step < 115:
            return 1.0
        if step < 150:
            return 1.0 - (step - 115) / 35.0
        return 0.0

    def _interpolate_pose(self, pose_0, pose_1, alpha: float) -> np.ndarray:
        pose_0 = np.asarray(pose_0, dtype=np.float32)
        pose_1 = np.asarray(pose_1, dtype=np.float32)
        return pose_0 * (1.0 - alpha) + pose_1 * alpha

    def _deform(self, vertices: np.ndarray, geometry, material, action) -> np.ndarray:
        return self._deform_with_progress(vertices, geometry, material, action, 1.0)

    def _build_slab_mesh(self, geometry) -> Tuple[np.ndarray, np.ndarray]:
        nx = geometry.nx
        ny = geometry.ny
        size_x = geometry.size_x
        size_y = geometry.size_y
        thickness = geometry.thickness
        half_x = size_x / 2.0
        half_y = size_y / 2.0
        z_top = thickness / 2.0
        z_bottom = -thickness / 2.0

        top = []
        bottom = []
        for j in range(ny + 1):
            y = -half_y + size_y * j / ny
            for i in range(nx + 1):
                x = -half_x + size_x * i / nx
                top.append((x, y, z_top))
                bottom.append((x, y, z_bottom))

        vertices = np.asarray(top + bottom, dtype=np.float32)
        faces = self._build_faces(nx, ny)
        return vertices, faces

    def _build_faces(self, nx: int, ny: int) -> np.ndarray:
        top_offset = 0
        bottom_offset = (nx + 1) * (ny + 1)
        counts = []

        for j in range(ny):
            for i in range(nx):
                a = top_offset + j * (nx + 1) + i
                b = a + 1
                c = a + (nx + 1) + 1
                d = a + (nx + 1)
                counts.append([a, b, c, d])

        for j in range(ny):
            for i in range(nx):
                a = bottom_offset + j * (nx + 1) + i
                b = a + (nx + 1)
                c = a + (nx + 1) + 1
                d = a + 1
                counts.append([a, b, c, d])

        for i in range(nx):
            top_a = top_offset + i
            top_b = top_offset + i + 1
            bot_b = bottom_offset + i + 1
            bot_a = bottom_offset + i
            counts.append([top_a, top_b, bot_b, bot_a])

            top_a = top_offset + ny * (nx + 1) + i
            top_b = top_offset + ny * (nx + 1) + i + 1
            bot_b = bottom_offset + ny * (nx + 1) + i + 1
            bot_a = bottom_offset + ny * (nx + 1) + i
            counts.append([top_b, top_a, bot_a, bot_b])

        for j in range(ny):
            top_a = top_offset + j * (nx + 1)
            top_b = top_offset + (j + 1) * (nx + 1)
            bot_b = bottom_offset + (j + 1) * (nx + 1)
            bot_a = bottom_offset + j * (nx + 1)
            counts.append([top_b, top_a, bot_a, bot_b])

            top_a = top_offset + j * (nx + 1) + nx
            top_b = top_offset + (j + 1) * (nx + 1) + nx
            bot_b = bottom_offset + (j + 1) * (nx + 1) + nx
            bot_a = bottom_offset + j * (nx + 1) + nx
            counts.append([top_a, top_b, bot_b, bot_a])

        return np.asarray(counts, dtype=np.int32)

    def _deform_with_progress(self, vertices: np.ndarray, geometry, material, action, progress: float) -> np.ndarray:
        out = vertices.copy()
        top_count = (geometry.nx + 1) * (geometry.ny + 1)
        top = out[:top_count]

        vector = np.asarray(action.vector, dtype=np.float32)
        contact_x = float(vector[0])
        contact_y = float(vector[1])
        direction = vector[2:5]
        depth = float(vector[5]) * progress
        direction_norm = np.linalg.norm(direction)
        if direction_norm == 0.0:
            direction = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        else:
            direction = direction / direction_norm

        compliance = self._compliance(material.youngs_modulus, material.damping)
        local_depth = depth * compliance
        sigma_core = max(geometry.size_x, geometry.size_y) * 0.14
        sigma_rim = sigma_core * 0.45

        xs = top[:, 0]
        ys = top[:, 1]
        r2 = (xs - contact_x) ** 2 + (ys - contact_y) ** 2
        core = np.exp(-r2 / (2.0 * sigma_core**2))
        rim = np.exp(-((np.sqrt(r2) - sigma_core * 1.7) ** 2) / (2.0 * sigma_rim**2))
        border = self._border_mask(xs, ys, geometry)
        displacement_z = (-local_depth * core + 0.20 * local_depth * rim) * border
        displacement = np.zeros_like(top)
        displacement[:, :3] = direction[:3] * displacement_z[:, None]
        displacement[:, 2] = displacement_z

        out[:top_count] = top + displacement
        return out

    def _border_mask(self, xs: np.ndarray, ys: np.ndarray, geometry) -> np.ndarray:
        half_x = geometry.size_x / 2.0
        half_y = geometry.size_y / 2.0
        margin_x = half_x * geometry.fixed_border_ratio
        margin_y = half_y * geometry.fixed_border_ratio
        inner_x = np.clip((half_x - np.abs(xs)) / max(margin_x, 1e-6), 0.0, 1.0)
        inner_y = np.clip((half_y - np.abs(ys)) / max(margin_y, 1e-6), 0.0, 1.0)
        return np.minimum(inner_x, inner_y)

    def _compliance(self, youngs_modulus: float, damping: float) -> float:
        stiffness_scale = 10_000.0 / max(youngs_modulus, 1.0)
        damping_scale = 1.0 / (1.0 + max(damping, 0.0) * 0.35)
        return float(np.clip(stiffness_scale * damping_scale, 0.25, 3.0))

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
            "logging": {
                "enabled": request.logging.enabled,
                "log_dir_name": request.logging.log_dir_name,
                "log_every_n": request.logging.log_every_n,
                "save_vertices": request.logging.save_vertices,
                "save_tool_pose": request.logging.save_tool_pose,
                "save_events": request.logging.save_events,
            },
        }
