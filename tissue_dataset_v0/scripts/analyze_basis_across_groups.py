#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze cross-group SOFA NJF response-basis similarity without running one global PCA."
    )
    parser.add_argument("dataset_or_groups", type=Path, help="Dataset root or groups/ directory.")
    parser.add_argument(
        "--rank",
        type=int,
        default=2,
        help="Top-r basis dimension for pairwise subspace comparison; default 2.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: DATASET_ROOT/analysis/basis_across_groups.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    group_dirs = discover_group_dirs(args.dataset_or_groups)
    if not group_dirs:
        print(f"No group_* directories found under {args.dataset_or_groups}", file=sys.stderr)
        return 2
    if args.rank <= 0:
        print("--rank must be positive", file=sys.stderr)
        return 2

    output_dir = args.output_dir or default_output_dir(args.dataset_or_groups)
    groups = [load_group(group_dir, rank=args.rank) for group_dir in group_dirs]
    pairwise = compute_pairwise(groups, rank=args.rank)
    shared_basis = compute_shared_basis_diagnostic(groups, pairwise=pairwise, rank=args.rank)
    metadata_summary = summarize_pairwise_by_metadata(groups, pairwise)
    material_scale = analyze_material_scale_pattern(groups, rank=args.rank)
    boundary_pattern = analyze_boundary_pattern(groups, rank=args.rank)
    per_group_rows = [group.per_group_row() for group in groups]
    summary = build_summary(groups, pairwise, metadata_summary, material_scale, boundary_pattern, shared_basis, rank=args.rank)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "per_group_metrics.csv", per_group_rows)
    write_csv(output_dir / "shared_basis_reconstruction.csv", shared_basis["rows"])
    write_matrix_csv(output_dir / "projection_similarity.csv", pairwise["projection_similarity"], groups)
    write_matrix_csv(output_dir / "principal_angles_mean.csv", pairwise["principal_angles_mean_deg"], groups)
    write_matrix_csv(output_dir / "principal_angles_max.csv", pairwise["principal_angles_max_deg"], groups)
    write_matrix_csv(output_dir / "cross_reconstruction_error.csv", pairwise["cross_reconstruction_error"], groups)
    write_csv(output_dir / "metadata_grouped_summary.csv", metadata_summary)
    write_csv(output_dir / "material_scale_pattern.csv", material_scale)
    write_csv(output_dir / "boundary_pattern.csv", boundary_pattern)
    write_json(output_dir / "summary.json", summary)
    (output_dir / "decision_summary.md").write_text(build_decision_report(summary), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(jsonable(summary), indent=2, sort_keys=True))
    else:
        print_text(summary, output_dir)
    return 0


@dataclass(frozen=True)
class GroupBasis:
    group_id: str
    group_dir: Path
    metadata: dict[str, Any]
    actions: np.ndarray
    responses: np.ndarray
    matrix: np.ndarray
    centered: np.ndarray
    basis: np.ndarray
    normalized_basis: np.ndarray
    singular_values: np.ndarray
    explained_variance: np.ndarray
    cumulative_explained: np.ndarray
    effective_rank: float
    leave_one_out_mean: float
    leave_one_out_max: float
    response_norm_mean: float
    response_norm_min: float
    response_norm_max: float
    rank: int

    @property
    def action_count(self) -> int:
        return int(self.matrix.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.responses.shape[1])

    @property
    def contact_point_id(self) -> str:
        return str(self.metadata.get("contact_point_id", "unknown_contact"))

    @property
    def material_id(self) -> str:
        return str(self.metadata.get("material_id", "unknown_material"))

    @property
    def boundary_id(self) -> str:
        return str(self.metadata.get("boundary_id", "unknown_boundary"))

    @property
    def youngs_modulus(self) -> float | None:
        material = self.metadata.get("material", {})
        if not isinstance(material, dict) or material.get("youngs_modulus") is None:
            return None
        return float(material["youngs_modulus"])

    @property
    def poisson_ratio(self) -> float | None:
        material = self.metadata.get("material", {})
        if not isinstance(material, dict) or material.get("poisson_ratio") is None:
            return None
        return float(material["poisson_ratio"])

    @property
    def contact_point_world(self) -> list[float]:
        value = self.metadata.get("contact_point_world", [])
        if isinstance(value, list):
            return [float(item) for item in value]
        return []

    def top_cumulative(self, index: int) -> float:
        if self.cumulative_explained.size == 0:
            return 0.0
        return float(self.cumulative_explained[min(index, self.cumulative_explained.size - 1)])

    def per_group_row(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "contact_point_id": self.contact_point_id,
            "material_id": self.material_id,
            "boundary_id": self.boundary_id,
            "youngs_modulus": self.youngs_modulus,
            "poisson_ratio": self.poisson_ratio,
            "contact_point_world": json.dumps(self.contact_point_world),
            "action_count": self.action_count,
            "vertex_count": self.vertex_count,
            "basis_rank": self.rank,
            "effective_rank": self.effective_rank,
            "top1_cumulative_explained": self.top_cumulative(0),
            "top2_cumulative_explained": self.top_cumulative(1),
            "top3_cumulative_explained": self.top_cumulative(2),
            "leave_one_out_error_mean": self.leave_one_out_mean,
            "leave_one_out_error_max": self.leave_one_out_max,
            "response_norm_mean_m": self.response_norm_mean,
            "response_norm_min_m": self.response_norm_min,
            "response_norm_max_m": self.response_norm_max,
        }


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
        return path / "analysis" / "basis_across_groups"
    if path.name == "groups":
        return path.parent / "analysis" / "basis_across_groups"
    return path / "analysis" / "basis_across_groups"


def load_group(group_dir: Path, *, rank: int) -> GroupBasis:
    metadata = load_json(group_dir / "group_metadata.json")
    actions = np.load(group_dir / "actions.npy")
    responses = np.load(group_dir / "responses.npy")
    if responses.ndim != 3:
        raise ValueError(f"{group_dir}: responses.npy must have shape [K, N, 3]")
    matrix = responses.reshape(responses.shape[0], -1).astype(np.float64)
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    _, singular_values, vh = np.linalg.svd(centered, full_matrices=False)
    energy = singular_values**2
    total_energy = float(energy.sum())
    explained = energy / total_energy if total_energy > 0.0 else np.zeros_like(energy)
    cumulative = np.cumsum(explained)
    chosen_rank = max(1, min(rank, vh.shape[0]))
    basis = vh[:chosen_rank]
    normalized = normalize_rows(matrix)
    normalized_centered = normalized - normalized.mean(axis=0, keepdims=True)
    _, _, normalized_vh = np.linalg.svd(normalized_centered, full_matrices=False)
    normalized_basis = normalized_vh[: max(1, min(chosen_rank, normalized_vh.shape[0]))]
    loo = leave_one_out_error(matrix, chosen_rank)
    norms = np.linalg.norm(matrix, axis=1)
    return GroupBasis(
        group_id=group_dir.name,
        group_dir=group_dir,
        metadata=metadata,
        actions=actions,
        responses=responses,
        matrix=matrix,
        centered=centered,
        basis=basis,
        normalized_basis=normalized_basis,
        singular_values=singular_values,
        explained_variance=explained,
        cumulative_explained=cumulative,
        effective_rank=entropy_effective_rank(explained),
        leave_one_out_mean=float(loo["mean_relative_error"]),
        leave_one_out_max=float(loo["max_relative_error"]),
        response_norm_mean=float(norms.mean()) if norms.size else 0.0,
        response_norm_min=float(norms.min()) if norms.size else 0.0,
        response_norm_max=float(norms.max()) if norms.size else 0.0,
        rank=chosen_rank,
    )


def compute_pairwise(groups: list[GroupBasis], *, rank: int) -> dict[str, np.ndarray]:
    n = len(groups)
    projection_similarity = np.zeros((n, n), dtype=np.float64)
    principal_angles_mean = np.zeros((n, n), dtype=np.float64)
    principal_angles_max = np.zeros((n, n), dtype=np.float64)
    cross_reconstruction_error = np.zeros((n, n), dtype=np.float64)
    for i, source in enumerate(groups):
        for j, target in enumerate(groups):
            r = max(1, min(rank, source.basis.shape[0], target.basis.shape[0]))
            sv = np.linalg.svd(source.basis[:r] @ target.basis[:r].T, compute_uv=False)
            sv = np.clip(sv, 0.0, 1.0)
            angles = np.degrees(np.arccos(sv))
            projection_similarity[i, j] = float(np.sum(sv**2) / r)
            principal_angles_mean[i, j] = float(angles.mean()) if angles.size else 0.0
            principal_angles_max[i, j] = float(angles.max()) if angles.size else 0.0
            cross_reconstruction_error[i, j] = reconstruction_error(target.centered, source.basis[:r])
    return {
        "projection_similarity": projection_similarity,
        "principal_angles_mean_deg": principal_angles_mean,
        "principal_angles_max_deg": principal_angles_max,
        "cross_reconstruction_error": cross_reconstruction_error,
    }


def summarize_pairwise_by_metadata(groups: list[GroupBasis], pairwise: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    buckets: dict[str, list[tuple[int, int]]] = {
        "same_contact_same_material_same_boundary": [],
        "same_contact_same_material_diff_boundary": [],
        "same_contact_same_boundary_diff_material": [],
        "same_material_same_boundary_diff_contact": [],
        "diff_contact_diff_material_or_boundary": [],
    }
    for i, source in enumerate(groups):
        for j, target in enumerate(groups):
            if i == j:
                continue
            same_contact = source.contact_point_id == target.contact_point_id
            same_material = source.material_id == target.material_id
            same_boundary = source.boundary_id == target.boundary_id
            if same_contact and same_material and same_boundary:
                key = "same_contact_same_material_same_boundary"
            elif same_contact and same_material and not same_boundary:
                key = "same_contact_same_material_diff_boundary"
            elif same_contact and same_boundary and not same_material:
                key = "same_contact_same_boundary_diff_material"
            elif same_material and same_boundary and not same_contact:
                key = "same_material_same_boundary_diff_contact"
            else:
                key = "diff_contact_diff_material_or_boundary"
            buckets[key].append((i, j))

    rows: list[dict[str, Any]] = []
    for key, pairs in buckets.items():
        rows.append(pairwise_stats_row(key, pairs, pairwise))
    return rows


def pairwise_stats_row(label: str, pairs: list[tuple[int, int]], pairwise: dict[str, np.ndarray]) -> dict[str, Any]:
    if not pairs:
        return {
            "comparison_type": label,
            "pair_count": 0,
            "projection_similarity_mean": None,
            "projection_similarity_std": None,
            "principal_angle_mean_deg": None,
            "principal_angle_max_deg": None,
            "cross_reconstruction_error_mean": None,
            "cross_reconstruction_error_std": None,
        }
    projection = values_for_pairs(pairwise["projection_similarity"], pairs)
    angle_mean = values_for_pairs(pairwise["principal_angles_mean_deg"], pairs)
    angle_max = values_for_pairs(pairwise["principal_angles_max_deg"], pairs)
    cross = values_for_pairs(pairwise["cross_reconstruction_error"], pairs)
    return {
        "comparison_type": label,
        "pair_count": len(pairs),
        "projection_similarity_mean": float(projection.mean()),
        "projection_similarity_std": float(projection.std()),
        "principal_angle_mean_deg": float(angle_mean.mean()),
        "principal_angle_max_deg": float(angle_max.max()),
        "cross_reconstruction_error_mean": float(cross.mean()),
        "cross_reconstruction_error_std": float(cross.std()),
    }


def analyze_boundary_pattern(groups: list[GroupBasis], *, rank: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = sorted({(group.contact_point_id, group.material_id) for group in groups})
    for contact_id, material_id in keys:
        matched = [group for group in groups if group.contact_point_id == contact_id and group.material_id == material_id]
        for index, source in enumerate(matched):
            for target in matched[index + 1 :]:
                if source.boundary_id == target.boundary_id:
                    continue
                r = max(1, min(rank, source.basis.shape[0], target.basis.shape[0]))
                raw_source_target = reconstruction_error(target.centered, source.basis[:r])
                raw_target_source = reconstruction_error(source.centered, target.basis[:r])
                source_norm = normalize_rows(source.matrix)
                target_norm = normalize_rows(target.matrix)
                source_norm_centered = source_norm - source_norm.mean(axis=0, keepdims=True)
                target_norm_centered = target_norm - target_norm.mean(axis=0, keepdims=True)
                norm_source_target = reconstruction_error(target_norm_centered, source.normalized_basis[:r])
                norm_target_source = reconstruction_error(source_norm_centered, target.normalized_basis[:r])
                sv = np.linalg.svd(source.normalized_basis[:r] @ target.normalized_basis[:r].T, compute_uv=False)
                sv = np.clip(sv, 0.0, 1.0)
                rows.append(
                    {
                        "contact_point_id": contact_id,
                        "material_id": material_id,
                        "source_group_id": source.group_id,
                        "target_group_id": target.group_id,
                        "source_boundary_id": source.boundary_id,
                        "target_boundary_id": target.boundary_id,
                        "source_boundary_type": boundary_type_from_metadata(source),
                        "target_boundary_type": boundary_type_from_metadata(target),
                        "source_fixed_node_count": fixed_node_count_from_metadata(source),
                        "target_fixed_node_count": fixed_node_count_from_metadata(target),
                        "response_norm_ratio_source_over_target": source.response_norm_mean / max(target.response_norm_mean, 1e-12),
                        "raw_cross_reconstruction_error_mean": float((raw_source_target + raw_target_source) / 2.0),
                        "normalized_cross_reconstruction_error_mean": float((norm_source_target + norm_target_source) / 2.0),
                        "normalized_projection_similarity": float(np.sum(sv**2) / r),
                        "interpretation": interpret_boundary_pattern(
                            float((norm_source_target + norm_target_source) / 2.0),
                            float(np.sum(sv**2) / r),
                        ),
                    }
                )
    return rows


def boundary_type_from_metadata(group: GroupBasis) -> str:
    boundary = group.metadata.get("boundary", {})
    if isinstance(boundary, dict):
        return str(boundary.get("boundary_type", group.boundary_id))
    return group.boundary_id


def fixed_node_count_from_metadata(group: GroupBasis) -> int | None:
    boundary = group.metadata.get("boundary", {})
    if isinstance(boundary, dict) and boundary.get("fixed_node_count") is not None:
        return int(boundary["fixed_node_count"])
    return None


def analyze_material_scale_pattern(groups: list[GroupBasis], *, rank: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for contact_id in sorted({group.contact_point_id for group in groups}):
        contact_groups = [group for group in groups if group.contact_point_id == contact_id]
        for index, a in enumerate(contact_groups):
            for b in contact_groups[index + 1 :]:
                if a.material_id == b.material_id:
                    continue
                low, high = sorted([a, b], key=lambda item: item.youngs_modulus or 0.0)
                r = max(1, min(rank, low.basis.shape[0], high.basis.shape[0]))
                raw_low_high = reconstruction_error(high.centered, low.basis[:r])
                raw_high_low = reconstruction_error(low.centered, high.basis[:r])
                norm_low = normalize_rows(low.matrix)
                norm_high = normalize_rows(high.matrix)
                norm_low_centered = norm_low - norm_low.mean(axis=0, keepdims=True)
                norm_high_centered = norm_high - norm_high.mean(axis=0, keepdims=True)
                norm_low_high = reconstruction_error(norm_high_centered, low.normalized_basis[:r])
                norm_high_low = reconstruction_error(norm_low_centered, high.normalized_basis[:r])
                sv = np.linalg.svd(low.normalized_basis[:r] @ high.normalized_basis[:r].T, compute_uv=False)
                sv = np.clip(sv, 0.0, 1.0)
                normalized_projection = float(np.sum(sv**2) / r)
                normalized_error = float((norm_low_high + norm_high_low) / 2.0)
                rows.append(
                    {
                        "contact_point_id": contact_id,
                        "low_material_id": low.material_id,
                        "high_material_id": high.material_id,
                        "low_youngs_modulus": low.youngs_modulus,
                        "high_youngs_modulus": high.youngs_modulus,
                        "poisson_ratio_low": low.poisson_ratio,
                        "poisson_ratio_high": high.poisson_ratio,
                        "response_norm_ratio_low_over_high": low.response_norm_mean / max(high.response_norm_mean, 1e-12),
                        "raw_cross_reconstruction_error_mean": float((raw_low_high + raw_high_low) / 2.0),
                        "normalized_cross_reconstruction_error_mean": normalized_error,
                        "normalized_projection_similarity": normalized_projection,
                        "interpretation": interpret_material_pattern(normalized_error, normalized_projection),
                    }
                )
    return rows



def compute_shared_basis_diagnostic(
    groups: list[GroupBasis],
    *,
    pairwise: dict[str, np.ndarray],
    rank: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if not groups:
        return {
            "rank": int(rank),
            "rows": rows,
            "aggregate": {},
            "interpretation": "not_answered; no groups",
        }

    clipped_rank = max(1, min(int(rank), min(group.basis.shape[0] for group in groups)))
    pooled_basis = basis_from_rows(np.concatenate([group.centered for group in groups], axis=0), clipped_rank)
    pairwise_cross = pairwise["cross_reconstruction_error"]

    for target_index, target in enumerate(groups):
        local_error = reconstruction_error(target.centered, target.basis[:clipped_rank])
        pooled_error = reconstruction_error(target.centered, pooled_basis)
        if len(groups) > 1:
            train_rows = np.concatenate(
                [group.centered for index, group in enumerate(groups) if index != target_index],
                axis=0,
            )
            loo_basis = basis_from_rows(train_rows, clipped_rank)
            loo_error = reconstruction_error(target.centered, loo_basis)
            candidates = [
                (float(pairwise_cross[source_index, target_index]), source_index)
                for source_index in range(len(groups))
                if source_index != target_index
            ]
            nearest_error, nearest_index = min(candidates, key=lambda item: item[0])
            nearest = groups[nearest_index]
            nearest_relation = metadata_relation(nearest, target)
        else:
            loo_error = None
            nearest_error = None
            nearest = None
            nearest_relation = "not_available"
        rows.append(
            {
                "group_id": target.group_id,
                "contact_point_id": target.contact_point_id,
                "material_id": target.material_id,
                "boundary_id": target.boundary_id,
                "rank": clipped_rank,
                "local_group_basis_error": float(local_error),
                "pooled_shared_basis_error": float(pooled_error),
                "leave_one_group_out_shared_basis_error": None if loo_error is None else float(loo_error),
                "nearest_group_basis_error": None if nearest_error is None else float(nearest_error),
                "nearest_group_id": None if nearest is None else nearest.group_id,
                "nearest_group_relation": nearest_relation,
                "pooled_minus_local_error": float(pooled_error - local_error),
                "loo_minus_local_error": None if loo_error is None else float(loo_error - local_error),
                "nearest_minus_local_error": None if nearest_error is None else float(nearest_error - local_error),
            }
        )

    aggregate = {
        "local_group_basis_error": stat_summary_from_rows(rows, "local_group_basis_error"),
        "pooled_shared_basis_error": stat_summary_from_rows(rows, "pooled_shared_basis_error"),
        "leave_one_group_out_shared_basis_error": stat_summary_from_rows(rows, "leave_one_group_out_shared_basis_error"),
        "nearest_group_basis_error": stat_summary_from_rows(rows, "nearest_group_basis_error"),
        "pooled_minus_local_error": stat_summary_from_rows(rows, "pooled_minus_local_error"),
        "loo_minus_local_error": stat_summary_from_rows(rows, "loo_minus_local_error"),
        "nearest_minus_local_error": stat_summary_from_rows(rows, "nearest_minus_local_error"),
    }
    return {
        "rank": clipped_rank,
        "rows": rows,
        "aggregate": aggregate,
        "interpretation": shared_basis_decision({"aggregate": aggregate}),
        "notes": [
            "Group-local basis is trained and evaluated on the same group and is an expression diagnostic, not a predictor.",
            "Pooled shared basis is trained on all centered group responses, including the target group.",
            "Leave-one-group-out shared basis excludes the target group and is the cleanest shared-basis generalization diagnostic.",
            "Nearest-group basis uses the best other group by reconstruction error and is an oracle nearest-neighbor diagnostic.",
        ],
    }


def basis_from_rows(rows: np.ndarray, rank: int) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.float64)
    if rows.ndim != 2 or rows.size == 0:
        return np.zeros((0, 0), dtype=np.float64)
    _, _, vh = np.linalg.svd(rows, full_matrices=False)
    return vh[: max(1, min(int(rank), vh.shape[0]))]


def metadata_relation(source: GroupBasis, target: GroupBasis) -> str:
    same_contact = source.contact_point_id == target.contact_point_id
    same_material = source.material_id == target.material_id
    same_boundary = source.boundary_id == target.boundary_id
    if same_contact and same_material and same_boundary:
        return "same_contact_same_material_same_boundary"
    if same_contact and same_material:
        return "same_contact_same_material_diff_boundary"
    if same_contact and same_boundary:
        return "same_contact_same_boundary_diff_material"
    if same_material and same_boundary:
        return "same_material_same_boundary_diff_contact"
    return "diff_contact_diff_material_or_boundary"


def stat_summary_from_rows(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = np.asarray([float(row[key]) for row in rows if row.get(key) is not None], dtype=np.float64)
    return stat_summary(values)

def build_summary(
    groups: list[GroupBasis],
    pairwise: dict[str, np.ndarray],
    metadata_summary: list[dict[str, Any]],
    material_scale: list[dict[str, Any]],
    boundary_pattern: list[dict[str, Any]],
    shared_basis: dict[str, Any],
    *,
    rank: int,
) -> dict[str, Any]:
    group_rows = [group.per_group_row() for group in groups]
    top2 = np.asarray([group.top_cumulative(1) for group in groups], dtype=np.float64)
    effective = np.asarray([group.effective_rank for group in groups], dtype=np.float64)
    loo = np.asarray([group.leave_one_out_mean for group in groups], dtype=np.float64)
    cross = pairwise["cross_reconstruction_error"]
    offdiag = cross[~np.eye(cross.shape[0], dtype=bool)] if cross.size else np.asarray([])
    return {
        "valid": True,
        "analysis_type": "basis_across_groups",
        "basis_rank": rank,
        "group_count": len(groups),
        "group_ids": [group.group_id for group in groups],
        "contact_point_ids": sorted({group.contact_point_id for group in groups}),
        "material_ids": sorted({group.material_id for group in groups}),
        "boundary_ids": sorted({group.boundary_id for group in groups}),
        "per_group_effective_rank": {group.group_id: group.effective_rank for group in groups},
        "per_group_top2_cumulative_explained": {group.group_id: group.top_cumulative(1) for group in groups},
        "per_group_leave_one_out_error_mean": {group.group_id: group.leave_one_out_mean for group in groups},
        "aggregate": {
            "effective_rank": stat_summary(effective),
            "top2_cumulative_explained": stat_summary(top2),
            "leave_one_out_error_mean": stat_summary(loo),
            "offdiag_cross_reconstruction_error": stat_summary(offdiag),
        },
        "pairwise_matrices": {
            "projection_similarity": matrix_to_nested_dict(pairwise["projection_similarity"], groups),
            "principal_angles_mean_deg": matrix_to_nested_dict(pairwise["principal_angles_mean_deg"], groups),
            "principal_angles_max_deg": matrix_to_nested_dict(pairwise["principal_angles_max_deg"], groups),
            "cross_reconstruction_error": matrix_to_nested_dict(pairwise["cross_reconstruction_error"], groups),
        },
        "per_group_rows": group_rows,
        "metadata_grouped_summary": metadata_summary,
        "material_scale_pattern": material_scale,
        "boundary_pattern": boundary_pattern,
        "questions": {
            "local_response_basis_low_dimensional": local_basis_decision(top2, effective),
            "basis_shared_across_contact_or_material": cross_group_decision(metadata_summary),
            "material_scale_or_pattern": material_decision(material_scale),
            "boundary_scale_or_pattern": boundary_decision(boundary_pattern),
            "shared_basis_generalization": shared_basis_decision(shared_basis),
        },
        "shared_basis_diagnostic": shared_basis,
        "notes": [
            "All PCA/SVD bases are computed per group on mean-centered response matrices.",
            "Pairwise reconstruction uses the source group's centered basis on the target group's centered response matrix.",
            "This analysis intentionally avoids treating all responses as one global PCA conclusion.",
        ],
    }


def build_decision_report(summary: dict[str, Any]) -> str:
    aggregate = summary["aggregate"]
    top2 = aggregate["top2_cumulative_explained"]["mean"]
    effective = aggregate["effective_rank"]["mean"]
    cross = aggregate["offdiag_cross_reconstruction_error"]["mean"]
    lines = [
        "# Cross-Group Response Basis Decision Summary",
        "",
        f"Groups analyzed: {summary['group_count']}",
        f"Basis rank for pairwise comparison: {summary['basis_rank']}",
        "",
        "## Main Metrics",
        "",
        f"- Mean effective rank: {effective:.6f}",
        f"- Mean top-2 cumulative explained variance: {top2:.6f}",
        f"- Mean off-diagonal cross reconstruction error: {cross:.6f}",
        "",
        "## Questions",
        "",
    ]
    for key, value in summary["questions"].items():
        lines.append(f"- {key}: {value}")
    shared = summary.get("shared_basis_diagnostic", {}).get("aggregate", {})
    if shared:
        lines.extend(
            [
                "",
                "## Shared Basis Diagnostic",
                "",
                "- Local group basis error mean: {value:.6f}".format(
                    value=shared["local_group_basis_error"]["mean"]
                ),
                "- Pooled shared basis error mean: {value:.6f}".format(
                    value=shared["pooled_shared_basis_error"]["mean"]
                ),
                "- Leave-one-group-out shared basis error mean: {value:.6f}".format(
                    value=shared["leave_one_group_out_shared_basis_error"]["mean"]
                ),
                "- Nearest-group basis error mean: {value:.6f}".format(
                    value=shared["nearest_group_basis_error"]["mean"]
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- A low per-group rank supports a local response basis at fixed contact/material/boundary.",
            "- High cross-group reconstruction error means the basis is condition-dependent.",
            "- Material conclusions should compare raw and normalized responses; normalized mismatch indicates pattern change, not just scale change.",
            "- Leave-one-group-out shared-basis reconstruction is the current H8 diagnostic; it is not a learned model benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def print_text(summary: dict[str, Any], output_dir: Path) -> None:
    aggregate = summary["aggregate"]
    effective = aggregate["effective_rank"]
    top2 = aggregate["top2_cumulative_explained"]
    cross = aggregate["offdiag_cross_reconstruction_error"]
    print("Cross-group response basis analysis: PASS")
    print(f"groups={summary['group_count']} rank={summary['basis_rank']}")
    print(
        "summary="
        f"eff_rank_mean={effective['mean']:.3f} "
        f"top2_mean={top2['mean']:.6f} "
        f"offdiag_cross_recon_mean={cross['mean']:.6f}"
    )
    shared = summary.get("shared_basis_diagnostic", {}).get("aggregate", {})
    if shared:
        print(
            "shared_basis="
            f"local_mean={shared['local_group_basis_error']['mean']:.6f} "
            f"pooled_mean={shared['pooled_shared_basis_error']['mean']:.6f} "
            f"loo_mean={shared['leave_one_group_out_shared_basis_error']['mean']:.6f} "
            f"nearest_mean={shared['nearest_group_basis_error']['mean']:.6f}"
        )
    for row in summary["metadata_grouped_summary"]:
        if not row["pair_count"]:
            continue
        print(
            f"- {row['comparison_type']}: pairs={row['pair_count']} "
            f"proj={row['projection_similarity_mean']:.6f} "
            f"angle={row['principal_angle_mean_deg']:.3f}deg "
            f"cross_err={row['cross_reconstruction_error_mean']:.6f}"
        )
    print(f"outputs={output_dir}")


def reconstruction_error(target_centered: np.ndarray, basis: np.ndarray) -> float:
    denominator = float(np.linalg.norm(target_centered))
    if denominator <= 0.0 or basis.size == 0:
        return 0.0
    reconstructed = (target_centered @ basis.T) @ basis
    return float(np.linalg.norm(target_centered - reconstructed) / max(denominator, 1e-12))


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def entropy_effective_rank(explained: np.ndarray) -> float:
    probs = explained[np.asarray(explained) > 0.0]
    if probs.size == 0:
        return 0.0
    entropy = -float(np.sum(probs * np.log(probs)))
    return float(np.exp(entropy))


def leave_one_out_error(matrix: np.ndarray, rank: int) -> dict[str, Any]:
    errors: list[float] = []
    for holdout in range(matrix.shape[0]):
        train = np.delete(matrix, holdout, axis=0)
        mean = train.mean(axis=0, keepdims=True)
        centered_train = train - mean
        if centered_train.shape[0] <= 1 or np.linalg.norm(matrix[holdout]) <= 0.0:
            errors.append(0.0)
            continue
        _, _, vh = np.linalg.svd(centered_train, full_matrices=False)
        basis = vh[: max(1, min(rank, vh.shape[0]))]
        target = matrix[holdout : holdout + 1] - mean
        reconstruction = mean + (target @ basis.T) @ basis
        numerator = float(np.linalg.norm(matrix[holdout : holdout + 1] - reconstruction))
        denominator = float(np.linalg.norm(matrix[holdout : holdout + 1]))
        errors.append(numerator / max(denominator, 1e-12))
    return {
        "relative_errors": errors,
        "mean_relative_error": float(np.mean(errors)) if errors else 0.0,
        "max_relative_error": float(np.max(errors)) if errors else 0.0,
    }


def stat_summary(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
    }


def values_for_pairs(matrix: np.ndarray, pairs: Iterable[tuple[int, int]]) -> np.ndarray:
    return np.asarray([matrix[i, j] for i, j in pairs], dtype=np.float64)


def matrix_to_nested_dict(matrix: np.ndarray, groups: list[GroupBasis]) -> dict[str, dict[str, float]]:
    return {
        source.group_id: {target.group_id: float(matrix[i, j]) for j, target in enumerate(groups)}
        for i, source in enumerate(groups)
    }


def local_basis_decision(top2: np.ndarray, effective: np.ndarray) -> str:
    if top2.size == 0:
        return "not_answered"
    if float(top2.mean()) >= 0.9 and float(effective.mean()) <= 3.0:
        return "yes; per-group responses are low-dimensional under the current rank criteria"
    return "unclear_or_no; inspect action/contact stability and local action magnitude"


def cross_group_decision(metadata_summary: list[dict[str, Any]]) -> str:
    useful = [row for row in metadata_summary if row.get("pair_count")]
    if not useful:
        return "not_answered"
    best_error = min(float(row["cross_reconstruction_error_mean"]) for row in useful)
    if best_error < 0.1:
        return "partly_shared; at least one metadata comparison reconstructs well"
    return "condition_dependent; cross-group reconstruction is not yet strong"


def shared_basis_decision(shared_basis: dict[str, Any]) -> str:
    aggregate = shared_basis.get("aggregate", {}) if isinstance(shared_basis, dict) else {}
    if not aggregate:
        return "not_answered"
    local = float(aggregate.get("local_group_basis_error", {}).get("mean", 0.0))
    pooled = float(aggregate.get("pooled_shared_basis_error", {}).get("mean", 0.0))
    loo = float(aggregate.get("leave_one_group_out_shared_basis_error", {}).get("mean", 0.0))
    nearest = float(aggregate.get("nearest_group_basis_error", {}).get("mean", 0.0))
    if loo <= max(0.15, local * 2.0):
        return "mostly_shared; leave-one-group-out shared basis reconstructs close to group-local basis"
    if nearest < loo and nearest <= max(0.25, local * 3.0):
        return "locally_or_conditionally_shared; nearest group is better than one global held-out shared basis"
    if pooled < loo:
        return "partly_shared_but_target_inclusion_matters; pooled basis improves when target group is included"
    return "condition_specific; held-out shared basis is much worse than group-local expression"


def boundary_decision(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "not_answered; no matched contact/material with different boundary"
    normalized_errors = np.asarray([float(row["normalized_cross_reconstruction_error_mean"]) for row in rows], dtype=np.float64)
    normalized_projection = np.asarray([float(row["normalized_projection_similarity"]) for row in rows], dtype=np.float64)
    if float(normalized_errors.mean()) < 0.1 and float(normalized_projection.mean()) > 0.9:
        return "mostly_scale_change_under_current_data"
    return "pattern_or_basis_changes_present; condition NJF on boundary"


def material_decision(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "not_answered; no matched contact with different material"
    normalized_errors = np.asarray([float(row["normalized_cross_reconstruction_error_mean"]) for row in rows], dtype=np.float64)
    normalized_projection = np.asarray([float(row["normalized_projection_similarity"]) for row in rows], dtype=np.float64)
    if float(normalized_errors.mean()) < 0.1 and float(normalized_projection.mean()) > 0.9:
        return "mostly_scale_change_under_current_data"
    return "pattern_or_basis_changes_present; condition NJF on material"


def interpret_material_pattern(normalized_error: float, normalized_projection: float) -> str:
    if normalized_error < 0.1 and normalized_projection > 0.9:
        return "scale_only_like"
    if normalized_error < 0.25 and normalized_projection > 0.75:
        return "mostly_scale_with_some_pattern_change"
    return "pattern_changes"




def interpret_boundary_pattern(normalized_error: float, normalized_projection: float) -> str:
    if normalized_error < 0.1 and normalized_projection > 0.9:
        return "scale_only_like"
    if normalized_error < 0.25 and normalized_projection > 0.75:
        return "mostly_scale_with_some_pattern_change"
    return "pattern_changes"


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


def write_matrix_csv(path: Path, matrix: np.ndarray, groups: list[GroupBasis]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["basis_from/reconstruct"] + [group.group_id for group in groups])
        for i, group in enumerate(groups):
            writer.writerow([group.group_id] + [float(matrix[i, j]) for j in range(len(groups))])


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


if __name__ == "__main__":
    raise SystemExit(main())
