from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .core import ReplayFrame, ReplayReader


class IsaacSimReplayViewer:
    """Replay logged tissue vertices into a USD scene for Isaac Sim.

    This viewer is intentionally an offline exporter first: it writes a USDA
    animation that Isaac Sim can open and play on the timeline. It does not
    rerun physics and does not require the high-cost viewport during dataset
    collection.
    """

    name = "isaacsim_usd"

    def __init__(self, output_name: str = "isaacsim_replay.usda"):
        self.output_name = output_name
        self.reader: ReplayReader | None = None
        self.output_dir: Path | None = None
        self.output_path: Path | None = None
        self.stage = None
        self.mesh = None
        self.points_attr = None
        self.tool_translate_op = None
        self.contact_point = None
        self.tool_radius = 0.007
        self.tool_start_clearance = 0.028
        self.tool_depth = 0.008
        self.tool_pose_0 = None
        self.tool_pose_1 = None
        self.use_saved_tool_pose = False
        self.tissue_top_z = 0.0
        self.frame_count = 0
        self.first_step: int | None = None
        self.last_step: int | None = None

    def setup(self, reader: ReplayReader) -> None:
        self.reader = reader
        self.output_dir = reader.sample_dir / "replay_isaacsim"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.output_dir / self.output_name
        if self.output_path.exists():
            self.output_path.unlink()

        Usd, UsdGeom, UsdLux, UsdShade, Sdf, Gf = self._pxr()
        self.stage = Usd.Stage.CreateNew(str(self.output_path))
        UsdGeom.SetStageUpAxis(self.stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(self.stage, 1.0)

        timeline = list(reader.iter_timeline())
        if timeline:
            self.stage.SetStartTimeCode(float(timeline[0]["step_index"]))
            self.stage.SetEndTimeCode(float(timeline[-1]["step_index"]))
        self.stage.SetFramesPerSecond(60)
        self.stage.SetTimeCodesPerSecond(60)

        world = UsdGeom.Xform.Define(self.stage, "/World")
        self.stage.SetDefaultPrim(world.GetPrim())

        vertices_0 = np.load(reader.sample_dir / "vertices_0.npy").astype(np.float32)
        faces = np.load(reader.sample_dir / "faces.npy").astype(np.int32)
        self.tissue_top_z = float(vertices_0[:, 2].max())
        self.contact_point = self._load_contact_point(reader)
        self.tool_depth = self._load_action_depth(reader)
        self._load_tool_motion(reader)
        self.mesh = UsdGeom.Mesh.Define(self.stage, "/World/TissuePatch")
        self.mesh.CreateFaceVertexCountsAttr(self._face_counts(faces))
        self.mesh.CreateFaceVertexIndicesAttr(self._face_indices(faces))
        self.mesh.CreateSubdivisionSchemeAttr("none")
        self.mesh.CreateDisplayColorAttr([Gf.Vec3f(0.82, 0.35, 0.32)])
        self.points_attr = self.mesh.GetPointsAttr()
        self.points_attr.Set(self._vec3f_list(vertices_0), Usd.TimeCode(0))

        tissue_mat = self._define_material(
            "/World/Materials/Tissue",
            color=(0.82, 0.35, 0.32),
            roughness=0.82,
        )
        UsdShade.MaterialBindingAPI(self.mesh.GetPrim()).Bind(tissue_mat)

        self._add_reference_geometry(vertices_0)
        self._add_contact_marker(reader)
        self._add_tool()
        self._add_lighting_and_camera()
        print(f"Isaac Sim replay export started: {self.output_path}")

    def show_frame(self, frame: ReplayFrame) -> None:
        if self.stage is None or self.points_attr is None:
            raise RuntimeError("viewer setup() must be called before show_frame()")
        vertices = frame.arrays.get("vertices")
        if vertices is None:
            return
        if self.frame_count == 0:
            self.first_step = frame.step_index
        self.last_step = frame.step_index
        self.frame_count += 1
        Usd, _, _, _, _, Gf = self._pxr()
        self.points_attr.Set(self._vec3f_list(vertices), Usd.TimeCode(frame.step_index))
        if self.tool_translate_op is not None and self.contact_point is not None:
            progress = float(frame.scalars.get("progress", 0.0))
            if self.use_saved_tool_pose and self.tool_pose_0 is not None and self.tool_pose_1 is not None:
                position = self._interpolate_tool_position(progress)
                self.tool_translate_op.Set(
                    Gf.Vec3d(float(position[0]), float(position[1]), float(position[2])),
                    Usd.TimeCode(frame.step_index),
                )
            else:
                z = self.tissue_top_z + self.tool_radius + self.tool_start_clearance - self.tool_depth * progress
                self.tool_translate_op.Set(
                    Gf.Vec3d(float(self.contact_point[0]), float(self.contact_point[1]), float(z)),
                    Usd.TimeCode(frame.step_index),
                )

    def finish(self) -> None:
        if self.stage is None or self.output_path is None:
            return
        self.stage.GetRootLayer().Export(str(self.output_path))
        self._try_open_in_isaac()
        print(
            "Isaac Sim replay exported: "
            f"{self.output_path} frames={self.frame_count} "
            f"first_step={self.first_step} last_step={self.last_step}"
        )

    def _pxr(self):
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

        return Usd, UsdGeom, UsdLux, UsdShade, Sdf, Gf


    def _load_contact_point(self, reader: ReplayReader) -> np.ndarray:
        contact_path = reader.sample_dir / "contact_point.npy"
        if contact_path.exists():
            return np.load(contact_path).astype(np.float32)
        return np.asarray((0.0, 0.0, 0.0), dtype=np.float32)

    def _load_action_depth(self, reader: ReplayReader) -> float:
        action_path = reader.sample_dir / "action.npy"
        if not action_path.exists():
            return 0.008
        action = np.load(action_path).astype(np.float32)
        if action.shape[0] < 6:
            return 0.008
        return max(float(action[5]), 0.001)

    def _load_tool_motion(self, reader: ReplayReader) -> None:
        pose_0_path = reader.sample_dir / "tool_pose_0.npy"
        pose_1_path = reader.sample_dir / "tool_pose_1.npy"
        geometry_path = reader.sample_dir / "tool_geometry.json"
        if pose_0_path.exists() and pose_1_path.exists():
            pose_0 = np.load(pose_0_path).astype(np.float32)
            pose_1 = np.load(pose_1_path).astype(np.float32)
            if pose_0.shape == (4, 4) and pose_1.shape == (4, 4):
                self.tool_pose_0 = pose_0
                self.tool_pose_1 = pose_1
                self.use_saved_tool_pose = True
        if geometry_path.exists():
            try:
                with geometry_path.open("r", encoding="utf-8") as f:
                    geometry = json.load(f)
                if isinstance(geometry, dict) and geometry.get("type") == "sphere":
                    self.tool_radius = float(geometry.get("radius", self.tool_radius))
            except Exception:
                return

    def _interpolate_tool_position(self, progress: float) -> np.ndarray:
        progress = float(np.clip(progress, 0.0, 1.0))
        p0 = np.asarray(self.tool_pose_0[:3, 3], dtype=np.float64)
        p1 = np.asarray(self.tool_pose_1[:3, 3], dtype=np.float64)
        return p0 + (p1 - p0) * progress

    def _face_counts(self, faces: np.ndarray) -> list[int]:
        if faces.ndim == 1:
            raise ValueError("faces must be a 2D array for USD replay")
        return [int(faces.shape[1])] * int(faces.shape[0])

    def _face_indices(self, faces: np.ndarray) -> list[int]:
        return [int(v) for v in faces.reshape(-1)]

    def _vec3f_list(self, vertices: np.ndarray):
        _, _, _, _, _, Gf = self._pxr()
        vertices = np.asarray(vertices, dtype=np.float32)
        return [Gf.Vec3f(float(x), float(y), float(z)) for x, y, z in vertices]

    def _define_material(self, path: str, color: tuple[float, float, float], roughness: float):
        _, _, _, UsdShade, Sdf, Gf = self._pxr()
        material = UsdShade.Material.Define(self.stage, path)
        shader = UsdShade.Shader.Define(self.stage, path + "/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        return material

    def _add_reference_geometry(self, vertices_0: np.ndarray) -> None:
        _, UsdGeom, _, UsdShade, _, Gf = self._pxr()
        min_xyz = vertices_0.min(axis=0)
        max_xyz = vertices_0.max(axis=0)
        center = (min_xyz + max_xyz) * 0.5
        size = max_xyz - min_xyz
        table = UsdGeom.Cube.Define(self.stage, "/World/Table")
        UsdGeom.Xformable(table).AddTranslateOp().Set(
            Gf.Vec3d(float(center[0]), float(center[1]), float(min_xyz[2] - 0.008))
        )
        UsdGeom.Xformable(table).AddScaleOp().Set(
            Gf.Vec3f(float(size[0] * 0.65), float(size[1] * 0.65), 0.003)
        )
        table_mat = self._define_material("/World/Materials/Table", (0.14, 0.16, 0.17), 0.72)
        UsdShade.MaterialBindingAPI(table.GetPrim()).Bind(table_mat)

    def _add_contact_marker(self, reader: ReplayReader) -> None:
        if self.contact_point is None:
            return
        _, UsdGeom, _, UsdShade, _, Gf = self._pxr()
        marker = UsdGeom.Sphere.Define(self.stage, "/World/ContactPoint")
        marker.CreateRadiusAttr(0.0025)
        UsdGeom.Xformable(marker).AddTranslateOp().Set(
            Gf.Vec3d(
                float(self.contact_point[0]),
                float(self.contact_point[1]),
                float(self.tissue_top_z + 0.002),
            )
        )
        mat = self._define_material("/World/Materials/ContactMarker", (0.95, 0.08, 0.04), 0.4)
        UsdShade.MaterialBindingAPI(marker.GetPrim()).Bind(mat)

    def _add_tool(self) -> None:
        if self.contact_point is None:
            return
        _, UsdGeom, _, UsdShade, _, Gf = self._pxr()
        tool = UsdGeom.Sphere.Define(self.stage, "/World/ToolSphere")
        tool.CreateRadiusAttr(self.tool_radius)
        self.tool_translate_op = UsdGeom.Xformable(tool).AddTranslateOp()
        if self.use_saved_tool_pose and self.tool_pose_0 is not None:
            start = np.asarray(self.tool_pose_0[:3, 3], dtype=np.float64)
            self.tool_translate_op.Set(Gf.Vec3d(float(start[0]), float(start[1]), float(start[2])))
        else:
            start_z = self.tissue_top_z + self.tool_radius + self.tool_start_clearance
            self.tool_translate_op.Set(
                Gf.Vec3d(float(self.contact_point[0]), float(self.contact_point[1]), float(start_z))
            )
        mat = self._define_material("/World/Materials/Tool", (0.55, 0.62, 0.7), 0.25)
        UsdShade.MaterialBindingAPI(tool.GetPrim()).Bind(mat)

    def _add_lighting_and_camera(self) -> None:
        _, UsdGeom, UsdLux, _, _, Gf = self._pxr()
        key = UsdLux.SphereLight.Define(self.stage, "/World/KeyLight")
        key.CreateIntensityAttr(1800)
        key.CreateRadiusAttr(0.6)
        UsdGeom.Xformable(key).AddTranslateOp().Set(Gf.Vec3d(0.18, -0.16, 0.22))

        dome = UsdLux.DomeLight.Define(self.stage, "/World/DomeLight")
        dome.CreateIntensityAttr(180)

        camera = UsdGeom.Camera.Define(self.stage, "/World/Camera")
        xform = UsdGeom.Xformable(camera)
        xform.AddTranslateOp().Set(Gf.Vec3d(0.13, -0.16, 0.09))
        xform.AddRotateXYZOp().Set(Gf.Vec3f(62, 0, 40))
        camera.CreateFocalLengthAttr(45)

    def _try_open_in_isaac(self) -> None:
        if self.output_path is None:
            return
        try:
            import omni.usd
        except Exception:
            return
        try:
            omni.usd.get_context().open_stage(str(self.output_path))
        except Exception as exc:
            print(f"Could not open replay stage in active Isaac Sim context: {exc}")
