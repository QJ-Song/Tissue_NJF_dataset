from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..backends import SofaFemBackend, ToyPressBackend
from ..layout import default_layout
from ..sampling import FixedGeometrySampler, SceneSampler, UniformGeometrySampler, UniformMaterialSampler, UniformPressActionSampler
from ..schema import GeometryConfig, LoggingConfig
from ..writer import FileSystemSampleWriter


@dataclass(frozen=True)
class GenerationConfig:
    output_dir: Path
    num_samples: int = 1
    seed: int = 0
    sample_id_start: int = 1
    backend_type: str = "toy_press"
    backend_extra: Mapping[str, Any] | None = None
    enabled_artifacts: tuple[str, ...] | None = None
    disabled_artifacts: tuple[str, ...] = ()
    logging: LoggingConfig = LoggingConfig()


def load_yaml(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def build_generation_config(data: dict[str, Any], base_dir: Path | None = None) -> GenerationConfig:
    dataset = data.get("dataset", {})
    backend = data.get("backend", {})
    logging = data.get("logging", {})
    artifacts = data.get("artifacts", {})

    output_dir = Path(dataset.get("output_dir", "outputs/dataset_yaml"))
    if base_dir is not None and not output_dir.is_absolute():
        output_dir = base_dir / output_dir

    enabled = artifacts.get("include")
    disabled = artifacts.get("exclude", ())

    return GenerationConfig(
        output_dir=output_dir,
        num_samples=int(dataset.get("num_samples", 1)),
        seed=int(dataset.get("seed", 0)),
        sample_id_start=int(dataset.get("sample_id_start", 1)),
        backend_type=str(backend.get("type", "toy_press")),
        backend_extra=dict(backend.get("extra", {}) or {}),
        enabled_artifacts=tuple(enabled) if enabled is not None else None,
        disabled_artifacts=tuple(disabled or ()),
        logging=LoggingConfig(
            enabled=bool(logging.get("enabled", True)),
            log_dir_name=str(logging.get("log_dir_name", "logs")),
            log_every_n=int(logging.get("log_every_n", 1)),
            save_vertices=bool(logging.get("save_vertices", True)),
            save_tool_pose=bool(logging.get("save_tool_pose", True)),
            save_events=bool(logging.get("save_events", True)),
            save_request=bool(logging.get("save_request", True)),
        ),
    )


def build_geometry(data: dict[str, Any]) -> GeometryConfig:
    geometry = data.get("geometry", {})
    return GeometryConfig(
        size_x=float(_range_midpoint(geometry.get("size_x", 0.10))),
        size_y=float(_range_midpoint(geometry.get("size_y", 0.10))),
        thickness=float(_range_midpoint(geometry.get("thickness", 0.01))),
        nx=int(geometry.get("nx", 24)),
        ny=int(geometry.get("ny", 24)),
        layers=int(geometry.get("layers", 2)),
        fixed_border_ratio=float(geometry.get("fixed_border_ratio", 0.12)),
    )


def build_geometry_sampler(data: dict[str, Any]):
    geometry = data.get("geometry", {})
    size_x = geometry.get("size_x", 0.10)
    size_y = geometry.get("size_y", 0.10)
    thickness = geometry.get("thickness", 0.01)
    if any(_is_range(value) for value in (size_x, size_y, thickness)):
        return UniformGeometrySampler(
            size_x_range=_float_pair_or_fixed(size_x),
            size_y_range=_float_pair_or_fixed(size_y),
            thickness_range=_float_pair_or_fixed(thickness),
            nx=int(geometry.get("nx", 24)),
            ny=int(geometry.get("ny", 24)),
            layers=int(geometry.get("layers", 2)),
            fixed_border_ratio=float(geometry.get("fixed_border_ratio", 0.12)),
        )
    return FixedGeometrySampler(build_geometry(data))


def build_material_sampler(data: dict[str, Any]) -> UniformMaterialSampler:
    cfg = data.get("material_sampler", {})
    if str(cfg.get("type", "uniform")) != "uniform":
        raise ValueError(f"Unsupported material_sampler.type: {cfg.get('type')}")
    return UniformMaterialSampler(
        youngs_modulus_range=_float_pair(cfg.get("youngs_modulus", (5_000.0, 50_000.0))),
        poisson_ratio_range=_float_pair(cfg.get("poisson_ratio", (0.40, 0.49))),
        damping_range=_float_pair(cfg.get("damping", (0.1, 2.0))),
        density=float(cfg.get("density", 1000.0)),
        boundary_condition=str(cfg.get("boundary_condition", "bottom_fixed")),
    )


def build_action_sampler(data: dict[str, Any]) -> UniformPressActionSampler:
    cfg = data.get("action_sampler", {})
    if str(cfg.get("type", "uniform_press")) != "uniform_press":
        raise ValueError(f"Unsupported action_sampler.type: {cfg.get('type')}")
    return UniformPressActionSampler(
        contact_margin=float(cfg.get("contact_margin", 0.03)),
        min_depth=float(cfg.get("depth", (0.002, 0.010))[0]),
        max_depth=float(cfg.get("depth", (0.002, 0.010))[1]),
        direction_mode=str(cfg.get("direction_mode", "vertical_down")),
        max_tilt_deg=float(cfg.get("max_tilt_deg", 45.0)),
    )


def build_scene_sampler(data: dict[str, Any]) -> SceneSampler:
    return SceneSampler(
        action_sampler=build_action_sampler(data),
        material_sampler=build_material_sampler(data),
        geometry_sampler=build_geometry_sampler(data),
    )


def build_backend(config: GenerationConfig):
    if config.backend_type == "toy_press":
        return ToyPressBackend()
    if config.backend_type == "sofa_fem":
        return SofaFemBackend()
    raise ValueError(f"Unsupported backend.type: {config.backend_type}")


def build_writer() -> FileSystemSampleWriter:
    return FileSystemSampleWriter(default_layout())


def load_generation_from_yaml(path: Path):
    path = Path(path)
    data = load_yaml(path)
    generation = build_generation_config(data, base_dir=path.parent)
    return data, generation, build_scene_sampler(data), build_backend(generation), build_writer()


def _float_pair(value) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Expected [min, max] pair, got: {value}")
    return (float(value[0]), float(value[1]))


def _float_pair_or_fixed(value) -> tuple[float, float]:
    if _is_range(value):
        return _float_pair(value)
    fixed = float(value)
    return (fixed, fixed)


def _is_range(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2


def _range_midpoint(value) -> float:
    if _is_range(value):
        low, high = _float_pair(value)
        return (low + high) * 0.5
    return float(value)
