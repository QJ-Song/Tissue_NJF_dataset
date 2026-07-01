# Task: Basis v2 Rollout Spike

## Goal

Generate and analyze a Mode C rollout dataset using the broader `basis_v2` single-contact action family before moving to coefficient prediction or NJF feasibility work.

## Implementation

`scripts/generate_liver_surface_rollout.py` now supports:

```text
--direction-set basis_v2
```

The rollout generator imports the same approach/action separation used by `scripts/generate_liver_surface_sample.py`:

```text
approach_direction = normal downward direction
action_direction = saved action direction
probe_approach_policy = normal_approach_for_basis_v2
```

This prevents 40-60 degree shear-like directions from also being used as the initial probe approach on the curved liver surface.

## Smoke Dataset

```text
root: tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_smoke
contact_set: top_center
material_set: single
direction_set: basis_v2
direction_id: shear60_pos_x
steps: 3
step_size_mm: 1.17
```

Checks run:

```bash
python3 -m py_compile scripts/generate_liver_surface_rollout.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_njf_dataset.py tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_smoke --require-mode rollout_trajectory --min-trajectories 1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py --dataset tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_smoke --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_smoke/analysis/rollout_drift_summary.json
```

Result: PASS. Contact was active for all `3/3` steps. Final max deformation was about `2.393 mm`. Fixed-first-step final relative L2 error was about `0.317`.

## Full Dataset

```text
root: tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
direction_set: basis_v2
direction_id: shear60_pos_x
trajectories: 9
steps per trajectory: 10
step_size_mm: 1.17
total_displacement_mm: 11.7
```

Validation result: PASS. Rollout readability and trajectory analysis passed. All `9` trajectories kept contact active for all `10/10` steps.

Rollout drift result:

```text
final max deformation mean=7.277 mm
final max deformation range=[6.388, 7.979] mm
adjacent response cosine mean=0.877623
adjacent relative response change mean=0.523788
fixed-first-step final relative L2 mean=0.604011
fixed-first-step final relative L2 range=[0.307949, 1.004665]
```

## Basis Projection Analysis

The `basis_v2` rollout was projected onto the matching Mode B factorial basis dataset:

```text
basis dataset: tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
rank2 final relative L2 mean=0.342624
rank3 final relative L2 mean=0.322752
rank4 final relative L2 mean=0.252178
rank4 step relative error mean=0.322845
rank4 step projection cosine mean=0.918620
fixed-first-step final relative L2 mean=0.604011
```

Interpretation: fixed Mode B basis projection is much better than repeating the first step, but the residual is still meaningful. This motivates a state/contact/material-conditioned coefficient/state diagnostic or NJF-style representation rather than a fixed basis alone.

## Matched Single-Large Comparison

Matched single-large dataset:

```text
root: tissue_dataset_v0/outputs/liver_surface_single_large_basis_v2_shear60_x_3x3_11p7_v1
samples: 9
direction_set: basis_v2
direction_id: shear60_pos_x
single action depth: 11.7 mm
```

Validation result: PASS for all `9` samples. Contact check passed with `0` errors. Tool direction check confirmed `60 deg` tilt.

Final-state comparison against the 10-step rollout:

```text
relative L2 mean=0.093038
relative L2 range=[0.021804, 0.266045]
pattern cosine mean=0.995152
max-node error mean=0.355 mm
max-node error range=[0.090, 0.641] mm
```

Interpretation: in this quasi-static SOFA setting, a slow single-large action can end close to the small-step rollout final state, but it does not provide local transition supervision. Mode C remains necessary for training/evaluating local Jacobian rollout behavior.

## Current Status

Complete as a targeted spike. Not yet integrated into `run_liver_surface_controlled_v1.py` as a standard branch. The next research task should be coefficient-prediction/NJF feasibility using saved Mode B basis groups and Mode C rollouts.
