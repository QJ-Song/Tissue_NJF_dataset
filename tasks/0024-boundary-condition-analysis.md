# Task: Boundary Condition Analysis

## Goal

Add real SOFA boundary-condition variation support so later NJF theory diagnostics can test whether boundary condition `B` changes local response bases.

This task is a boundary-analysis engineering prerequisite. It does not yet claim that boundary effects are fully characterized.

## Implemented

Updated `SofaFemBackend` so `MaterialConfig.boundary_condition` now changes the actual `FixedProjectiveConstraint` node set instead of only being saved as metadata.

Supported boundary types:

```text
bottom_fixed
back_fixed
bottom_and_back_fixed
small_bottom_patch_fixed
```

Boundary metadata now records:

```text
boundary_id
boundary_type
selection_method
fixed_node_count
free_node_count
total_node_count
fixed_centroid
fixed_z
boundary_box
mask/index artifact names
```

Updated the NJF Mode B planner so `sampling.response_basis.boundary_conditions` expands factorial groups across boundary conditions while keeping material/contact/action factors explicit.

Added smoke config:

```text
tissue_dataset_v0/configs/sofa_njf_boundary_smoke.yaml
```

It generates:

```text
4 boundary groups x 3 actions = 12 samples
1 material
1 contact point
3 action directions
```

## Verification

Generated ignored smoke output:

```text
tissue_dataset_v0/outputs/sofa_njf_boundary_smoke
```

Commands run:

```bash
python3 -m py_compile \
  tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py \
  tissue_dataset_v0/src/tissue_dataset_v0/njf/plan.py \
  tissue_dataset_v0/scripts/check_boundary_solver.py

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_njf_dataset.py \
  --config tissue_dataset_v0/configs/sofa_njf_boundary_smoke.yaml \
  --overwrite

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_smoke

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_smoke/samples \
  --min-samples 12

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_smoke/samples \
  --require boundary \
  --require boundary_mask \
  --require fixed_node_indices \
  --require free_node_indices \
  --require solver_summary \
  --require contact_summary
```

Results:

```text
py_compile: PASS
NJF dataset validation: PASS, 12 samples, 4 groups, 0 errors, 4 smoke-size K warnings
boundary/solver check: PASS, 12 samples, 0 errors
read_dataset_smoke: PASS
```

Observed group boundary metadata:

```text
group_boundary_smoke_000001: boundary_000001 bottom_fixed fixed=63
group_boundary_smoke_000002: boundary_000002 back_fixed fixed=36
group_boundary_smoke_000003: boundary_000003 bottom_and_back_fixed fixed=90
group_boundary_smoke_000004: boundary_000004 small_bottom_patch_fixed fixed=3
```

All smoke samples had max fixed-node displacement `0.000000 mm`.


## Paired Boundary Mode B v1

Result table and interpretation summary:

```text
docs/NJF_BOUNDARY_DIAGNOSTIC_SUMMARY.md
```


Added formal paired boundary config:

```text
tissue_dataset_v0/configs/sofa_njf_boundary_basis_v1.yaml
```

Generated ignored output:

```text
tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1
```

Design:

```text
2 contact points
1 material: Young's modulus 5000, Poisson ratio 0.45
4 boundary conditions
8 action directions x 3 magnitudes = 24 actions/group
8 groups, 192 samples total
```

Validation commands:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_njf_dataset.py \
  --config tissue_dataset_v0/configs/sofa_njf_boundary_basis_v1.yaml \
  --overwrite

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1/samples \
  --min-samples 192

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1/samples \
  --require boundary \
  --require boundary_mask \
  --require fixed_node_indices \
  --require free_node_indices \
  --require solver_summary \
  --require contact_summary
```

Validation results:

```text
NJF dataset validation: PASS, 192 samples, 8 groups, 0 errors, 0 warnings
boundary/solver check: PASS, 192 samples, 0 errors
read_dataset_smoke: PASS
```

Analysis commands:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1 \
  --rank 2 \
  --output-dir tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1/analysis/boundary_rank2

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py \
  tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1 \
  --rank 4 \
  --output-dir tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1/analysis/boundary_rank4
```

Rank-4 boundary results:

```text
effective_rank_mean=2.090
top2_cumulative_explained_mean=0.899835
rank4 local_group_basis_error_mean=0.047787
same_contact_same_material_diff_boundary cross_err_mean=0.742796
same_contact_same_material_diff_boundary projection_similarity_mean=0.427059
same_contact_same_material_diff_boundary principal_angle_mean=49.970 deg
boundary_pattern raw_cross_error_mean=0.742796
boundary_pattern normalized_cross_error_mean=0.736558
boundary_pattern normalized_projection_similarity_mean=0.427186
pattern_changes=10/12 paired boundary comparisons
mostly_scale_with_some_pattern_change=2/12 paired boundary comparisons
```

Interpretation:

```text
For this simplified SOFA liver setup, boundary changes strongly alter response basis patterns under fixed contact/material/action family. The effect is not explained by response magnitude alone because normalized cross-boundary reconstruction error remains high. This provides initial empirical support for including boundary condition B in J_phi(X, p, theta, B).
```

Caveat:

```text
This is still a controlled simulation diagnostic. It does not fully characterize realistic anatomical support, contact with a table, abdominal constraints, adhesion, or clinical boundary conditions.
```

## Remaining Work

The actual boundary-effect experiment remains to be run. Recommended next matrix:

```text
2-3 contact points
1-2 materials
4 boundary conditions
24 basis_v2 actions per group
```

Analysis should compare paired groups with same contact/material/action family and different boundary using:

```text
per-group effective rank
top-k explained variance
projection similarity
principal angles
cross-boundary reconstruction error
normalized-response cross reconstruction error
response norm ratios
```

## Status

Boundary selector, smoke validation, and first paired boundary Mode B diagnostic complete. Boundary effects are initially supported in simplified SOFA constraints, but realistic boundary characterization remains incomplete.


## Related Theory Note

The basis-versus-coefficient interpretation that uses this boundary result is saved in:

```text
docs/NJF_BASIS_COEFFICIENT_FACTOR_ANALYSIS.md
```
