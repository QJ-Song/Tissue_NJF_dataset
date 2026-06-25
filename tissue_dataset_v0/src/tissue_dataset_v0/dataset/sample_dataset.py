from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class SampleRecord:
    """One manifest-driven dataset sample.

    Arrays and JSON payloads are stored by artifact name so future fields can
    be added without changing the record shape.
    """

    sample_dir: Path
    manifest: Mapping[str, Any]
    artifacts: Mapping[str, Any]

    def get(self, name: str, default: Any = None) -> Any:
        return self.artifacts.get(name, default)

    @property
    def sample_id(self) -> str:
        return self.sample_dir.name

    @property
    def arrays(self) -> dict[str, np.ndarray]:
        return {key: value for key, value in self.artifacts.items() if isinstance(value, np.ndarray)}

    @property
    def metadata(self) -> dict[str, Any]:
        meta = self.artifacts.get("meta", {})
        return dict(meta) if isinstance(meta, dict) else {}


class TissueSampleDataset:
    """Manifest-driven reader for generated `sample_*` directories.

    The loader intentionally does not assume a fixed model input. It reads all
    present artifacts declared in `sample_manifest.json` by default and exposes
    them as a dictionary, which keeps it compatible with future field additions
    or optional removals.
    """

    def __init__(
        self,
        root_dirs: str | Path | Iterable[str | Path],
        *,
        artifact_names: Iterable[str] | None = None,
        require_artifacts: Iterable[str] = (),
        load_all_present: bool = True,
    ):
        if isinstance(root_dirs, (str, Path)):
            root_list = [Path(root_dirs)]
        else:
            root_list = [Path(path) for path in root_dirs]
        self.sample_dirs = discover_sample_dirs(root_list)
        self.artifact_names = set(artifact_names) if artifact_names is not None else None
        self.require_artifacts = set(require_artifacts)
        self.load_all_present = load_all_present

    def __len__(self) -> int:
        return len(self.sample_dirs)

    def __getitem__(self, index: int) -> SampleRecord:
        sample_dir = self.sample_dirs[index]
        manifest = load_json(sample_dir / "sample_manifest.json")
        specs = manifest.get("artifacts", [])
        if not isinstance(specs, list):
            raise ValueError(f"Manifest artifacts must be a list: {sample_dir}")
        artifacts: dict[str, Any] = {}
        present_names = {spec.get("name") for spec in specs if isinstance(spec, dict) and spec.get("present")}
        missing_required = sorted(self.require_artifacts - present_names)
        if missing_required:
            raise KeyError(f"Missing required artifacts in {sample_dir}: {missing_required}")
        for spec in specs:
            if not isinstance(spec, dict) or not spec.get("present"):
                continue
            name = str(spec.get("name"))
            if not self.load_all_present and (self.artifact_names is None or name not in self.artifact_names):
                continue
            if self.artifact_names is not None and name not in self.artifact_names:
                continue
            artifacts[name] = load_artifact(sample_dir, name=name, kind=str(spec.get("kind", "")))
        return SampleRecord(sample_dir=sample_dir, manifest=manifest, artifacts=artifacts)

    def iter_records(self):
        for index in range(len(self)):
            yield self[index]

    def summary(self) -> dict[str, Any]:
        artifact_shapes: dict[str, set[tuple[int, ...]]] = {}
        artifact_dtypes: dict[str, set[str]] = {}
        material_keys: set[str] = set()
        loaded_names: set[str] = set()
        for record in self.iter_records():
            loaded_names.update(record.artifacts.keys())
            for name, value in record.arrays.items():
                artifact_shapes.setdefault(name, set()).add(tuple(int(dim) for dim in value.shape))
                artifact_dtypes.setdefault(name, set()).add(str(value.dtype))
            material = record.get("material")
            if isinstance(material, dict):
                material_keys.update(str(key) for key in material.keys())
        return {
            "sample_count": len(self),
            "sample_dirs": [str(path) for path in self.sample_dirs],
            "loaded_artifacts": sorted(loaded_names),
            "array_shapes": {key: sorted([list(shape) for shape in shapes]) for key, shapes in artifact_shapes.items()},
            "array_dtypes": {key: sorted(values) for key, values in artifact_dtypes.items()},
            "fixed_array_shapes": {key: len(shapes) == 1 for key, shapes in artifact_shapes.items()},
            "material_keys": sorted(material_keys),
        }


def discover_sample_dirs(paths: Iterable[Path]) -> list[Path]:
    sample_dirs: list[Path] = []
    for path in paths:
        if path.name.startswith("sample_") and path.is_dir():
            sample_dirs.append(path)
            continue
        if path.is_dir():
            sample_dirs.extend(child for child in path.iterdir() if child.is_dir() and child.name.startswith("sample_"))
    return sorted(set(sample_dirs))


def load_artifact(sample_dir: Path, *, name: str, kind: str) -> Any:
    path = sample_dir / artifact_filename(name, kind)
    if kind == "npy":
        return np.load(path)
    if kind == "json":
        return load_json(path)
    if kind == "txt":
        return path.read_text(encoding="utf-8")
    if kind == "png":
        return np.asarray(load_image(path))
    raise ValueError(f"Unsupported artifact kind for {sample_dir}: {name} ({kind})")


def artifact_filename(name: str, kind: str) -> str:
    suffix = {
        "npy": ".npy",
        "json": ".json",
        "txt": ".txt",
        "png": ".png",
    }.get(kind, "")
    return f"{name}{suffix}"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def load_image(path: Path):
    from PIL import Image

    return Image.open(path)
