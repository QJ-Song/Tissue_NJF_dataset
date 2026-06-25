#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@dataclass(frozen=True)
class SampleStats:
    sample_dir: Path
    sample_id: str
    material: dict[str, Any]
    meta: dict[str, Any]
    action: np.ndarray
    contact_point: np.ndarray
    vertex_count: int
    max_displacement_mm: float
    max_downward_z_mm: float
    max_upward_z_mm: float
    max_displacement_contact_distance_mm: float
    geometry: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_dir": str(self.sample_dir),
            "sample_id": self.sample_id,
            "vertex_count": self.vertex_count,
            "action": self.action.astype(float).tolist(),
            "contact_point": self.contact_point.astype(float).tolist(),
            "material": self.material,
            "geometry": self.geometry,
            "tissue_type": self.meta.get("tissue_type"),
            "sofa_tissue_shape": self.meta.get("extra", {}).get("sofa_tissue_shape"),
            "max_displacement_mm": self.max_displacement_mm,
            "max_downward_z_mm": self.max_downward_z_mm,
            "max_upward_z_mm": self.max_upward_z_mm,
            "max_displacement_contact_distance_mm": self.max_displacement_contact_distance_mm,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage A/B sanity checks over generated tissue samples.")
    parser.add_argument("dataset_or_samples", nargs="+", type=Path, help="Dataset root(s) or sample_* directory path(s).")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--min-samples", type=int, default=2)
    parser.add_argument("--min-max-displacement-mm", type=float, default=0.3)
    parser.add_argument("--max-max-displacement-mm", type=float, default=6.0)
    parser.add_argument("--max-downward-z-mm", type=float, default=5.0)
    parser.add_argument("--max-contact-distance-mm", type=float, default=None)
    parser.add_argument("--min-contact-spread-mm", type=float, default=1.0)
    parser.add_argument("--min-depth-spread-mm", type=float, default=0.5)
    parser.add_argument("--material-mode", choices=("fixed", "varying"), default="fixed")
    parser.add_argument("--geometry-mode", choices=("fixed", "varying"), default="fixed")
    parser.add_argument("--direction-mode", choices=("fixed", "varying"), default="fixed")
    parser.add_argument("--max-tilt-deg", type=float, default=0.0)
    parser.add_argument("--min-direction-spread-deg", type=float, default=5.0)
    parser.add_argument("--min-youngs-spread-pa", type=float, default=1000.0)
    parser.add_argument("--min-poisson-spread", type=float, default=0.005)
    parser.add_argument("--min-damping-spread", type=float, default=0.1)
    parser.add_argument("--min-size-x-spread-mm", type=float, default=5.0)
    parser.add_argument("--min-size-y-spread-mm", type=float, default=3.0)
    parser.add_argument("--min-thickness-spread-mm", type=float, default=1.0)
    parser.add_argument("--geometry-tol", type=float, default=1e-8)
    parser.add_argument("--material-tol", type=float, default=1e-8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sample_dirs = discover_samples(args.dataset_or_samples)
    issues: list[dict[str, str]] = []
    if len(sample_dirs) < args.min_samples:
        issues.append(
            {
                "level": "error",
                "message": f"Expected at least {args.min_samples} samples, found {len(sample_dirs)}.",
            }
        )

    stats = [load_stats(sample_dir) for sample_dir in sample_dirs]
    if args.material_mode == "fixed":
        issues.extend(check_fixed_material(stats, tol=args.material_tol))
    else:
        issues.extend(
            check_material_variation(
                stats,
                min_youngs_spread_pa=args.min_youngs_spread_pa,
                min_poisson_spread=args.min_poisson_spread,
                min_damping_spread=args.min_damping_spread,
            )
        )
    if args.geometry_mode == "fixed":
        issues.extend(check_fixed_geometry(stats, tol=args.geometry_tol))
    else:
        issues.extend(
            check_geometry_variation(
                stats,
                min_size_x_spread_mm=args.min_size_x_spread_mm,
                min_size_y_spread_mm=args.min_size_y_spread_mm,
                min_thickness_spread_mm=args.min_thickness_spread_mm,
            )
        )
    issues.extend(check_fixed_topology(stats))
    issues.extend(check_contact_points_inside_geometry(stats))
    issues.extend(check_action_directions(
        stats,
        direction_mode=args.direction_mode,
        max_tilt_deg=args.max_tilt_deg,
        min_direction_spread_deg=args.min_direction_spread_deg,
    ))
    issues.extend(check_action_variation(stats, min_contact_spread_mm=args.min_contact_spread_mm, min_depth_spread_mm=args.min_depth_spread_mm))
    issues.extend(
        check_displacement_range(
            stats,
            min_max_displacement_mm=args.min_max_displacement_mm,
            max_max_displacement_mm=args.max_max_displacement_mm,
            max_downward_z_mm=args.max_downward_z_mm,
        )
    )
    issues.extend(check_locality(stats, max_contact_distance_mm=args.max_contact_distance_mm))

    valid = not any(issue["level"] == "error" for issue in issues)
    payload = {
        "valid": valid,
        "sample_count": len(sample_dirs),
        "error_count": sum(1 for issue in issues if issue["level"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["level"] == "warning"),
        "material_mode": args.material_mode,
        "geometry_mode": args.geometry_mode,
        "direction_mode": args.direction_mode,
        "issues": issues,
        "samples": [item.to_dict() for item in stats],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if valid else 1


def discover_samples(paths: list[Path]) -> list[Path]:
    sample_dirs: list[Path] = []
    for path in paths:
        if path.name.startswith("sample_") and path.is_dir():
            sample_dirs.append(path)
            continue
        if path.is_dir():
            sample_dirs.extend(sorted(child for child in path.iterdir() if child.is_dir() and child.name.startswith("sample_")))
    return sorted(set(sample_dirs))


def load_stats(sample_dir: Path) -> SampleStats:
    vertices_0 = np.load(sample_dir / "vertices_0.npy")
    displacement = np.load(sample_dir / "displacement.npy")
    action = np.load(sample_dir / "action.npy")
    contact_point = np.load(sample_dir / "contact_point.npy")
    material = load_json(sample_dir / "material.json")
    meta = load_json(sample_dir / "meta.json")
    magnitudes = np.linalg.norm(displacement, axis=1)
    max_index = int(magnitudes.argmax())
    distance_xy = np.linalg.norm(vertices_0[max_index, :2] - contact_point[:2])
    return SampleStats(
        sample_dir=sample_dir,
        sample_id=sample_dir.name,
        material=material,
        meta=meta,
        action=action,
        contact_point=contact_point,
        vertex_count=int(vertices_0.shape[0]),
        max_displacement_mm=float(magnitudes.max() * 1000.0),
        max_downward_z_mm=float(abs(min(float(displacement[:, 2].min()), 0.0)) * 1000.0),
        max_upward_z_mm=float(max(float(displacement[:, 2].max()), 0.0) * 1000.0),
        max_displacement_contact_distance_mm=float(distance_xy * 1000.0),
        geometry=dict(meta.get("geometry", {})) if isinstance(meta.get("geometry", {}), dict) else {},
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def check_fixed_material(stats: list[SampleStats], *, tol: float) -> list[dict[str, str]]:
    if not stats:
        return []
    issues: list[dict[str, str]] = []
    reference = material_signature(stats[0].material)
    for item in stats[1:]:
        current = material_signature(item.material)
        if not signatures_close(reference, current, tol=tol):
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": "Material differs from the first sample; Stage A should keep material fixed.",
                }
            )
    return issues


def check_material_variation(
    stats: list[SampleStats],
    *,
    min_youngs_spread_pa: float,
    min_poisson_spread: float,
    min_damping_spread: float,
) -> list[dict[str, str]]:
    if len(stats) < 2:
        return []
    values = {
        "youngs_modulus": np.asarray([float(item.material.get("youngs_modulus", 0.0)) for item in stats], dtype=np.float64),
        "poisson_ratio": np.asarray([float(item.material.get("poisson_ratio", 0.0)) for item in stats], dtype=np.float64),
        "damping": np.asarray([float(item.material.get("damping", 0.0)) for item in stats], dtype=np.float64),
    }
    thresholds = {
        "youngs_modulus": min_youngs_spread_pa,
        "poisson_ratio": min_poisson_spread,
        "damping": min_damping_spread,
    }
    units = {
        "youngs_modulus": "Pa",
        "poisson_ratio": "",
        "damping": "",
    }
    issues: list[dict[str, str]] = []
    for key, array in values.items():
        spread = float(np.ptp(array))
        threshold = thresholds[key]
        if spread < threshold:
            unit = f" {units[key]}" if units[key] else ""
            issues.append(
                {
                    "level": "error",
                    "message": f"Material {key} spread is {spread:.6g}{unit}, below {threshold:.6g}{unit}.",
                }
            )
    return issues



def check_fixed_geometry(stats: list[SampleStats], *, tol: float) -> list[dict[str, str]]:
    if not stats:
        return []
    issues: list[dict[str, str]] = []
    reference = geometry_signature(stats[0])
    for item in stats[1:]:
        current = geometry_signature(item)
        if not signatures_close(reference, current, tol=tol):
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": "Geometry differs from the first sample while geometry-mode=fixed.",
                }
            )
    return issues


def check_geometry_variation(
    stats: list[SampleStats],
    *,
    min_size_x_spread_mm: float,
    min_size_y_spread_mm: float,
    min_thickness_spread_mm: float,
) -> list[dict[str, str]]:
    if len(stats) < 2:
        return []
    values = {
        "size_x": np.asarray([float(geometry_signature(item).get("size_x", 0.0)) for item in stats], dtype=np.float64),
        "size_y": np.asarray([float(geometry_signature(item).get("size_y", 0.0)) for item in stats], dtype=np.float64),
        "thickness": np.asarray([float(geometry_signature(item).get("thickness", 0.0)) for item in stats], dtype=np.float64),
    }
    thresholds = {
        "size_x": min_size_x_spread_mm,
        "size_y": min_size_y_spread_mm,
        "thickness": min_thickness_spread_mm,
    }
    issues: list[dict[str, str]] = []
    for key, array in values.items():
        spread_mm = float(np.ptp(array) * 1000.0)
        threshold = thresholds[key]
        if spread_mm < threshold:
            issues.append(
                {
                    "level": "error",
                    "message": f"Geometry {key} spread is {spread_mm:.3f} mm, below {threshold:.3f} mm.",
                }
            )
    return issues


def check_fixed_topology(stats: list[SampleStats]) -> list[dict[str, str]]:
    if not stats:
        return []
    issues: list[dict[str, str]] = []
    reference = topology_signature(stats[0])
    for item in stats[1:]:
        if topology_signature(item) != reference:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": "Topology differs across samples; Stage C v1 expects fixed topology.",
                }
            )
    return issues


def check_contact_points_inside_geometry(stats: list[SampleStats]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in stats:
        geometry = geometry_signature(item)
        if not geometry:
            continue
        if geometry.get("size_x") is None or geometry.get("size_y") is None:
            continue
        half_x = float(geometry.get("size_x", 0.0)) * 0.5
        half_y = float(geometry.get("size_y", 0.0)) * 0.5
        x = float(item.contact_point[0])
        y = float(item.contact_point[1])
        if abs(x) > half_x or abs(y) > half_y:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": "Contact point is outside the sampled geometry bounds.",
                }
            )
    return issues


def geometry_signature(item: SampleStats) -> dict[str, Any]:
    if item.geometry:
        return {
            "size_x": item.geometry.get("size_x"),
            "size_y": item.geometry.get("size_y"),
            "thickness": item.geometry.get("thickness"),
            "nx": item.geometry.get("nx"),
            "ny": item.geometry.get("ny"),
            "layers": item.geometry.get("layers"),
        }
    return {
        "nx": None,
        "ny": None,
        "layers": None,
    }


def topology_signature(item: SampleStats) -> tuple[Any, ...]:
    geometry = geometry_signature(item)
    return (item.vertex_count, geometry.get("nx"), geometry.get("ny"), geometry.get("layers"))

def material_signature(material: dict[str, Any]) -> dict[str, Any]:
    return {
        "youngs_modulus": material.get("youngs_modulus"),
        "poisson_ratio": material.get("poisson_ratio"),
        "density": material.get("density"),
        "damping": material.get("damping"),
        "boundary_condition": material.get("boundary_condition"),
    }


def signatures_close(left: dict[str, Any], right: dict[str, Any], *, tol: float) -> bool:
    for key, left_value in left.items():
        right_value = right.get(key)
        if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
            if not math.isclose(float(left_value), float(right_value), rel_tol=tol, abs_tol=tol):
                return False
        elif left_value != right_value:
            return False
    return True


def check_action_directions(
    stats: list[SampleStats],
    *,
    direction_mode: str,
    max_tilt_deg: float,
    min_direction_spread_deg: float,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    directions: list[np.ndarray] = []
    for item in stats:
        if item.action.shape[0] < 5:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": "Action vector must include direction slots action[2:5].",
                }
            )
            continue
        raw_direction = np.asarray(item.action[2:5], dtype=np.float64)
        norm = float(np.linalg.norm(raw_direction))
        if not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": f"Action direction norm is {norm:.6f}, expected 1.0.",
                }
            )
        if norm <= 1e-12:
            continue
        direction = raw_direction / norm
        directions.append(direction)
        if float(direction[2]) >= 0.0:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": "Action direction must point downward with dir_z < 0.",
                }
            )
        tilt_deg = direction_tilt_deg(direction)
        if tilt_deg > max_tilt_deg + 1e-3:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": f"Action tilt is {tilt_deg:.3f} deg, above {max_tilt_deg:.3f} deg.",
                }
            )
    if len(directions) < 2:
        return issues

    spread_deg = max_direction_spread_deg(directions)
    if direction_mode == "fixed":
        if spread_deg > 0.1:
            issues.append(
                {
                    "level": "error",
                    "message": f"Action direction spread is {spread_deg:.3f} deg while direction-mode=fixed.",
                }
            )
    elif spread_deg < min_direction_spread_deg:
        issues.append(
            {
                "level": "error",
                "message": f"Action direction spread is {spread_deg:.3f} deg, below {min_direction_spread_deg:.3f} deg.",
            }
        )
    return issues


def direction_tilt_deg(direction: np.ndarray) -> float:
    cos_theta = float(np.clip(-direction[2], -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_theta)))


def max_direction_spread_deg(directions: list[np.ndarray]) -> float:
    max_spread = 0.0
    for index, left in enumerate(directions):
        for right in directions[index + 1 :]:
            dot = float(np.clip(np.dot(left, right), -1.0, 1.0))
            max_spread = max(max_spread, float(np.degrees(np.arccos(dot))))
    return max_spread


def check_action_variation(stats: list[SampleStats], *, min_contact_spread_mm: float, min_depth_spread_mm: float) -> list[dict[str, str]]:
    if len(stats) < 2:
        return []
    contacts = np.asarray([item.contact_point[:2] for item in stats], dtype=np.float64)
    depths = np.asarray([item.action[5] if item.action.shape[0] >= 6 else 0.0 for item in stats], dtype=np.float64)
    contact_spread_mm = float(np.ptp(contacts, axis=0).max() * 1000.0)
    depth_spread_mm = float(np.ptp(depths) * 1000.0)
    issues: list[dict[str, str]] = []
    if contact_spread_mm < min_contact_spread_mm:
        issues.append(
            {
                "level": "error",
                "message": f"Contact point spread is {contact_spread_mm:.3f} mm, below {min_contact_spread_mm:.3f} mm.",
            }
        )
    if depth_spread_mm < min_depth_spread_mm:
        issues.append(
            {
                "level": "error",
                "message": f"Press depth spread is {depth_spread_mm:.3f} mm, below {min_depth_spread_mm:.3f} mm.",
            }
        )
    return issues


def check_displacement_range(
    stats: list[SampleStats],
    *,
    min_max_displacement_mm: float,
    max_max_displacement_mm: float,
    max_downward_z_mm: float,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in stats:
        if item.max_displacement_mm < min_max_displacement_mm:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": f"Max displacement is {item.max_displacement_mm:.3f} mm, below {min_max_displacement_mm:.3f} mm.",
                }
            )
        if item.max_displacement_mm > max_max_displacement_mm:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": f"Max displacement is {item.max_displacement_mm:.3f} mm, above {max_max_displacement_mm:.3f} mm.",
                }
            )
        if item.max_downward_z_mm > max_downward_z_mm:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": f"Max downward z displacement is {item.max_downward_z_mm:.3f} mm, above {max_downward_z_mm:.3f} mm.",
                }
            )
    return issues


def check_locality(stats: list[SampleStats], *, max_contact_distance_mm: float | None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in stats:
        limit = max_contact_distance_mm
        if limit is None:
            probe_radius = item.meta.get("extra", {}).get("sofa_probe_radius")
            if isinstance(probe_radius, (int, float)):
                limit = max(30.0, float(probe_radius) * 1000.0 * 1.25)
            else:
                limit = 30.0
        if item.max_displacement_contact_distance_mm > limit:
            issues.append(
                {
                    "level": "error",
                    "sample": item.sample_id,
                    "message": (
                        "Max displacement is "
                        f"{item.max_displacement_contact_distance_mm:.3f} mm from contact point, above {limit:.3f} mm."
                    ),
                }
            )
    return issues


def print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload["valid"] else "FAIL"
    print(f"Stage sanity check: {status}")
    print(
        f"samples={payload['sample_count']} material_mode={payload['material_mode']} "
        f"geometry_mode={payload['geometry_mode']} direction_mode={payload['direction_mode']} "
        f"errors={payload['error_count']} warnings={payload['warning_count']}"
    )
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            sample = f" {issue['sample']}:" if "sample" in issue else ""
            print(f"- {issue['level'].upper()}{sample} {issue['message']}")
    print("Samples:")
    for item in payload["samples"]:
        action = item["action"]
        contact = item["contact_point"]
        direction = np.asarray(action[2:5], dtype=np.float64) if len(action) >= 5 else np.asarray([0.0, 0.0, -1.0])
        norm = float(np.linalg.norm(direction))
        if norm > 1e-12:
            direction = direction / norm
        tilt_deg = direction_tilt_deg(direction)
        print(
            f"- {item['sample_id']}: vertices={item['vertex_count']} "
            f"contact=({contact[0]:.4f}, {contact[1]:.4f}) depth={action[5] * 1000.0:.2f} mm "
            f"dir=({direction[0]:.3f}, {direction[1]:.3f}, {direction[2]:.3f}) tilt={tilt_deg:.1f} deg "
            f"geom=({item['geometry'].get('size_x')}, {item['geometry'].get('size_y')}, {item['geometry'].get('thickness')}) "
            f"E={item['material'].get('youngs_modulus')} nu={item['material'].get('poisson_ratio')} "
            f"damping={item['material'].get('damping')} "
            f"max={item['max_displacement_mm']:.2f} mm down={item['max_downward_z_mm']:.2f} mm "
            f"dist={item['max_displacement_contact_distance_mm']:.2f} mm"
        )


if __name__ == "__main__":
    raise SystemExit(main())
