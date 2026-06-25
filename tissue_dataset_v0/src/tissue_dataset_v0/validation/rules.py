from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..trajectory import EpisodeTrajectoryReader
from .core import ValidationContext, ValidationReport, artifact_suffix


@dataclass(frozen=True)
class SampleStructureRule:
    name: str = "sample_structure"

    def validate(self, context: ValidationContext, report: ValidationReport) -> None:
        if not context.sample_dir.exists():
            report.error("sample_dir_missing", "Sample directory does not exist", context.sample_dir)
            return
        if not context.sample_dir.is_dir():
            report.error("sample_dir_not_directory", "Sample path is not a directory", context.sample_dir)
            return
        if not context.manifest_path.is_file():
            report.error("manifest_missing", "sample_manifest.json is required for current sample validation", context.manifest_path)


@dataclass(frozen=True)
class ManifestArtifactRule:
    name: str = "manifest_artifacts"

    def validate(self, context: ValidationContext, report: ValidationReport) -> None:
        manifest = _read_json_or_error(context.manifest_path, report)
        if manifest is None:
            return
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            report.error("manifest_artifacts_invalid", "Manifest must contain an artifacts list", context.manifest_path)
            return

        seen: set[str] = set()
        present_count = 0
        for index, item in enumerate(artifacts):
            if not isinstance(item, dict):
                report.error("manifest_artifact_invalid", "Manifest artifact entry must be an object", context.manifest_path, index=index)
                continue
            name = item.get("name")
            kind = item.get("kind")
            if not isinstance(name, str) or not name:
                report.error("artifact_name_invalid", "Artifact entry has invalid name", context.manifest_path, index=index)
                continue
            if name in seen:
                report.error("artifact_duplicate", "Duplicate artifact name in manifest", context.manifest_path, artifact=name)
            seen.add(name)
            if not isinstance(kind, str) or not kind:
                report.error("artifact_kind_invalid", "Artifact entry has invalid kind", context.manifest_path, artifact=name)
                continue

            suffix = artifact_suffix(kind)
            if not suffix:
                if item.get("present"):
                    report.warning("artifact_kind_unknown", "Cannot infer filename for unknown artifact kind", context.manifest_path, artifact=name, kind=kind)
                continue

            path = context.artifact_path(name, kind)
            exists = path.is_file()
            required = bool(item.get("required", False))
            present = bool(item.get("present", False))
            if present:
                present_count += 1
            if required and not present:
                report.error("required_artifact_not_present", "Required artifact is marked not present", context.manifest_path, artifact=name)
            if present and not exists:
                report.error("artifact_file_missing", "Manifest marks artifact present but file is missing", path, artifact=name, kind=kind)
                continue
            if required and not exists:
                report.error("required_artifact_file_missing", "Required artifact file is missing", path, artifact=name, kind=kind)
                continue
            if exists and not present:
                report.warning("artifact_file_unlisted", "Artifact file exists but manifest marks it not present", path, artifact=name, kind=kind)
            if exists:
                _validate_artifact_file(path, item, report)

        report.properties["manifest_artifact_count"] = len(artifacts)
        report.properties["manifest_present_artifact_count"] = present_count


@dataclass(frozen=True)
class CoreArrayConsistencyRule:
    name: str = "core_array_consistency"
    displacement_atol: float = 1e-5
    displacement_rtol: float = 1e-4

    def validate(self, context: ValidationContext, report: ValidationReport) -> None:
        arrays = {
            "vertices_0": _load_optional_npy(context.sample_dir / "vertices_0.npy", report),
            "vertices_1": _load_optional_npy(context.sample_dir / "vertices_1.npy", report),
            "displacement": _load_optional_npy(context.sample_dir / "displacement.npy", report),
            "faces": _load_optional_npy(context.sample_dir / "faces.npy", report),
            "action": _load_optional_npy(context.sample_dir / "action.npy", report),
            "contact_point": _load_optional_npy(context.sample_dir / "contact_point.npy", report),
        }
        v0 = arrays["vertices_0"]
        v1 = arrays["vertices_1"]
        displacement = arrays["displacement"]
        faces = arrays["faces"]
        action = arrays["action"]
        contact_point = arrays["contact_point"]

        for key in ("vertices_0", "vertices_1", "displacement"):
            value = arrays[key]
            if value is None:
                continue
            if value.ndim != 2 or value.shape[1] != 3:
                report.error("vertex_array_shape_invalid", f"{key} must have shape [N, 3]", context.sample_dir / f"{key}.npy", shape=list(value.shape))
            _check_finite(key, value, context.sample_dir / f"{key}.npy", report)

        if v0 is not None and v1 is not None and v0.shape != v1.shape:
            report.error("vertex_shape_mismatch", "vertices_0 and vertices_1 must have the same shape", context.sample_dir, vertices_0=list(v0.shape), vertices_1=list(v1.shape))
        if v0 is not None and displacement is not None and v0.shape != displacement.shape:
            report.error("displacement_shape_mismatch", "displacement must match vertices_0 shape", context.sample_dir, vertices_0=list(v0.shape), displacement=list(displacement.shape))
        if v0 is not None and v1 is not None and displacement is not None and v0.shape == v1.shape == displacement.shape:
            expected = v1 - v0
            if not np.allclose(expected, displacement, atol=self.displacement_atol, rtol=self.displacement_rtol):
                max_abs = float(np.max(np.abs(expected - displacement)))
                report.error("displacement_value_mismatch", "displacement does not match vertices_1 - vertices_0", context.sample_dir / "displacement.npy", max_abs_error=max_abs)

        if faces is not None:
            if faces.ndim != 2 or faces.shape[1] < 3:
                report.error("faces_shape_invalid", "faces must have shape [F, K] with K >= 3", context.sample_dir / "faces.npy", shape=list(faces.shape))
            if not np.issubdtype(faces.dtype, np.integer):
                report.error("faces_dtype_invalid", "faces must use an integer dtype", context.sample_dir / "faces.npy", dtype=str(faces.dtype))
            if v0 is not None and faces.size:
                min_index = int(np.min(faces))
                max_index = int(np.max(faces))
                if min_index < 0 or max_index >= len(v0):
                    report.error("faces_index_out_of_range", "faces reference vertices outside vertices_0", context.sample_dir / "faces.npy", min_index=min_index, max_index=max_index, vertex_count=len(v0))

        if action is not None:
            if action.ndim != 1 or action.shape[0] == 0:
                report.error("action_shape_invalid", "action must be a non-empty 1D vector", context.sample_dir / "action.npy", shape=list(action.shape))
            _check_finite("action", action, context.sample_dir / "action.npy", report)
        if contact_point is not None:
            if contact_point.shape != (3,):
                report.error("contact_point_shape_invalid", "contact_point must have shape [3]", context.sample_dir / "contact_point.npy", shape=list(contact_point.shape))
            _check_finite("contact_point", contact_point, context.sample_dir / "contact_point.npy", report)


@dataclass(frozen=True)
class MetadataConsistencyRule:
    name: str = "metadata_consistency"
    required_meta_keys: Sequence[str] = ("sample_id", "scene_id", "simulator", "unit")

    def validate(self, context: ValidationContext, report: ValidationReport) -> None:
        meta_path = context.sample_dir / "meta.json"
        material_path = context.sample_dir / "material.json"
        request_path = context.log_dir / "request.json"
        manifest_path = context.manifest_path

        meta = _read_json_or_error(meta_path, report)
        material = _read_json_or_error(material_path, report)
        request = _read_json_or_none(request_path, report)
        manifest = _read_json_or_none(manifest_path, report)

        if isinstance(meta, dict):
            for key in self.required_meta_keys:
                if key not in meta:
                    report.warning("meta_key_missing", "Recommended metadata key is missing", meta_path, key=key)
            if "logging" in meta and not isinstance(meta["logging"], dict):
                report.error("meta_logging_invalid", "meta.logging must be an object when present", meta_path)
        if isinstance(material, dict) and not material:
            report.warning("material_empty", "material.json is empty", material_path)

        if isinstance(meta, dict) and isinstance(request, dict):
            config = request.get("config", {})
            if isinstance(config, dict):
                _compare_common_scalar("sample_id", meta, config, meta_path, report)
                _compare_common_scalar("scene_id", meta, config, meta_path, report)
                _compare_common_scalar("simulator", meta, config, meta_path, report)
            else:
                report.error("request_config_invalid", "request.config must be an object", request_path)

            request_material = request.get("material")
            if isinstance(material, dict) and isinstance(request_material, dict):
                for key in sorted(set(material).intersection(request_material)):
                    if _is_scalar(material[key]) and _is_scalar(request_material[key]) and material[key] != request_material[key]:
                        report.warning("material_request_mismatch", "material.json differs from logs/request.json for a shared key", material_path, key=key, material_value=material[key], request_value=request_material[key])

        if isinstance(meta, dict) and isinstance(manifest, dict):
            summary = manifest.get("summary", {})
            if isinstance(summary, dict):
                _compare_common_scalar("sample_id", meta, summary, manifest_path, report)


@dataclass(frozen=True)
class LogIntegrityRule:
    name: str = "log_integrity"
    required_array_coverage: bool = False

    def validate(self, context: ValidationContext, report: ValidationReport) -> None:
        require_logs = _logs_required(context)
        if not context.log_dir.exists():
            if require_logs:
                report.error("log_dir_missing", "Log directory is required but missing", context.log_dir)
            return
        if not context.frames_dir.exists():
            report.error("frames_dir_missing", "Log frames directory is missing", context.frames_dir)
            return

        timeline_path = context.log_dir / "timeline.jsonl"
        if not timeline_path.is_file():
            report.error("timeline_missing", "timeline.jsonl is missing", timeline_path)
            return
        try:
            rows = context.read_jsonl(timeline_path)
        except ValueError as exc:
            report.error("timeline_jsonl_invalid", str(exc), timeline_path)
            return
        if not rows:
            report.error("timeline_empty", "timeline.jsonl contains no frames", timeline_path)
            return

        seen_steps: set[int] = set()
        last_step: int | None = None
        last_time: float | None = None
        array_key_counts: dict[str, int] = {}
        for row_index, row in enumerate(rows):
            step = row.get("step_index")
            time_code = row.get("time_code")
            if not isinstance(step, int):
                report.error("timeline_step_invalid", "timeline row step_index must be an integer", timeline_path, row=row_index, value=step)
                continue
            if not isinstance(time_code, (int, float)):
                report.error("timeline_time_invalid", "timeline row time_code must be numeric", timeline_path, row=row_index, value=time_code)
                continue
            if step in seen_steps:
                report.error("timeline_step_duplicate", "timeline contains duplicate step_index", timeline_path, row=row_index, step_index=step)
            seen_steps.add(step)
            if last_step is not None and step <= last_step:
                report.error("timeline_step_not_increasing", "timeline step_index must be strictly increasing", timeline_path, row=row_index, previous_step=last_step, step_index=step)
            if last_time is not None and float(time_code) < last_time:
                report.error("timeline_time_decreased", "timeline time_code must not decrease", timeline_path, row=row_index, previous_time=last_time, time_code=float(time_code))
            last_step = step
            last_time = float(time_code)

            row_array_keys = _string_list(row.get("array_keys", []))
            row_scalar_keys = _string_list(row.get("scalar_keys", []))
            for key in row_array_keys:
                array_key_counts[key] = array_key_counts.get(key, 0) + 1
            _validate_frame_npz(context, row, row_index, row_array_keys, report)
            _validate_frame_json(context, row, row_index, row_scalar_keys, report)

        for key, count in sorted(array_key_counts.items()):
            if count != len(rows):
                severity = report.error if self.required_array_coverage else report.warning
                severity("frame_array_partial_coverage", "Frame array key is not present on every timeline row", timeline_path, key=key, count=count, frame_count=len(rows))

        events_path = context.log_dir / "events.jsonl"
        if events_path.exists():
            try:
                context.read_jsonl(events_path)
            except ValueError as exc:
                report.error("events_jsonl_invalid", str(exc), events_path)

        report.properties["timeline_frame_count"] = len(rows)
        report.properties["timeline_first_step"] = rows[0].get("step_index")
        report.properties["timeline_last_step"] = rows[-1].get("step_index")


@dataclass(frozen=True)
class TrajectorySummaryRule:
    name: str = "trajectory_summary"
    require_summary: bool = False

    def validate(self, context: ValidationContext, report: ValidationReport) -> None:
        summary_path = context.log_dir / "trajectory_summary.json"
        try:
            reader = EpisodeTrajectoryReader(context.sample_dir, log_dir_name=context.log_dir_name)
            expected = reader.build_summary()
        except Exception as exc:
            report.error("trajectory_reader_failed", f"Cannot build trajectory summary from logs: {exc}", context.log_dir, detail_type=type(exc).__name__)
            return

        if not summary_path.exists():
            if self.require_summary:
                report.error("trajectory_summary_missing", "trajectory_summary.json is required but missing", summary_path)
            else:
                report.warning("trajectory_summary_missing", "trajectory_summary.json is missing; run write_trajectory_summary.py or regenerate the sample", summary_path)
            report.properties["trajectory_frame_count"] = expected.get("frame_count")
            return

        actual = _read_json_or_error(summary_path, report)
        if not isinstance(actual, dict):
            return
        for key in ("schema_version", "sample_id", "scene_id", "simulator", "backend", "action_type", "frame_count", "first_step", "last_step", "first_time_code", "last_time_code"):
            if actual.get(key) != expected.get(key):
                report.error("trajectory_summary_mismatch", "trajectory summary differs from logs", summary_path, key=key, expected=expected.get(key), actual=actual.get(key))
        for key in ("array_keys", "scalar_keys", "artifact_names"):
            if sorted(actual.get(key, [])) != sorted(expected.get(key, [])):
                report.error("trajectory_summary_keys_mismatch", "trajectory summary key list differs from logs", summary_path, key=key, expected=expected.get(key, []), actual=actual.get(key, []))
        report.properties["trajectory_frame_count"] = expected.get("frame_count")
        report.properties["trajectory_summary_path"] = str(summary_path)


def _validate_artifact_file(path: Path, item: Mapping[str, Any], report: ValidationReport) -> None:
    kind = item.get("kind")
    if kind == "npy":
        array = _load_optional_npy(path, report)
        if array is None:
            return
        expected_shape = item.get("shape")
        if expected_shape is not None and list(array.shape) != list(expected_shape):
            report.error("artifact_shape_mismatch", "Artifact shape differs from manifest", path, artifact=item.get("name"), expected=expected_shape, actual=list(array.shape))
        expected_dtype = item.get("dtype")
        if expected_dtype is not None and str(array.dtype) != str(expected_dtype):
            report.error("artifact_dtype_mismatch", "Artifact dtype differs from manifest", path, artifact=item.get("name"), expected=expected_dtype, actual=str(array.dtype))
    elif kind == "json":
        _read_json_or_error(path, report)
    elif kind in {"txt", "png"}:
        if path.stat().st_size == 0:
            report.warning("artifact_file_empty", "Artifact file is empty", path, artifact=item.get("name"), kind=kind)


def _validate_frame_npz(context: ValidationContext, row: Mapping[str, Any], row_index: int, row_array_keys: list[str], report: ValidationReport) -> None:
    frame_npz = row.get("frame_npz")
    if not frame_npz:
        if row_array_keys:
            report.error("frame_npz_missing_ref", "timeline row has array_keys but no frame_npz", context.log_dir / "timeline.jsonl", row=row_index)
        return
    path = context.frames_dir / str(frame_npz)
    if not path.is_file():
        report.error("frame_npz_missing", "Referenced frame npz is missing", path, row=row_index)
        return
    try:
        with np.load(path) as data:
            actual_keys = sorted(data.files)
            for key in actual_keys:
                value = data[key]
                if not np.all(np.isfinite(value)):
                    report.error("frame_array_non_finite", "Frame array contains NaN or Inf", path, row=row_index, key=key)
    except Exception as exc:
        report.error("frame_npz_invalid", f"Cannot read frame npz: {exc}", path, row=row_index)
        return
    if sorted(row_array_keys) != actual_keys:
        report.error("frame_npz_keys_mismatch", "timeline array_keys differ from npz contents", path, row=row_index, expected=row_array_keys, actual=actual_keys)


def _validate_frame_json(context: ValidationContext, row: Mapping[str, Any], row_index: int, row_scalar_keys: list[str], report: ValidationReport) -> None:
    frame_json = row.get("frame_json")
    if not frame_json:
        if row_scalar_keys:
            report.error("frame_json_missing_ref", "timeline row has scalar_keys but no frame_json", context.log_dir / "timeline.jsonl", row=row_index)
        return
    path = context.frames_dir / str(frame_json)
    data = _read_json_or_error(path, report)
    if not isinstance(data, dict):
        return
    if data.get("step_index") != row.get("step_index"):
        report.error("frame_json_step_mismatch", "frame json step_index differs from timeline", path, row=row_index, frame_step=data.get("step_index"), timeline_step=row.get("step_index"))
    if "time_code" in data and abs(float(data["time_code"]) - float(row.get("time_code", 0.0))) > 1e-9:
        report.error("frame_json_time_mismatch", "frame json time_code differs from timeline", path, row=row_index, frame_time=data.get("time_code"), timeline_time=row.get("time_code"))
    actual_scalar_keys = sorted(k for k in data.keys() if k not in {"step_index", "time_code"})
    if sorted(row_scalar_keys) != actual_scalar_keys:
        report.warning("frame_json_scalar_keys_mismatch", "timeline scalar_keys differ from frame json contents", path, row=row_index, expected=row_scalar_keys, actual=actual_scalar_keys)


def _logs_required(context: ValidationContext) -> bool:
    configured = context.options.get("require_logs")
    if configured is not None:
        return bool(configured)
    meta = _read_json_or_none(context.sample_dir / "meta.json", None)
    if isinstance(meta, dict):
        logging_cfg = meta.get("logging")
        if isinstance(logging_cfg, dict) and logging_cfg.get("enabled") is False:
            return False
    return True


def _read_json_or_error(path: Path, report: ValidationReport | None) -> Any | None:
    if not path.is_file():
        if report is not None:
            report.error("json_missing", "JSON file is missing", path)
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        if report is not None:
            report.error("json_invalid", f"Cannot read JSON file: {exc}", path)
        return None


def _read_json_or_none(path: Path, report: ValidationReport | None) -> Any | None:
    if not path.is_file():
        return None
    return _read_json_or_error(path, report)


def _load_optional_npy(path: Path, report: ValidationReport) -> np.ndarray | None:
    if not path.is_file():
        return None
    try:
        return np.load(path)
    except Exception as exc:
        report.error("npy_invalid", f"Cannot read npy file: {exc}", path)
        return None


def _check_finite(name: str, value: np.ndarray, path: Path, report: ValidationReport) -> None:
    if not np.all(np.isfinite(value)):
        report.error("array_non_finite", f"{name} contains NaN or Inf", path)


def _compare_common_scalar(key: str, left: Mapping[str, Any], right: Mapping[str, Any], path: Path, report: ValidationReport) -> None:
    if key in left and key in right and _is_scalar(left[key]) and _is_scalar(right[key]) and left[key] != right[key]:
        report.error("metadata_scalar_mismatch", "Metadata scalar differs across files", path, key=key, left=left[key], right=right[key])


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
