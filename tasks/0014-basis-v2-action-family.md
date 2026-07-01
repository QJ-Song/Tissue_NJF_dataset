# Task: Basis v2 Single-Contact Action Family

## Goal

Extend the SOFA liver surface-collision response-basis dataset beyond `basis_v1` small-cone press actions while keeping the experiment single-contact and interpretable. Multi-point contact and grasper-like actions remain out of scope for this task; they should be handled later as `multi_contact_v1`.

## Action Family

Current `basis_v2` is implemented in `scripts/generate_liver_surface_sample.py --direction-set basis_v2`. It contains `17` action directions:

```text
normal: 1 direction
oblique press: +/-x, +/-y at 15 deg
oblique press: +/-x, +/-y at 30 deg
mixed press-shear: +/-x, +/-y at 40 deg
shear-like: +/-x, +/-y at 60 deg
```

All directions still have a downward component (`dir_z < 0`) because the current scene does not yet support pure tangential sliding or retraction as a stable first-class action mode. Pure tangent, retraction/release, frictional sliding, and multi-contact/grasping are future extensions.

## Probe Approach Semantics

A key implementation change was needed for `basis_v2`: the probe approach direction must be separated from the action direction. If a 40-60 degree action is also used as the initial approach vector, the rigid sphere can overlap the curved liver surface before the intended action, causing excessive apparent penetration and unrealistic displacement.

For `basis_v2`, the generator now uses:

```text
approach_direction = normal downward direction
action_direction = saved action[2:5]
probe_start = contact point offset along approach direction by probe radius/clearance
probe_end = probe_start + action_direction * action_magnitude
```

The generator records `approach_direction` and `probe_approach_policy` in `meta.json` and request/action metadata. Existing `vertical`, `basis_smoke`, and `basis_v1` behavior remains action-aligned.

## Smoke Result

Command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --layout grouped \
  --contact-set top_center \
  --material-set single \
  --direction-set basis_v2 \
  --output tissue_dataset_v0/outputs/liver_surface_basis_v2_smoke \
  --sample-id 1 \
  --depths-mm 1.17 \
  --preload-steps 0 \
  --settle-steps 20
```

Checks run:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/liver_surface_basis_v2_smoke/samples/sample_*
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_basis_v2_smoke/samples --min-samples 17 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_basis_v2_smoke/samples --min-samples 17 --max-angle-error-deg 0.2 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 55.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py tissue_dataset_v0/outputs/liver_surface_basis_v2_smoke --rank 4 --output tissue_dataset_v0/outputs/liver_surface_basis_v2_smoke/analysis/response_basis_summary.json
```

Result summary:

```text
sample validation: PASS for 17/17 samples
contact check: PASS, 17 samples, 0 errors
tool direction check: PASS, 17 samples, max tilt 60 deg
response basis: PASS, K=17, effective rank ~= 1.051, top2 explained ~= 0.998030, LOO mean error ~= 0.000710
```

## Acceptance Criteria For Full Basis v2

The smoke run only verifies that the action family and metadata are usable at one contact/material setting. Full acceptance should run:

```text
contact_set = top_three
material_set = young_three
direction_set = basis_v2
depths_mm = initially 1.17; optionally add 2.35 after contact validation
```

Then run:

```text
- sample validation
- contact validation
- tool direction validation
- per-group response-basis analysis
- cross-group basis similarity/reconstruction analysis
```

The main question is whether the broader single-contact action family remains low-dimensional within each fixed contact/material group and whether cross-group basis dependence becomes stronger than in `basis_v1`.

## Known Limitations

- `basis_v2` is still single-contact.
- `shear60_*` is shear-like motion with inward normal component, not pure sliding.
- Retraction/release is not implemented because it requires a preloaded `X_t` state.
- Frictional sliding and contact force export are still unavailable.
- The smoke effective rank is unexpectedly very low; the full factorial run is needed before interpreting this as a robust research result.


## Full Factorial Acceptance Result

Generated full `basis_v2` factorial data at:

```text
tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
```

Design:

```text
contact_set: top_three
material_set: young_three
direction_set: basis_v2
depths_mm: 1.17
samples: 153
groups: 9
actions per group: 17
```

Generation command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --layout grouped \
  --contact-set top_three \
  --material-set young_three \
  --direction-set basis_v2 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1 \
  --sample-id 1 \
  --depths-mm 1.17 \
  --preload-steps 0 \
  --settle-steps 20
```

Validation commands run:

```bash
find tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/samples -maxdepth 1 -type d -name 'sample_*' | wc -l
find tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/groups -maxdepth 1 -type d -name 'group_*' | wc -l
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/samples/sample_*
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/samples --min-samples 153 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/samples --min-samples 153 --max-angle-error-deg 0.3 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 55.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/samples --min-samples 153
```

Validation result:

```text
sample directories: 153
group directories: 9
sample validation: PASS for 153/153 samples
read_dataset_smoke: PASS
contact check: PASS, 153 samples, 0 errors
tool direction check: PASS, 153 samples, max tilt 60 deg
boundary/solver check: PASS, 153 samples, 0 errors
```

Analysis commands run:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1 --rank 4 --output tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/analysis/response_basis_summary.json
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1 --rank 2 --output-dir tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/analysis/basis_across_groups_rank2
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1 --rank 4 --output-dir tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/analysis/basis_across_groups_rank4
```

Analysis result:

```text
Per-group basis:
  groups=9
  effective_rank_mean=1.071
  effective_rank_range=[1.025, 1.144]
  top2_explained_mean=0.997322
  loo_mean=0.002532

Cross-group rank 2:
  offdiag_cross_reconstruction_mean=0.535110
  same_contact_diff_material_cross_err=0.317654
  same_material_diff_contact_cross_err=0.576413
  diff_contact_diff_material_cross_err=0.623186

Cross-group rank 4:
  offdiag_cross_reconstruction_mean=0.426280
  same_contact_diff_material_cross_err=0.278777
  same_material_diff_contact_cross_err=0.425404
  diff_contact_diff_material_cross_err=0.500469
```

Interpretation:

```text
- `basis_v2` passes full factorial acceptance for the current 1.17 mm action scale.
- Fixed contact/material groups remain strongly low-dimensional despite the broader action family.
- Compared with `basis_v1`, per-group effective rank is lower, but cross-contact reconstruction is worse at rank 2.
- This supports the hypothesis that local response is low-dimensional but contact/geometry conditioned.
- Adding shear-like directions does not remove low-rank structure; it makes shared/global basis assumptions less reliable.
```

Engineering status: `basis_v2` is now available as an optional branch in `run_liver_surface_controlled_v1.py`, while `basis_v1` remains the default reference dataset. Next research step: decide between `basis_v2` rollout data and a first coefficient-diagnostic/NJF feasibility analysis.


## Orchestration Integration

`basis_v2` is now integrated into the standard controlled dataset orchestration script as an opt-in branch. The default command remains unchanged and still runs the `basis_v1` reference path only.

Dry run for the default path:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py --dry-run --reuse-existing --stages all
```

Dry run for only the `basis_v2` branch:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --dry-run \
  --reuse-existing \
  --include-basis-v2 \
  --only-basis-v2 \
  --stages all
```

Validated execution for the existing `basis_v2` dataset:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --reuse-existing \
  --include-basis-v2 \
  --only-basis-v2 \
  --stages validate analyze
```

Result: PASS. The orchestration reproduced the `basis_v2` validation and analysis checks: `153` samples, `0` validation errors, contact/tool-direction/boundary checks passed, per-group basis analysis passed, and rank-2/rank-4 cross-group analysis passed.

Implementation notes:

```text
--include-basis-v2: append the basis_v2 branch to selected stages
--only-basis-v2: filter selected stages to the basis_v2 branch only; implies --include-basis-v2
```

Next step: choose between generating `basis_v2` rollout trajectories and implementing a first coefficient-diagnostic/NJF feasibility analysis on existing Mode B/Mode C data.
