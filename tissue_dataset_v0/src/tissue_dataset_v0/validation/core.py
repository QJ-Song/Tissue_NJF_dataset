from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import numpy as np


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str
    path: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "detail": dict(self.detail),
        }


@dataclass
class ValidationReport:
    sample_dir: Path
    issues: list[ValidationIssue] = field(default_factory=list)
    checked_rules: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)

    def add(
        self,
        severity: ValidationSeverity,
        code: str,
        message: str,
        path: str | Path | None = None,
        **detail: Any,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
                path=str(path) if path is not None else None,
                detail=detail,
            )
        )

    def error(self, code: str, message: str, path: str | Path | None = None, **detail: Any) -> None:
        self.add(ValidationSeverity.ERROR, code, message, path, **detail)

    def warning(self, code: str, message: str, path: str | Path | None = None, **detail: Any) -> None:
        self.add(ValidationSeverity.WARNING, code, message, path, **detail)

    def info(self, code: str, message: str, path: str | Path | None = None, **detail: Any) -> None:
        self.add(ValidationSeverity.INFO, code, message, path, **detail)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.INFO)

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_dir": str(self.sample_dir),
            "valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "checked_rules": list(self.checked_rules),
            "properties": _jsonable(self.properties),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def format_text(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        lines = [
            f"Validation {status}: {self.sample_dir}",
            f"rules={len(self.checked_rules)} errors={self.error_count} warnings={self.warning_count} info={self.info_count}",
        ]
        for issue in self.issues:
            location = f" [{issue.path}]" if issue.path else ""
            lines.append(f"{issue.severity.value.upper()} {issue.code}{location}: {issue.message}")
            if issue.detail:
                lines.append(f"  detail={json.dumps(_jsonable(issue.detail), sort_keys=True)}")
        return "\n".join(lines)


class ValidationRule(Protocol):
    name: str

    def validate(self, context: "ValidationContext", report: ValidationReport) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class ValidationContext:
    sample_dir: Path
    log_dir_name: str = "logs"
    options: Mapping[str, Any] = field(default_factory=dict)

    @property
    def log_dir(self) -> Path:
        return self.sample_dir / self.log_dir_name

    @property
    def frames_dir(self) -> Path:
        return self.log_dir / "frames"

    @property
    def manifest_path(self) -> Path:
        return self.sample_dir / "sample_manifest.json"

    def artifact_path(self, name: str, kind: str) -> Path:
        suffix = artifact_suffix(kind)
        return self.sample_dir / f"{name}{suffix}"

    def read_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def read_json_if_exists(self, path: Path) -> Any | None:
        if not path.exists():
            return None
        return self.read_json(path)

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"JSONL row must be an object at {path}:{line_no}")
                rows.append(value)
        return rows

    def load_npy(self, path: Path) -> np.ndarray:
        return np.load(path)


class SampleValidator:
    def __init__(self, rules: Sequence[ValidationRule]):
        self.rules = list(rules)

    def validate(
        self,
        sample_dir: Path,
        *,
        log_dir_name: str = "logs",
        options: Mapping[str, Any] | None = None,
    ) -> ValidationReport:
        context = ValidationContext(Path(sample_dir), log_dir_name=log_dir_name, options=dict(options or {}))
        report = ValidationReport(sample_dir=context.sample_dir)
        for rule in self.rules:
            report.checked_rules.append(rule.name)
            try:
                rule.validate(context, report)
            except Exception as exc:  # Keep validation robust when a plugin has a bug.
                report.error(
                    "rule_failed",
                    f"Validation rule failed: {rule.name}: {exc}",
                    detail_type=type(exc).__name__,
                )
        return report


def artifact_suffix(kind: str) -> str:
    return {
        "npy": ".npy",
        "json": ".json",
        "txt": ".txt",
        "png": ".png",
    }.get(kind, "")


def load_rule(spec: str) -> ValidationRule:
    module_name, sep, attr_name = spec.partition(":")
    if not sep:
        raise ValueError("rule spec must be 'module:ClassName'")
    module = importlib.import_module(module_name)
    rule_cls = getattr(module, attr_name)
    return rule_cls()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value
