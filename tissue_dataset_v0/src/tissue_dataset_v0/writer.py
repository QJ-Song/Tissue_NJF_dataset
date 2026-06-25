from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .layout import DatasetLayout
from .schema import SampleResult


class FileSystemSampleWriter:
    """Write sample artifacts using a declarative artifact layout."""

    def __init__(self, layout: DatasetLayout):
        self.layout = layout

    def write_sample(
        self,
        sample_dir: Path,
        result: SampleResult,
        include_artifacts: Iterable[str] | None = None,
        exclude_artifacts: Iterable[str] | None = None,
    ) -> Path:
        sample_dir.mkdir(parents=True, exist_ok=True)
        include_set = set(include_artifacts) if include_artifacts is not None else None
        exclude_set = set(exclude_artifacts or ())
        manifest = self._build_manifest(result, include_set=include_set, exclude_set=exclude_set)

        for spec in self.layout.enabled_specs():
            if include_set is not None and spec.name not in include_set:
                continue
            if spec.name in exclude_set:
                continue
            if spec.name not in result.artifacts:
                if spec.required:
                    raise KeyError(f"Missing required artifact: {spec.name}")
                continue
            self._write_one(sample_dir / self._filename(spec), result.artifacts[spec.name], spec.kind)

        self._write_json(sample_dir / "sample_manifest.json", manifest)
        return sample_dir

    def _build_manifest(
        self,
        result: SampleResult,
        include_set: set[str] | None = None,
        exclude_set: set[str] | None = None,
    ) -> dict:
        specs = []
        for spec in self.layout.artifacts:
            if include_set is not None and spec.name not in include_set:
                continue
            if spec.name in exclude_set:
                continue
            item = {
                "name": spec.name,
                "kind": spec.kind,
                "required": spec.required,
                "enabled": spec.enabled,
                "present": spec.name in result.artifacts,
                "description": spec.description,
            }
            value = result.artifacts.get(spec.name)
            if isinstance(value, np.ndarray):
                item["shape"] = list(value.shape)
                item["dtype"] = str(value.dtype)
            specs.append(item)
        return {
            "artifacts": specs,
            "summary": result.summary,
        }

    def _filename(self, spec) -> str:
        suffix = {
            "npy": ".npy",
            "json": ".json",
            "txt": ".txt",
            "png": ".png",
        }.get(spec.kind, "")
        return f"{spec.name}{suffix}"

    def _write_one(self, path: Path, value: Any, kind: str) -> None:
        if kind == "npy":
            np.save(path, value)
            return
        if kind == "json":
            self._write_json(path, value)
            return
        if kind == "txt":
            path.write_text(str(value), encoding="utf-8")
            return
        if kind == "png":
            self._write_png(path, value)
            return
        raise ValueError(f"Unsupported artifact kind: {kind}")

    def _write_json(self, path: Path, value: Any) -> None:
        if hasattr(value, "tolist"):
            value = value.tolist()
        elif hasattr(value, "__dict__") and not isinstance(value, dict):
            value = asdict(value)
        with path.open("w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True)
            f.write("\n")

    def _write_png(self, path: Path, value: Any) -> None:
        from PIL import Image

        array = np.asarray(value)
        if array.ndim == 2:
            mode = "L"
        elif array.ndim == 3 and array.shape[2] == 3:
            mode = "RGB"
        else:
            raise ValueError(f"Unsupported png array shape: {array.shape}")
        image = Image.fromarray(array.astype(np.uint8), mode=mode)
        image.save(path)
