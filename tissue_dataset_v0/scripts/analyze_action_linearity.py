#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze small-action magnitude linearity and tangent-direction superposition for SOFA NJF groups."
    )
    parser.add_argument("dataset_or_groups", type=Path, help="Dataset root, groups/ directory, or one group_* directory.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: DATASET_ROOT/analysis/action_linearity.",
    )
    parser.add_argument(
        "--linearity-threshold",
        type=float,
        default=0.10,
        help="Recommended maximum relative scale error; default 0.10.",
    )
    parser.add_argument(
        "--superposition-threshold",
        type=float,
        default=0.15,
        help="Recommended maximum relative tangent-superposition error; default 0.15.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    group_dirs = discover_group_dirs(args.dataset_or_groups)
    if not group_dirs:
        print(f"No group_* directories found under {args.dataset_or_groups}", file=sys.stderr)
        return 2

    groups = [load_group(group_dir) for group_dir in group_dirs]
    linearity_rows = [row for group in groups for row in analyze_group_linearity(group, args.linearity_threshold)]
    superposition_rows = [
        row for group in groups for row in analyze_group_superposition(group, args.superposition_threshold)
    ]
    linearity_summary = summarize_linearity(linearity_rows)
    superposition_summary = summarize_superposition(superposition_rows)
    decision = build_decision(linearity_summary, superposition_summary, args)
    payload = {
        "valid": True,
        "analysis_type": "action_linearity",
        "group_count": len(groups),
        "group_ids": [group.group_id for group in groups],
        "linearity_threshold": args.linearity_threshold,
        "superposition_threshold": args.superposition_threshold,
        "linearity_summary": linearity_summary,
        "superposition_summary": superposition_summary,
        "decision": decision,
        "notes": [
            "Magnitude linearity compares each direction/magnitude response to a scaled smallest-magnitude reference.",
            "Superposition is tangent residual superposition around the normal/downward action baseline.",
            "This script diagnoses existing grouped data; it does not run SOFA or create new samples.",
        ],
    }

    output_dir = args.output_dir or default_output_dir(args.dataset_or_groups)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "linearity_by_direction.csv", linearity_rows)
    write_csv(output_dir / "linearity_summary_by_magnitude.csv", linearity_summary["by_magnitude"])
    write_csv(output_dir / "linearity_summary_by_group.csv", linearity_summary["by_group"])
    write_csv(output_dir / "superposition_tests.csv", superposition_rows)
    write_csv(output_dir / "superposition_summary_by_group.csv", superposition_summary["by_group"])
    write_json(output_dir / "summary.json", payload)
    (output_dir / "decision_summary.md").write_text(build_report(payload), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(jsonable(payload), indent=2, sort_keys=True))
    else:
        print_text(payload, output_dir)
    return 0


@dataclass(frozen=True)
class ActionResponse:
    index: int
    direction: np.ndarray
    magnitude_m: float
    response: np.ndarray

    @property
    def magnitude_mm(self) -> float:
        return self.magnitude_m * 1e3

    @property
    def direction_key(self) -> str:
        return direction_key(self.direction)


@dataclass(frozen=True)
class GroupData:
    group_id: str
    group_dir: Path
    metadata: dict[str, Any]
    actions: np.ndarray
    responses: np.ndarray
    records: list[ActionResponse]

    @property
    def contact_point_id(self) -> str:
        return str(self.metadata.get("contact_point_id", "unknown_contact"))

    @property
    def material_id(self) -> str:
        return str(self.metadata.get("material_id", "unknown_material"))

    @property
    def youngs_modulus(self) -> float | None:
        material = self.metadata.get("material", {})
        if isinstance(material, dict) and material.get("youngs_modulus") is not None:
            return float(material["youngs_modulus"])
        return None

    @property
    def poisson_ratio(self) -> float | None:
        material = self.metadata.get("material", {})
        if isinstance(material, dict) and material.get("poisson_ratio") is not None:
            return float(material["poisson_ratio"])
        return None


def discover_group_dirs(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_dir() and path.name.startswith("group_"):
        return [path]
    if path.is_dir() and path.name == "groups":
        return sorted(item for item in path.iterdir() if item.is_dir() and item.name.startswith("group_"))
    groups_dir = path / "groups"
    if groups_dir.is_dir():
        return sorted(item for item in groups_dir.iterdir() if item.is_dir() and item.name.startswith("group_"))
    return []


def default_output_dir(path: Path) -> Path:
    path = Path(path)
    if path.name.startswith("group_"):
        return path / "analysis" / "action_linearity"
    if path.name == "groups":
        return path.parent / "analysis" / "action_linearity"
    return path / "analysis" / "action_linearity"


def load_group(group_dir: Path) -> GroupData:
    metadata = load_json(group_dir / "group_metadata.json")
    actions = np.load(group_dir / "actions.npy")
    responses = np.load(group_dir / "responses.npy")
    if actions.ndim != 2 or actions.shape[1] < 6:
        raise ValueError(f"{group_dir}: actions.npy must have shape [K, >=6]")
    if responses.ndim != 3 or responses.shape[0] != actions.shape[0]:
        raise ValueError(f"{group_dir}: responses.npy must have shape [K, N, 3] and match actions")
    flat_responses = responses.reshape(responses.shape[0], -1).astype(np.float64)
    records = [
        ActionResponse(
            index=index,
            direction=normalize(actions[index, 2:5].astype(np.float64)),
            magnitude_m=float(actions[index, 5]),
            response=flat_responses[index],
        )
        for index in range(actions.shape[0])
    ]
    return GroupData(
        group_id=group_dir.name,
        group_dir=group_dir,
        metadata=metadata,
        actions=actions,
        responses=responses,
        records=records,
    )


def analyze_group_linearity(group: GroupData, threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for direction, records in records_by_direction(group.records).items():
        ordered = sorted(records, key=lambda item: item.magnitude_m)
        if len(ordered) < 2:
            continue
        reference = ordered[0]
        ref_norm = float(np.linalg.norm(reference.response))
        if ref_norm <= 0.0 or reference.magnitude_m <= 0.0:
            continue
        for record in ordered[1:]:
            scale = record.magnitude_m / reference.magnitude_m
            predicted = scale * reference.response
            actual_norm = float(np.linalg.norm(record.response))
            absolute_error = float(np.linalg.norm(record.response - predicted))
            relative_error = absolute_error / max(actual_norm, 1e-12)
            cosine = cosine_similarity(record.response, predicted)
            rows.append(
                {
                    "group_id": group.group_id,
                    "contact_point_id": group.contact_point_id,
                    "material_id": group.material_id,
                    "youngs_modulus": group.youngs_modulus,
                    "poisson_ratio": group.poisson_ratio,
                    "direction_key": direction,
                    "reference_magnitude_mm": reference.magnitude_mm,
                    "magnitude_mm": record.magnitude_mm,
                    "scale_factor": scale,
                    "response_norm_m": actual_norm,
                    "scaled_reference_norm_m": float(np.linalg.norm(predicted)),
                    "absolute_scale_error_m": absolute_error,
                    "relative_scale_error": relative_error,
                    "cosine_with_scaled_reference": cosine,
                    "recommendation": "keep" if relative_error <= threshold else "reject_or_retest",
                }
            )
    return rows


def analyze_group_superposition(group: GroupData, threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    records_by_mag: dict[float, list[ActionResponse]] = {}
    for record in group.records:
        records_by_mag.setdefault(round(record.magnitude_m, 10), []).append(record)
    for _, records in sorted(records_by_mag.items()):
        normal = find_normal_record(records)
        if normal is None:
            continue
        x_records = [record for record in records if is_axis_tangent(record.direction, axis=0)]
        y_records = [record for record in records if is_axis_tangent(record.direction, axis=1)]
        diagonal_records = [record for record in records if is_diagonal_tangent(record.direction)]
        for x_record in x_records:
            for y_record in y_records:
                if np.sign(x_record.direction[0]) == 0.0 or np.sign(y_record.direction[1]) == 0.0:
                    continue
                target = find_diagonal_match(diagonal_records, x_record.direction, y_record.direction)
                if target is None:
                    continue
                lateral_x = x_record.direction[:2]
                lateral_y = y_record.direction[:2]
                lateral_target = target.direction[:2]
                alpha = projection_scale(lateral_target, lateral_x)
                beta = projection_scale(lateral_target, lateral_y)
                residual_x = x_record.response - normal.response
                residual_y = y_record.response - normal.response
                residual_target = target.response - normal.response
                predicted = alpha * residual_x + beta * residual_y
                denominator = float(np.linalg.norm(residual_target))
                absolute_error = float(np.linalg.norm(residual_target - predicted))
                relative_error = absolute_error / max(denominator, 1e-12)
                rows.append(
                    {
                        "group_id": group.group_id,
                        "contact_point_id": group.contact_point_id,
                        "material_id": group.material_id,
                        "youngs_modulus": group.youngs_modulus,
                        "poisson_ratio": group.poisson_ratio,
                        "magnitude_mm": target.magnitude_mm,
                        "normal_direction_key": normal.direction_key,
                        "axis_x_direction_key": x_record.direction_key,
                        "axis_y_direction_key": y_record.direction_key,
                        "combined_direction_key": target.direction_key,
                        "alpha": alpha,
                        "beta": beta,
                        "target_residual_norm_m": denominator,
                        "absolute_superposition_error_m": absolute_error,
                        "relative_superposition_error": relative_error,
                        "cosine_with_predicted_residual": cosine_similarity(residual_target, predicted),
                        "recommendation": "keep" if relative_error <= threshold else "reject_or_retest",
                    }
                )
    return rows


def records_by_direction(records: list[ActionResponse]) -> dict[str, list[ActionResponse]]:
    grouped: dict[str, list[ActionResponse]] = {}
    for record in records:
        grouped.setdefault(record.direction_key, []).append(record)
    return grouped


def summarize_linearity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": summarize_error_rows(rows, "relative_scale_error"),
        "by_magnitude": summarize_by_keys(rows, ["magnitude_mm"], "relative_scale_error"),
        "by_group": summarize_by_keys(rows, ["group_id", "contact_point_id", "material_id"], "relative_scale_error"),
        "by_material": summarize_by_keys(rows, ["material_id"], "relative_scale_error"),
    }


def summarize_superposition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": summarize_error_rows(rows, "relative_superposition_error"),
        "by_magnitude": summarize_by_keys(rows, ["magnitude_mm"], "relative_superposition_error"),
        "by_group": summarize_by_keys(rows, ["group_id", "contact_point_id", "material_id"], "relative_superposition_error"),
        "by_material": summarize_by_keys(rows, ["material_id"], "relative_superposition_error"),
    }


def summarize_by_keys(rows: list[dict[str, Any]], keys: list[str], error_key: str) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(tuple(row.get(key) for key in keys), []).append(row)
    output: list[dict[str, Any]] = []
    for key_values, bucket in sorted(buckets.items(), key=lambda item: tuple(str(v) for v in item[0])):
        summary = summarize_error_rows(bucket, error_key)
        result = {key: key_values[index] for index, key in enumerate(keys)}
        result.update(summary)
        output.append(result)
    return output


def summarize_error_rows(rows: list[dict[str, Any]], error_key: str) -> dict[str, Any]:
    values = np.asarray([float(row[error_key]) for row in rows if row.get(error_key) is not None], dtype=np.float64)
    if values.size == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "median": None,
            "p90": None,
        }
    return {
        "count": int(values.size),
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
    }


def build_decision(linearity_summary: dict[str, Any], superposition_summary: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    linearity_overall = linearity_summary["overall"]
    superposition_overall = superposition_summary["overall"]
    safe_magnitudes = [
        row["magnitude_mm"]
        for row in linearity_summary["by_magnitude"]
        if row.get("mean") is not None and float(row["mean"]) <= args.linearity_threshold
    ]
    return {
        "linearity": decision_text(
            linearity_overall,
            args.linearity_threshold,
            pass_text="current magnitude sweep is approximately scale-linear",
            fail_text="current magnitude sweep is not scale-linear enough for strict NJF supervision",
        ),
        "superposition": decision_text(
            superposition_overall,
            args.superposition_threshold,
            pass_text="available tangent combinations approximately satisfy superposition",
            fail_text="available tangent combinations do not yet satisfy superposition",
        ),
        "safe_magnitudes_mm_by_mean_error": safe_magnitudes,
        "next_data_need": next_data_need(linearity_summary, superposition_summary, args),
    }


def decision_text(summary: dict[str, Any], threshold: float, *, pass_text: str, fail_text: str) -> str:
    if not summary.get("count"):
        return "not_answered; no compatible rows found"
    if float(summary["mean"]) <= threshold:
        return f"{pass_text}; mean_error={summary['mean']:.6f} threshold={threshold:.6f}"
    return f"{fail_text}; mean_error={summary['mean']:.6f} threshold={threshold:.6f}"


def next_data_need(
    linearity_summary: dict[str, Any],
    superposition_summary: dict[str, Any],
    args: argparse.Namespace,
) -> str:
    if not linearity_summary["overall"].get("count"):
        return "generate groups with at least two magnitudes per direction"
    linearity_mean = linearity_summary["overall"].get("mean")
    if linearity_mean is not None and float(linearity_mean) > args.linearity_threshold:
        return (
            "do not expand to larger magnitudes yet; first verify action depth/contact parameterization, "
            "then generate a smaller incremental probe such as 0.01, 0.02, and 0.05 mm"
        )
    if not superposition_summary["overall"].get("count"):
        return "generate groups with normal, x, y, and diagonal x+y directions at matched magnitudes"
    return "if current errors are acceptable, expand magnitude sweep to include 0.5 and 1.0 mm for boundary finding"


def build_report(payload: dict[str, Any]) -> str:
    linearity = payload["linearity_summary"]["overall"]
    superposition = payload["superposition_summary"]["overall"]
    lines = [
        "# Action Linearity And Superposition Summary",
        "",
        f"Groups analyzed: {payload['group_count']}",
        "",
        "## Magnitude Linearity",
        "",
        f"- tests: {linearity['count']}",
        f"- mean relative scale error: {format_optional(linearity['mean'])}",
        f"- p90 relative scale error: {format_optional(linearity['p90'])}",
        f"- max relative scale error: {format_optional(linearity['max'])}",
        f"- decision: {payload['decision']['linearity']}",
        "",
        "## Tangent Superposition",
        "",
        f"- tests: {superposition['count']}",
        f"- mean relative superposition error: {format_optional(superposition['mean'])}",
        f"- p90 relative superposition error: {format_optional(superposition['p90'])}",
        f"- max relative superposition error: {format_optional(superposition['max'])}",
        f"- decision: {payload['decision']['superposition']}",
        "",
        "## Next Data Need",
        "",
        payload["decision"]["next_data_need"],
        "",
    ]
    return "\n".join(lines)


def print_text(payload: dict[str, Any], output_dir: Path) -> None:
    linearity = payload["linearity_summary"]["overall"]
    superposition = payload["superposition_summary"]["overall"]
    print("Action linearity analysis: PASS")
    print(f"groups={payload['group_count']}")
    print(
        "linearity="
        f"count={linearity['count']} mean={format_optional(linearity['mean'])} "
        f"p90={format_optional(linearity['p90'])} max={format_optional(linearity['max'])}"
    )
    print(
        "superposition="
        f"count={superposition['count']} mean={format_optional(superposition['mean'])} "
        f"p90={format_optional(superposition['p90'])} max={format_optional(superposition['max'])}"
    )
    print(f"decision_linearity={payload['decision']['linearity']}")
    print(f"decision_superposition={payload['decision']['superposition']}")
    print(f"outputs={output_dir}")


def find_normal_record(records: list[ActionResponse]) -> ActionResponse | None:
    if not records:
        return None
    return min(records, key=lambda item: float(np.linalg.norm(item.direction[:2])))


def is_axis_tangent(direction: np.ndarray, *, axis: int) -> bool:
    lateral = direction[:2]
    other = 1 - axis
    return abs(lateral[axis]) > 1e-4 and abs(lateral[other]) < 1e-4


def is_diagonal_tangent(direction: np.ndarray) -> bool:
    lateral = direction[:2]
    return abs(lateral[0]) > 1e-4 and abs(lateral[1]) > 1e-4


def find_diagonal_match(records: list[ActionResponse], x_direction: np.ndarray, y_direction: np.ndarray) -> ActionResponse | None:
    x_sign = np.sign(x_direction[0])
    y_sign = np.sign(y_direction[1])
    candidates = [
        record
        for record in records
        if np.sign(record.direction[0]) == x_sign and np.sign(record.direction[1]) == y_sign
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: abs(item.direction[0]) + abs(item.direction[1]))


def projection_scale(target: np.ndarray, source: np.ndarray) -> float:
    denominator = float(np.dot(source, source))
    if denominator <= 0.0:
        return 0.0
    return float(np.dot(target, source) / denominator)


def direction_key(direction: np.ndarray) -> str:
    return ",".join(f"{float(value):.4f}" for value in direction)


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return vector
    return vector / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(jsonable(value), sort_keys=True)
    return value


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def format_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
