from __future__ import annotations

from collections.abc import Sequence

from .core import SampleValidator, ValidationRule
from .rules import CoreArrayConsistencyRule, LogIntegrityRule, ManifestArtifactRule, MetadataConsistencyRule, SampleStructureRule, TrajectorySummaryRule


def default_rules() -> list[ValidationRule]:
    return [
        SampleStructureRule(),
        ManifestArtifactRule(),
        CoreArrayConsistencyRule(),
        MetadataConsistencyRule(),
        LogIntegrityRule(),
        TrajectorySummaryRule(),
    ]


def build_default_validator(extra_rules: Sequence[ValidationRule] | None = None) -> SampleValidator:
    rules = default_rules()
    rules.extend(extra_rules or [])
    return SampleValidator(rules)
