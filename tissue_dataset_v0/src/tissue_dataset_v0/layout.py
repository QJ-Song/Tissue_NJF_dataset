from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    kind: str
    required: bool = False
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class DatasetLayout:
    artifacts: Sequence[ArtifactSpec] = field(default_factory=tuple)

    def enabled_specs(self) -> List[ArtifactSpec]:
        return [spec for spec in self.artifacts if spec.enabled]

    def enabled_names(self) -> List[str]:
        return [spec.name for spec in self.enabled_specs()]

    def spec_map(self) -> dict[str, ArtifactSpec]:
        return {spec.name: spec for spec in self.artifacts}


def default_layout() -> DatasetLayout:
    return DatasetLayout(
        artifacts=(
            ArtifactSpec(
                name="vertices_0",
                kind="npy",
                required=True,
                description="Initial tissue vertex positions",
            ),
            ArtifactSpec(
                name="vertices_1",
                kind="npy",
                required=True,
                description="Deformed tissue vertex positions",
            ),
            ArtifactSpec(
                name="displacement",
                kind="npy",
                required=True,
                description="Vertex-wise displacement",
            ),
            ArtifactSpec(
                name="faces",
                kind="npy",
                required=True,
                description="Surface mesh faces or connectivity",
            ),
            ArtifactSpec(
                name="action",
                kind="npy",
                required=True,
                description="Action vector used for the sample",
            ),
            ArtifactSpec(
                name="contact_point",
                kind="npy",
                required=True,
                description="Tool/tissue contact point",
            ),
            ArtifactSpec(
                name="material",
                kind="json",
                required=True,
                description="Material parameters and boundary conditions",
            ),
            ArtifactSpec(
                name="meta",
                kind="json",
                required=True,
                description="Sample metadata",
            ),
            ArtifactSpec(
                name="tool_pose_0",
                kind="npy",
                required=False,
                enabled=True,
                description="Optional tool pose before interaction",
            ),
            ArtifactSpec(
                name="tool_pose_1",
                kind="npy",
                required=False,
                enabled=True,
                description="Optional tool pose after interaction",
            ),
            ArtifactSpec(
                name="tool_geometry",
                kind="json",
                required=False,
                enabled=True,
                description="Optional tool geometry metadata",
            ),
            ArtifactSpec(
                name="contact_summary",
                kind="json",
                required=False,
                enabled=True,
                description="Optional contact/proximity summary metadata",
            ),
            ArtifactSpec(
                name="fixed_node_indices",
                kind="npy",
                required=False,
                enabled=True,
                description="Optional indices of fixed tissue nodes",
            ),
            ArtifactSpec(
                name="free_node_indices",
                kind="npy",
                required=False,
                enabled=True,
                description="Optional indices of free tissue nodes",
            ),
            ArtifactSpec(
                name="boundary_mask",
                kind="npy",
                required=False,
                enabled=True,
                description="Optional boolean mask for fixed tissue nodes",
            ),
            ArtifactSpec(
                name="boundary",
                kind="json",
                required=False,
                enabled=True,
                description="Optional boundary condition metadata",
            ),
            ArtifactSpec(
                name="solver_summary",
                kind="json",
                required=False,
                enabled=True,
                description="Optional SOFA solver and run metadata",
            ),
            ArtifactSpec(
                name="rgb_0",
                kind="png",
                required=False,
                enabled=False,
                description="Optional render at t0",
            ),
            ArtifactSpec(
                name="depth_0",
                kind="npy",
                required=False,
                enabled=False,
                description="Optional depth map at t0",
            ),
        )
    )
