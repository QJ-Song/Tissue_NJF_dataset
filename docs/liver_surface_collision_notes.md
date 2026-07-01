# Liver Surface Collision Notes

## Purpose

The current Stage D point-collision probe is not enough to explain why the practical local-linear action range stays below the desired `0.05` to `0.2 mm` scale. The next diagnostic step is a standalone SOFA liver scene that keeps tetrahedral FEM mechanics while replacing the official liver demo's sphere-based liver collision with a surface triangle collision model.

This scene is intentionally separate from `SofaFemBackend` until it loads and smoke-tests reliably.

## References

Use the SOFA official demo structure as follows:

- `examples/Demos/liver.scn`: base liver FEM structure using `liver.msh`, `TetrahedralCorotationalFEMForceField`, mass, solver, visual surface, and fixed points.
- `examples/Demos/liverConfiguration.scn`: additional reference for `liver.msh` and `liver-smooth.obj` usage.
- `examples/Demos/fallingSOFA.scn`: reference for tetrahedral FEM plus surface collision and proximity/contact pipeline.
- `examples/Demos/caduceus.scn`: reference for a separate collision OBJ mapped to a deformable mechanical model via `BarycentricMapping`.

## Planned Scene Structure

`scenes/liver_surface_collision.py` should build:

- a liver volume FEM node from SOFA's `liver.msh`;
- tetrahedral topology, mechanical object, mass, `TetrahedralCorotationalFEMForceField`, solver, and fixed constraint;
- a separate liver collision child node from `liver-smooth.obj`;
- `TriangleCollisionModel`, `LineCollisionModel`, and `PointCollisionModel` on the collision surface;
- `BarycentricMapping` from the liver FEM mechanical state to the surface collision state;
- a separate visual surface node;
- a simple kinematic rigid sphere probe for contact testing.

The liver collision node must not use `SphereCollisionModel`. A sphere model is acceptable for the probe only.

## Smoke Test

Run:

```bash
scripts/run_sofa_python.sh scripts/check_liver_surface_collision.py
```

The smoke test should:

- load the scene with SofaPython3;
- run several simulation steps;
- check that the liver is FEM-deformable;
- check that the liver collision surface uses triangle, line, and point collision models;
- check that the liver collision surface is mapped through `BarycentricMapping`;
- check that the liver collision surface does not use `SphereCollisionModel`;
- move the probe into the surface and report whether contact/proximity is detected;
- fail with a clear error if SOFA mesh files are missing.

## Known Risks

- `liver-smooth.obj` to `liver.msh` barycentric mapping may fail if the installed mesh pair has scale or containment issues. If that happens, fallback to the `fallingSOFA.scn` pattern: extract a collision surface from the tetrahedral topology with `Tetra2TriangleTopologicalMapping`.
- The official liver fixed constraint uses a few point indices and is acceptable for smoke testing only. Dataset generation should later use explicit ROI-style boundary metadata.
- This first smoke does not prove NJF-quality local linearity. After the surface scene is stable, rerun the action-depth linearity diagnostics at `0.05`, `0.1`, and `0.2 mm`.

## Implementation Status

Status on 2026-06-29: standalone scene and smoke test are implemented and smoke-tested.

Files:

- `scenes/liver_surface_collision.py`
- `scripts/check_liver_surface_collision.py`

Observed smoke command:

```bash
scripts/run_sofa_python.sh scripts/check_liver_surface_collision.py --format json
```

Observed result:

```text
valid: true
volume mesh: liver.msh
surface mesh: liver-smooth.obj
mechanical nodes: 181
surface nodes: 2194
liver collision models: TriangleCollisionModel, LineCollisionModel, PointCollisionModel
liver collision mapping: BarycentricMapping
probe geometry: sphere
first contact/proximity step: 29
contact/proximity frames: 54
min signed gap: 0.05044 scene units, with detection threshold 0.051
max liver displacement: 0.51386 scene units
max surface displacement: 0.52510 scene units
```

The scene passes the current surface-collision smoke criteria, but it is not yet connected to `SofaFemBackend` or the NJF dataset orchestration layer.

## Small-Depth Linearity Diagnostic

Status on 2026-06-29: `scripts/diagnose_liver_surface_linearity.py` was added to test fixed-contact small-depth linearity on the standalone surface-collision liver scene. The diagnostic treats official liver coordinates as scene units by default and exposes `--scene-units-per-mm` if later calibration is needed.

Default diagnostic command:

```bash
scripts/run_sofa_python.sh scripts/diagnose_liver_surface_linearity.py --format json
```

Observed default result for `0.05`, `0.1`, and `0.2 mm` with `scene_units_per_mm=1.0`:

```text
valid: true
0.05 mm response norm: 0.30462, max displacement: 0.06108
0.10 mm response norm: 0.61183, max displacement: 0.11386
0.20 mm response norm: 1.21029, max displacement: 0.21324
0.05 -> 0.10 mm relative scale error: 0.05509, cosine: 0.99849
0.05 -> 0.20 mm relative scale error: 0.09858, cosine: 0.99520
```

Extended diagnostic command:

```bash
scripts/run_sofa_python.sh scripts/diagnose_liver_surface_linearity.py --depths-mm 0.05 0.1 0.2 0.3 0.5 --output tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_extended.json
```

Observed extended result:

```text
0.05 -> 0.10 mm relative scale error: 0.05509, keep
0.05 -> 0.20 mm relative scale error: 0.09858, keep but near threshold
0.05 -> 0.30 mm relative scale error: 0.12724, reject_or_retest
0.05 -> 0.50 mm relative scale error: 0.39802, reject_or_retest
```

Interpretation: surface collision appears to recover a practical local-linear range up to about `0.2 mm` under this fixed-contact, fixed-material, fixed-boundary diagnostic. `0.3 mm` already exceeds the current 10% scale-error threshold, so Stage 3 should use `0.05`, `0.1`, and cautious `0.2 mm` local actions until this is validated through the dataset backend.


## Scale Calibration

Status on 2026-06-29: `scripts/calibrate_liver_mesh_scale.py` was added to calibrate official liver scene units with a bounding-box long-axis assumption. The default target liver long axis is `150 mm`; callers can override it with `--target-long-axis-mm`.

Default command:

```bash
scripts/run_sofa_python.sh scripts/calibrate_liver_mesh_scale.py --format json
```

Observed default calibration from `liver-smooth.obj`:

```text
mesh bbox scene units: x=6.386355, y=4.907551, z=4.412135
long axis: x = 6.386355 scene units
target long axis: 150 mm
mm_per_scene_unit: 23.487576
scene_units_per_mm: 0.0425757
```

Converted action depths under this calibration:

```text
0.05 scene units -> 1.174 mm
0.10 scene units -> 2.349 mm
0.20 scene units -> 4.698 mm
0.30 scene units -> 7.046 mm
0.50 scene units -> 11.744 mm
```

A sanity run with `--target-long-axis-mm 120` produced `mm_per_scene_unit=18.790061` and `scene_units_per_mm=0.05321963`, confirming that external liver-size assumptions are supported.

Calibrated physical-mm linearity command:

```bash
scripts/run_sofa_python.sh scripts/diagnose_liver_surface_linearity.py --depths-mm 1 2 5 7 --scene-units-per-mm 0.0425757 --output tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_calibrated_150mm.json
```

Observed calibrated result:

```text
1 -> 2 mm relative scale error: 0.06050, keep
1 -> 5 mm relative scale error: 0.11418, reject_or_retest
1 -> 7 mm relative scale error: 0.13664, reject_or_retest
```

Interpretation after scale calibration: the robust NJF local target range is approximately `1-2 mm` under the 150 mm liver-long-axis assumption. Around `4-5 mm` is a near-boundary or rollout-evaluation range, not the safest core local Jacobian supervision range.

## Visualization

Status on 2026-06-29: `scripts/visualize_liver_surface_diagnostics.py` was added to render the scale calibration and local-linearity diagnostics as a standalone HTML/SVG report.

Command:

```bash
python3 scripts/visualize_liver_surface_diagnostics.py
```

Default inputs:

- `tissue_dataset_v0/outputs/liver_surface_scale_calibration/summary.json`
- `tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_calibrated_150mm.json`
- `tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_extended.json`

Default output:

```text
tissue_dataset_v0/outputs/liver_surface_visualization/report.html
```

The report visualizes mesh bounding-box calibration, scene-unit to physical-mm conversion, calibrated physical-mm relative scale error, response norm, and the uncalibrated scene-unit sweep. It is an offline diagnostic report, not a live SOFA renderer.

## Isaac Sim Tissue Deformation Visualization

Status on 2026-06-29: two scripts were added to visualize the actual liver surface deformation in Isaac Sim using the existing offline USD/USDA replay pattern.

Generate the SOFA deformation state:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_deformation_state.py --depth-mm 2
```

Export the Isaac Sim USDA replay:

```bash
env_isaacsim/bin/python scripts/export_liver_surface_deformation_isaacsim.py
```

Default output:

```text
tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/isaacsim_liver_surface_deformation.usda
```

The default USDA contains:

- `/World/LiverSurface`: animated mapped liver surface mesh with stable natural liver material, with time samples from baseline to deformed state;
- `/World/Probe`: animated sphere probe;
- `/World/ContactPoint`: contact marker.

To avoid unnatural color blending, baseline ghost mesh and displacement vectors are disabled by default. A debug version can be exported with:

```bash
env_isaacsim/bin/python scripts/export_liver_surface_deformation_isaacsim.py --show-baseline-ghost --show-displacement-vectors --output tissue_dataset_v0/outputs/liver_surface_deformation_isaacsim/isaacsim_liver_surface_deformation_debug.usda
```

The debug USDA additionally contains `/World/BaselineGhost` and `/World/DisplacementVectors`.

Observed 2 mm calibrated run:

```text
surface nodes: 2194
faces: 4384
contact frames: 120
max surface displacement: 0.101698 scene units
output USDA size: about 243 KB for the default natural-color view; debug USDA about 405 KB
```

This is the actual tissue deformation visualization path in Isaac Sim. It is separate from the diagnostic HTML report and follows the repository rule that SOFA simulation and offline replay/export stay separated.


## Dataset-Compatible Bridge Sample

Status on 2026-06-29: `scripts/generate_liver_surface_sample.py` now acts as a lightweight bridge from the standalone official-liver surface-collision scene into the existing `sample_*` artifact schema. This is intentionally not yet a full `SofaFemBackend` rewrite.

Single-sample command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite
```

Apples-to-apples calibrated local perturbation command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py --overwrite --output tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated --sample-id 1 --depths-mm 1.17 2.35 4.70
```

The bridge writes `vertices_0.npy`, `vertices_1.npy`, `displacement.npy`, `faces.npy`, `action.npy`, `tool_pose_0.npy`, `tool_pose_1.npy`, `tool_geometry.json`, `contact_summary.json`, `fixed_node_indices.npy`, `free_node_indices.npy`, `boundary_mask.npy`, `boundary.json`, `solver_summary.json`, simulation-time frame logs, `trajectory_summary.json`, and root-level `dataset_metadata.json`.

Coordinate and unit policy:

- SOFA official liver coordinates are converted before writing: `dataset_xyz = sofa_xzy`, so dataset `z` is vertical.
- Output vertex and tool coordinates are in meters.
- The default scale assumes a 150 mm liver long axis, matching `scripts/calibrate_liver_mesh_scale.py`; override with `--target-long-axis-mm`.
- `0.05`, `0.10`, and `0.20` SOFA scene units correspond to approximately `1.17`, `2.35`, and `4.70` mm under the default 150 mm calibration.

Contact and stepping policy:

- `--contact-distance-mm` now controls the SOFA contact response threshold and defaults to `0.1 mm`.
- `--contact-observation-distance-mm` controls only the discrete nearest-surface-vertex contact summary threshold and defaults to `1.2 mm`.
- `--alarm-distance-mm` remains a broad-phase/narrow-phase proximity setting and defaults to `12 mm`.
- `--probe-clearance-mm` defaults to `0.0`, so saved `tool_pose_0 -> tool_pose_1` motion matches the action depth.
- The bridge now follows `preload -> record X_t -> action_steps -> settle_steps -> record X_next`, matching the standalone linearity diagnostic more closely.
- Defaults are `preload_steps=60`, `action_steps=40`, and `settle_steps=80`.

Boundary policy for this bridge:

- The official liver demo fixes volume nodes `3, 39, 64`.
- Current bridge outputs surface vertices, not volume vertices, so the surface-level `boundary_mask` is all false and `fixed_node_indices.npy` is empty.
- `boundary.json` records `boundary_type: official_liver_volume_fixed_indices_surface_unmapped` to make this explicit.
- `tissue_dataset_v0/scripts/check_boundary_solver.py` accepts this boundary type instead of forcing `fixed_bottom` for all samples.

Observed calibrated bridge result:

```text
sample_000001: tool motion 1.170 mm, max displacement 1.631 mm
sample_000002: tool motion 2.350 mm, max displacement 3.083 mm
sample_000003: tool motion 4.700 mm, max displacement 5.413 mm
```

Verification passed:

```bash
python3 -m py_compile scripts/generate_liver_surface_sample.py tissue_dataset_v0/scripts/check_boundary_solver.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated/sample_000001 tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated/sample_000002 tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated/sample_000003
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated --min-samples 3 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated --min-samples 3 --max-angle-error-deg 0.1 --min-motion-mm 1.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_a_bridge_calibrated --min-samples 3
```

Linearity diagnostic on the calibrated bridge:

```text
1.17 -> 2.35 mm: scale_error=0.02506, cosine=0.99977
1.17 -> 4.70 mm: scale_error=0.05934, cosine=0.99867
```

Interpretation: after reducing SOFA `contactDistance`, separating contact-observation distance, and matching the standalone preload/action/settle procedure, the dataset-compatible bridge reproduces the earlier surface-collision linearity conclusion. The prior poor `0.25/0.5/1.0 mm` bridge result was caused by using action magnitudes smaller than the previous contact/proximity scale and by not matching the standalone diagnostic protocol.


## Mode B Response-Basis Bridge Smoke

Status on 2026-06-30: the surface-collision bridge can now generate a smoke-sized Mode B response-basis group with fixed official-liver state/contact/material/boundary and varied action direction/magnitude.

Command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --layout grouped \
  --direction-set basis_smoke \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke \
  --sample-id 1 \
  --depths-mm 1.17 2.35 \
  --preload-steps 0
```

Important Mode B state rule:

- `--preload-steps 0` is intentional for this group. It keeps `vertices_0` identical across directions, so the group satisfies fixed `X_t` semantics.
- Using direction-specific preload before recording `X_t` caused about `0.38 mm` max baseline mismatch across directions, which is not acceptable for strict response-basis grouping.
- The calibrated single-direction linearity diagnostic can still use preload/action/settle; Mode B basis grouping must prioritize a fixed initial state.

Direction and magnitude set:

```text
directions: normal, 12 degree tilt_x, 12 degree tilt_y
magnitudes: 1.17 mm, 2.35 mm
K: 6 actions
```

Output structure:

```text
tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/
  dataset_metadata.json
  samples/sample_000001 ... sample_000006
  groups/group_000001/
    group_metadata.json
    state_initial.npy
    fixed_node_mask.npy
    surface_points.npy
    actions.npy
    responses.npy
    contact_point.npy
    contact_normal.npy
```

Observed group facts:

```text
state_mismatch_max_m: 0.0
actions shape: [6, 6]
responses shape: [6, 2194, 3]
unique directions: 3
max response: about 3.53 mm
```

Verification passed:

```bash
python3 -m py_compile scenes/liver_surface_collision.py scripts/generate_liver_surface_sample.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples/sample_000001 tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples/sample_000002 tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples/sample_000003 tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples/sample_000004 tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples/sample_000005 tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples/sample_000006
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples --min-samples 6 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples --min-samples 6 --max-angle-error-deg 0.2 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 5.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/samples --min-samples 6
```

Response-basis analysis command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py \
  tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_smoke/analysis/response_basis_summary.json
```

Observed response-basis smoke result:

```text
effective_rank: 1.442
top1 cumulative explained: 0.895643
top2 cumulative explained: 0.991183
top3 cumulative explained: 0.999781
leave-one-out mean relative error: 0.050239
leave-one-out max relative error: 0.069371
```

Interpretation: this K=6 group is smoke-sized, but it already shows low-dimensional response structure under surface collision. The next dataset step should increase K to at least 12 by adding more directions and/or magnitudes before using the result as a research claim.

## Mode B Response-Basis Bridge v1

Status on 2026-06-30: the surface-collision bridge now supports a non-smoke Mode B response-basis group with `K=18` actions for one fixed official-liver state/contact/material/boundary.

Generator update:

- `scripts/generate_liver_surface_sample.py` adds `--direction-set basis_v1`.
- `basis_v1` keeps the previous normal direction and adds five 12 degree tilted directions: `tilt_pos_x`, `tilt_neg_x`, `tilt_pos_y`, `tilt_neg_y`, and `tilt_diag_xy`.
- The action type is now `surface_collision_directed_press`; vertical-only naming should no longer be used for nonvertical basis data.
- The group type is now `surface_collision_bridge_response_basis`; `smoke_sized_group` remains available to distinguish K<12 smoke groups.

Command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --layout grouped \
  --direction-set basis_v1 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1 \
  --sample-id 1 \
  --depths-mm 1.17 2.35 4.70 \
  --preload-steps 0
```

Mode B fixed-state rule remains unchanged: `--preload-steps 0` is required for this grouped basis dataset so `vertices_0` is identical across all actions.

Observed group facts:

```text
action_count: 18
unique directions: 6
action magnitudes: 1.17 mm, 2.35 mm, 4.70 mm
surface vertices: 2194
responses shape: [18, 2194, 3]
state_mismatch_max_m: 0.0
smoke_sized_group: false
max response: about 6.32 mm
```

Verification passed:

```bash
python3 -m py_compile scripts/generate_liver_surface_sample.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1/samples/sample_000001 ... sample_000018
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1/samples --min-samples 18 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1/samples --min-samples 18 --max-angle-error-deg 0.2 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 5.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1/samples --min-samples 18
```

Response-basis analysis:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_response_basis.py \
  tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_bridge_v1/analysis/response_basis_summary.json
```

Observed basis metrics:

```text
effective_rank: 1.358
top1 cumulative explained: 0.920643
top2 cumulative explained: 0.991576
top3 cumulative explained: 0.999615
leave-one-out mean relative error: 0.044930
leave-one-out max relative error: 0.094149
```

Interpretation: this single fixed-contact group supports the local low-dimensional response-basis hypothesis more strongly than the K=6 smoke group. It is still only one contact/material/boundary group, so it cannot answer cross-contact, cross-material, or shared-basis questions. The next experiment should generate multiple groups with one controlled variable changed at a time.

Known observation: the diagonal tilted direction has the largest observed penetration in this run, about `0.13 mm`, still below the current `2.0 mm` validation limit. Keep monitoring penetration and contact stability when adding more directions or contact points.

## Mode B Multi-Contact Response-Basis Dataset v1

Status on 2026-06-30: the surface-collision bridge can generate multiple Mode B groups by varying contact point while keeping material, boundary, solver, tool geometry, directions, and magnitudes fixed.

Generator update:

- `scenes/liver_surface_collision.py` accepts an optional explicit `contact_point` in SOFA coordinates. If omitted, it preserves the previous top-center default.
- `scripts/generate_liver_surface_sample.py` adds `--contact-set top_center|top_three`.
- `top_three` samples three top-surface contact points: `contact_top_left_000001`, `contact_top_center_000001`, and `contact_top_right_000001`.
- In grouped layout, each contact point writes one independent Mode B group, preserving the rule that a group fixes exactly one contact point.

Command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --layout grouped \
  --contact-set top_three \
  --direction-set basis_v1 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1 \
  --sample-id 1 \
  --depths-mm 1.17 2.35 4.70 \
  --preload-steps 0
```

Dataset facts:

```text
groups: 3
samples: 54
per-group K: 18
per-group directions: 6
per-group magnitudes: 1.17 mm, 2.35 mm, 4.70 mm
material: material_000001, Young's modulus 3000, Poisson ratio 0.3
boundary: boundary_official_liver_volume_fixed_indices
state_mismatch_max_m: 0.0 for every group
```

Verification passed:

```bash
scripts/run_sofa_python.sh -c "... build_default_validator over all 54 samples ..."
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1/samples --min-samples 54 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1/samples --min-samples 54 --max-angle-error-deg 0.2 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 5.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1/samples --min-samples 54
```

Group facts:

```text
group_000001 contact_top_left_000001: K=18, top2 explained=0.979604, effective_rank=1.711, loo_mean=0.093317, max_response=6.394 mm
group_000002 contact_top_center_000001: K=18, top2 explained=0.994204, effective_rank=1.158, loo_mean=0.049255, max_response=7.127 mm
group_000003 contact_top_right_000001: K=18, top2 explained=0.998654, effective_rank=1.041, loo_mean=0.021630, max_response=7.134 mm
```

Cross-group analysis command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py \
  tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1 \
  --rank 2 \
  --output-dir tissue_dataset_v0/outputs/liver_surface_mode_b_contact_three_v1/analysis/basis_across_groups
```

Cross-group result:

```text
mean effective rank: 1.303441
mean top2 cumulative explained: 0.990821
same_material_diff_contact pairs: 6
same_material_diff_contact projection similarity mean: 0.679566
same_material_diff_contact principal angle mean: 31.582 deg
same_material_diff_contact cross reconstruction error mean: 0.438450
```

Interpretation: group-internal responses remain low-dimensional at each contact point, but rank-2 bases are condition-dependent across contact points. This supports the NJF design assumption that the model should condition on contact point and local geometry instead of relying on one fixed global basis. The current dataset does not answer material or boundary variation; those require separate controlled groups.

## Mode B Material-Variation Response-Basis Dataset v1

Status on 2026-06-30: the surface-collision bridge can generate multiple Mode B groups by varying Young's modulus while keeping contact point, boundary, solver, tool geometry, action directions, and action magnitudes fixed.

Generator update:

- `scripts/generate_liver_surface_sample.py` adds `--material-set single|young_three`.
- `young_three` generates three materials with fixed Poisson ratio and Young's modulus values `1000`, `3000`, and `10000`.
- Material IDs and material parameters are now written into sample material payloads, request metadata, group metadata, and root dataset metadata.
- In grouped layout, each material writes one independent Mode B group, preserving the rule that a group fixes exactly one material.

Command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --layout grouped \
  --contact-set top_center \
  --material-set young_three \
  --direction-set basis_v1 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1 \
  --sample-id 1 \
  --depths-mm 1.17 2.35 4.70 \
  --preload-steps 0
```

Dataset facts:

```text
groups: 3
samples: 54
contact point: contact_top_center_000001 for every group
per-group K: 18
per-group directions: 6
per-group magnitudes: 1.17 mm, 2.35 mm, 4.70 mm
Young's modulus values: 1000, 3000, 10000
Poisson ratio: 0.3
state_mismatch_max_m: 0.0 for every group
```

Verification passed:

```bash
scripts/run_sofa_python.sh -c "... build_default_validator over all 54 samples ..."
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1/samples --min-samples 54 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1/samples --min-samples 54 --max-angle-error-deg 0.2 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 5.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1/samples --min-samples 54
```

Group facts:

```text
group_000001 material_young_1000: K=18, top2 explained=0.997753, effective_rank=1.209, loo_mean=0.025464, response_norm_mean=0.097851 m, max_response=8.447 mm
group_000002 material_young_3000: K=18, top2 explained=0.994204, effective_rank=1.158, loo_mean=0.049255, response_norm_mean=0.065985 m, max_response=7.127 mm
group_000003 material_young_10000: K=18, top2 explained=0.988022, effective_rank=1.242, loo_mean=0.080493, response_norm_mean=0.033249 m, max_response=7.324 mm
```

Cross-group analysis command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_basis_across_groups.py \
  tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1 \
  --rank 2 \
  --output-dir tissue_dataset_v0/outputs/liver_surface_mode_b_material_three_v1/analysis/basis_across_groups
```

Cross-material result:

```text
mean effective rank: 1.203186
mean top2 cumulative explained: 0.993326
same_contact_diff_material pairs: 6
same_contact_diff_material projection similarity mean: 0.760302
same_contact_diff_material principal angle mean: 27.189 deg
same_contact_diff_material cross reconstruction error mean: 0.323145
```

Material-scale result:

```text
E 1000 vs 3000: response_norm_ratio=1.482933, normalized_cross_error=0.301817, normalized_projection_similarity=0.866815
E 1000 vs 10000: response_norm_ratio=2.942958, normalized_cross_error=0.589260, normalized_projection_similarity=0.669125
E 3000 vs 10000: response_norm_ratio=1.984552, normalized_cross_error=0.465776, normalized_projection_similarity=0.844478
```

Interpretation: each fixed-material group remains low-dimensional. Increasing Young's modulus reduces response norm on average, but not according to a simple inverse-stiffness scale law under the current position-controlled constraint-contact setup. Normalized cross-material errors indicate that material changes also alter response pattern/basis, not only amplitude. Future NJF inputs should include material conditioning.

## Mode B Factorial Contact-Material Dataset v1

Status on 2026-06-30: the surface-collision bridge generated a small factorial Mode B dataset crossing contact point and Young's modulus.

Command:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --layout grouped \
  --contact-set top_three \
  --material-set young_three \
  --direction-set basis_v1 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1 \
  --sample-id 1 \
  --depths-mm 1.17 2.35 4.70 \
  --preload-steps 0
```

Dataset facts:

```text
contacts: 3, top_left/top_center/top_right
materials: 3, Young's modulus 1000/3000/10000, Poisson ratio 0.3
groups: 9
samples: 162
per-group K: 18
per-group directions: 6
per-group magnitudes: 1.17 mm, 2.35 mm, 4.70 mm
state_mismatch_max_m: 0.0 for every group
```

Verification passed:

```bash
python3 -m py_compile scenes/liver_surface_collision.py scripts/generate_liver_surface_sample.py
scripts/run_sofa_python.sh -c "... build_default_validator over all 162 samples ..."
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1/samples --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require boundary_mask --require fixed_node_indices --require free_node_indices --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1/samples --min-samples 162 --max-min-gap-mm 2.0 --max-penetration-mm 2.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1/samples --min-samples 162 --max-angle-error-deg 0.2 --min-motion-mm 1.0 --require-nonvertical --min-max-tilt-deg 5.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1/samples --min-samples 162
```

Per-group response basis result:

```text
groups: 9
mean effective rank: 1.286046
mean top2 cumulative explained: 0.987973
mean leave-one-out error: 0.061361
effective rank range: 1.041 to 1.711
top2 range: 0.967158 to 0.999208
```

Cross-group rank-2 basis result:

```text
same_contact_diff_material: pairs=18, projection_similarity=0.800843, principal_angle_mean=24.021 deg, cross_reconstruction_error=0.343122
same_material_diff_contact: pairs=18, projection_similarity=0.614229, principal_angle_mean=36.844 deg, cross_reconstruction_error=0.490669
diff_contact_diff_material: pairs=36, projection_similarity=0.565954, principal_angle_mean=40.695 deg, cross_reconstruction_error=0.534312
all off-diagonal cross_reconstruction_error mean: 0.475604
```

Material-scale pattern across all contacts:

```text
Many same-contact material comparisons remain pattern-changing after normalization.
Examples:
left E1000 vs E3000: normalized_cross_error=0.208872, mostly scale with some pattern change
center E1000 vs E10000: normalized_cross_error=0.589260, pattern changes
right E1000 vs E10000: normalized_cross_error=0.801861, pattern changes
```

Held-out shared-basis smoke:

```text
train groups: left + center contacts, all three materials, 6 groups
test groups: right contact, all three materials, 3 groups
rank: 2
test_error_mean: 0.260164
test_error_max: 0.313995
per-test errors: E1000=0.208318, E3000=0.258177, E10000=0.313995
```

Interpretation: the factorial dataset confirms the earlier one-factor findings. Every fixed contact/material group remains low-dimensional, but basis transfer degrades as conditions change. Material changes at fixed contact are easier to reconstruct than contact changes at fixed material, and changing both contact and material is hardest. A rank-2 shared basis trained on left+center contacts partially generalizes to right contact but still has nontrivial reconstruction error. This supports conditioning NJF on both contact/local geometry and material parameters.

## Mode C Rollout Bridge v1

The first surface-collision Mode C rollout bridge is implemented in `scripts/generate_liver_surface_rollout.py`. It runs one continuous SOFA scene and writes trajectory artifacts directly under `trajectories/traj_*`, rather than stitching together independent single-step samples. The contact point mode is `fixed_material_point`; per-step geometric contact observations are currently nearest-surface signed-gap summaries, not SOFA contact forces.

Command used for the first useful T=10 rollout:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_rollout.py \
  --overwrite \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1 \
  --steps 10 \
  --step-size-mm 1.17 \
  --contact-set top_center \
  --material-set single \
  --direction-set vertical \
  --direction-id normal \
  --preload-steps 0 \
  --action-substeps 40 \
  --settle-steps-per-step 20
```

Generated trajectory artifacts:

```text
metadata.json
dataset_metadata.json
trajectories/traj_000001/trajectory_metadata.json
trajectories/traj_000001/solver_status.json
trajectories/traj_000001/states.npy          # [11, 2194, 3]
trajectories/traj_000001/actions.npy         # [10, 6]
trajectories/traj_000001/responses.npy       # [10, 2194, 3]
trajectories/traj_000001/contact_points.npy  # [10, 3]
trajectories/traj_000001/contact_normals.npy # [10, 3]
trajectories/traj_000001/tool_poses.npy      # [11, 4, 4]
trajectories/traj_000001/fixed_node_mask.npy # [2194]
trajectories/traj_000001/contact_status.npy  # [10]
trajectories/traj_000001/contact_distances.npy # [10]
```

Validation passed:

```bash
python3 -m py_compile scripts/generate_liver_surface_rollout.py tissue_dataset_v0/src/tissue_dataset_v0/njf/dataset.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1 --min-steps 10
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_njf_dataset.py tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1 --require-mode rollout_trajectory --min-trajectories 1
```

Observed result:

```text
T: 10
step_size: 1.170 mm
final_max_deformation: 15.866 mm
max_per_step_response: 1.772 mm
contact_active: 10/10
contact_distance_range: 0.111 mm to 0.338 mm
tool_step_error_max: 0.000009 mm
tool_action_angle_error_max: 0.000000 deg
fixed_node_motion_max: 0.000000 mm
reader trajectory_state_shape: [11, 2194, 3]
```

Interpretation: this dataset is not a local-linearity proof by itself. It is the first Mode C artifact for evaluating rolling prediction: ten small fixed-contact tool increments are saved with all intermediate states, actions, tool poses, contact status, and responses. The accumulated deformation is intentionally much larger than the per-step target, so it should be used to test whether a small-step model can integrate over a longer action, not as a single local Jacobian supervision sample.

## Mode C Rollout Analysis v1

The rollout analyzer now reports response-drift metrics, a no-model constant-first-step rollout baseline, optional matched single-large-step comparison, and per-step CSV output. The current command sequence was:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py \
  tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1 \
  --min-steps 10 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1/analysis/rollout_drift_summary.json \
  --csv-dir tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1/analysis

scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --output tissue_dataset_v0/outputs/liver_surface_single_large_11p7_v1 \
  --sample-id 1 \
  --layout flat \
  --contact-set top_center \
  --material-set single \
  --direction-set vertical \
  --depth-mm 11.7 \
  --preload-steps 0 \
  --action-steps 400 \
  --settle-steps 200

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py \
  tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1 \
  --min-steps 10 \
  --single-step-sample tissue_dataset_v0/outputs/liver_surface_single_large_11p7_v1/sample_000001 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1/analysis/rollout_vs_single_large_summary.json \
  --csv-dir tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_v1/analysis
```

Result summary:

```text
rollout: PASS
single-large sample validation/contact/tool-direction: PASS
adjacent response cosine mean: 0.981063
adjacent relative response change mean: 0.204464
first-step vs final-step response cosine: 0.946018
constant-first-step final relative L2 error: 0.221470
constant-first-step final max node error: 4.612 mm
single-large vs 10-step rollout relative L2 error: 0.022662
single-large vs 10-step rollout pattern cosine: 0.999745
single-large vs 10-step rollout max node error: 0.487 mm
```

Interpretation: for this top-center vertical quasi-static trajectory, the final state is nearly path-independent between one slow 11.7 mm press and ten 1.17 mm steps. However, the local per-step response is not constant across the rollout; repeating the first-step response produces a substantial final error. This supports using Mode C for state-conditioned rolling response evaluation. It does not, by itself, prove large-step final-state prediction is bad in this simplified quasi-static scene.

## Mode C Tilt-X 3x3 Rollout Analysis v1

Generated a non-vertical rollout batch to test whether the single top-center vertical rollout conclusion generalizes across contact and material conditions. The batch uses `tilt_pos_x` from `basis_v1`, top-left/top-center/top-right contacts, and Young modulus 1000/3000/10000. Each trajectory uses `T=10`, `step_size=1.17 mm`, total displacement `11.7 mm`, fixed material contact point, `40` action substeps, and `20` settle steps per rollout step.

Generation and validation:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_rollout.py \
  --overwrite \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1 \
  --steps 10 \
  --step-size-mm 1.17 \
  --contact-set top_three \
  --material-set young_three \
  --direction-set basis_v1 \
  --direction-id tilt_pos_x \
  --preload-steps 0 \
  --action-substeps 40 \
  --settle-steps-per-step 20

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py \
  tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1 \
  --min-steps 10 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_drift_summary.json \
  --csv-dir tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_njf_dataset.py \
  tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1 \
  --require-mode rollout_trajectory \
  --min-trajectories 9
```

Validation passed with `9` trajectories, `0` errors, `0` warnings. `read_njf_dataset.py` also passed with `trajectory_count=9`. All trajectories had `contact_active=10/10`.

Aggregate results:

```text
final_max_mm: min=13.269013, mean=15.533157, max=19.755029
step_response_max_mm: min=1.651124, mean=2.246438, max=3.934977
adjacent_cos_mean: min=0.780920, mean=0.903977, max=0.987810
adjacent_rel_change_mean: min=0.160621, mean=0.394453, max=0.712843
first_step_cos_final: min=0.051641, mean=0.798732, max=0.957254
constant_first_step_final_rel_l2: min=0.202028, mean=0.432849, max=0.803623
constant_first_step_final_max_node_error_mm: min=3.453103, mean=7.062486, max=11.996601
```

Worst fixed-first-step baseline was `traj_000009` (`contact_top_right_000001`, `material_young_10000`): final relative L2 error `0.803623`, final max-node error `6.455 mm`, and first-step/final-step cosine `0.051641`.

Interpretation: the top-center vertical rollout was too narrow to characterize Mode C behavior. Under non-vertical tilted action, response drift varies strongly across contact/material settings. This strengthens the need for state-conditioned rolling prediction evaluation. A fixed initial response/Jacobian baseline is not reliable across the 3x3 batch.

Artifacts:

```text
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_drift_summary.json
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_tilt_x_3x3_metrics.csv
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_tilt_x_3x3_report.md
```

## Mode C Tilt-X 3x3 Matched Single-Large Comparison v1

Added `--direction-id` to `scripts/generate_liver_surface_sample.py`, so matched single-large samples can be generated for one selected direction from `basis_v1` instead of all six directions. Also extended `tissue_dataset_v0/scripts/analyze_rollout_trajectories.py` so `--single-step-sample` can point at a dataset root with multiple `sample_*` directories; the analyzer matches each trajectory by `contact_point_id`, `material_id`, `direction_id`, and total action magnitude.

Matched single-large generation:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_sample.py \
  --overwrite \
  --output tissue_dataset_v0/outputs/liver_surface_single_large_tilt_x_3x3_11p7_v1 \
  --sample-id 1 \
  --layout flat \
  --contact-set top_three \
  --material-set young_three \
  --direction-set basis_v1 \
  --direction-id tilt_pos_x \
  --depth-mm 11.7 \
  --preload-steps 0 \
  --action-steps 400 \
  --settle-steps 200
```

Validation passed: default sample validation checked `9` samples with `0` errors and `0` warnings; contact check passed; tool-direction check passed with `12` degree tilt for every sample.

Matched comparison command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/analyze_rollout_trajectories.py \
  tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1 \
  --min-steps 10 \
  --single-step-sample tissue_dataset_v0/outputs/liver_surface_single_large_tilt_x_3x3_11p7_v1 \
  --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_vs_single_large_summary.json \
  --csv-dir tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis
```

Result summary:

```text
single_large_rel_l2: min=0.015604, mean=0.071319, max=0.221009
single_large_pattern_cosine: min=0.976668, mean=0.995937, max=0.999929
single_large_max_node_error_mm: min=0.205648, mean=0.734584, max=1.905619
constant_first_step_final_rel_l2: min=0.202028, mean=0.432849, max=0.803623
constant_first_step_final_max_node_error_mm: min=3.453103, mean=7.062486, max=11.996601
```

Worst single-large mismatch was `traj_000009` (`contact_top_right_000001`, `material_young_10000`): single-large relative L2 error `0.221009`, pattern cosine `0.976668`, max node error `1.493 mm`.

Interpretation: even in the non-vertical 3x3 batch, one slow 11.7 mm press is usually close to the final state of ten 1.17 mm steps. However, this does not make large-step data sufficient for NJF because the per-step response changes along the rollout. The same batch has much larger fixed-first-step rollout errors. The final-state map can be quasi-static/path-insensitive while the local response field is still state-conditioned.

Artifacts:

```text
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_vs_single_large_summary.json
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_vs_single_large_tilt_x_3x3_metrics.csv
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_vs_single_large_tilt_x_3x3_report.md
```

## Mode C Basis-Projection Diagnostic v1

Implemented `tissue_dataset_v0/scripts/analyze_rollout_basis_projection.py` to test whether fixed Mode B response bases explain Mode C rollout step responses. This is a SOFA-free offline analysis; it reads saved `groups/group_*` and `trajectories/traj_*` artifacts only.

Basis definition for this experiment:

```text
source: tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_v1/groups/group_*
fixed variables per basis: tissue mesh/state X0, contact_point_id, material_id, boundary_id, tool geometry, solver/contact config
varied variables inside the basis group: action direction and action magnitude
basis construction: uncentered SVD/PCA on response rows, R_g = [delta_X_1, ..., delta_X_K]
rollout use: one fixed U_g per matched trajectory; U_g is not recomputed for X_k
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

Validation/result status: PASS, `9` trajectories matched to `9` basis groups, `27` rank-specific results, `0` errors.

Aggregate results:

```text
rank 2:
  step_relative_error_mean=0.258662
  final_accumulated_relative_l2_error_mean=0.211910
  final_accumulated_relative_l2_error_max=0.423117
  constant_first_step_final_relative_l2_mean=0.432849
  improvement_vs_constant_final_l2_mean=0.220939

rank 3:
  step_relative_error_mean=0.187414
  final_accumulated_relative_l2_error_mean=0.176309
  final_accumulated_relative_l2_error_max=0.417558
  constant_first_step_final_relative_l2_mean=0.432849
  improvement_vs_constant_final_l2_mean=0.256540

rank 4:
  step_relative_error_mean=0.170237
  final_accumulated_relative_l2_error_mean=0.168869
  final_accumulated_relative_l2_error_max=0.375371
  constant_first_step_final_relative_l2_mean=0.432849
  improvement_vs_constant_final_l2_mean=0.263980
```

Interpretation: fixed Mode B bases substantially improve over the fixed-first-step response baseline, which means response subspaces are more stable than individual step responses. However, rank 4 still leaves nontrivial rollout error, especially in worst-case trajectories. This suggests the current `basis_v1` small-cone action family captures an important part of the rollout response space but is not a complete state-conditioned model. The next modeling/evaluation target should be coefficient prediction or state-conditioned basis/Jacobian prediction, not just a fixed response vector.

Artifacts:

```text
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_summary.json
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_metrics.csv
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_tilt_x_3x3_v1/analysis/rollout_basis_projection_report.md
```

