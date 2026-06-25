# Task: SOFA Stage D Probe Contact Plan

## Goal

Plan Stage D before implementation. Stage D should replace or augment the current localized probe-force approximation with a more physical SOFA probe/contact interaction while preserving the existing dataset pipeline, replay separation, manifest-driven loader, and randomization-axis independence from Stage A/B/C.

## Current State

Current `SofaFemBackend` supports:

- fixed or randomized liver-like geometry with fixed topology;
- randomized action, material, and geometry axes;
- localized top-surface force around `ActionSpec.contact_point`;
- core sample artifacts: `vertices_0`, `vertices_1`, `displacement`, `faces`, `action`, `contact_point`, `material`, `meta`;
- simulation-time vertex logging;
- offline replay/Isaac USD export;
- manifest-driven dataset reading.

Limitation: the probe is not a physical SOFA rigid body or collision/contact object. The replay tool sphere remains a visual marker.

## Design Principle

Stage D must be incremental. Do not replace the current backend behavior in-place. Add a new interaction mode and keep the current localized force mode available for regression:

```yaml
backend:
  type: sofa_fem
  extra:
    sofa_interaction_model: localized_probe_force  # existing behavior
    # or
    sofa_interaction_model: probe_contact          # Stage D target
```

New fields should be optional and manifest-declared. Existing Stage A/B/C data must remain readable and valid. Default validator rules should continue to check core sample integrity; contact-specific checks should be separate.

## Proposed Stage D Segments

### D0: Standalone SOFA Contact Prototype

Goal: prove SOFA contact can run headlessly before touching the dataset pipeline.

Proposed file:

```text
scripts/prototype_sofa_probe_contact.py
```

Prototype should include:

- deformable FEM tissue, preferably the current liver-like or a simplified slab first;
- rigid or kinematic sphere/capsule probe;
- SOFA collision/contact pipeline;
- vertical press motion;
- summary output with displacement and contact/proximity indicators.

Acceptance criteria:

- runs headlessly in `$HOME/conda/envs/sofa`;
- completes all steps;
- no NaN/Inf;
- visible bounded deformation, roughly `0.5 mm` to `5 mm`;
- probe motion and tissue deformation directions are coherent.

No dataset writing in D0.

Implementation result:

- Status: implemented on 2026-06-24 as `scripts/prototype_sofa_probe_contact.py`.
- Scope: standalone prototype only; it does not import `tissue_dataset_v0`, does not write `sample_*` data, and does not change dataset schema.
- Scene: simplified FEM slab, bottom fixed constraint, kinematic sphere probe, SOFA collision pipeline, vertical probe motion.
- SOFA 25.06 component names used: `CollisionPipeline` and `CollisionResponse`; older aliases `DefaultPipeline` and `DefaultContactManager` are not available in this install.
- Contact/proximity is currently summarized from sphere-to-vertex signed gap and the configured SOFA `contactDistance`; no reliable SOFA contact force is exported yet.

Smoke command:

```bash
scripts/run_sofa_python.sh scripts/prototype_sofa_probe_contact.py --format json
```

Observed result with defaults:

```text
valid: true
steps: 160
dt: 0.005
probe radius: 10 mm
probe z: 29.0 mm -> 16.5 mm
contact/proximity first step: 103
contact/proximity frames: 58
min signed gap: 1.922 mm
max displacement: 4.422 mm
max downward z displacement: 4.422 mm
max upward z displacement: 0.116 mm
```

Interpretation: D0 proves that a headless SOFA contact/collision pipeline can drive bounded tissue deformation without using the existing localized `ConstantForceField`. This is still a prototype, not a dataset backend. D1 should port the same pattern into `SofaFemBackend` behind a new interaction mode without schema expansion.

### D1: Backend Mode, No Schema Expansion

Goal: add `sofa_interaction_model: probe_contact` to `SofaFemBackend` while still writing only the existing core artifacts.

Acceptance criteria:

- add a contact YAML, for example `sofa_liver_contact_d1.yaml`;
- one sample generates through `DatasetPipeline`;
- `validate_sample.py` passes;
- `check_stage_a.py` or a minimal contact sanity passes for bounded displacement;
- `read_dataset_smoke.py` passes;
- Isaac USD replay exports saved tissue states without rerunning SOFA.

Implementation result:

- Status: implemented on 2026-06-24.
- `SofaFemBackend` now supports `sofa_interaction_model: localized_probe_force` and `sofa_interaction_model: probe_contact`.
- `localized_probe_force` remains the backward-compatible default and was regression-generated successfully from a temporary config.
- `probe_contact` uses SOFA `FreeMotionAnimationLoop`, `GenericConstraintSolver`, collision pipeline, `PointCollisionModel` on tissue vertices, and a kinematic `SphereCollisionModel` probe.
- D1 still writes only the existing core artifacts. With `sofa_record_tool_motion: false`, `tool_pose_0`, `tool_pose_1`, and `tool_geometry` remain absent/present=false.
- The probe currently moves vertically from `contact_point`; directional tool-pose mapping is deferred to a later extension after D2.

New config:

```text
tissue_dataset_v0/configs/sofa_liver_contact_d1.yaml
```

Generated sample:

```text
tissue_dataset_v0/outputs/sofa_liver_contact_d1/sample_000001
```

Observed D1 result:

```text
sofa_interaction_model: probe_contact
vertex_count: 252
face_count: 180
frame_count: 17
max displacement: 3.952 mm
max downward z displacement: 3.80 mm
max displacement contact distance: 2.73 mm
```

Verification commands run:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d1.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d1/sample_000001
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_contact_d1 --min-samples 1 --min-max-displacement-mm 0.5 --max-max-displacement-mm 5.0 --max-downward-z-mm 5.0 --min-contact-spread-mm 0 --min-depth-spread-mm 0 --max-contact-distance-mm 35.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d1/sample_000001 --viewer summary --stride 1 --max-print 3
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d1/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

Results: validator passed with zero errors/warnings, contact sanity passed, dataset reader passed, summary replay reported 17 frames from step 0 to 160, and Isaac USD replay exported `sample_000001/replay_isaacsim/isaacsim_replay.usda`.

Remaining limitation: D1 does not yet record actual tool poses or contact summary artifacts. It also does not expose reliable SOFA contact force or contact normal. D2 should add optional tool motion fields first.

### D2: Tool Motion Fields

Goal: record the actual probe motion so replay and training can know what the tool did.

Recommended optional final artifacts:

```text
tool_pose_0.npy
tool_pose_1.npy
tool_geometry.json
```

Recommended per-frame log fields:

```text
tool_position
tool_pose, if reliable
tool_velocity, if reliable
tool_radius or tool geometry id
```

Notes:

- `layout.py` already has optional disabled `tool_pose_0` and `tool_pose_1`. In Stage D they should become optional enabled specs (`required=False`, `enabled=True`) only when backend can provide them reliably.
- `tool_geometry.json` should be optional and describe sphere/capsule radius, type, and local frame.
- Do not make these fields required for old samples.

Acceptance criteria:

- old Stage A/B/C samples still validate/read;
- D2 sample manifest marks tool fields present;
- replay can still fallback if tool fields are absent.

Implementation result:

- Status: implemented on 2026-06-24.
- `tool_pose_0.npy` and `tool_pose_1.npy` are now enabled optional artifacts in `layout.py`.
- `tool_geometry.json` was added as an enabled optional artifact.
- `SofaFemBackend` writes these tool artifacts for `sofa_interaction_model: probe_contact` only when `sofa_record_tool_motion: true`; D1 and localized-force samples keep them absent/present=false.
- Tool poses are `4x4` matrices in meters. The translation column is the sphere center.
- `tool_geometry.json` currently records `type: sphere`, `radius`, `frame: tool_pose_center`, `unit: meter`, and `source: sofa_probe_contact`.
- Per-frame logs now include `tool_position` and `tool_radius` when probe_contact is active.
- `IsaacSimReplayViewer` now prefers saved `tool_pose_0/tool_pose_1/tool_geometry` for the gray probe sphere; if absent, it falls back to the older action/contact-derived marker path.
- `scripts/check_tool_motion.py` was added to validate D2 tool fields and log consistency.

New config:

```text
tissue_dataset_v0/configs/sofa_liver_contact_d2.yaml
```

Generated sample:

```text
tissue_dataset_v0/outputs/sofa_liver_contact_d2/sample_000001
```

Observed D2 result:

```text
tool_pose_0 xyz: [0.0, 0.0, 0.0290]
tool_pose_1 xyz: [0.0, 0.0, 0.0165]
tool z drop: 12.5 mm
tool radius: 10 mm
max log/pose mismatch: ~8.3e-7 mm
max tissue displacement: 3.95 mm
frame_count: 17
```

Verification commands run:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/layout.py tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py tissue_dataset_v0/src/tissue_dataset_v0/replay/isaacsim.py
python3 -m py_compile tissue_dataset_v0/scripts/check_tool_motion.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d2.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d2/sample_000001
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_contact_d2 --min-samples 1 --min-max-displacement-mm 0.5 --max-max-displacement-mm 5.0 --max-downward-z-mm 5.0 --min-contact-spread-mm 0 --min-depth-spread-mm 0 --max-contact-distance-mm 35.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d2 --require tool_pose_0 --require tool_pose_1 --require tool_geometry
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_motion.py tissue_dataset_v0/outputs/sofa_liver_contact_d2 --min-samples 1 --min-z-drop-mm 1.0 --max-z-drop-mm 20.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d2/sample_000001 --viewer summary --stride 1 --max-print 3
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d2/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

Results: validator passed, bounded-displacement sanity passed, dataset reader required all D2 tool artifacts successfully, tool motion check passed, summary replay included `tool_position`/`tool_radius` scalar keys, and Isaac USD export wrote `sample_000001/replay_isaacsim/isaacsim_replay.usda`. D1 replay fallback was also re-exported successfully after the replay change. Temporary flag-check samples confirmed that `sofa_record_tool_motion: false` omits tool artifacts while `true` writes and validates them. A temporary localized-force sample generated and validated successfully with tool artifacts absent, confirming backward compatibility.

Remaining limitation: D2 still uses vertical probe motion for saved tool poses. Mapping directional `action[2:5]` to oblique probe pose/motion remains a future extension before broad directional contact data. Contact force, normal, first-contact step, and penetration summaries are deferred to D3.

### D3: Contact Summary and Contact Logs

Goal: record evidence that contact occurred and provide first usable contact-conditioned labels.

Recommended optional final artifact:

```text
contact_summary.json
```

Suggested summary fields:

```json
{
  "contact_detected": true,
  "first_contact_step": 42,
  "contact_frame_count": 50,
  "max_contact_force": 1.23,
  "mean_contact_force": 0.42,
  "max_penetration": 0.001
}
```

Recommended per-frame log fields, only if reliable:

```text
contact_active
contact_force
contact_normal
contact_point_observed
penetration_depth
```

Do not start with all SOFA contact pairs as required artifacts. Use summary/scalars first, because contact pair formats may be unstable and difficult to batch.

Implementation result:

- Status: implemented on 2026-06-25.
- `contact_summary.json` is now an enabled optional artifact in `layout.py`.
- `SofaFemBackend` records contact/proximity for `probe_contact` samples when `sofa_record_contact_summary: true` using the same geometric sphere-to-vertex signed-gap method proven in D0.
- Per-frame logs now include `contact_active`, `signed_gap`, `contact_distance`, `penetration_depth`, `contact_point_observed`, and `nearest_contact_vertex_index` when contact summary recording is enabled.
- `contact_force` and `contact_normal` remain unavailable/not exported in D3; `contact_summary.json` records `force_available: false` and `contact_force_method: unavailable`.
- `scripts/check_contact.py` validates `contact_summary.json`, manifest presence, finite gap/penetration values, contact/proximity occurrence, and frame log contact scalars.
- New config: `tissue_dataset_v0/configs/sofa_liver_contact_d3.yaml`.
- Generated sample: `tissue_dataset_v0/outputs/sofa_liver_contact_d3/sample_000001`.

Observed D3 result:

```text
contact_detected: true
first_contact_step: 107
contact_frame_count: 54
observation_count: 161
min_signed_gap: 1.924 mm
max_penetration: 0.000 mm
logged contact-active frames: 6
force_available: false
```

Verification commands run:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/layout.py tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py tissue_dataset_v0/scripts/check_contact.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d3.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d3/sample_000001
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d3 --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_motion.py tissue_dataset_v0/outputs/sofa_liver_contact_d3 --min-samples 1 --min-z-drop-mm 1.0 --max-z-drop-mm 20.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_liver_contact_d3 --min-samples 1
```

Results: compile passed, sample generation passed, core validator passed with zero errors/warnings, reader smoke loaded `contact_summary`, D2 tool motion check still passed, and D3 contact check passed with zero errors/warnings.

### D4: Sequence-Level Tool/Contact Artifacts and Replay Upgrade

Only after D2/D3 are stable, consider sequence-level artifacts for training:

```text
tool_pose_seq.npy        # [T, 4, 4] or [T, 7]
contact_force_seq.npy    # [T, 3]
contact_active_seq.npy   # [T]
contact_point_seq.npy    # [T, 3]
```

Replay priority should become:

1. use `tool_pose_seq` if present;
2. else interpolate `tool_pose_0` to `tool_pose_1` if present;
3. else fallback to current action-derived visual marker.

Replay must remain offline and must not rerun SOFA physics.

## Field Expansion Strategy

### Keep Required Core Fields Stable

These remain required for all generated training samples:

```text
vertices_0
vertices_1
displacement
faces
action
contact_point
material
meta
```

### Add Optional Tool Fields First

Recommended optional artifacts for D2:

```text
tool_pose_0.npy
tool_pose_1.npy
tool_geometry.json
```

### Add Optional Contact Summary Next

Recommended optional artifact for D3:

```text
contact_summary.json
```

Potential later optional artifacts:

```text
contact_force.npy
contact_normal.npy
contact_active.npy
tool_pose_seq.npy
contact_force_seq.npy
contact_active_seq.npy
contact_point_seq.npy
```

### Layout Policy

Optional artifacts should generally be `required=False` and `enabled=True` once the writer should include them when present. Backend absence should result in `present=false` or omission, not failure. Avoid making contact fields required until the physical contact implementation and downstream readers are stable.

## Compatibility Requirements

- Keep `localized_probe_force` for Stage A/B/C regression.
- Add `probe_contact` as a new interaction model.
- Keep simulation-time logging separate from replay.
- Keep `validate_sample.py` default profile focused on core schema.
- Add contact-specific validation as either a new script (`scripts/check_contact.py`) or optional validator rule.
- Keep `TissueSampleDataset` manifest-driven; it should read optional tool/contact fields without code changes when they are present.
- Keep randomization axes independent: action, material, geometry, and interaction model should be configurable separately in YAML.


## Replanned Role for SOFA NJF Dataset v1

Update on 2026-06-25: Stage D should now be treated as the contact-physics foundation for the first SOFA NJF tissue-contact dataset, not as an open-ended push toward clinical contact realism.

The first NJF dataset needs stable, explainable, reproducible small-step probe-contact responses for local NJF training, response basis analysis, and rollout validation. Stage D should therefore prioritize:

- consistency between saved action vectors and actual probe motion;
- evidence that contact/proximity occurred;
- bounded, repeatable tissue deformation;
- optional but explicit per-step contact and tool metadata;
- backward compatibility with existing Stage A/B/C samples and replay.

Stage D should not block the first NJF dataset on complex surface collision, friction, grasper contact, cutting, puncture, or reliable SOFA contact-force export. Those can remain later extensions.

### Revised Remaining Stage D Work

#### D3: Contact Summary and Contact Logs

Priority: required before the NJF dataset v1 smoke dataset.

Goal: add lightweight sample-level and step-level contact summaries that prove contact/proximity occurred and give downstream code enough information to filter or analyze local perturbation, basis, and rollout samples.

Recommended optional final artifact:

```text
contact_summary.json
```

Recommended first fields:

```json
{
  "contact_detected": true,
  "first_contact_step": 103,
  "contact_frame_count": 58,
  "min_signed_gap": 0.0019,
  "max_penetration": 0.0,
  "contact_distance": 0.002,
  "method": "sphere_to_vertex_gap",
  "force_available": false
}
```

Recommended per-frame or per-step scalars for D3:

```text
contact_active
signed_gap
contact_distance
```

Do not make `contact_force` or `contact_normal` required in D3. Add them only if the installed SOFA contact setup exposes stable values that pass validation.

Acceptance criteria:

- D2 samples remain readable and valid.
- New D3 contact samples include `contact_summary.json` when contact summary recording is enabled.
- Step-level logs expose enough contact status to build rollout `contact_points.npy` and `contact_normals.npy` later, even if force is unavailable.
- A contact-specific checker can validate no NaN/Inf, bounded gap/penetration, and contact/proximity occurrence.
- Replay remains offline and does not rerun SOFA.

#### D4: Directional Small-Step Probe Contact

Priority: required if NJF dataset v1 samples non-vertical action directions.

Goal: make physical probe motion match small `delta_a` actions and `ActionSpec.vector[2:5]` instead of always moving vertically.

Implementation intent:

- Map normalized action direction to the kinematic probe start/end positions.
- Keep `tool_pose_0` and `tool_pose_1` consistent with the actual probe displacement.
- Support small-step displacement scales such as `0.05`, `0.1`, and `0.2` mm for NJF local perturbations.
- Record action direction, approach direction, and insertion depth in metadata.
- Start with a bounded direction set or a small cone, such as 20 to 30 degrees from the top-surface normal, before using broad upper-hemisphere random directions.

Acceptance criteria:

- Saved tool displacement direction agrees with saved action direction within a small angular tolerance.
- Contact/proximity still occurs for the configured smoke cases.
- Deformation remains bounded.
- Isaac replay shows the same tool motion recorded by SOFA.

Implementation result:

- Status: implemented on 2026-06-25.
- `SofaFemBackend._tool_start_end_positions()` now maps `ActionSpec.vector[2:5]` to the kinematic probe center displacement for `probe_contact`. The vertical case remains backward-compatible because direction `(0, 0, -1)` produces the previous z-only motion.
- The probe center start/end rule is `contact_anchor - direction * (radius + clearance)` to `contact_anchor - direction * radius + direction * depth`, so `tool_pose_0 -> tool_pose_1` follows the saved action direction. Setting clearance to zero allows local small-step motions such as `0.2 mm`.
- `tool_geometry.json` records `motion_direction_source: action_vector_2_4`.
- `scripts/check_tool_direction.py` validates action direction, saved tool-pose displacement direction, angle error, motion length, tilt, xy motion, and z drop.
- New configs: `tissue_dataset_v0/configs/sofa_liver_contact_d4_directional.yaml` and `tissue_dataset_v0/configs/sofa_liver_contact_d4_small_step.yaml`.
- Generated directional dataset: `tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional` with 3 samples.
- Generated small-step sample: `tissue_dataset_v0/outputs/sofa_liver_contact_d4_small_step/sample_000001`.

Observed D4 directional result:

```text
sample_000001: tilt 4.905 deg, angle error 0.000001 deg, motion 12.500 mm, max displacement 1.06 mm
sample_000002: tilt 9.365 deg, angle error 0.000000 deg, motion 12.500 mm, max displacement 4.10 mm
sample_000003: tilt 9.026 deg, angle error 0.000000 deg, motion 12.500 mm, max displacement 2.99 mm
```

Observed D4 small-step result:

```text
depth: 0.2 mm
clearance: 0.0 mm
tilt: 6.791 deg
motion: 0.200 mm
angle error: 0.000065 deg
contact_detected: true
first_contact_step: 0
```

Verification commands run:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py tissue_dataset_v0/scripts/check_tool_direction.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d4_directional.yaml --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3 --require-nonvertical --min-max-tilt-deg 5.0 --max-angle-error-deg 0.1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3 --direction-mode varying --max-tilt-deg 15 --min-direction-spread-deg 2.0 --min-max-displacement-mm 0.5 --max-max-displacement-mm 5.0 --max-downward-z-mm 5.0 --min-contact-spread-mm 1.0 --min-depth-spread-mm 0.0 --max-contact-distance-mm 35.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require fixed_node_indices --require free_node_indices --require boundary_mask --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_motion.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3 --min-z-drop-mm 1.0 --max-z-drop-mm 20.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional/sample_000001 tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional/sample_000002 tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional/sample_000003
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d4_small_step.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_small_step --min-samples 1 --max-angle-error-deg 0.1 --min-motion-mm 0.05
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_small_step --min-samples 1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_small_step/sample_000001
```

Results: compile passed; D4 direction, bounded deformation, contact, boundary/solver, reader, tool motion, and core validators passed. The first attempted 25 degree/large contact-margin smoke produced one under-deformed sample, so the committed D4 smoke config uses a conservative center-region 15 degree cone for stable validation.

#### D5: Boundary, Solver, and Contact Metadata

Priority: required before NJF dataset v1 is treated as a training source.

Goal: make fixed boundary and solver assumptions explicit in sample artifacts and metadata.

Recommended optional artifacts or metadata fields:

```text
fixed_node_indices.npy
free_node_indices.npy
boundary_mask.npy
boundary.json
solver_summary.json
```

At minimum, record:

- boundary type;
- boundary box or threshold;
- fixed/free node counts;
- `dt`;
- settling step count;
- record interval;
- solver/contact solver components;
- valid/converged flag if available;
- NaN/Inf flag.

Implementation result:

- Status: implemented on 2026-06-25.
- `fixed_node_indices.npy`, `free_node_indices.npy`, `boundary_mask.npy`, `boundary.json`, and `solver_summary.json` are now enabled optional artifacts in `layout.py`.
- `SofaFemBackend` writes these artifacts when `sofa_record_boundary_solver: true`; the flag defaults to `true` for new SOFA samples and can be disabled or excluded through artifact policy.
- Current boundary metadata records `boundary_type: fixed_bottom`, `FixedProjectiveConstraint`, regular-grid bottom-layer selection, fixed/free counts, and a boundary box in meters.
- Current solver summary records `dt`, `total_steps`, `settling_steps`, record interval, interaction model, solver component names, configured solver tolerances, finite-state validity, max displacement, and contact summary linkage. SOFA residual/convergence is not reliably exported yet, so `solver_converged` and `solver_residual` are `null` and `solver_status_method` is `finite_state_check_only`.
- `scripts/check_boundary_solver.py` validates artifact presence, mask/index consistency, fixed/free partitioning, fixed-node displacement, boundary metadata counts, and solver summary validity.
- New config: `tissue_dataset_v0/configs/sofa_liver_contact_d5.yaml`.
- Generated sample: `tissue_dataset_v0/outputs/sofa_liver_contact_d5/sample_000001`.

Observed D5 result:

```text
fixed_node_count: 63
free_node_count: 189
boundary_mask shape: [252]
max fixed-node displacement: 0.000000 mm
dt: 0.005
total_steps: 160
solver valid: true
```

Verification commands run:

```bash
python3 -m py_compile tissue_dataset_v0/src/tissue_dataset_v0/layout.py tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py tissue_dataset_v0/scripts/check_boundary_solver.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d5.yaml --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d5/sample_000001
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d5 --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require fixed_node_indices --require free_node_indices --require boundary_mask --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_motion.py tissue_dataset_v0/outputs/sofa_liver_contact_d5 --min-samples 1 --min-z-drop-mm 1.0 --max-z-drop-mm 20.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_liver_contact_d5 --min-samples 1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/sofa_liver_contact_d5 --min-samples 1
```

Results: compile passed, sample generation passed, core validator passed with zero errors/warnings, reader smoke loaded all D5 artifacts, D2 tool motion check passed, D3 contact check passed, and D5 boundary/solver check passed.

#### D6: Surface Collision

Priority: defer until after controlled dataset v1 unless D3/D4 prove point-collision contact is insufficient.

Surface collision would require a tissue collision surface, mapping between mechanical and collision/visual models, contact normal validation, and likely a stronger contact checker. It is useful, but it should not block the first controlled dataset if point-collision probe contact gives stable bounded responses.

#### D7: Sequence-Level Tool and Contact Artifacts

Priority: required for Mode C rollout, after D3 through D5 are stable.

Potential optional artifacts remain:

```text
tool_pose_seq.npy
contact_active_seq.npy
contact_force_seq.npy
contact_point_seq.npy
```

For NJF rollout, sequence artifacts should support:

```text
states.npy
actions.npy
responses.npy
tool_poses.npy
contact_points.npy
contact_normals.npy
solver_status.json
```

Smoke rollout may start with `T = 3`; useful rollout validation should target `T >= 10`. Vertical-only contact is not a complete Mode B response-basis target because it varies only action magnitude, not the local action direction basis.

### Minimum Stage D Completion for SOFA NJF Dataset v1

Stage D is sufficient to start SOFA NJF dataset v1 when:

- D2 tool pose artifacts remain stable;
- D3 contact summary and per-step contact status are implemented and validated;
- D4 directional small-step probe contact works for the action directions used by complete v1 response-basis data; vertical-only remains only a smoke/debug/regression setting;
- D5 boundary and solver metadata are recorded;
- D7-like sequence fields are available for Mode C rollout;
- `localized_probe_force` remains available for regression;
- existing Stage A/B/C/D1/D2 samples remain readable.

## Stage D Validation Plan

### Prototype Checks

For D0:

- no NaN/Inf;
- step count complete;
- probe moves as intended;
- displacement bounded;
- contact/proximity indicator occurs.

### Dataset Checks

For D1 and later:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py path/to/sample --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py path/to/dataset --material-mode varying --geometry-mode varying ...
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py path/to/dataset
```

### Contact-Specific Checks

Recommended future command:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_contact.py path/to/dataset
```

Potential checks:

- tool pose fields exist when expected;
- tool z decreases during vertical press;
- final tool position is consistent with `contact_point`;
- `contact_active` occurs for contact samples;
- contact force has no NaN/Inf and no extreme outliers;
- contact normal roughly agrees with expected surface/probe direction;
- penetration depth remains bounded;
- optional artifacts listed as present in manifest exist and have expected shape.

## Suggested Next Implementation Prompt

```text
Use the project-context-maintainer skill. Read AGENTS.md, docs/ARCHITECTURE.md, docs/DATASET_SCHEMA.md, docs/ROADMAP.md, tasks/0009-sofa-liver-stage-c.md, and tasks/0010-sofa-stage-d-probe-contact-plan.md.

Start Stage D with D0 only: create a standalone SOFA contact prototype, not a dataset backend change. Add scripts/prototype_sofa_probe_contact.py that runs headlessly in the sofa conda environment, creates a small deformable FEM tissue and a kinematic sphere/capsule probe with SOFA collision/contact, moves the probe downward, and prints a JSON summary with step count, max displacement, min z displacement, contact/proximity indicator, and NaN/Inf status. Do not change sample schema yet. Run compile checks and the prototype smoke test. Update this task file and relevant docs with actual results.
```

## Open Questions

- Which SOFA contact components are available in the installed package and stable headlessly?
- Should the first probe be a sphere or capsule? Sphere is simpler; capsule may better match surgical tools.
- Can SOFA expose reliable contact force/normal in the intended contact setup, or should D3 start with geometric contact/proximity summaries only?
- Should D2 use 4x4 homogeneous matrices or compact pose vectors for `tool_pose_*`?
