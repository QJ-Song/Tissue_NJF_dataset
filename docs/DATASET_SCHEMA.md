# Dataset Schema

## Scope

This document defines the target minimal schema for one simulation episode. The current `tissue_dataset_v0` implementation writes both final supervised sample artifacts and simulation-time logs. The target episode schema should remain compatible with offline replay and future training.

## Minimal Episode Fields

At minimum, one episode should be able to provide:

```text
episode_id
frame_id
simulation_time or timestamp
tool_pose
tool_velocity, if available
action
tissue_vertex_positions
tissue_vertex_velocities, if available
contact_point, if available
contact_force, if available
contact_normal, if available
material_parameters
camera_rgb
camera_depth, if available
camera_segmentation, if available
metadata
```

Current `tissue_dataset_v0` artifacts include `vertices_0`, `vertices_1`, `displacement`, `faces`, `action`, `contact_point`, `material`, `meta`, and `sample_manifest.json`. Current logs include request, summary, timeline, events, and per-frame `vertices` arrays.

Current compact press `action.npy` uses six values:

```text
[contact_x, contact_y, dir_x, dir_y, dir_z, depth]
```

`dir_*` should be a unit vector. Press-like actions require `dir_z < 0`. Existing vertical samples use `(0, 0, -1)`; directional Stage A samples use a bounded upper-hemisphere cone while keeping the same required `action.npy` shape.

## Recommended First-Stage Storage Layout

```text
dataset/
  episode_000001/
    meta.json
    actions.npy
    tool_pose.npy
    vertex_pos.npy
    vertex_vel.npy
    contact.npy
    rgb/
      000000.png
      000001.png
    depth/
      000000.npy
      000001.npy
```

The current sample naming convention uses `sample_000001/`. It can be kept for sample-level outputs, but future sequence datasets should clearly distinguish `sample_*` final artifacts from `episode_*` trajectory logs.

## Current `tissue_dataset_v0` Layout

```text
sample_000001/
  vertices_0.npy
  vertices_1.npy
  displacement.npy
  faces.npy
  action.npy
  contact_point.npy
  material.json
  meta.json
  sample_manifest.json
  logs/
    request.json
    summary.json
    timeline.jsonl
    events.jsonl
    frames/
      frame_000000.npz
      frame_000000.json
```

## Large-Scale Storage Options

Large-scale data can later move to:

```text
HDF5
Zarr
NPZ
```

Choose the storage backend based on random access needs, expected dataset size, compression, and compatibility with training code.

## Validation Requirements

- All frame-dependent arrays must have the same number of frames.
- `meta.json` must include seed, config path, scene version, material parameters, generation timestamp, and software version if detectable.
- Offline replay must be possible from saved states.
- Dataset generation should not silently append to or overwrite existing episodes. Existing non-empty sample directories must fail by default; explicit `--overwrite` is required to regenerate them.
- Every episode should be reproducible as much as possible through seed and config metadata.
- `sample_manifest.json` or an equivalent manifest should state which artifacts exist, their dtype/shape, and whether optional data is missing.
- Replay must not depend on live simulator state unless testing reproducibility.

## Episode Trajectory Interface

The current trajectory layer is implemented under `tissue_dataset_v0/src/tissue_dataset_v0/trajectory/`. It does not change existing `sample_*` artifacts; it provides a stable semantic reader over saved logs.

Current frame interface:

```text
TrajectoryFrame
  frame_id
  step_index
  time_code
  arrays
  scalars
  source_npz
  source_json
```

Current reader interface:

```text
EpisodeTrajectoryReader(sample_dir, log_dir_name="logs")
  iter_frames(start=None, stop=None, stride=1)
  iter_transitions(stride=1)
  build_summary()
  write_summary()
```

New samples generated through `DatasetPipeline.generate()` write:

```text
logs/trajectory_summary.json
```

The summary records frame count, first/last step, first/last time, array keys, scalar keys, sample id, scene id, simulator, backend, material, logging config, and source files. Older samples can be upgraded without rerunning simulation:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/write_trajectory_summary.py path/to/sample_000001
```

Replay should depend on this trajectory interface. Validator should validate this summary when present and warn, not fail, when old samples do not have it yet.

## Optional Tool Motion Fields

Stage D2 adds optional tool motion artifacts for `probe_contact` samples when `sofa_record_tool_motion: true`:

```text
tool_pose_0.npy      # [4, 4], initial tool pose in meters
tool_pose_1.npy      # [4, 4], final tool pose in meters
tool_geometry.json   # tool type/radius/frame/unit metadata
```

These fields are enabled in the layout but remain `required=false`. Old samples and non-contact samples may omit them. For the current sphere probe, the translation column of each pose is the sphere center, and `tool_geometry.json` uses `frame: tool_pose_center`. Stage D4 maps `ActionSpec.vector[2:5]` to the saved probe center displacement, with `tool_geometry.json` recording `motion_direction_source: action_vector_2_4`. Per-frame logs may include scalar `tool_position` and `tool_radius`; offline replay should prefer saved tool poses when present and fall back to action/contact-derived visualization otherwise.

The D2 checker is:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_motion.py path/to/dataset
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py path/to/dataset
```


## Optional Contact Summary Fields

Stage D3 adds an optional contact/proximity summary for `probe_contact` samples when `sofa_record_contact_summary: true`:

```text
contact_summary.json
```

The first D3 implementation uses geometric sphere-to-vertex signed gap, not exported SOFA contact forces. Per-frame logs may include:

```text
contact_active
signed_gap
contact_distance
penetration_depth
contact_point_observed
nearest_contact_vertex_index
```

Current `contact_summary.json` fields include `contact_detected`, `first_contact_step`, `first_contact_time`, `contact_frame_count`, `observation_count`, `min_signed_gap`, `max_penetration`, `contact_distance`, `alarm_distance`, `method: sphere_to_vertex_gap`, `force_available: false`, and nearest-point metadata at minimum gap. Contact force and contact normal remain unavailable in D3 and should not be treated as required fields.

The D3 checker is:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py path/to/dataset
```

## Optional Boundary and Solver Metadata Fields

Stage D5 adds optional boundary and solver metadata artifacts for SOFA samples when `sofa_record_boundary_solver: true`:

```text
fixed_node_indices.npy
free_node_indices.npy
boundary_mask.npy
boundary.json
solver_summary.json
```

The current boundary implementation records the bottom-layer `FixedProjectiveConstraint` used by `SofaFemBackend`, including fixed/free node counts and a boundary box in meters. `boundary_mask.npy` is a boolean mask over mechanical vertices.

The current solver summary records solver component names and configured parameters such as `dt`, total/settling steps, record interval, ODE solver, linear solver, constraint solver, finite-state validity, and max displacement. SOFA residual/convergence is not reliably exported in D5; `solver_converged` and `solver_residual` may be `null`, with `solver_status_method: finite_state_check_only`.

The D5 checker is:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py path/to/dataset
```

## SOFA NJF Dataset v1 Layout

The NJF dataset target extends the current single-sample layout with dataset-level groups and trajectories. It should support three modes:

```text
Mode A: local perturbation samples
Mode B: response basis groups
Mode C: multi-step rollout trajectories
```

Recommended root layout:

```text
dataset_root/
  metadata.json
  config.yaml
  samples/
  groups/
  trajectories/
  splits.json
```

Mode A stores local small-step records:

```text
X_t
delta_a
X_next
delta_X
```

Mode B stores fixed-contact response basis groups. Within one group, `state_id`, `material_id`, `boundary_id`, `contact_point_id`, tool geometry, and solver config must remain fixed; only action direction and magnitude should vary. Suggested group artifacts:

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

Current Mode B smoke implementation writes these group artifacts under `dataset_root/groups/group_000001/` and references the underlying `sample_*` records used to assemble the group. It validates that `state_initial`, `contact_point`, `state_id`, `material_id`, `boundary_id`, and `contact_point_id` stay fixed while `action.npy` varies. Smoke groups may use `K = 3`; response-basis analysis should generate `K >= 12`.

Mode C stores multi-step rollout trajectories:

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

Current Mode C smoke implementation writes these artifacts under `dataset_root/trajectories/traj_000001/`. It also keeps the rollout source SOFA run as a normal `sample_*` record for traceability. The validator checks `responses == states[1:] - states[:-1]`, per-step action magnitude, fixed-node stability, shape consistency, finite arrays, and source sample existence.

The first NJF dataset should use small action magnitudes such as `0.05`, `0.1`, and `0.2` mm. Larger actions for rollout should be decomposed into small steps, not stored only as one final deformation.

NJF dataset validation should check:

- `delta_X == X_next - X_t`;
- `responses[k] == states[k+1] - states[k]`;
- group fixed variables remain fixed;
- group contact point remains fixed;
- trajectory state count equals action count plus one;
- fixed-node displacement is near zero;
- no NaN/Inf values;
- action magnitude is within configured small-step ranges;
- required material, boundary, contact, tool, solver, seed, and config metadata are present.

## Current SOFA Sample Field Inventory

The current SOFA `sample_*` layout is still the storage atom used by the NJF orchestration layer. Mode A writes one `sample_*` per local perturbation under `dataset_root/samples/`. Mode B and Mode C should reuse these fields when assembling group and trajectory arrays.

| Field | Meaning | Mode A | Mode B | Mode C | Notes |
| --- | --- | --- | --- | --- | --- |
| `vertices_0.npy` | `X_t`, mechanical node positions before the action, meters | required | source for `state_initial.npy` and responses | source for `states[k]` | Current smoke shape is `[N, 3]`. |
| `vertices_1.npy` | `X_next`, mechanical node positions after settling | required | source for per-action response checks | source for `states[k+1]` | In Mode C this should become a sequence artifact rather than only final state. |
| `displacement.npy` | `delta_X = X_next - X_t` | required | columns of response matrix | source for `responses[k]` | Validator checks consistency with vertices. |
| `faces.npy` | Current surface/visual connectivity for replay and geometry checks | useful | useful for `surface_points` context | useful for replay | Optional for model input; needed for visualization. |
| `action.npy` | Compact action `[contact_x, contact_y, dir_x, dir_y, dir_z, depth]` | required | varied variable inside group | per-step action | `dir_*` is a unit vector; current probe mode expects `dir_z < 0`. |
| `contact_point.npy` | Requested fixed material/geometric action anchor | required | fixed inside one basis group | per-step or fixed anchor | For v1, Mode A/B prioritize `fixed_material_point`. |
| `material.json` | Young's modulus, Poisson ratio, density, damping, boundary-condition label | required | fixed or controlled variable by group | fixed along trajectory unless explicitly varied | This is `theta` for NJF. |
| `meta.json` | Sample id, scene id, simulator, unit, notes, backend extras | required | required provenance | required provenance | Mode A adds `meta.extra.njf_mode`, ids, action direction, and contact mode. |
| `sample_manifest.json` | Declares present artifacts, shapes, dtypes, optional/required status | required | required for sample discovery | useful for per-step provenance | Keeps optional fields backward compatible. |
| `tool_pose_0.npy` | Initial tool pose, `[4, 4]`, probe-center frame | required for NJF SOFA samples | fixed initial pose for each action in group | `tool_poses[k]` | Added in D2. |
| `tool_pose_1.npy` | Final tool pose after the action | required | per-action varied result | `tool_poses[k+1]` | D4 makes actual motion match `action[2:5]`. |
| `tool_geometry.json` | Tool type, radius, frame, motion direction source | required | fixed inside group | fixed unless tool changes | Current v1 tool is a sphere probe. |
| `contact_summary.json` | Geometric contact/proximity status and signed-gap summary | required for NJF validation | required for filtering group actions | per-step status source | D3 does not provide reliable force/normal yet. |
| `fixed_node_indices.npy` | Mechanical nodes fixed by boundary constraints | required | fixed inside group | fixed along trajectory | Needed for boundary condition `B`. |
| `free_node_indices.npy` | Mechanical nodes not fixed by boundary constraints | required | fixed inside group | fixed along trajectory | Useful for training masks and QA. |
| `boundary_mask.npy` | Boolean fixed-node mask over mechanical nodes | required | written as `fixed_node_mask.npy` in groups | required trajectory metadata | Validator checks fixed-node displacement. |
| `boundary.json` | Boundary type, box, fixed/free counts, units | required | fixed inside group | fixed along trajectory | Current boundary is bottom fixed. |
| `solver_summary.json` | SOFA solver names, dt, step count, validity, tolerances | required | fixed inside group | per-trajectory/per-step QA | Residual/convergence may be unavailable; finite-state validity is used. |
| `logs/frames/*.npz` | Simulation-time arrays, usually vertices per logged step | optional but useful | optional QA | temporary source for Mode C until explicit trajectories exist | Replay reads saved states only. |
| `logs/frames/*.json` | Per-frame scalars: contact status, gap, observed contact point, tool position | useful | useful for basis diagnostics | important for per-step contact metadata | Current fields are scalar summaries, not full SOFA contact force. |
| `logs/trajectory_summary.json` | Frame count, time range, available arrays/scalars, source files | useful | useful | useful | Supports replay and sequence QA. |

Current gaps relative to full Mode A/B/C: contact force is not reliably exported; Mode B `groups/` artifacts are generated for smoke-sized fixed-contact response basis groups, but the stored `contact_normal.npy` is currently an approximate upward normal for the fixed-topology surface. Mode C `trajectories/` artifacts are generated for smoke-sized continuous rollout source samples, with per-step actions and responses extracted from logged intermediate frames.

## Dataset Reader

The current model-agnostic sample reader lives under `tissue_dataset_v0/src/tissue_dataset_v0/dataset/`. `TissueSampleDataset` discovers `sample_*` directories, reads each `sample_manifest.json`, and loads artifacts declared as `present`. The returned `SampleRecord` stores artifacts by name rather than by a fixed dataclass field list. This keeps the reader compatible with optional future fields such as tool poses, contact force, normals, RGB, depth, masks, or per-vertex attributes.

Reader behavior:

- default mode loads all present artifacts declared in the manifest;
- `artifact_names` can restrict loading to a model-specific subset;
- `require_artifacts` can enforce the fields a given experiment needs;
- `summary()` reports loaded artifact names, array shapes, dtypes, material keys, and whether each array shape is fixed across the dataset.

Smoke command:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py path/to/dataset_root
```

This reader is not yet a PyTorch Dataset and does not define batching, normalization, train/val splits, or model inputs. Those should be added only after the model family is chosen. For Stage C geometry randomization, the current implementation randomizes `size_x`, `size_y`, and `thickness` while keeping `nx`, `ny`, and `layers` fixed, so direct array batching remains possible. Variable topology will need a model-specific collate function.

## Validator

The current validator entry point is:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/validator_smoke/sample_990001
```

The validator is implemented as a pluggable rule system under `tissue_dataset_v0/src/tissue_dataset_v0/validation/`. The default profile checks:

- sample directory and `sample_manifest.json`;
- manifest-to-file consistency for declared artifacts;
- `.npy` shape and dtype consistency against the manifest;
- core array consistency, including `displacement == vertices_1 - vertices_0`;
- mesh face index validity;
- metadata/request/material consistency for shared scalar keys;
- `logs/timeline.jsonl`, referenced `logs/frames/*.npz`, and referenced `logs/frames/*.json`;
- duplicate or non-increasing timeline steps;
- `logs/trajectory_summary.json` consistency when present.

External rules can be added without changing the CLI:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py \
  path/to/sample_000001 \
  --rule my_package.validation:IsaacSimSpecificRule
```

This design is intended to handle future parameter additions, optional fields, and simulator migration. Current rules treat unknown optional artifacts conservatively and validate only fields that are declared in the manifest or present in logs. Simulator-specific requirements should be added as extra rules or future profiles, not hard-coded into the default validator.

## Notes for Future Fields

Useful extensions include camera intrinsics/extrinsics, segmentation IDs, per-vertex boundary masks, contact force vectors, tool geometry identifiers, material randomization metadata, and scene asset versions.
