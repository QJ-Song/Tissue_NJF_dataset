# Controlled SOFA Dataset v1

## Purpose

Controlled SOFA Dataset v1 is the current standard simulation-analysis package for the liver surface-collision work. Its purpose is not to prove NJF superiority on real tissue. Its purpose is to provide a reproducible controlled dataset and analysis pipeline for:

- local response basis analysis;
- contact/material condition-dependence analysis;
- rollout step-response drift analysis;
- single-large final-state comparison;
- fixed Mode B basis projection as a non-learning diagnostic reference;
- deciding what future real phantom/tissue data must record.

The standard entry point is:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py --dry-run --reuse-existing --stages all
```

To run analysis against existing generated datasets:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py --reuse-existing --stages analyze
```

To regenerate all standard outputs, run with:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py --overwrite --stages all
```

Regeneration runs SOFA and can take longer. Generated datasets are ignored artifacts and should not be committed.

The default pipeline intentionally remains the `basis_v1` reference path. The experimental `basis_v2` Mode B branch is opt-in:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --reuse-existing \
  --include-basis-v2 \
  --only-basis-v2 \
  --stages validate analyze
```

Use `--include-basis-v2` without `--only-basis-v2` to append the basis_v2 branch to the standard stages. Use `--only-basis-v2` for targeted reruns of the v2 validation and analysis.

`basis_v2` rollout is currently a targeted experiment, not yet part of the default orchestration command.

## Standard Datasets

The controlled v1 orchestration uses these dataset roots by default:

```text
tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1
tissue_dataset_v0/outputs/liver_surface_single_large_tilt_x_3x3_11p7_v1
```

### Mode B Response Basis

```text
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
groups: 9
actions per group: 18
directions: basis_v1, 6 small-cone press directions
magnitudes: 1.17 mm, 2.35 mm, 4.70 mm
```

This dataset answers whether fixed contact/material/boundary responses are locally low-rank and condition-dependent.

### Mode C Rollout

```text
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
trajectories: 9
direction: tilt_pos_x
steps per trajectory: 10
step size: 1.17 mm
total displacement: 11.7 mm
```

This dataset answers whether rollout step responses change over state and whether local transition data are needed for NJF-style learning.

### Matched Single-Large

```text
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
samples: 9
direction: tilt_pos_x
single action depth: 11.7 mm
```

This dataset compares final deformation from one slow large action against ten small rollout steps. It does not replace rollout supervision because it only gives `X_0 -> X_T`, not per-step `X_k -> X_{k+1}`.

## Standard Validation

The orchestration validates:

- Mode B sample artifacts with the default sample validator;
- required artifact readability through `read_dataset_smoke.py`;
- contact summaries through `check_contact.py`;
- tool direction and motion consistency through `check_tool_direction.py`;
- boundary and solver metadata through `check_boundary_solver.py`;
- Mode C trajectory readability through `read_njf_dataset.py`;
- Mode C trajectory consistency through `analyze_rollout_trajectories.py`;
- matched single-large sample validity, contact, and tool direction.

## Standard Analysis Outputs

Mode B analysis:

```text
liver_surface_mode_b_factorial_3x3_v1/analysis/response_basis_summary.json
liver_surface_mode_b_factorial_3x3_v1/analysis/basis_across_groups/
```

Mode C analysis:

```text
liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_drift_summary.json
liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_vs_single_large_summary.json
liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_summary.json
liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_metrics.csv
liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_report.md
```

Current reference results from the standard analysis:

```text
Mode B:
  groups=9
  effective rank mean=1.286
  top2 explained mean=0.987973

Cross-group basis:
  same_contact_diff_material cross error=0.343122
  same_material_diff_contact cross error=0.490669
  diff_contact_diff_material cross error=0.534312

Mode C fixed-first-step diagnostic:
  final relative L2 mean=0.432849

Matched single-large final-state comparison:
  relative L2 mean=0.071319
  pattern cosine mean=0.995937

Mode B fixed-basis projection:
  rank2 final relative L2 mean=0.211910
  rank3 final relative L2 mean=0.176309
  rank4 final relative L2 mean=0.168869
```

## Interpretation

The current controlled SOFA evidence supports these dataset-design conclusions:

- fixed-condition local response is low-dimensional;
- response basis changes with contact and material;
- rollout step responses are not well represented by a fixed first response vector;
- a fixed Mode B basis is much stronger than fixed first response, but still leaves residual rollout error;
- one slow single-large final state can be close to the rollout final state in this quasi-static setting, but it does not provide local transition supervision.

This supports Mode A/B/C style dataset organization for NJF feasibility work.


## Basis v2 Action-Family Spike

`scripts/generate_liver_surface_sample.py` now supports `--direction-set basis_v2`. This is an experimental single-contact action family intended to test whether the response basis remains low-dimensional beyond the small-cone `basis_v1` press actions.

Current `basis_v2` directions:

```text
normal: 1 direction
oblique press: +/-x, +/-y at 15 deg and 30 deg
mixed press-shear: +/-x, +/-y at 40 deg
shear-like: +/-x, +/-y at 60 deg
K = 17 directions per depth/contact/material group
```

Important implementation detail: `basis_v2` separates probe approach direction from action direction. The probe is placed using a normal approach, then moved along the saved action direction. This avoids artificial curved-surface overlap that occurred when 40-60 degree actions were also used as the approach vector. Metadata records `approach_direction` and `probe_approach_policy`.

Smoke command:

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

Smoke status: sample validation passed for all `17` samples; contact check passed with `0` errors; tool direction check passed with maximum tilt `60 deg`; response-basis analysis passed with one group, `K=17`, effective rank about `1.051`, top-2 explained variance about `0.998030`, and leave-one-out mean relative error about `0.000710`.

Full factorial acceptance dataset:

```text
root: tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
directions: basis_v2, K=17 per group
depth: 1.17 mm
samples: 153
groups: 9
```

Validation status: sample validation passed for all `153` samples; read smoke passed; contact check passed with `0` errors; tool direction check passed with maximum tilt `60 deg`; boundary/solver check passed.

Per-group basis result:

```text
groups=9
effective_rank_mean=1.071
effective_rank_range=[1.025, 1.144]
top2_explained_mean=0.997322
loo_mean=0.002532
```

Cross-group basis result:

```text
rank 2:
  offdiag_cross_reconstruction_mean=0.535110
  same_contact_diff_material_cross_err=0.317654
  same_material_diff_contact_cross_err=0.576413
  diff_contact_diff_material_cross_err=0.623186

rank 4:
  offdiag_cross_reconstruction_mean=0.426280
  same_contact_diff_material_cross_err=0.278777
  same_material_diff_contact_cross_err=0.425404
  diff_contact_diff_material_cross_err=0.500469
```

Interpretation: the broader `basis_v2` action family remains strongly low-dimensional within each fixed contact/material group. Compared with `basis_v1`, the group-internal rank is lower, but cross-contact sharing is weaker at rank 2. This suggests that adding shear-like directions does not destroy local low-rank structure, but it makes the response basis more contact/geometry dependent.


## Basis v2 Rollout Spike

`scripts/generate_liver_surface_rollout.py` now accepts `--direction-set basis_v2`. Like the Mode B sample generator, rollout generation separates probe approach direction from tool action direction:

```text
approach_direction = normal downward direction
action_direction = saved rollout action direction
probe_approach_policy = normal_approach_for_basis_v2
```

This is required for shear-like rollout actions. If the 60 degree shear-like action is also used as the initial probe approach, the sphere can start with artificial overlap on the curved liver surface.

Smoke dataset:

```text
root: tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_smoke
direction_set: basis_v2
direction_id: shear60_pos_x
contact_set: top_center
material_set: single
steps: 3
step_size: 1.17 mm
```

Smoke status: rollout readability passed, trajectory analysis passed, contact was active for all `3/3` steps, final max deformation was about `2.393 mm`, and the fixed-first-step final relative L2 error was about `0.317`.

Full rollout dataset:

```text
root: tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
direction_set: basis_v2
direction_id: shear60_pos_x
trajectories: 9
steps per trajectory: 10
step size: 1.17 mm
total displacement: 11.7 mm
```

Validation status: rollout readability passed; trajectory analysis passed; all `9` trajectories had contact active for all `10/10` steps; response consistency and fixed-node checks passed.

Key rollout metrics:

```text
final max deformation mean=7.277 mm
final max deformation range=[6.388, 7.979] mm
adjacent response cosine mean=0.877623
adjacent relative response change mean=0.523788
fixed-first-step final relative L2 mean=0.604011
fixed-first-step final relative L2 range=[0.307949, 1.004665]
```

Mode B fixed-basis projection onto the matching `basis_v2` factorial dataset:

```text
basis dataset: tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
rank2 final relative L2 mean=0.342624
rank3 final relative L2 mean=0.322752
rank4 final relative L2 mean=0.252178
rank4 step relative error mean=0.322845
rank4 step projection cosine mean=0.918620
fixed-first-step final relative L2 mean=0.604011
```

Matched single-large dataset:

```text
root: tissue_dataset_v0/outputs/liver_surface_single_large_basis_v2_shear60_x_3x3_11p7_v1
samples: 9
direction_set: basis_v2
direction_id: shear60_pos_x
single action depth: 11.7 mm
```

Single-large validation passed for all `9` samples, contact check passed with `0` errors, and tool direction check confirmed the expected `60 deg` tilt. Comparing the quasi-static single-large final state with the 10-step rollout final state:

```text
relative L2 mean=0.093038
relative L2 range=[0.021804, 0.266045]
pattern cosine mean=0.995152
max-node error mean=0.355 mm
max-node error range=[0.090, 0.641] mm
```

Interpretation: the `basis_v2` shear-like rollout is harder than the `basis_v1` tilt rollout. The fixed-first-step diagnostic drifts substantially, which supports saving per-step local transitions. A fixed Mode B basis improves the rollout approximation, especially at rank 4, but still leaves meaningful residual error; this is the regime where a state/contact/material-conditioned coefficient or NJF-style predictor becomes useful. The matched single-large final state can be close in this quasi-static setting, but it still lacks the intermediate `X_k -> X_{k+1}` supervision needed to train or evaluate local Jacobian behavior.


## Coefficient Diagnostics v1

A lightweight diagnostic layer now evaluates whether Mode B response bases can express Mode C rollout responses and what coefficient information changes over rollout. This is a mechanism diagnostic, not a model benchmark. The implementation lives in:

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/basis.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/metrics.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/baselines.py
tissue_dataset_v0/scripts/evaluate_coefficient_baseline.py
docs/NJF_MECHANISM_DIAGNOSTICS.md
```

Primary experiment:

```text
basis dataset: tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
rollout dataset: tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1
output: tissue_dataset_v0/outputs/evaluations/coefficient_baseline_v1_basis_v2_shear60
```

Primary result:

```text
B0 repeat first response final relative L2 mean=0.604011
B1 oracle basis projection rank4 final relative L2 mean=0.252178
B2 fixed first coefficient rank4 final relative L2 mean=0.602582
B3 prefix depth trend rank4 final relative L2 mean=0.829939
```

Sensitivity checks showed that a linear trend fit on the first `5` steps improves B3 to about `0.455366` final relative L2 at rank 4, while a quadratic trend over-extrapolates and degrades to about `0.840647`. Interpretation: the basis has expression value, fixed coefficients are insufficient, and simple depth-only coefficient trends are not robust enough. This identifies state/contact/material/action conditioning as necessary information for future NJF formulation and real-data acquisition.


### Multi-Direction Coefficient Diagnostic Check

The coefficient diagnostic was extended from one `shear60_pos_x` rollout direction to three `basis_v2` directions:

```text
normal
oblique30_pos_x
shear60_pos_x
```

All three directions use the same `top_three x young_three` 3x3 design, `10` rollout steps, `1.17 mm` step size, and the same Mode B `basis_v2` factorial basis.

Final relative L2 means:

```text
direction        B0_repeat  B1_oracle_rank4  B2_fixed_coeff_rank4  B3_linear3_rank4  B3_linear5_rank4
normal           0.417490   0.249987         0.417742              0.952569          0.780563
oblique30_pos_x  0.680118   0.379538         0.680483              1.066296          0.686794
shear60_pos_x    0.604011   0.252178         0.602582              0.829939          0.455366
```

Interpretation: the Mode B basis consistently improves expression of rollout responses, but fixed first-step coefficients do not help, and simple cumulative-depth coefficient trends are not robust across action directions. This strengthens the case that NJF-related data must preserve state/contact/material/action information; it is not yet a learned-model benchmark.


### Fitted Coefficient Diagnostic v1

A NumPy ridge fitted diagnostic was added above the coefficient diagnostics. It tests whether simple engineered features explain Mode B basis coefficients for Mode C rollout steps.

```text
implementation: tissue_dataset_v0/src/tissue_dataset_v0/njf/fitted.py
script: tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py
output: tissue_dataset_v0/outputs/evaluations/fitted_coefficient_predictor_v1_basis_v2_3dir
```

Diagnostic variants:

```text
R1_non_autoregressive: step/depth/action/material/contact-distance features
R2_autoregressive: R1 + previous coefficient features, recursively predicted at test time
```

Splits:

```text
prefix_per_trajectory: first 5 steps train, last 5 steps test
heldout_direction_within_group: train on two directions within one contact/material group, test held-out direction
```

Reference averages across `normal`, `oblique30_pos_x`, and `shear60_pos_x`:

```text
B0 final relative L2 mean=0.567206
B1 oracle rank4 final relative L2 mean=0.293901
B2 fixed coefficient rank4 final relative L2 mean=0.566936
B3 linear 5-step trend rank4 final relative L2 mean=0.640908
```

Best stable ridge sensitivity result used strong regularization, `alpha=100`:

```text
heldout_direction R1 rank4 final relative L2 mean=0.699563
heldout_direction R2 rank4 final relative L2 mean=0.738773
prefix R1 rank4 final relative L2 mean=0.827004
prefix R2 rank4 final relative L2 mean=0.827190
```

Low-regularization recursive R2 was unstable and could explode. Interpretation: simple linear coefficient diagnostics from scalar depth/action/material/contact-distance features do not explain the coefficient evolution. The B1 oracle gap remains valuable: the basis can express useful responses, but the coefficients require richer state/contact-geometry information or nonlinear state-conditioned modeling.


### State Local Ridge Feature v1

`R3_state_local_ridge` was added to the fitted coefficient diagnostic to test local `X_t` statistics around the contact point. It uses nearest-node local patches, patch displacement statistics, weighted local displacement, and simple local geometry summaries.

Stable `alpha=100` rank-4 final relative L2 means:

```text
split                         R1_scalar  R2_autoreg  R3_state_local
heldout_direction_within_group 0.699563  0.738773    0.711574
prefix_per_trajectory          0.827004  0.827190    0.896943
```

Patch size `32` slightly improved R3 but still did not beat R1:

```text
heldout_direction_within_group R3 rank4=0.707538
prefix_per_trajectory R3 rank4=0.880351
```

Interpretation: these hand-designed local statistics do not explain coefficient evolution better than scalar features. The result supports moving away from more scalar ridge diagnostics and toward clearer NJF state/contact representation design.


### Boundary Condition Selector Smoke

Boundary variation support was added as an engineering prerequisite for later boundary-effect diagnostics. `SofaFemBackend` now uses `MaterialConfig.boundary_condition` to choose actual `FixedProjectiveConstraint` node sets instead of only recording the string as metadata. The supported selector types are:

```text
bottom_fixed
back_fixed
bottom_and_back_fixed
small_bottom_patch_fixed
```

Smoke config:

```text
tissue_dataset_v0/configs/sofa_njf_boundary_smoke.yaml
```

Smoke output, not committed:

```text
tissue_dataset_v0/outputs/sofa_njf_boundary_smoke
```

Observed smoke metadata:

```text
bottom_fixed: fixed=63
back_fixed: fixed=36
bottom_and_back_fixed: fixed=90
small_bottom_patch_fixed: fixed=3
```

Validation status: `validate_njf_dataset.py` passed with `12` samples and `4` groups; `check_boundary_solver.py` passed with `0` errors; read smoke passed. The only validation warnings are expected because each smoke group has `K=3`, below the useful basis-analysis threshold.

Interpretation: boundary conditions can now be varied in real SOFA constraints and recorded in dataset metadata. This is not yet a boundary-effect analysis. The next boundary experiment should generate paired Mode B groups with fixed contact/material/action family and varied boundary, then compare cross-boundary basis reconstruction and normalized response patterns.


### Paired Boundary Mode B v1

A first paired boundary-effect dataset was generated after the boundary selector smoke passed. It fixes material and action family while varying boundary condition.

Config:

```text
tissue_dataset_v0/configs/sofa_njf_boundary_basis_v1.yaml
```

Output, not committed:

```text
tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1
```

Design:

```text
2 contact points x 1 material x 4 boundary conditions x 24 basis_v2-style actions
8 groups, 192 samples
```

Validation status: NJF dataset validation passed with `192` samples and `8` groups; boundary/solver check passed with `0` errors; read smoke passed.

Rank-4 cross-boundary result:

```text
effective_rank_mean=2.090
top2_cumulative_explained_mean=0.899835
rank4 local_group_basis_error_mean=0.047787
same_contact_same_material_diff_boundary cross_err_mean=0.742796
same_contact_same_material_diff_boundary projection_similarity_mean=0.427059
same_contact_same_material_diff_boundary principal_angle_mean=49.970 deg
boundary_pattern normalized_cross_error_mean=0.736558
boundary_pattern normalized_projection_similarity_mean=0.427186
```

Interpretation: under fixed contact/material/action family, changing simplified fixed-node boundary conditions strongly changes the response basis. The normalized cross-boundary error remains high, so this is not just a response-scale effect. This gives initial controlled-SOFA evidence that boundary condition `B` should be represented in `J_phi(X, p, theta, B)`. The result remains a simplified boundary diagnostic, not a claim that realistic anatomical boundary effects are fully characterized.

## Current Limitations

The current controlled dataset is intentionally limited:

- SOFA-only simulation, not real tissue evidence;
- official liver mesh with simplified fixed volume-node boundary;
- fixed material contact point mode;
- no reliable exported contact force;
- approximate contact normals;
- the standard controlled v1 orchestration still uses `basis_v1` small-cone press actions by default;
- `basis_v2` full factorial acceptance passed and is available as an opt-in orchestration branch, but it is not the default reference path;
- `basis_v2` rollout has been generated and analyzed as a targeted spike, but is not yet integrated into the standard orchestration command;
- no pure tangent, frictional sliding, retraction, or multi-contact/grasping action family yet;
- no friction/sliding realism study;
- no real phantom/tissue benchmark or model comparison against existing deformation models.

Do not present this dataset as proof of clinical realism or NJF superiority. Present it as controlled simulation analysis for variable isolation and dataset design.

## Next Work

Recommended next steps:

1. Use this orchestration as the standard reproducibility entry point.
2. Stop adding hand-designed scalar ridge features; the current R3 result is not competitive.
3. Add a shared-basis or locally aligned basis diagnostic only if needed to clarify coefficient-coordinate comparability across groups.
4. If continuing SOFA-side analysis, use richer local/state encodings only as mechanism probes, not as final model comparisons.
5. Draft a real phantom/tissue acquisition plan aligned with this schema.
