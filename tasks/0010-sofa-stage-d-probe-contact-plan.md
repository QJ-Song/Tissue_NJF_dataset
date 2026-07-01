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

Priority: active as of 2026-06-29. Earlier work deferred surface collision, but point-collision probe contact has not produced a realistic local-linear action range: micro steps near `0.01 mm` can pass, while `0.05` to `0.2 mm` remains too nonlinear/noisy for the intended NJF local perturbation scale. Because `0.01 mm` is not a practical target, surface collision is now the next blocker before Stage 3 response-basis expansion.

Goal: build and smoke-test a standalone SOFA official-liver scene with tetrahedral FEM mechanics and mapped surface triangle collision before changing `SofaFemBackend`.

References:

- `examples/Demos/liver.scn` and `liverConfiguration.scn` for the official liver FEM using `liver.msh` and `liver-smooth.obj`;
- `examples/Demos/fallingSOFA.scn` for tetrahedral FEM plus surface collision/contact pipeline;
- `examples/Demos/caduceus.scn` for a separate OBJ collision mesh mapped to deformable DOFs via `BarycentricMapping`.

Implementation result:

- Status: standalone scene and smoke test implemented on 2026-06-29.
- New scene: `scenes/liver_surface_collision.py`.
- New smoke script: `scripts/check_liver_surface_collision.py`.
- The scene uses SOFA-installed `liver.msh` for the volume FEM and `liver-smooth.obj` for the mapped collision/visual surface.
- The liver collision node uses `TriangleCollisionModel`, `LineCollisionModel`, and `PointCollisionModel`; the liver collision node does not use `SphereCollisionModel`.
- The collision surface maps to the liver FEM mechanical state with `BarycentricMapping`.
- The probe is a simple kinematic sphere for smoke testing only.
- Mesh lookup uses `SOFA_MESH_DIR`, `SOFA_ROOT`, `CONDA_PREFIX`, or `sys.prefix`; the project does not hard-code a private mesh path.

Observed smoke result:

```text
command: scripts/run_sofa_python.sh scripts/check_liver_surface_collision.py --format json
valid: true
volume mesh: liver.msh
surface mesh: liver-smooth.obj
mechanical nodes: 181
surface nodes: 2194
collision models: TriangleCollisionModel, LineCollisionModel, PointCollisionModel
mapping: BarycentricMapping
first contact/proximity step: 29
contact/proximity frames: 54
min signed gap: 0.05044 scene units, with detection threshold 0.051
max liver displacement: 0.51386 scene units
max surface displacement: 0.52510 scene units
```

Acceptance status: D6 standalone surface collision is smoke-tested and now has a standalone fixed-contact small-depth linearity diagnostic. It is not yet integrated into dataset generation.

Small-depth diagnostic result:

- New script: `scripts/diagnose_liver_surface_linearity.py`.
- Default command: `scripts/run_sofa_python.sh scripts/diagnose_liver_surface_linearity.py --format json`.
- Default depths: `0.05`, `0.1`, and `0.2 mm`, with `scene_units_per_mm=1.0`.
- Result: default diagnostic passed. Relative scale errors were `0.05509` for `0.05 -> 0.10 mm` and `0.09858` for `0.05 -> 0.20 mm`.
- Extended sweep `0.05 0.1 0.2 0.3 0.5` showed `0.3 mm` fails the 10% threshold with relative scale error `0.12724`, and `0.5 mm` clearly fails with `0.39802`.

Interpretation before physical scale calibration: the standalone surface-collision liver scene appears to recover a practical local-linear range up to about `0.2 scene units`, while `0.3 scene units` and above should not be used as local Jacobian supervision without further retuning.

Scale calibration result:

- New script: `scripts/calibrate_liver_mesh_scale.py`.
- Default command: `scripts/run_sofa_python.sh scripts/calibrate_liver_mesh_scale.py --format json`.
- Default method: bounding-box long-axis calibration on `liver-smooth.obj`.
- Default anatomical assumption: target liver long axis `150 mm`; callers can override with `--target-long-axis-mm`.
- Observed mesh size: `x=6.386355`, `y=4.907551`, `z=4.412135` scene units.
- Observed scale for 150 mm target: `mm_per_scene_unit=23.487576`, `scene_units_per_mm=0.0425757`.
- Under this calibration, `0.05`, `0.10`, and `0.20` scene units correspond to about `1.17`, `2.35`, and `4.70 mm`.
- A 120 mm target sanity run produced `mm_per_scene_unit=18.790061` and `scene_units_per_mm=0.05321963`, confirming that external liver-size assumptions are supported.

Calibrated physical-mm diagnostic:

- Command: `scripts/run_sofa_python.sh scripts/diagnose_liver_surface_linearity.py --depths-mm 1 2 5 7 --scene-units-per-mm 0.0425757 --output tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_calibrated_150mm.json`.
- Result: `1 -> 2 mm` relative scale error `0.06050` passed; `1 -> 5 mm` error `0.11418` and `1 -> 7 mm` error `0.13664` exceeded the 10% threshold.

Interpretation after scale calibration: with the 150 mm long-axis assumption, the robust NJF local target range is approximately `1-2 mm`. Around `4-5 mm` should be treated as near-boundary or rollout-evaluation range, not core local Jacobian supervision.

Visualization result:

- Diagnostic report script: `scripts/visualize_liver_surface_diagnostics.py`.
- Diagnostic command: `python3 scripts/visualize_liver_surface_diagnostics.py`.
- Diagnostic output: `tissue_dataset_v0/outputs/liver_surface_visualization/report.html`.
- Actual tissue deformation visualization now uses the existing Isaac Sim offline USD/USDA replay pattern.
- New SOFA state script: `scripts/generate_liver_surface_deformation_state.py`.
- New Isaac Sim export script: `scripts/export_liver_surface_deformation_isaacsim.py`.
- Commands:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_deformation_state.py --depth-mm 2
env_isaacsim/bin/python scripts/export_liver_surface_deformation_isaacsim.py
```

- Output: `tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/isaacsim_liver_surface_deformation.usda`.
- The default USDA contains animated `/World/LiverSurface` with stable natural liver material, animated `/World/Probe`, and `/World/ContactPoint`.
- To avoid unnatural color blending, `/World/BaselineGhost` and `/World/DisplacementVectors` are disabled by default and are available only with `--show-baseline-ghost --show-displacement-vectors`.
- Debug command: `env_isaacsim/bin/python scripts/export_liver_surface_deformation_isaacsim.py --show-baseline-ghost --show-displacement-vectors --output tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/isaacsim_liver_surface_deformation_debug.usda`.
- Observed 2 mm calibrated run: 2194 surface nodes, 4384 faces, 120 contact frames, max surface displacement `0.101698` scene units, default output USDA about 243 KB, debug USDA about 405 KB.

Dataset-compatible bridge result:

- New script: `scripts/generate_liver_surface_sample.py`.
- Purpose: expose the standalone official-liver surface-collision scene through the existing `sample_*` artifact schema before rewriting `SofaFemBackend`.
- Default command: `scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite`.
- Default output: `tissue_dataset_v0/outputs/liver_surface_contact_sample/sample_000001`.
- Output unit/axis policy: SOFA coordinates are converted with `dataset_xyz = sofa_xzy`, so dataset `z` is vertical; vertices and tool poses are written in meters.
- Default scale: 150 mm liver long-axis calibration.
- Default action: 2 mm vertical surface-collision press with `--probe-clearance-mm 0.0`, so `tool_pose_0 -> tool_pose_1` motion equals saved action depth.
- Observed result: 2194 surface nodes, 4384 faces, 2.000 mm tool motion, max surface displacement `4.005 mm`, contact detected from step 0 with 118 contact/proximity frames.
- Verification passed: `python3 -m py_compile scripts/generate_liver_surface_sample.py`; `validate_sample.py` with zero errors/warnings; `read_dataset_smoke.py` requiring tool/contact/solver artifacts; `check_contact.py`; and `check_tool_direction.py` with zero angle error.

Bridge Mode A update:

- `scripts/generate_liver_surface_sample.py` supports `--depths-mm` for multi-sample local perturbation bridge datasets.
- It writes root-level `dataset_metadata.json` plus the existing sample artifacts.
- It records optional boundary artifacts for the official-liver surface output: `fixed_node_indices.npy`, `free_node_indices.npy`, `boundary_mask.npy`, and `boundary.json`. Because the official demo fixes volume nodes `3, 39, 64` while this bridge exports surface vertices, the surface mask is explicitly all false and `boundary_type` is `official_liver_volume_fixed_indices_surface_unmapped`.
- `tissue_dataset_v0/scripts/check_boundary_solver.py` accepts this bridge boundary type instead of assuming all D5-like samples use `fixed_bottom`.
- `--contact-distance-mm` now controls the SOFA contact response threshold and defaults to `0.1 mm`.
- `--contact-observation-distance-mm` controls only the nearest-surface-vertex contact summary threshold and defaults to `1.2 mm`.
- The bridge now follows `preload -> record X_t -> action_steps -> settle_steps -> record X_next`, with defaults `preload_steps=60`, `action_steps=40`, and `settle_steps=80`.

Observed calibrated bridge dataset:

```text
command: scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --output tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated --sample-id 1 --depths-mm 1.17 2.35 4.70
sample_000001: tool motion 1.170 mm, max displacement 1.631 mm
sample_000002: tool motion 2.350 mm, max displacement 3.083 mm
sample_000003: tool motion 4.700 mm, max displacement 5.413 mm
```

Verification passed: compile, core `validate_sample.py`, `read_dataset_smoke.py` requiring tool/contact/boundary/solver artifacts, `check_contact.py`, `check_tool_direction.py`, and bridge-aware `check_boundary_solver.py`.

Calibrated bridge linearity result:

```text
1.17 -> 2.35 mm: scale_error=0.02506, cosine=0.99977
1.17 -> 4.70 mm: scale_error=0.05934, cosine=0.99867
```

Interpretation: after reducing SOFA `contactDistance`, separating the vertex-gap contact observation threshold, and matching the standalone preload/action/settle protocol, the dataset-compatible bridge reproduces the earlier surface-collision linearity conclusion. The earlier poor `0.25/0.5/1.0 mm` bridge result was not a contradiction of the prior benchmark; those actions were below the previous contact/proximity scale and were not apples-to-apples with the standalone diagnostic.


#### D6.5: Surface-Collision Mode B Bridge Smoke

Status: implemented on 2026-06-30.

Goal: move from single-direction calibrated linearity to a smoke-sized response-basis group using the official liver surface-collision bridge.

Implementation result:

- `scenes/liver_surface_collision.py` now supports configurable `probe_direction` in SOFA coordinates.
- `scripts/generate_liver_surface_sample.py` now supports `--direction-set basis_smoke`, `--layout grouped`, and `--group-id`.
- `basis_smoke` uses three dataset-frame directions: normal, 12 degree `tilt_x`, and 12 degree `tilt_y`.
- Grouped output writes `samples/` plus `groups/group_000001/` with `actions.npy`, `responses.npy`, `state_initial.npy`, `fixed_node_mask.npy`, `surface_points.npy`, `contact_point.npy`, `contact_normal.npy`, and `group_metadata.json`.
- Mode B smoke uses `--preload-steps 0` intentionally so all directions share identical `vertices_0`. A direction-specific preload produced about `0.38 mm` baseline mismatch and is not valid for fixed-state response-basis grouping.

Smoke command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --layout grouped --direction-set basis_smoke --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke --sample-id 1 --depths-mm 1.17 2.35 --preload-steps 0
```

Observed result:

```text
samples: 6
unique action directions: 3
action magnitudes: 1.17 mm, 2.35 mm
surface vertices: 2194
faces: 4384
state_mismatch_max_m: 0.0
max response: about 3.53 mm
```

Verification passed:

- `python3 -m py_compile scenes/liver_surface_collision.py scripts/generate_liver_surface_sample.py`
- `validate_sample.py` on all six samples
- `read_dataset_smoke.py` requiring tool/contact/boundary/solver artifacts
- `check_contact.py`
- `check_tool_direction.py --require-nonvertical`
- `check_boundary_solver.py`

Response-basis analysis:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/analysis/response_basis_summary.json
```

Observed smoke basis metrics:

```text
effective_rank: 1.442
top1 cumulative explained: 0.895643
top2 cumulative explained: 0.991183
top3 cumulative explained: 0.999781
leave-one-out mean relative error: 0.050239
leave-one-out max relative error: 0.069371
```

Interpretation: the K=6 group is smoke-sized but already shows low-dimensional response structure under surface collision. Do not present this as a final research result; the next basis step should increase to K>=12 with more directions and/or magnitudes while preserving fixed `X_t`.


#### D6.6: Surface-Collision Mode B Bridge v1

Status: implemented on 2026-06-30.

Goal: promote the Mode B bridge from K=6 smoke to a first usable fixed-contact response-basis group.

Implementation result:

- `scripts/generate_liver_surface_sample.py` now supports `--direction-set basis_v1`.
- `basis_v1` contains 6 directions: normal, +/-x tilt, +/-y tilt, and diagonal xy tilt.
- All tilted directions use a 12 degree total tilt relative to the normal.
- The action type is now `surface_collision_directed_press`.
- Mode B group metadata now uses `surface_collision_bridge_response_basis`; `smoke_sized_group` marks whether K<12.

Run command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --layout grouped --direction-set basis_v1 --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1 --sample-id 1 --depths-mm 1.17 2.35 4.70 --preload-steps 0
```

Observed group:

```text
action_count: 18
unique directions: 6
action magnitudes: 1.17 mm, 2.35 mm, 4.70 mm
responses shape: [18, 2194, 3]
state_mismatch_max_m: 0.0
smoke_sized_group: false
max response: about 6.32 mm
```

Verification passed:

- `python3 -m py_compile scripts/generate_liver_surface_sample.py`
- `validate_sample.py` on all 18 samples
- `read_dataset_smoke.py` requiring tool/contact/boundary/solver artifacts
- `check_contact.py --min-samples 18 --max-min-gap-mm 2.0 --max-penetration-mm 2.0`
- `check_tool_direction.py --require-nonvertical`
- `check_boundary_solver.py --min-samples 18`
- `analyze_response_basis.py`

Basis result:

```text
effective_rank: 1.358
top1 cumulative explained: 0.920643
top2 cumulative explained: 0.991576
top3 cumulative explained: 0.999615
leave-one-out mean relative error: 0.044930
leave-one-out max relative error: 0.094149
```

Interpretation: this fixed-contact K=18 group is now sufficient for a first single-group Mode B sanity conclusion: local responses are strongly low-dimensional under the current official-liver surface-collision setup. It is not sufficient for cross-group or shared-basis conclusions.

Next step after D6.6: generate multiple Mode B groups by changing one factor at a time. The recommended order is same material/boundary with multiple contact points first, then material variation at a fixed contact point, then boundary variation later after boundary encoding is improved.


#### D6.7: Multi-Contact Mode B Response-Basis Dataset v1

Status: implemented on 2026-06-30.

Goal: test whether response bases remain shared when only contact point changes, while material, boundary, tool geometry, solver config, action directions, and action magnitudes stay fixed.

Implementation result:

- `scenes/liver_surface_collision.py` now supports an optional explicit `contact_point`.
- `scripts/generate_liver_surface_sample.py` now supports `--contact-set top_center|top_three`.
- `top_three` writes three Mode B groups, one per contact point: left, center, and right top-surface contacts.
- Each group still fixes exactly one contact point and varies only action direction/magnitude.

Run command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --layout grouped --contact-set top_three --direction-set basis_v1 --output tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1 --sample-id 1 --depths-mm 1.17 2.35 4.70 --preload-steps 0
```

Observed dataset:

```text
groups: 3
samples: 54
per-group K: 18
directions per group: 6
magnitudes per group: 1.17 mm, 2.35 mm, 4.70 mm
state_mismatch_max_m: 0.0 for every group
```

Verification passed:

- validator over all 54 samples: invalid=0, errors=0, warnings=0
- `read_dataset_smoke.py` with tool/contact/boundary/solver requirements
- `check_contact.py --min-samples 54 --max-min-gap-mm 2.0 --max-penetration-mm 2.0`
- `check_tool_direction.py --require-nonvertical`
- `check_boundary_solver.py --min-samples 54`
- `analyze_response_basis.py`
- `analyze_basis_across_groups.py --rank 2`

Per-group basis result:

```text
group_000001 contact_top_left_000001: effective_rank=1.711, top2=0.979604, loo_mean=0.093317
group_000002 contact_top_center_000001: effective_rank=1.158, top2=0.994204, loo_mean=0.049255
group_000003 contact_top_right_000001: effective_rank=1.041, top2=0.998654, loo_mean=0.021630
mean effective_rank=1.303441
mean top2=0.990821
```

Cross-contact basis result:

```text
same_material_diff_contact pairs: 6
projection_similarity_mean: 0.679566
principal_angle_mean_deg: 31.582
cross_reconstruction_error_mean: 0.438450
```

Interpretation: each fixed-contact group remains strongly low-dimensional, but cross-contact reconstruction is not strong. This is the expected and useful result for NJF: basis appears local and condition-dependent, so the future model should condition on contact point/local geometry rather than using one fixed global basis.

Next step after D6.7: controlled material variation at fixed contact point, using the same `basis_v1` action set and `--preload-steps 0`, so we can compare same-contact/different-material basis similarity and response scaling.


#### D6.8: Material-Variation Mode B Response-Basis Dataset v1

Status: implemented on 2026-06-30.

Goal: test whether response bases remain shared when only material changes, while contact point, boundary, solver config, tool geometry, action directions, and action magnitudes stay fixed.

Implementation result:

- `scripts/generate_liver_surface_sample.py` now supports `--material-set single|young_three`.
- `young_three` creates three Young's modulus settings: `1000`, `3000`, and `10000`, with Poisson ratio fixed at `0.3` unless overridden.
- Material IDs and parameters are written into sample and group metadata.
- Each material writes one Mode B group, so group semantics remain valid: a group fixes exactly one material and varies only action direction/magnitude.

Run command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --layout grouped --contact-set top_center --material-set young_three --direction-set basis_v1 --output tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1 --sample-id 1 --depths-mm 1.17 2.35 4.70 --preload-steps 0
```

Observed dataset:

```text
groups: 3
samples: 54
contact point: contact_top_center_000001 for every group
per-group K: 18
directions per group: 6
magnitudes per group: 1.17 mm, 2.35 mm, 4.70 mm
Young's modulus values: 1000, 3000, 10000
Poisson ratio: 0.3
state_mismatch_max_m: 0.0 for every group
```

Verification passed:

- validator over all 54 samples: invalid=0, errors=0, warnings=0
- `read_dataset_smoke.py` with tool/contact/boundary/solver requirements
- `check_contact.py --min-samples 54 --max-min-gap-mm 2.0 --max-penetration-mm 2.0`
- `check_tool_direction.py --require-nonvertical`
- `check_boundary_solver.py --min-samples 54`
- `analyze_response_basis.py`
- `analyze_basis_across_groups.py --rank 2`

Per-group basis result:

```text
group_000001 material_young_1000: effective_rank=1.209, top2=0.997753, loo_mean=0.025464, response_norm_mean=0.097851 m
group_000002 material_young_3000: effective_rank=1.158, top2=0.994204, loo_mean=0.049255, response_norm_mean=0.065985 m
group_000003 material_young_10000: effective_rank=1.242, top2=0.988022, loo_mean=0.080493, response_norm_mean=0.033249 m
mean effective_rank=1.203186
mean top2=0.993326
```

Cross-material basis result:

```text
same_contact_diff_material pairs: 6
projection_similarity_mean: 0.760302
principal_angle_mean_deg: 27.189
cross_reconstruction_error_mean: 0.323145
```

Material-scale result:

```text
E 1000 vs 3000: response_norm_ratio=1.482933, normalized_cross_error=0.301817
E 1000 vs 10000: response_norm_ratio=2.942958, normalized_cross_error=0.589260
E 3000 vs 10000: response_norm_ratio=1.984552, normalized_cross_error=0.465776
```

Interpretation: each fixed-material group remains strongly low-dimensional. Material variation changes both response amplitude and response pattern; it is not a pure scalar rescaling under the current contact setup. This supports conditioning NJF on material parameters.

Next step after D6.8: decide whether to move to Mode C rollout artifacts or first add a combined small factorial dataset, e.g. 3 contacts x 3 materials x 18 actions, to support a cleaner shared-basis train/held-out test.


#### D6.9: Factorial Contact-Material Mode B Dataset v1

Status: implemented on 2026-06-30.

Goal: combine the contact-point and material sweeps into one small controlled factorial dataset for cleaner cross-group and shared-basis analysis.

Run command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --layout grouped --contact-set top_three --material-set young_three --direction-set basis_v1 --output tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1 --sample-id 1 --depths-mm 1.17 2.35 4.70 --preload-steps 0
```

Observed dataset:

```text
contacts: 3
materials: 3
groups: 9
samples: 162
per-group K: 18
directions per group: 6
magnitudes per group: 1.17 mm, 2.35 mm, 4.70 mm
state_mismatch_max_m: 0.0 for every group
```

Verification passed:

- compile for `scenes/liver_surface_collision.py` and `scripts/generate_liver_surface_sample.py`
- validator over all 162 samples: invalid=0, errors=0, warnings=0
- `read_dataset_smoke.py` with tool/contact/boundary/solver requirements
- `check_contact.py --min-samples 162 --max-min-gap-mm 2.0 --max-penetration-mm 2.0`
- `check_tool_direction.py --require-nonvertical`
- `check_boundary_solver.py --min-samples 162`
- `analyze_response_basis.py`
- `analyze_basis_across_groups.py --rank 2`

Per-group basis result:

```text
mean effective_rank=1.286046
mean top2=0.987973
mean leave-one-out error=0.061361
effective_rank range=[1.041, 1.711]
top2 range=[0.967158, 0.999208]
```

Cross-group rank-2 basis result:

```text
same_contact_diff_material: pairs=18, projection_similarity=0.800843, principal_angle_mean_deg=24.021, cross_reconstruction_error=0.343122
same_material_diff_contact: pairs=18, projection_similarity=0.614229, principal_angle_mean_deg=36.844, cross_reconstruction_error=0.490669
diff_contact_diff_material: pairs=36, projection_similarity=0.565954, principal_angle_mean_deg=40.695, cross_reconstruction_error=0.534312
offdiag_cross_reconstruction_error_mean=0.475604
```

Held-out shared-basis smoke:

```text
train: left + center contacts, all materials, 6 groups
test: right contact, all materials, 3 groups
rank: 2
test_error_mean=0.260164
test_error_max=0.313995
E1000 test error=0.208318
E3000 test error=0.258177
E10000 test error=0.313995
```

Interpretation: factorial results strengthen the current conclusion. Fixed-condition responses are low-dimensional, but cross-condition basis transfer is condition-dependent. Material variation at the same contact is easier than contact variation at the same material; changing both is hardest. This supports NJF conditioning on both `p`/local geometry and material `theta`.

Next step after D6.9: move to Mode C rollout artifacts, because the Mode B fixed-condition and cross-condition evidence is now sufficient for the first controlled dataset phase.

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

#### D7.1: Surface-Collision Mode C Rollout Bridge v1

Implemented `scripts/generate_liver_surface_rollout.py` as the first direct Mode C rollout bridge for the official liver surface-collision scene. It runs one continuous SOFA trajectory and writes `trajectories/traj_*` artifacts directly: `states.npy`, `actions.npy`, `responses.npy`, `contact_points.npy`, `contact_normals.npy`, `tool_poses.npy`, `fixed_node_mask.npy`, `contact_status.npy`, `contact_distances.npy`, `trajectory_metadata.json`, and `solver_status.json`.

The first useful run used top-center fixed material contact, single material `E=3000`, vertical normal direction, `T=10`, `step_size=1.17 mm`, `40` action substeps, and `20` settle steps per rollout step. Output root: `tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1`.

Validation result:

```text
analyze_rollout_trajectories: PASS
read_njf_dataset: PASS
T: 10
states shape: [11, 2194, 3]
actions shape: [10, 6]
responses shape: [10, 2194, 3]
final max deformation: 15.866 mm
max per-step response: 1.772 mm
contact active: 10/10
contact distance range: 0.111 mm to 0.338 mm
tool step error max: 0.000009 mm
tool/action angle error max: 0 deg
fixed-node motion max: 0 mm
```

Also updated `tissue_dataset_v0/src/tissue_dataset_v0/njf/dataset.py` so `NJFDataset.summary()` counts `trajectories/` as `rollout_trajectory`. This lets Mode C-only roots pass `read_njf_dataset.py --require-mode rollout_trajectory`.

Interpretation: D7 sequence fields are now available for a first Mode C rollout evaluation. This is still fixed material contact with approximate upward contact normals and nearest-vertex signed-gap observations; reliable contact force export and recomputed geometric contact point remain future work.


#### D7.2: Rollout Drift and Single-Large-Step Analysis v1

Extended `tissue_dataset_v0/scripts/analyze_rollout_trajectories.py` with:

- adjacent response cosine and adjacent relative response change;
- first-step-to-later-step response drift;
- constant-first-step rollout diagnostic;
- optional `--single-step-sample` final-state comparison;
- optional `--csv-dir` per-step CSV export.

Generated a matched single-large-step sample at `tissue_dataset_v0/outputs/liver_surface_single_large_11p7_v1/sample_000001` using the same top-center contact, material, vertical direction, and total displacement as the T=10 rollout. Validation, contact check, and tool-direction check passed.

Observed metrics:

```text
adjacent_response_cosine_mean=0.981063
adjacent_relative_change_mean=0.204464
first_step_response_cosine_final=0.946018
first_step_relative_change_final=0.388764
constant_first_step_final_relative_l2_error=0.221470
constant_first_step_final_max_node_error=4.612 mm
single_large_vs_rollout_relative_l2_error=0.022662
single_large_vs_rollout_pattern_cosine=0.999745
single_large_vs_rollout_max_node_error=0.487 mm
```

Interpretation: in this simplified quasi-static vertical press, one slow 11.7 mm action and ten 1.17 mm rollout steps reach nearly the same final deformation. The stronger NJF-relevant signal is per-step response drift: a constant first-step response field accumulates about 22% relative L2 final error, so rollout evaluation should test state-conditioned small-step prediction rather than only final-state equivalence.

Next rollout analysis should repeat this on non-vertical directions, multiple contact points, and multiple materials before drawing general conclusions about path dependence or local Jacobian validity.


#### D7.3: Non-Vertical Contact-Material Rollout Batch v1

Generated and analyzed a non-vertical Mode C batch at `tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1` using:

```text
direction: tilt_pos_x from basis_v1
contacts: top_left, top_center, top_right
materials: Young modulus 1000, 3000, 10000
trajectories: 9
steps per trajectory: 10
step size: 1.17 mm
total displacement: 11.7 mm
```

Validation passed:

```text
analyze_rollout_trajectories: PASS, 9 trajectories, 0 errors, 0 warnings
read_njf_dataset --require-mode rollout_trajectory --min-trajectories 9: PASS
contact_active: 10/10 for every trajectory
```

Aggregate response-drift results:

```text
final_max_mm: min=13.269013, mean=15.533157, max=19.755029
step_response_max_mm: min=1.651124, mean=2.246438, max=3.934977
adjacent_cos_mean: min=0.780920, mean=0.903977, max=0.987810
adjacent_rel_change_mean: min=0.160621, mean=0.394453, max=0.712843
first_step_cos_final: min=0.051641, mean=0.798732, max=0.957254
constant_first_step_final_rel_l2: min=0.202028, mean=0.432849, max=0.803623
constant_first_step_final_max_node_error_mm: min=3.453103, mean=7.062486, max=11.996601
```

Interpretation: response drift is much stronger and more condition-dependent in the tilt-x 3x3 batch than in the single vertical top-center rollout. Fixed-first-step rollout is unreliable across contact/material conditions, with mean final relative L2 error about `0.43` and worst case about `0.80`. This supports using Mode C to evaluate state-conditioned rolling models rather than a fixed local response field.

Next useful step: add matched single-large-step generation/comparison for this 3x3 batch or implement a Mode-B-basis-per-step diagnostic. The current `generate_liver_surface_sample.py` can make single-large comparisons but needs a direction-id filter to avoid generating all six `basis_v1` directions when only `tilt_pos_x` is required.


#### D7.4: Matched Single-Large Comparison for Tilt-X 3x3

Added `--direction-id` filtering to `scripts/generate_liver_surface_sample.py`. This allows targeted single-large sample generation for `tilt_pos_x` without generating all `basis_v1` directions. Extended `tissue_dataset_v0/scripts/analyze_rollout_trajectories.py` so `--single-step-sample` can be a dataset root with multiple `sample_*` directories; each rollout trajectory is matched to a single-large sample by contact point, material, direction id, and total action magnitude.

Generated matched single-large data at `tissue_dataset_v0/outputs/liver_surface_single_large_tilt_x_3x3_11p7_v1`:

```text
samples: 9
contact_set: top_three
material_set: young_three
direction_id: tilt_pos_x
depth: 11.7 mm
action_steps: 400
settle_steps: 200
```

Validation passed:

```text
default sample validation: 9 samples, 0 errors, 0 warnings
check_contact: PASS
check_tool_direction: PASS, nonvertical 12 degree tilt
analyze_rollout_trajectories with matched single-large root: PASS, 9 trajectories, 0 errors, 0 warnings
```

Matched comparison metrics:

```text
single_large_rel_l2: min=0.015604, mean=0.071319, max=0.221009
single_large_pattern_cosine: min=0.976668, mean=0.995937, max=0.999929
single_large_max_node_error_mm: min=0.205648, mean=0.734584, max=1.905619
constant_first_step_final_rel_l2: min=0.202028, mean=0.432849, max=0.803623
constant_first_step_final_max_node_error_mm: min=3.453103, mean=7.062486, max=11.996601
```

Interpretation: final-state path dependence remains modest for most matched single-large comparisons, but fixed-first-step rolling error is much larger. For NJF, the stronger claim is not that a one-step final-state predictor always fails; it is that a local response model must be evaluated on per-step state-conditioned transitions. Large-step final-state data does not expose the changing local response field along the rollout.

Next useful step: implement a Mode-B-basis-per-step diagnostic, using fixed-condition response basis groups to reconstruct each rollout step, then compare it against constant-first-step and future NJF predictions.


#### D7.5: Mode-B-Basis-Per-Step Rollout Diagnostic v1

Implemented `tissue_dataset_v0/scripts/analyze_rollout_basis_projection.py`. It matches each Mode C rollout trajectory to a fixed Mode B response-basis group by `contact_point_id`, `material_id`, and `boundary_id`, then projects every rollout step response `delta_X_k` onto that fixed initial-state basis. The basis is not updated across rollout steps.

Basis variables:

```text
fixed per Mode B basis: mesh/state X0, contact point, material, boundary, tool geometry, solver/contact config
varied inside Mode B basis: action direction and action magnitude
current action family: basis_v1 small-cone press directions, 6 directions x 3 magnitudes
```

Command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_basis_projection.py \
  --rollout-dataset tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1 \
  --basis-dataset tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1 \
  --ranks 2 3 4 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_summary.json \
  --csv-output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_metrics.csv \
  --report-output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_report.md
```

Result: PASS, `9` trajectories, `9` matched basis groups, `27` rank-specific results, `0` errors.

Aggregate metrics:

```text
rank 2: step_err_mean=0.258662, final_err_mean=0.211910, final_err_max=0.423117, constant_final_mean=0.432849
rank 3: step_err_mean=0.187414, final_err_mean=0.176309, final_err_max=0.417558, constant_final_mean=0.432849
rank 4: step_err_mean=0.170237, final_err_mean=0.168869, final_err_max=0.375371, constant_final_mean=0.432849
```

Interpretation: a fixed response basis is much stronger than repeating the first response vector, but it is still not perfect. The current small-cone Mode B basis captures a stable low-dimensional subspace shared across rollout steps, while residual error indicates either state-conditioned basis changes, incomplete action-family coverage, or contact/nonlinearity effects. This supports the next modeling step: predict basis coefficients or a state-conditioned Jacobian, and use fixed-basis projection as a non-learning diagnostic reference.

Next useful step: decide whether to implement a first coefficient diagnostic from saved data, or expand Mode B action family with wider cone/tangential components before training-side work.



#### D7.6: Research Positioning Correction

The Stage D / liver surface-collision experiments should be interpreted as controlled simulation analysis, not as the final NJF benchmark. Their purpose is to identify which variables affect local response and therefore what the dataset must include: contact point, material, boundary condition, action family, state/rollout step, tool geometry, and solver/contact metadata.

Simulation-only baselines used so far, including fixed first-step response, fixed Mode B basis projection, and single-large-step final-state comparison, are diagnostic tools. They help explain why Mode B groups and Mode C rollout transitions are needed. They should not be presented as sufficient evidence that NJF outperforms existing deformation models on real tissue.

The stronger reviewer-facing benchmark should eventually use real phantom/tissue data with calibrated tool actions and observed deformation, then compare NJF against existing deformation prediction models. SOFA remains valuable as a theory-analysis and dataset-design tool that improves interpretability and guides which variables the real acquisition should cover.

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
