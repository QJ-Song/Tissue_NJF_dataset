#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "tissue_dataset_v0" / "outputs"
DEFAULT_RUNNER = REPO_ROOT / "scripts" / "run_sofa_python.sh"


@dataclass(frozen=True)
class DatasetPaths:
    output_root: Path
    mode_b: Path
    rollout: Path
    single_large: Path
    mode_b_basis_v2: Path


@dataclass(frozen=True)
class Step:
    name: str
    stage: str
    argv: tuple[str, ...]
    skip_if_exists: Path | None = None
    branch: str = "default"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the standard liver surface controlled SOFA dataset v1 pipeline."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=("generate", "validate", "analyze", "all"),
        default=("all",),
        help="Pipeline stages to run. Default: all.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Regenerate outputs instead of reusing existing data.")
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Skip generation steps whose target dataset directory already exists.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--include-basis-v2",
        action="store_true",
        help="Append the experimental basis_v2 response-basis factorial branch to the standard pipeline.",
    )
    parser.add_argument(
        "--only-basis-v2",
        action="store_true",
        help="Run only the basis_v2 branch. Implies --include-basis-v2.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stages = set(args.stages)
    if "all" in stages:
        stages = {"generate", "validate", "analyze"}
    include_basis_v2 = bool(args.include_basis_v2 or args.only_basis_v2)
    paths = build_paths(args.output_root)
    steps = build_steps(paths, runner=args.runner, overwrite=args.overwrite, include_basis_v2=include_basis_v2)
    if args.only_basis_v2:
        steps = [step for step in steps if step.branch == "basis_v2"]
    selected = [step for step in steps if step.stage in stages]
    if not selected:
        print("No steps selected.", file=sys.stderr)
        return 2

    print("Liver surface controlled SOFA dataset v1")
    print(f"output_root={paths.output_root}")
    print(f"mode_b={paths.mode_b}")
    print(f"rollout={paths.rollout}")
    print(f"single_large={paths.single_large}")
    if include_basis_v2:
        print(f"mode_b_basis_v2={paths.mode_b_basis_v2}")
    print(
        f"stages={sorted(stages)} dry_run={args.dry_run} "
        f"reuse_existing={args.reuse_existing} include_basis_v2={include_basis_v2} "
        f"only_basis_v2={args.only_basis_v2}"
    )
    for step in selected:
        if should_skip(step, reuse_existing=args.reuse_existing, overwrite=args.overwrite):
            print(f"[skip] {step.name}: {step.skip_if_exists}")
            continue
        print(f"[run] {step.name}")
        print("      " + shell_join(step.argv))
        if args.dry_run:
            continue
        subprocess.run(step.argv, cwd=REPO_ROOT, check=True)
    return 0


def build_paths(output_root: Path) -> DatasetPaths:
    output_root = output_root.resolve()
    return DatasetPaths(
        output_root=output_root,
        mode_b=output_root / "liver_surface_mode_b_factorial_3x3_v1",
        rollout=output_root / "liver_surface_mode_c_rollout_tilt_x_3x3_v1",
        single_large=output_root / "liver_surface_single_large_tilt_x_3x3_11p7_v1",
        mode_b_basis_v2=output_root / "liver_surface_mode_b_factorial_3x3_basis_v2_v1",
    )


def build_steps(paths: DatasetPaths, *, runner: Path, overwrite: bool, include_basis_v2: bool = False) -> list[Step]:
    runner_s = rel_or_abs(runner)
    mode_b_samples = paths.mode_b / "samples"
    analysis = paths.rollout / "analysis"
    overwrite_arg = ("--overwrite",) if overwrite else ()
    steps = [
        Step(
            name="generate Mode B 3x3 response-basis dataset",
            stage="generate",
            skip_if_exists=paths.mode_b,
            argv=(
                runner_s,
                "scripts/generate_liver_surface_sample.py",
                *overwrite_arg,
                "--layout",
                "grouped",
                "--contact-set",
                "top_three",
                "--material-set",
                "young_three",
                "--direction-set",
                "basis_v1",
                "--output",
                str(paths.mode_b),
                "--sample-id",
                "1",
                "--depths-mm",
                "1.17",
                "2.35",
                "4.70",
                "--preload-steps",
                "0",
            ),
        ),
        Step(
            name="generate Mode C tilt-x 3x3 rollout dataset",
            stage="generate",
            skip_if_exists=paths.rollout,
            argv=(
                runner_s,
                "scripts/generate_liver_surface_rollout.py",
                *overwrite_arg,
                "--output",
                str(paths.rollout),
                "--steps",
                "10",
                "--step-size-mm",
                "1.17",
                "--contact-set",
                "top_three",
                "--material-set",
                "young_three",
                "--direction-set",
                "basis_v1",
                "--direction-id",
                "tilt_pos_x",
                "--preload-steps",
                "0",
                "--action-substeps",
                "40",
                "--settle-steps-per-step",
                "20",
            ),
        ),
        Step(
            name="generate matched tilt-x 3x3 single-large dataset",
            stage="generate",
            skip_if_exists=paths.single_large,
            argv=(
                runner_s,
                "scripts/generate_liver_surface_sample.py",
                *overwrite_arg,
                "--output",
                str(paths.single_large),
                "--sample-id",
                "1",
                "--layout",
                "flat",
                "--contact-set",
                "top_three",
                "--material-set",
                "young_three",
                "--direction-set",
                "basis_v1",
                "--direction-id",
                "tilt_pos_x",
                "--depth-mm",
                "11.7",
                "--preload-steps",
                "0",
                "--action-steps",
                "400",
                "--settle-steps",
                "200",
            ),
        ),
        Step(
            name="validate Mode B sample artifacts",
            stage="validate",
            argv=bulk_validate_step(runner_s, mode_b_samples, expected=162),
        ),
        Step(
            name="read Mode B samples",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/read_dataset_smoke.py",
                str(mode_b_samples),
                "--require",
                "tool_pose_0",
                "--require",
                "tool_pose_1",
                "--require",
                "tool_geometry",
                "--require",
                "contact_summary",
                "--require",
                "boundary_mask",
                "--require",
                "fixed_node_indices",
                "--require",
                "free_node_indices",
                "--require",
                "boundary",
                "--require",
                "solver_summary",
            ),
        ),
        Step(
            name="check Mode B contact",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_contact.py",
                str(mode_b_samples),
                "--min-samples",
                "162",
                "--max-min-gap-mm",
                "2.0",
                "--max-penetration-mm",
                "2.0",
            ),
        ),
        Step(
            name="check Mode B tool directions",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_tool_direction.py",
                str(mode_b_samples),
                "--min-samples",
                "162",
                "--max-angle-error-deg",
                "0.2",
                "--min-motion-mm",
                "1.0",
                "--require-nonvertical",
                "--min-max-tilt-deg",
                "5.0",
            ),
        ),
        Step(
            name="check Mode B boundary/solver metadata",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_boundary_solver.py",
                str(mode_b_samples),
                "--min-samples",
                "162",
            ),
        ),
        Step(
            name="read Mode C rollout dataset",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/read_njf_dataset.py",
                str(paths.rollout),
                "--require-mode",
                "rollout_trajectory",
                "--min-trajectories",
                "9",
            ),
        ),
        Step(
            name="validate Mode C rollout trajectories",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_rollout_trajectories.py",
                str(paths.rollout),
                "--min-steps",
                "10",
                "--output",
                str(analysis / "rollout_drift_summary.json"),
                "--csv-dir",
                str(analysis),
            ),
        ),
        Step(
            name="validate matched single-large samples",
            stage="validate",
            argv=bulk_validate_step(runner_s, paths.single_large, expected=9),
        ),
        Step(
            name="check matched single-large contact",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_contact.py",
                str(paths.single_large),
                "--min-samples",
                "9",
                "--max-min-gap-mm",
                "2.0",
                "--max-penetration-mm",
                "2.0",
            ),
        ),
        Step(
            name="check matched single-large tool direction",
            stage="validate",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_tool_direction.py",
                str(paths.single_large),
                "--min-samples",
                "9",
                "--max-angle-error-deg",
                "0.2",
                "--min-motion-mm",
                "10.0",
                "--require-nonvertical",
                "--min-max-tilt-deg",
                "5.0",
            ),
        ),
        Step(
            name="analyze Mode B per-group basis",
            stage="analyze",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_response_basis.py",
                str(paths.mode_b),
                "--output",
                str(paths.mode_b / "analysis" / "response_basis_summary.json"),
            ),
        ),
        Step(
            name="analyze Mode B cross-group basis",
            stage="analyze",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_basis_across_groups.py",
                str(paths.mode_b),
                "--rank",
                "2",
                "--output-dir",
                str(paths.mode_b / "analysis" / "basis_across_groups"),
            ),
        ),
        Step(
            name="analyze rollout vs matched single-large",
            stage="analyze",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_rollout_trajectories.py",
                str(paths.rollout),
                "--min-steps",
                "10",
                "--single-step-sample",
                str(paths.single_large),
                "--output",
                str(analysis / "rollout_vs_single_large_summary.json"),
                "--csv-dir",
                str(analysis),
            ),
        ),
        Step(
            name="analyze rollout basis projection",
            stage="analyze",
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_rollout_basis_projection.py",
                "--rollout-dataset",
                str(paths.rollout),
                "--basis-dataset",
                str(paths.mode_b),
                "--ranks",
                "2",
                "3",
                "4",
                "--output",
                str(analysis / "rollout_basis_projection_summary.json"),
                "--csv-output",
                str(analysis / "rollout_basis_projection_metrics.csv"),
                "--report-output",
                str(analysis / "rollout_basis_projection_report.md"),
            ),
        ),
    ]
    if include_basis_v2:
        steps.extend(build_basis_v2_steps(paths, runner_s=runner_s, overwrite_arg=overwrite_arg))
    return steps


def build_basis_v2_steps(paths: DatasetPaths, *, runner_s: str, overwrite_arg: tuple[str, ...]) -> list[Step]:
    samples = paths.mode_b_basis_v2 / "samples"
    analysis = paths.mode_b_basis_v2 / "analysis"
    branch = "basis_v2"
    return [
        Step(
            name="generate Mode B basis_v2 3x3 response-basis dataset",
            stage="generate",
            skip_if_exists=paths.mode_b_basis_v2,
            branch=branch,
            argv=(
                runner_s,
                "scripts/generate_liver_surface_sample.py",
                *overwrite_arg,
                "--layout",
                "grouped",
                "--contact-set",
                "top_three",
                "--material-set",
                "young_three",
                "--direction-set",
                "basis_v2",
                "--output",
                str(paths.mode_b_basis_v2),
                "--sample-id",
                "1",
                "--depths-mm",
                "1.17",
                "--preload-steps",
                "0",
                "--settle-steps",
                "20",
            ),
        ),
        Step(
            name="validate Mode B basis_v2 sample artifacts",
            stage="validate",
            branch=branch,
            argv=bulk_validate_step(runner_s, samples, expected=153),
        ),
        Step(
            name="read Mode B basis_v2 samples",
            stage="validate",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/read_dataset_smoke.py",
                str(samples),
                "--require",
                "tool_pose_0",
                "--require",
                "tool_pose_1",
                "--require",
                "tool_geometry",
                "--require",
                "contact_summary",
                "--require",
                "boundary_mask",
                "--require",
                "fixed_node_indices",
                "--require",
                "free_node_indices",
                "--require",
                "boundary",
                "--require",
                "solver_summary",
            ),
        ),
        Step(
            name="check Mode B basis_v2 contact",
            stage="validate",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_contact.py",
                str(samples),
                "--min-samples",
                "153",
                "--max-min-gap-mm",
                "2.0",
                "--max-penetration-mm",
                "2.0",
            ),
        ),
        Step(
            name="check Mode B basis_v2 tool directions",
            stage="validate",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_tool_direction.py",
                str(samples),
                "--min-samples",
                "153",
                "--max-angle-error-deg",
                "0.3",
                "--min-motion-mm",
                "1.0",
                "--require-nonvertical",
                "--min-max-tilt-deg",
                "55.0",
            ),
        ),
        Step(
            name="check Mode B basis_v2 boundary/solver metadata",
            stage="validate",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/check_boundary_solver.py",
                str(samples),
                "--min-samples",
                "153",
            ),
        ),
        Step(
            name="analyze Mode B basis_v2 per-group basis",
            stage="analyze",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_response_basis.py",
                str(paths.mode_b_basis_v2),
                "--rank",
                "4",
                "--output",
                str(analysis / "response_basis_summary.json"),
            ),
        ),
        Step(
            name="analyze Mode B basis_v2 cross-group basis rank 2",
            stage="analyze",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_basis_across_groups.py",
                str(paths.mode_b_basis_v2),
                "--rank",
                "2",
                "--output-dir",
                str(analysis / "basis_across_groups_rank2"),
            ),
        ),
        Step(
            name="analyze Mode B basis_v2 cross-group basis rank 4",
            stage="analyze",
            branch=branch,
            argv=(
                runner_s,
                "tissue_dataset_v0/scripts/analyze_basis_across_groups.py",
                str(paths.mode_b_basis_v2),
                "--rank",
                "4",
                "--output-dir",
                str(analysis / "basis_across_groups_rank4"),
            ),
        ),
    ]


def bulk_validate_step(runner: str, sample_root: Path, *, expected: int) -> tuple[str, ...]:
    code = (
        "from pathlib import Path; "
        "from tissue_dataset_v0.validation import build_default_validator; "
        f"root=Path({str(sample_root)!r}); "
        "v=build_default_validator(); "
        "reports=[v.validate(p) for p in sorted(root.glob('sample_*'))]; "
        "errors=sum(r.error_count for r in reports); "
        "warnings=sum(r.warning_count for r in reports); "
        f"print(f'Validation samples={{len(reports)}} errors={{errors}} warnings={{warnings}} expected={expected}'); "
        f"raise SystemExit(0 if errors==0 and len(reports)>={expected} else 1)"
    )
    return (runner, "-c", code)


def should_skip(step: Step, *, reuse_existing: bool, overwrite: bool) -> bool:
    return bool(reuse_existing and not overwrite and step.stage == "generate" and step.skip_if_exists and step.skip_if_exists.exists())


def rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def shell_join(argv: tuple[str, ...]) -> str:
    return " ".join(quote(arg) for arg in argv)


def quote(value: str) -> str:
    if not value:
        return "''"
    if all(ch.isalnum() or ch in "-_./:=," for ch in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
