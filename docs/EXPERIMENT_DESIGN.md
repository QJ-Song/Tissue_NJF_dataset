# Experiment Design

## Experiment 1: Minimal Tissue Pressing

- Single tissue patch.
- Single probe.
- Fixed camera.
- One contact location.
- One action magnitude.
- Record vertex displacement.
- Replay saved state.

Purpose: verify that simulation, logging, storage, and replay work end to end.

## Experiment 2: Contact-Location Variation

- Multiple contact locations.
- Same material.
- Same action magnitude.
- Compare displacement fields.

Purpose: test spatial generalization and ensure action/contact metadata is useful.

## Experiment 3: Action-Magnitude Variation

- Same contact location.
- Multiple action magnitudes.
- Check approximate local linearity.

Purpose: measure whether the local response can be approximated by a Jacobian-like map for small actions.

## Experiment 4: Material Variation

- Different Young's modulus values.
- Different Poisson ratio values, if supported.
- Check whether material parameters affect deformation response.

Purpose: determine whether material metadata is logged well enough for material-conditioned learning.

## Future Baseline Experiments

- Displacement-field prediction baseline.
- Action-conditioned dynamics baseline.
- NJF model baseline.

## Possible Evaluation Metrics

- Vertex displacement error.
- Endpoint error.
- Deformation field error.
- Local linearity residual.
- Generalization to unseen contact locations.
- Generalization to unseen material parameters.
- Visual comparison between predicted and ground-truth deformation.

## Current Practical Entry Point

Use the YAML config path first:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/slab_v0.yaml
```

Then verify replay:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py   tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001   --viewer summary   --stride 10
```


# NJF Response Basis Validation Plan

## Group Definition

A response-basis `group` is the unit of local analysis. Inside one group, only the small action perturbation should vary.

| Variable | Group Setting | Reason |
| --- | --- | --- |
| tissue geometry / mesh | fixed | Avoid mixing geometry effects into the local basis. |
| initial tissue state | fixed | NJF is a local response model conditioned on current state `X`. |
| material parameters | fixed | Stiffness and Poisson effects should not vary inside one local basis. |
| boundary condition | fixed | Boundary constraints strongly affect deformation propagation. |
| contact point | fixed | The basis is local to one action/contact anchor `p`. |
| contact radius / tool size | fixed | Contact area changes deformation patterns. |
| solver / dt / damping | fixed | Avoid numerical or dynamic differences inside a group. |
| action duration / settling | fixed | Keep responses comparable. |
| action direction | varied | Probe local response directions. |
| action magnitude | varied in a small range | Probe local linearity while staying in NJF's small-step regime. |

Each group response matrix is:

```text
R_g = [delta_X_1, delta_X_2, ..., delta_X_K]
```

where each `delta_X_i` is flattened from `[N, 3]` to `[3N]` for SVD/PCA and reconstruction metrics.

## Data To Collect Per Action

Every action/sample used in these experiments should preserve enough metadata to interpret a response:

| Field | Purpose |
| --- | --- |
| `vertices_0.npy` / `X_t` | Initial tissue state for this action. |
| `vertices_1.npy` / `X_next` | Tissue state after action/settling. |
| `displacement.npy` / `delta_X` | Supervised response field. |
| `action.npy` | Compact `[contact_x, contact_y, dir_x, dir_y, dir_z, depth]`. |
| `delta_a` from reader | 3D action displacement `direction * magnitude`. |
| `contact_point.npy` | Requested contact/action anchor. |
| `tool_pose_0.npy`, `tool_pose_1.npy` | Tool motion consistency and future rollout use. |
| `material.json` | Young's modulus, Poisson ratio, density, damping. |
| `boundary_mask.npy`, `boundary.json` | Boundary condition `B` and fixed-node validation. |
| `contact_summary.json` | Contact/proximity validity and filtering. |
| `solver_summary.json` | Solver settings and finite-state validity. |
| `meta.json.extra` | `state_id`, `material_id`, `boundary_id`, `contact_point_id`, `group_id`, `action_id`. |

For Mode B groups, also collect:

| Field | Purpose |
| --- | --- |
| `group_metadata.json` | Fixed/varied variables, material/contact IDs, sample references. |
| `state_initial.npy` | Group-shared `X_t`. |
| `actions.npy` | `[K, action_dim]` action set. |
| `responses.npy` | `[K, N, 3]` response set. |
| `contact_point.npy`, `contact_normal.npy` | Local contact anchor and approximate normal. |
| `fixed_node_mask.npy` | Group boundary mask. |

## Experiment Stages

| Stage | Experiment | Fixed Variables | Varied Variables | Data Needed | Main Outputs | Question Answered |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Per-group low-rank basis | geometry, state, material, boundary, contact point, tool, solver | action direction, small magnitude | each `groups/group_*` actions/responses/metadata | per-group SVD, effective rank, top-k variance, LOO reconstruction | Is each local response basis low-dimensional? |
| 1b | Cross-group basis similarity | one factor class at a time for interpretation | contact point and/or material across groups | top-r basis `U_g` from every group | principal angles, projection similarity, cross reconstruction | Are bases similar across contact/material, or condition-dependent? |
| 2 | Magnitude linearity | geometry, state, material, boundary, contact point, tool, direction, solver | action magnitude | magnitude sweep responses | scale consistency error | What action magnitude range is locally linear enough for NJF? |
| 2b | Superposition | geometry, state, material, boundary, contact point, tool, magnitude, solver | direction combinations such as `dx`, `dy`, `dx+dy` | single-direction and combined-action responses | superposition error | Does response behave like a local linear map across directions? |
| 3 | Factorial basis dataset | controlled grid with validated contacts/actions | contact point, material, optionally boundary | validated groups with complete metadata | larger per-factor basis summaries | Are Stage 1/2 conclusions stable over more factors? |
| 4 | Shared-basis generalization | train/test group split policy | held-out contact/material/group | train groups and held-out groups | shared/nearest/local/zero reconstruction errors | Is a shared basis enough, or must NJF predict condition-dependent basis/Jacobian? |

## Expected Result Tables

### Table 1: Per-Group Low-Rank Summary

Purpose: show whether each fixed-condition group has a low-dimensional local response basis.

| group_id | contact_id | material_id | E | nu | contact_xyz | K | effective_rank | top1_var | top2_var | top3_var | loo_error_mean | loo_error_max |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| group_000001 | contact_000001 | material_000001 | 3000 | 0.45 | [0, 0, 0.009] | 24 | ... | ... | ... | ... | ... | ... |

This table answers: does local low-rank response hold group by group?

### Table 2: Pairwise Basis Similarity Matrices

Purpose: compare basis subspaces rather than mixing all responses into one PCA.

Required matrices:

| Matrix | Cell Meaning | Interpretation |
| --- | --- | --- |
| `projection_similarity.csv` | `||U_i^T U_j||_F^2 / r` | Higher means basis subspaces overlap more. |
| `principal_angles_mean.csv` | mean principal angle in degrees | Lower means bases are more aligned. |
| `principal_angles_max.csv` | max principal angle in degrees | Captures worst-aligned basis direction. |
| `cross_reconstruction_error.csv` | `||R_j - U_i U_i^T R_j||_F / ||R_j||_F` | Lower means basis from group `i` reconstructs group `j`. |

Use source rows and target columns:

| basis_from / reconstruct | group_000001 | group_000002 | group_000003 | ... |
| --- | ---: | ---: | ---: | ---: |
| group_000001 | local error | cross error | cross error | ... |
| group_000002 | cross error | local error | cross error | ... |

This table answers: can one group's basis explain another group's responses?

### Table 3: Metadata-Grouped Comparison Summary

Purpose: turn pairwise matrices into interpretable factor comparisons.

| comparison_type | pair_count | projection_similarity_mean | projection_similarity_std | principal_angle_mean_deg | cross_recon_error_mean | cross_recon_error_std |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| same_contact_diff_material | ... | ... | ... | ... | ... | ... |
| same_material_diff_contact | ... | ... | ... | ... | ... | ... |
| diff_contact_diff_material | ... | ... | ... | ... | ... | ... |

This table answers: which factor changes basis more, contact point or material?

### Table 4: Material Scale vs Pattern Analysis

Purpose: separate material-driven response scale changes from response pattern/basis changes.

| contact_id | E_soft | E_hard | response_norm_ratio_soft_over_hard | raw_cross_recon_error | normalized_cross_recon_error | normalized_projection_similarity | interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| contact_000001 | 3000 | 10000 | ... | ... | ... | ... | scale_only / pattern_changes |

Compute this for matched contact points across material groups. Use two versions of the response matrix:

```text
raw:        R_g
normalized: each response vector divided by its norm
```

Interpretation:

- raw difference high but normalized error low: material mainly changes scale;
- normalized error high or projection similarity low: material changes pattern/basis and NJF should condition strongly on material.

### Table 5: Linearity And Superposition Summary

Purpose: choose a justified NJF local action range.

| contact_id | material_id | direction | magnitude_mm | scale_error | reference_magnitude_mm | recommendation |
| --- | --- | --- | ---: | ---: | ---: | --- |
| contact_000001 | material_000001 | normal | 0.2 | ... | 0.1 | keep / reject |

| contact_id | material_id | action_a | action_b | combined_action | superposition_error | recommendation |
| --- | --- | --- | --- | --- | ---: | --- |
| contact_000001 | material_000001 | dx | dy | dx+dy | ... | keep / reject |

This table answers: how small must `delta_a` be for a local Jacobian approximation to be defensible?

### Table 6: Shared-Basis Decision Summary

Purpose: convert analysis into modeling decisions.

| question | metric | result | decision |
| --- | --- | --- | --- |
| Is each group low-rank? | top2 variance / effective rank | ... | local basis holds / does not hold |
| Does contact point change basis? | same-material different-contact cross error | ... | condition on contact point: yes/no |
| Does material only change scale? | normalized material error | ... | material as scale / full condition |
| Is shared basis enough? | held-out shared-basis reconstruction | ... | shared basis / NJF dynamic basis |
| Is action range valid? | linearity and superposition error | ... | allowed magnitude range |

## Minimum Outputs For `analyze_basis_across_groups.py`

The first implementation should write:

```text
analysis/basis_across_groups/
  summary.json
  per_group_metrics.csv
  projection_similarity.csv
  principal_angles_mean.csv
  principal_angles_max.csv
  cross_reconstruction_error.csv
  metadata_grouped_summary.csv
  material_scale_pattern.csv
  decision_summary.md
```

Heatmap PNGs are useful but optional in the first version. The report must explicitly state that all-group global PCA is not the main conclusion.

Stage 1 implementation status: `tissue_dataset_v0/scripts/analyze_basis_across_groups.py` now writes these required CSV/JSON/Markdown artifacts, except heatmap PNGs. The first validated run used `tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid` and wrote outputs to `analysis/basis_across_groups/` under that ignored dataset root.
