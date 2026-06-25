# SOFA NJF Dataset Design

## Purpose

The first SOFA NJF dataset should support local small-step response learning and rollout validation. It should not be a collection of single large tool presses.

The target local model is:

```text
delta_X = J_phi(X, p, theta, B) * delta_a
```

where:

- `X` is the current tissue state;
- `p` is the current contact point or action anchor;
- `theta` is material metadata such as Young's modulus and Poisson ratio;
- `B` is boundary condition metadata such as fixed-node masks;
- `delta_a` is a small tool action;
- `delta_X` is the resulting tissue response.

Large one-step actions, such as `1 mm` directly supervised as a single response, are not a clean local Jacobian target. They are closer to a secant or average response over a finite interval. NJF v1 should therefore prioritize small actions such as `0.05`, `0.1`, and `0.2` mm.

## Dataset Modes

### Mode A: Local Perturbation

Mode A is the training atom for local NJF. Each record is one small action step:

```text
X_t
delta_a
X_next
delta_X = X_next - X_t
```

Each step must also save material, boundary, contact, tool, solver, and seed/config metadata.

### Mode B: Response Basis Group

Mode B validates whether one local contact point has a low-dimensional response basis.

Within one group, fix:

```text
state_id
material_id
boundary_id
contact_point_id
tool geometry
solver config
```

Within one group, vary only action direction and action magnitude.

Do not mix contact points in one response basis group. The contact point defines the local response operator. Mixing contact points would mix spatial variation with action variation and make PCA/SVD results hard to interpret.

The response matrix is:

```text
R_p = [delta_X_1, delta_X_2, ..., delta_X_K]
```

Smoke tests may use `K = 3`; basis analysis should target `K >= 12`, preferably `K = 24` or `32`. The group should include multiple action directions and magnitudes. Vertical-only groups test only normal-direction compliance and small-step stability; they are acceptable for smoke/debug/regression, but not sufficient for the complete v1 response-basis dataset.

### Mode C: Multi-Step Rollout

Mode C tests whether small-step NJF predictions can integrate to larger deformations.

Large tool motion should be split into small steps:

```text
1.0 mm = 10 steps * 0.1 mm
```

Each trajectory must save all intermediate states:

```text
states.npy       # [T+1, N, 3]
actions.npy      # [T, action_dim]
responses.npy    # [T, N, 3]
tool_poses.npy   # [T+1, pose_dim]
contact_points.npy
contact_normals.npy
solver_status.json
```

This enables comparison of:

- single-step deformation prediction;
- single-step NJF with a large action;
- rolling NJF with small actions.

## Contact Point Semantics

The schema should support two contact point modes:

1. `fixed_material_point`: keep the same material/surface point as the action anchor. This is the v1 priority for local perturbation and basis validation.
2. `recomputed_geometric_contact`: recompute the actual closest/current surface contact point each step. This is closer to real tool motion and can remain a later TODO.

For rollout trajectories, per-step contact point fields should be saved even when using `fixed_material_point`.

## Architecture

Keep the current single-sample pipeline:

```text
SampleRequest -> SimulationBackend.simulate() -> SampleResult -> FileSystemSampleWriter
```

Add a thin NJF dataset orchestration layer above it:

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/
  plan.py
  modes.py
  recorder.py
  validate.py
```

The SOFA backend should remain focused on physics. Group, rollout, split, and response-basis logic should live in the NJF orchestration layer.

## Target Layout

```text
dataset_root/
  metadata.json
  config.yaml
  samples/
  groups/
  trajectories/
  splits.json
```

Existing `sample_*` artifacts remain valid for legacy single-step data. NJF v1 adds group and trajectory outputs.

## Current Implementation Status

The lightweight orchestration layer now exists under `tissue_dataset_v0/src/tissue_dataset_v0/njf/`:

```text
njf/schema.py      # plan/action dataclasses
njf/plan.py        # YAML -> NJFDatasetPlan and Mode A SampleRequest builders
njf/modes.py       # implemented Mode A generation
njf/recorder.py    # dataset root, metadata, config copy, splits
njf/validate.py    # dataset-level Mode A validator
```

Implemented commands:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/run_njf_smoke_test.py --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_njf_dataset.py --config tissue_dataset_v0/configs/sofa_njf_dataset.yaml --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_mode_a_smoke
```

The current `sofa_njf_dataset.yaml` smoke config implements Mode A only. It writes three local perturbation samples using `0.05`, `0.1`, and `0.2` mm downward actions under `dataset_root/samples/`, plus dataset-level `metadata.json`, copied `config.yaml`, empty `groups/`, empty `trajectories/`, and `splits.json`. Mode B and Mode C directories are intentionally present as placeholders, but group and trajectory artifacts are not yet generated.

## Validation Requirements

The NJF dataset validator should check:

- `delta_X == X_next - X_t`;
- `responses[k] == states[k+1] - states[k]`;
- group fixed variables remain fixed;
- group contact point remains fixed;
- trajectory state count equals action count plus one;
- fixed-node displacement is near zero;
- no NaN/Inf values;
- action magnitude is within configured small-step ranges;
- metadata includes material, boundary, solver, tool, contact, seed, and config information;
- solver/contact status indicates a valid sample or explicit failure.

## Priority Plan

1. Update task/design context for NJF Mode A/B/C.
2. Finish Stage D3 contact summary.
3. Finish Stage D5 boundary and solver metadata.
4. Finish D4 small-step directional probe motion for complete response-basis data; keep vertical-only only as smoke/debug/regression.
5. Add the lightweight `njf/` orchestration layer. Done for Mode A.
6. Implement Mode A local perturbation. Done for the current smoke config.
7. Implement Mode B response basis groups. Next.
8. Implement Mode C rollout trajectories.
9. Extend dataset-level validation from Mode A to groups and trajectories.
10. Add split metadata and a small demo dataset command beyond smoke.

## Deferred Work

The following should remain outside v1 unless required by validation failure:

- surface collision;
- material heterogeneity;
- anisotropy;
- grasper contact;
- friction studies;
- cutting, puncture, tearing, suturing;
- photorealistic rendering;
- full robot dynamics.
