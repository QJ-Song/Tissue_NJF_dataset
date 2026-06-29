# Task: SOFA NJF Dataset v1

## Background

The project goal has shifted from a controlled single-step contact dataset to a SOFA dataset pipeline for training and validating Neural Jacobian Field (NJF) models. NJF should be treated as a local small-step response model:

```text
delta_X = J_phi(X, p, theta, B) * delta_a
```

The first useful dataset must therefore emphasize small local perturbations, response basis groups, and multi-step rollout trajectories instead of one large action-response sample.

This task is an integration and acceptance task. It should compose existing capabilities from Stage A/B/C/D, keep the current single-sample pipeline compatible, and add a lightweight NJF dataset orchestration layer above it.

## Goal

Create the first SOFA NJF dataset generation path with three supported modes:

```text
Mode A: local perturbation samples
Mode B: response basis groups
Mode C: multi-step rollout trajectories
```

The goal is not clinical realism. The goal is stable, explainable, reproducible local tissue response data suitable for:

- local NJF training;
- response basis analysis;
- rolling NJF prediction tests;
- comparison against single-step deformation predictors.

## Scope

Implement or integrate:

- fixed simple tissue geometry, preferably slab/cuboid or an ellipsoid patch for v1;
- fixed topology;
- fixed bottom or back boundary condition;
- deterministic material parameter grid;
- small-step action magnitudes, defaulting to `0.05`, `0.1`, and `0.2` mm;
- grouped local action sampling;
- SOFA `probe_contact` interaction mode;
- saved tool poses and tool geometry from Stage D2;
- contact summary and per-step contact status from Stage D3;
- boundary and solver metadata from Stage D5;
- NJF dataset orchestration above the existing single-sample pipeline;
- dataset-level validation for samples, groups, and trajectories.

Do not implement for v1:

- real liver mesh;
- broad random geometry as the default;
- anisotropic material;
- heterogeneous material fields;
- complex friction;
- grasper contact;
- cutting, tearing, puncture, or suturing;
- full robot dynamics;
- photorealistic rendering;
- HDF5-only storage.

## Architecture Direction

Do not rewrite the existing single-sample pipeline. Keep:

- `SimulationBackend.simulate(request, logger)`;
- `DatasetPipeline.generate()`;
- `FileSystemSampleWriter`;
- `DirectorySimulationLogger`;
- manifest-driven sample artifacts;
- offline replay separated from simulation.

Add a thin NJF orchestration layer above it:

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/
  plan.py
  modes.py
  recorder.py
  validate.py
```

Initial responsibilities:

- `plan.py`: build dataset, group, and trajectory plans from config;
- `modes.py`: define Mode A/B/C generation logic;
- `recorder.py`: write `samples/`, `groups/`, `trajectories/`, dataset metadata, and splits;
- `validate.py`: check NJF dataset-level consistency.

Do not move group, rollout, split, or basis logic into `SofaFemBackend`. The backend should remain responsible for physical simulation and state extraction.

## Relevant Context

Read first:

- `AGENTS.md`
- `docs/CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DATASET_SCHEMA.md`
- `docs/NJF_FORMULATION.md`
- `docs/sofa_njf_dataset_design.md`
- `tasks/0010-sofa-stage-d-probe-contact-plan.md`
- `tasks/0011-sofa-stage-a-directional-action.md`
- `tasks/0012-sofa-stage-b-material-extensions.md`

Likely to modify:

- `tissue_dataset_v0/configs/sofa_njf_dataset.yaml`
- `tissue_dataset_v0/src/tissue_dataset_v0/njf/`
- `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/layout.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/validation/`
- `tissue_dataset_v0/scripts/generate_njf_dataset.py`
- `tissue_dataset_v0/scripts/validate_njf_dataset.py`
- `tissue_dataset_v0/scripts/run_njf_smoke_test.py`
- `docs/DATASET_SCHEMA.md`
- `docs/ROADMAP.md`

## Mode A: Local Perturbation Dataset

Purpose: train local NJF.

Each small-step sample should provide:

```text
X_t
delta_a
X_next
delta_X = X_next - X_t
```

Requirements:

- use small displacement actions, defaulting to `0.05`, `0.1`, and `0.2` mm;
- record state before the action;
- execute one small tool step;
- settle or step for a fixed configured number of simulation steps;
- record the next state and response;
- save tool pose, contact metadata, material, boundary, and solver metadata.

## Mode B: Response Basis Group Dataset

Purpose: verify low-dimensional response bases at a fixed contact point.

Within each group, fix:

```text
state_id
initial tissue state X_t
material_id
boundary_id
contact_point_id
tool geometry
solver config
```

Within each group, vary only:

```text
action direction
action magnitude
```

Do not mix different contact points in one response basis group.

Each group should write:

```text
group_metadata.json
state_initial.npy
fixed_node_mask.npy
surface_points.npy
actions.npy
responses.npy
contact_point.npy
contact_normal.npy
```

Formal response basis checks should use at least `K >= 12` actions per group. Smoke tests may use `K = 3`. A complete v1 response-basis group must include multiple action directions; vertical-only groups are useful for smoke/debug/regression but are not sufficient for the research v1 basis dataset.

## Mode C: Multi-Step Rollout Trajectory Dataset

Purpose: test whether NJF can integrate small local responses to predict larger tool motion.

Do not store only the final state for a large displacement. Split larger actions into small steps, such as:

```text
1.0 mm = 10 steps * 0.1 mm
2.0 mm = 20 steps * 0.1 mm
```

Each trajectory should write:

```text
trajectory_metadata.json
states.npy          # [T+1, N, 3]
actions.npy         # [T, action_dim]
responses.npy       # [T, N, 3]
contact_points.npy  # [T, 3]
contact_normals.npy # [T, 3]
tool_poses.npy      # [T+1, pose_dim]
solver_status.json
```

Smoke tests may use `T = 3`. Useful rollout validation should target `T >= 10`.

## Contact Point Modes

Support two semantics in the schema:

1. `fixed_material_point`: keep the same material/surface point as the contact anchor. This is the v1 priority for Mode A and Mode B.
2. `recomputed_geometric_contact`: recompute the actual closest/current surface contact point during tool motion. This is useful for later rollouts but may remain a TODO initially.

For rollout trajectories, record per-step contact point information even when using the fixed material point mode.

## Dataset Layout Target

The NJF dataset root should distinguish single samples, basis groups, and trajectories:

```text
dataset_root/
  metadata.json
  config.yaml
  samples/
    sample_000001.npz or sample_000001/
  groups/
    group_000001/
      group_metadata.json
      state_initial.npy
      fixed_node_mask.npy
      actions.npy
      responses.npy
      contact_point.npy
      contact_normal.npy
  trajectories/
    traj_000001/
      trajectory_metadata.json
      states.npy
      actions.npy
      responses.npy
      contact_points.npy
      contact_normals.npy
      tool_poses.npy
      solver_status.json
  splits.json
```

The existing `sample_*` layout remains valid for legacy and single-step compatibility.

## Required Step Fields

Each local step should preserve enough metadata to interpret the response:

- `sample_id`, `group_id`, `trajectory_id` if applicable, `step_id`;
- `state_id`, `material_id`, `boundary_id`, `contact_point_id`;
- `X_t`, `X_next`, `delta_X`;
- `delta_a`, action direction, action magnitude;
- tool pose before and after the step;
- tool radius and geometry type;
- contact point, contact normal, contact status, contact distance;
- contact force if reliable, otherwise mark unavailable;
- Young's modulus, Poisson ratio, density, damping;
- fixed node mask, fixed/free node indices, boundary type and box;
- `dt`, settling steps, solver types, tolerance, convergence/validity status;
- random seed and config hash or config path.

## Split Requirements

Support these split names in metadata:

```text
train
val
test_unseen_contact
test_unseen_material
test_rollout
```

Do not randomly split actions from the same basis group across train/test by default. Split by group, contact point, or material unless explicitly running leave-one-action-out analysis.

## Dependencies

Before the NJF dataset is treated as training-ready, Stage D should provide:

- D2 stable tool pose artifacts;
- D3 contact summary and per-step contact status;
- D4 directional small-step probe contact for complete Mode B response-basis data;
- D5 boundary and solver metadata;
- D7-like sequence artifacts for Mode C rollout.

If D4 is not complete, the project may generate a vertical-only smoke/debug baseline, but it should not be labeled as the complete SOFA NJF Dataset v1 for response-basis experiments. The config and metadata must make any vertical-only limitation explicit.

## Priority Plan

P0: Update task/design context and schema for NJF Mode A/B/C.

P1: Finish Stage D metadata required by NJF:

- D3 contact summary;
- D5 boundary and solver metadata;
- D4 small-step directional probe motion. This is a hard dependency for complete Mode B response-basis data, not merely an optional extension.

P2: Add the lightweight `njf/` orchestration layer.

P3: Implement Mode A local perturbation.

P4: Implement Mode B response basis groups.

P5: Implement Mode C rollout trajectories.

P6: Implement dataset-level validation and smoke test.

P7: Add split metadata and a small demo dataset command.

## Acceptance Criteria

- `sofa_njf_dataset.yaml` exists.
- A smoke dataset can be generated without overwriting existing data.
- Smoke dataset includes:
  - one local perturbation sample set;
  - one response basis group with 3 actions;
  - one rollout trajectory with 3 steps.
- Complete v1 Mode B data includes multiple action directions at each fixed contact point; vertical-only output is accepted only as smoke/debug/regression data.
- Dataset-level validation passes.
- `delta_X == X_next - X_t` for local samples.
- `responses[k] == states[k+1] - states[k]` for trajectories.
- Group fixed variables remain fixed within each basis group.
- Fixed node displacement is near zero.
- Tool pose, action direction, contact point, and contact summary are mutually consistent.
- Offline replay remains independent from SOFA execution.

## Suggested Smoke Command Shape

Exact commands should be updated after implementation:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/run_njf_smoke_test.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py path/to/dataset_root
```

## Progress

* [x] Planning discussion captured.
* [x] Stage D3 contact summary implemented.
* [x] Stage D5 boundary and solver metadata implemented.
* [x] Stage D4 directional small-step probe motion implemented for complete Mode B response-basis data.
* [x] Lightweight `njf/` orchestration layer added.
* [x] Mode A local perturbation implemented.
* [x] Mode B response basis groups implemented for smoke-sized K=3 groups.
* [x] Mode C rollout trajectories implemented for smoke-sized T=3 trajectories.
* [x] Dataset-level Mode A/B/C validator implemented.
* [x] NJF Mode A/B/C smoke dataset generated and validated.
* [x] Docs updated for current Mode A/B/C state, group/trajectory schema, and field inventory.
* [x] Non-smoke demo config added for K=24 and T=10.
* [x] Response basis analysis script added and sanity-checked on smoke output.
* [x] Non-smoke demo dataset generated, validated, and analyzed.
* [x] Rollout trajectory analysis script added and validated on smoke and non-smoke outputs.
* [x] Response Basis Batch v1 planner/config/analysis implemented and validated.
* [x] SOFA-free NJF dataset reader and smoke/metric CLI implemented and validated.
* [x] Stage 1 cross-group response-basis analysis implemented and run on `sofa_njf_basis_batch_valid`.
* [x] Stage 2 action-magnitude linearity and tangent-superposition analysis implemented and run on `sofa_njf_basis_batch_valid`.

## Notes

- Do not create a parallel top-level `soft_tissue_dataset/` module. Integrate v1 into `tissue_dataset_v0/`.
- Keep Stage A/B/C configs for regression and experimentation.
- Keep `localized_probe_force` available for regression.
- Keep optional artifacts manifest-driven and backward compatible.
- Surface collision is a later extension unless point-collision probe contact fails validation.
- Vertical-only probe motion should remain available as a smoke/debug/regression setting, but it is not the completion criterion for v1 response-basis data.
- Stage B material heterogeneity and anisotropy remain deferred until the homogeneous NJF dataset path is reliable.

## Current Implementation Notes

The current implementation adds a lightweight `tissue_dataset_v0.njf` layer and keeps SOFA physics in `SofaFemBackend`. `sofa_njf_dataset.yaml` currently enables Mode A, Mode B, and Mode C. It generates three Mode A local perturbation samples with `0.05`, `0.1`, and `0.2` mm actions, one smoke-sized Mode B response-basis group with three fixed-contact `0.1` mm actions, and one smoke-sized Mode C rollout trajectory with three `0.1` mm steps. The dataset root contains `metadata.json`, copied `config.yaml`, `splits.json`, `samples/`, `groups/group_000001/`, and `trajectories/traj_000001/`.

Validated smoke output:

```text
tissue_dataset_v0/outputs/sofa_njf_smoke
```

Checks run and passed:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/njf/*.py tissue_dataset_v0/scripts/generate_njf_dataset.py tissue_dataset_v0/scripts/validate_njf_dataset.py tissue_dataset_v0/scripts/run_njf_smoke_test.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/run_njf_smoke_test.py --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_smoke
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_njf_smoke/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require fixed_node_indices --require free_node_indices --require boundary_mask --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_njf_smoke/samples --min-samples 7 --max-angle-error-deg 0.1 --min-motion-mm 0.04
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_njf_smoke/samples --min-samples 7
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/sofa_njf_smoke/samples --min-samples 7
scripts/run_sofa_python.sh -c "import numpy as np, pathlib; p=pathlib.Path('tissue_dataset_v0/outputs/sofa_njf_smoke/trajectories/traj_000001'); print({'states': np.load(p/'states.npy').shape, 'actions': np.load(p/'actions.npy').shape, 'responses': np.load(p/'responses.npy').shape, 'tool_poses': np.load(p/'tool_poses.npy').shape, 'contact_points': np.load(p/'contact_points.npy').shape})"
```

Next step: implement Stage 1 cross-group response-basis analysis on `sofa_njf_basis_batch_valid` before expanding the dataset or training NJF. Keep SOFA/Isaac Sim out of analysis and model code.


## Demo Analysis Notes

Added `tissue_dataset_v0/configs/sofa_njf_demo.yaml` as the first non-smoke dataset config. It keeps fixed geometry/material/boundary/contact point, expands Mode B to `K=24`, and expands Mode C to `T=10`. Planner sanity check confirmed `mode_a=3`, `mode_b_groups=1`, `mode_b_actions=24`, `mode_c=1`, and `rollout_steps=10`.

Added `tissue_dataset_v0/scripts/analyze_response_basis.py`. It reads `groups/group_*/actions.npy` and `responses.npy`, computes SVD/PCA spectrum, cumulative explained variance, entropy effective rank, and leave-one-action-out reconstruction error. Smoke sanity check on `tissue_dataset_v0/outputs/sofa_njf_smoke` passed and reported expected `K=3` limitations.

Do not treat smoke analysis metrics as scientific evidence. The meaningful response-basis check should use `tissue_dataset_v0/outputs/sofa_njf_demo` or a larger dataset with at least `K>=12` actions per group.

Generated and validated non-smoke demo output:

```text
tissue_dataset_v0/outputs/sofa_njf_demo
```

Checks run and passed:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_njf_dataset.py --config tissue_dataset_v0/configs/sofa_njf_demo.yaml --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_demo
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py tissue_dataset_v0/outputs/sofa_njf_demo
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_njf_demo/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require fixed_node_indices --require free_node_indices --require boundary_mask --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_njf_demo/samples --min-samples 28 --max-angle-error-deg 0.1 --min-motion-mm 0.04
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_njf_demo/samples --min-samples 28
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/sofa_njf_demo/samples --min-samples 28
```

Validation summary:

```text
samples=28 groups=1 trajectories=1 errors=0 warnings=0
group_000001: actions=24 unique_dirs=8 max_response=0.0020564389415085316
traj_000001: steps=10 max_step=9.999999747378752e-05 max_response=0.0017272776458412409
```

Response-basis analysis on `group_000001`:

```text
K=24 dirs=8 effective_rank=1.845
leave_one_action_out_mean=0.018086
leave_one_action_out_max=0.034408
cumulative_explained_top=[0.7720297196504429, 0.977187054379935, 0.9997504921454429, 0.9999834543594373, 0.9999896814547918]
```

Rollout trajectory analysis script:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py tissue_dataset_v0/outputs/sofa_njf_demo
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py tissue_dataset_v0/outputs/sofa_njf_smoke
```

The script reads `trajectories/traj_*` only; it does not rerun SOFA. It reports trajectory length, action step size, per-step response norms, cumulative deformation, fixed-node drift, tool-pose/action consistency, contact activity, contact-distance range, contact-point drift, and placeholder fields for future rolling-NJF prediction metrics. Demo output passed with `T=10`, `ready=True`, final max deformation `2.592 mm`, max per-step node response `1.727 mm`, max tool step error `0.000002 mm`, contact active `10/10`, and fixed-node drift `0.000000 mm`. Smoke output passed with a warning because `T=3` is shorter than the useful rollout threshold `T>=10`.

## Response Basis Batch v1 Notes

Implemented planner support for multi-contact and multi-material Mode B groups. `response_basis.contact_points_xy` now accepts a list of `[x, y]` points, and `response_basis.material_grid` can generate a small grid over Young's modulus, Poisson ratio, density, and damping. The backend still receives one ordinary `SampleRequest` per action; batch logic remains in the NJF orchestration layer.

Added `tissue_dataset_v0/configs/sofa_njf_basis_batch.yaml` for the first batch experiment. It writes to `tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid` and generates:

```text
3 contact points: [0.0, 0.0], [-0.01, 0.0], [-0.015, 0.0]
2 Young's modulus values: 3000.0, 10000.0
6 Mode B groups
24 actions per group
144 samples total
```

An initial wider contact set produced a failed generated dataset at `tissue_dataset_v0/outputs/sofa_njf_basis_batch` because `[0.025, 0.0]` and several y-offset candidate points did not produce contact on the current procedural liver-like geometry. That output should be treated as a failed experiment artifact and not used for training or conclusions. It was not deleted.

Checks run and passed for the valid batch:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/njf/schema.py tissue_dataset_v0/src/tissue_dataset_v0/njf/plan.py tissue_dataset_v0/src/tissue_dataset_v0/njf/modes.py tissue_dataset_v0/scripts/analyze_response_basis.py
scripts/run_sofa_python.sh -c "from pathlib import Path; from tissue_dataset_v0.njf.plan import load_njf_plan; p=load_njf_plan(Path('tissue_dataset_v0/configs/sofa_njf_basis_batch.yaml')); print({'mode_b_groups': len(p.mode_b_groups), 'mode_b_actions': sum(len(g.actions) for g in p.mode_b_groups)})"
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_njf_dataset.py --config tissue_dataset_v0/configs/sofa_njf_basis_batch.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require fixed_node_indices --require free_node_indices --require boundary_mask --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid/samples --min-samples 144 --max-angle-error-deg 0.1 --min-motion-mm 0.04
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid/samples --min-samples 144
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid/samples --min-samples 144
```

Valid batch result:

```text
validator: samples=144 groups=6 trajectories=0 errors=0 warnings=0
basis summary: effective_rank_mean=1.903, effective_rank_range=[1.376, 2.430], leave_one_action_out_mean=0.014674, top2_cumulative_explained_mean=0.963488
```

## SOFA-Free NJF Reader Notes

Added `tissue_dataset_v0/src/tissue_dataset_v0/njf/dataset.py` and `tissue_dataset_v0/scripts/read_njf_dataset.py`. The reader returns numpy-based records for Mode A/B/C without importing SOFA or Isaac Sim:

```text
LocalPerturbationRecord: x_t, x_next, delta_x, action, delta_a, material, boundary, contact, tool poses, fixed_node_mask. `delta_a` is the 3D displacement vector `action_direction * action_magnitude`; the full compact `[contact, direction, depth]` representation remains in `action`
ResponseBasisGroupRecord: state_initial, actions, responses, response_matrix, contact point/normal, fixed_node_mask
RolloutTrajectoryRecord: states, actions, responses, contact_points, contact_normals, tool_poses, contact status/distances
```

Checks run and passed:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/njf/dataset.py tissue_dataset_v0/src/tissue_dataset_v0/njf/__init__.py tissue_dataset_v0/scripts/read_njf_dataset.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_smoke --require-mode local_perturbation --require-mode response_basis_group --require-mode rollout_trajectory --min-groups 1 --min-trajectories 1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_demo --require-mode local_perturbation --require-mode response_basis_group --require-mode rollout_trajectory --min-groups 1 --min-trajectories 1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid --require-mode response_basis_group --min-groups 6
scripts/run_sofa_python.sh -c "import sys; from pathlib import Path; from tissue_dataset_v0.njf.dataset import NJFDataset; d=NJFDataset(Path('tissue_dataset_v0/outputs/sofa_njf_demo')); s=d.summary(); print({'sample_count': s.sample_count, 'sofa_loaded': 'Sofa' in sys.modules, 'sofa_runtime_loaded': 'SofaRuntime' in sys.modules})"
```

Smoke results:

```text
sofa_njf_smoke: samples=7, groups=1, trajectories=1
sofa_njf_demo: samples=28, groups=1, trajectories=1
sofa_njf_basis_batch_valid: samples=144, groups=6, trajectories=0
SOFA import check: sofa_loaded=False, sofa_runtime_loaded=False
```

## Response Basis Validation Roadmap

Do response-basis validation in four stages. Do not concatenate all groups and run one global PCA as the primary conclusion; that mixes contact/material/boundary effects and is hard to interpret.

Stage 1: cross-group basis analysis on current data.

- Input: `tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid`.
- Implement: `tissue_dataset_v0/scripts/analyze_basis_across_groups.py`.
- Per group: load `responses.npy`, `actions.npy`, and `group_metadata.json`; flatten responses to `3N`; run SVD/PCA; compute effective rank, top-1/top-2/top-3 explained variance, and reconstruction error.
- Across groups: compute pairwise principal angles, projection similarity `||U_i^T U_j||_F^2 / r`, and cross-group reconstruction error `||R_j - U_i U_i^T R_j||_F / ||R_j||_F`.
- Metadata summaries: same material/different contact, same contact/different material, different material/different contact.
- Outputs: `summary.json`, `per_group_metrics.csv`, `principal_angles.csv`, `projection_similarity.csv`, `cross_reconstruction_error.csv`, and `report.md`. Heatmap PNGs are useful but optional for the first version.
- Acceptance: handles all 6 groups, emits 6x6 matrices, distinguishes material/contact comparison classes, and clearly states that global mixed PCA is not the main conclusion.

Stage 2: action magnitude linearity and superposition.

- Add a small probe config such as `sofa_njf_linearity_probe.yaml`.
- Fixed variables: tissue, material, boundary, contact point, solver, tool.
- Vary magnitude along fixed directions: e.g. `0.05, 0.1, 0.2, 0.5, 1.0` mm.
- Add combination actions such as `dx`, `dy`, and `dx + dy`.
- Analyze scale consistency `delta_X(alpha u) ~= alpha delta_X(u)` and superposition `delta_X(dx + dy) ~= delta_X(dx) + delta_X(dy)`.
- Acceptance: recommends an action magnitude range where local Jacobian assumptions are reasonable and explains when rollout is needed.

Stage 3: factorial response-basis dataset.

- Generate only after Stage 1/2 define safe contact and action ranges.
- Conservative target: `5 contact points x 3 materials x 1 boundary x 8 directions x 4 magnitudes = 15 groups, 480 samples`.
- Boundary-condition target: `5 x 3 x 2 x 8 x 4 = 30 groups, 960 samples`.
- Every broader contact set must pass a candidate contact smoke test or use a surface-aware sampler before full generation.
- Acceptance: validator passes, each group has `K >= 32`, metadata tracks factors, and failed contact candidates are not used for conclusions.

Stage 4: shared-basis generalization.

- Learn shared basis from train groups and reconstruct held-out groups.
- Splits: held-out contact, held-out material, held-out contact+material.
- Compare group-local basis, shared basis, nearest-group basis, and zero-response baseline.
- Acceptance: answers whether a shared global basis is enough or whether NJF must predict condition-dependent local Jacobian/basis from `X, p, theta, B`.

Interpretation cases:

- Group-local low rank plus cross-group similarity: shared low-dimensional response structure.
- Group-local low rank but poor cross-group reconstruction: condition-dependent local basis; this supports NJF.
- No group-local low rank: investigate action size, contact stability, solver noise, nonlinear mixing, time-step mixing, correspondence, material, or boundary control.

Result-table plan: `docs/EXPERIMENT_DESIGN.md` now defines the required tables for per-group low-rank summary, pairwise basis similarity matrices, metadata-grouped comparisons, material scale-vs-pattern analysis, linearity/superposition, and shared-basis decisions. Stage 1 implementation should use that document as the output contract for `analyze_basis_across_groups.py`.

## Stage 1 Cross-Group Basis Analysis Result

Implemented command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid
```

Generated outputs are under the ignored dataset output tree:

```text
tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid/analysis/basis_across_groups/
```

The experiment fixes group-local geometry/state/boundary/contact/material/tool/solver and varies only action direction and small action magnitude inside each group. Across groups, the current batch varies contact point and Young's modulus while keeping boundary and Poisson ratio fixed.

Collected data:

- `responses.npy` as `[K, N, 3]` response fields per group;
- `actions.npy` for direction/magnitude metadata;
- `group_metadata.json` for `contact_point_id`, `material_id`, `boundary_id`, Young's modulus, Poisson ratio, and contact point world coordinates.

Main output tables:

- `per_group_metrics.csv`: effective rank, top-k explained variance, leave-one-action-out error, response norms;
- `projection_similarity.csv`: pairwise basis overlap;
- `principal_angles_mean.csv` and `principal_angles_max.csv`: pairwise subspace angles;
- `cross_reconstruction_error.csv`: how well basis from group `i` reconstructs responses from group `j`;
- `metadata_grouped_summary.csv`: same-contact/different-material and same-material/different-contact summaries;
- `material_scale_pattern.csv`: raw-vs-normalized material comparison;
- `decision_summary.md` and `summary.json`: machine-readable and human-readable conclusions.

Current result on six groups:

```text
effective_rank_mean=1.903
top2_cumulative_explained_mean=0.963488
offdiag_cross_reconstruction_error_mean=0.728994
same_contact_diff_material: projection_similarity_mean=0.928783, cross_reconstruction_error_mean=0.267751
same_material_diff_contact: projection_similarity_mean=0.285415, cross_reconstruction_error_mean=0.840230
diff_contact_diff_material: projection_similarity_mean=0.262767, cross_reconstruction_error_mean=0.848380
```

Question answered: group-local responses are low-dimensional, but bases do not transfer well across contact points in the current dataset. Same-contact/different-material basis subspaces are much more aligned than different-contact subspaces, but normalized material reconstruction errors remain non-trivial; do not claim material is only a scalar stiffness factor yet.

Next task: Stage 2 action-magnitude linearity and direction-superposition analysis. This should answer what small-action range is valid for local NJF supervision and whether directional responses approximately add.

## Stage 2 Action Linearity And Superposition Result

Implemented command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_action_linearity.py tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid
```

Generated outputs are under the ignored dataset output tree:

```text
tissue_dataset_v0/outputs/sofa_njf_basis_batch_valid/analysis/action_linearity/
```

The experiment uses existing Mode B groups. Within each group, geometry/state/material/boundary/contact/tool/solver remain fixed. The analysis varies:

- action magnitude for scale-linearity checks;
- matched x/y/diagonal tangent direction residuals around the normal baseline for superposition checks.

Collected data:

- `actions.npy` for direction and magnitude;
- `responses.npy` for `[K, N, 3]` response fields;
- `group_metadata.json` for contact/material IDs and material values.

Main output tables:

- `linearity_by_direction.csv`: per group/direction/magnitude scale error relative to the smallest magnitude;
- `linearity_summary_by_magnitude.csv`: aggregate scale error by magnitude;
- `linearity_summary_by_group.csv`: aggregate scale error by group;
- `superposition_tests.csv`: tangent residual superposition tests around normal baseline;
- `superposition_summary_by_group.csv`: aggregate superposition error by group;
- `summary.json` and `decision_summary.md`: machine-readable and human-readable conclusions.

Current result:

```text
linearity_tests=96
linearity_mean_relative_scale_error=1.785657
linearity_p90_relative_scale_error=2.689482
linearity_by_magnitude: 0.1 mm mean=0.935031, 0.2 mm mean=2.636283
superposition_tests=54
superposition_mean_relative_error=0.067291
superposition_p90_relative_error=0.116776
superposition_max_relative_error=0.156394
```

Question answered: current grouped data does not satisfy magnitude scale-linearity, so it should not be used as strict local-Jacobian magnitude supervision as-is. Tangent-direction residuals around the normal baseline approximately satisfy superposition, which supports keeping the directional action design, but action depth/contact semantics need diagnosis.

Next task: inspect why `0.05 mm` already produces nearly the same response norm as `0.1` and `0.2 mm`. Check action depth semantics, initial contact state, contact saturation, settling procedure, and position-controlled probe setup. Then generate a smaller incremental Stage 2 probe such as `0.01`, `0.02`, and `0.05 mm` before expanding to larger magnitudes.
