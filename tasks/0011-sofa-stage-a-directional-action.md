# Task: SOFA Stage A Directional Action Extension

## Goal

Extend Stage A action sampling so the press action is not always vertical downward. The tissue and material should remain fixed, but the action should randomize contact point, press depth, and direction. This should happen before Stage D probe/contact work so action direction semantics are stable before mapping action to tool pose.

## Motivation

The current action vector already has direction slots:

```text
(contact_x, contact_y, dir_x, dir_y, dir_z, depth)
```

Current configs always use:

```text
dir = (0, 0, -1)
```

This only represents vertical pressing from above. Real tool-tissue interactions often include tilted approaches, oblique pressing, and tangential components. Direction is an important action condition for future deformation learning and Stage D physical probe/contact.

## Scope

Implement an action-direction extension of Stage A:

- fixed tissue shape/topology;
- fixed material;
- randomized contact point;
- randomized depth;
- randomized direction sampled from the upper hemisphere above the table plane, but initially constrained to a cone for stability.

Do not use a full unconstrained hemisphere at first. Directions with `dir_z` near zero behave more like scraping/shearing than pressing and may destabilize the current localized-force approximation and future contact prototype.

## Proposed Action Sampling

Add config fields to `action_sampler`:

```yaml
action_sampler:
  type: uniform_press
  contact_margin: 0.026
  depth: [0.004, 0.008]
  direction_mode: upper_hemisphere_cone
  max_tilt_deg: 45
```

Sampling rule:

```text
phi ~ Uniform(0, 2*pi)
cos(theta) ~ Uniform(cos(max_tilt), 1)
dir_x = sin(theta) * cos(phi)
dir_y = sin(theta) * sin(phi)
dir_z = -cos(theta)
```

This samples directions in a downward cone from the upper hemisphere. The initial implementation uses `max_tilt_deg=30` for the default directional config. A 45 degree smoke run produced one sample with excessive displacement, so wider cones should be treated as later tuning experiments rather than the first stable default.

Keep `direction_mode: vertical_down` as backward-compatible default.

## Backend Change

Current localized force direction is fixed downward. It should use the normalized action direction:

```text
force_vec = force_magnitude * normalize(action[2:5])
```

Requirements:

- if action direction is missing or zero-norm, fallback to `(0, 0, -1)`;
- require/validate `dir_z < 0` for press-like actions;
- keep force magnitude/depth behavior unchanged except for direction.

This is still a localized force approximation, not physical probe contact.

## New Config

Do not overwrite existing Stage A. Add a separate config, suggested name:

```text
tissue_dataset_v0/configs/sofa_liver_stage_a_directional.yaml
```

This config should keep Stage A fixed tissue/material and enable action direction randomization.

## Sanity Checks

Extend `check_stage_a.py` or add a small action-direction check. Required checks:

- action direction norm is close to `1`;
- `dir_z < 0`;
- tilt angle does not exceed configured `max_tilt_deg` plus tolerance;
- direction spread is nonzero across samples;
- contact point remains inside sampled geometry;
- displacement remains bounded and visible;
- old vertical Stage A/B/C checks still pass.

Suggested CLI options:

```text
--direction-mode fixed|varying
--max-tilt-deg 45
--min-direction-spread-deg 5
```

## Replay Notes

The current gray replay sphere is a visual marker and does not need to touch the surface. Directional action can initially be validated numerically without changing replay. Later, add an optional direction arrow/line marker or use saved tool poses after Stage D D2.

## Compatibility Requirements

- Keep existing `UniformPressActionSampler` behavior by default.
- Do not break Stage A/B/C generated data.
- Do not change required core sample fields.
- Direction remains encoded in existing `action.npy`, so the manifest/loader should not need a new required field.
- The change should be compatible with Stage D, where direction will inform `tool_pose_0 -> tool_pose_1`.

## Suggested Implementation Plan

1. Extend `UniformPressActionSampler` with `direction_mode` and `max_tilt_deg`.
2. Extend YAML loader to read those fields.
3. Update `SofaFemBackend._force_from_action` or equivalent force-vector helper to apply force along `action[2:5]`.
4. Add `sofa_liver_stage_a_directional.yaml`.
5. Extend sanity checker for direction norm/tilt/spread.
6. Generate a small directional Stage A dataset.
7. Run compile checks, validator, sanity checker, dataset reader, and one replay export.
8. Update this task with actual results.

## Acceptance Criteria

- Directional Stage A config generates at least 5 samples.
- All samples pass `validate_sample.py`.
- Sanity checker confirms direction variation and bounded tilt.
- Dataset reader smoke passes.
- Existing Stage A/B/C sanity checks still pass.
- One sample exports to Isaac USD replay.

## Implementation Results

Status: implemented on 2026-06-24.

Changed code/config:

- `UniformPressActionSampler` now supports `direction_mode` and `max_tilt_deg`.
- `direction_mode: vertical_down` remains the backward-compatible default.
- `direction_mode: upper_hemisphere_cone` samples directions uniformly over solid angle inside a downward cone.
- `config/yaml_loader.py` forwards `direction_mode` and `max_tilt_deg` from YAML.
- `SofaFemBackend` now applies the localized `ConstantForceField` along normalized `action[2:5]` instead of hard-coding vertical `z` force.
- `check_stage_a.py` now validates direction norm, downward `dir_z`, max tilt, and fixed/varying direction spread.
- `tissue_dataset_v0/configs/sofa_liver_stage_a_directional.yaml` was added.

Default directional tuning:

- The first attempted 45 degree cone generated 5 samples but one sample reached `7.953 mm` max displacement, above the current `6 mm` sanity bound.
- The stable smoke config was narrowed to `max_tilt_deg: 30` and writes to `tissue_dataset_v0/outputs/sofa_liver_stage_a_directional_30deg/`.
- Observed 30 degree smoke displacement range was `2.20 mm` to `5.44 mm`, with max tilt `25.3 deg` in the generated 5-sample set.

Verification run:

```bash
python3 -m py_compile \
  tissue_dataset_v0/src/tissue_dataset_v0/sampling/action_sampler.py \
  tissue_dataset_v0/src/tissue_dataset_v0/config/yaml_loader.py \
  tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py \
  tissue_dataset_v0/scripts/check_stage_a.py

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py \
  tissue_dataset_v0/configs/sofa_liver_stage_a_directional.yaml

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_a_directional_30deg \
  --min-samples 5 \
  --direction-mode varying \
  --max-tilt-deg 30 \
  --min-direction-spread-deg 5 \
  --max-contact-distance-mm 35.0

scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_a_directional_30deg

env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py \
  tissue_dataset_v0/outputs/sofa_liver_stage_a_directional_30deg/sample_000001 \
  --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

Results:

- `validate_sample.py` passed for all 5 directional samples.
- Directional sanity passed with zero errors and zero warnings.
- `read_dataset_smoke.py` passed with fixed shapes: `vertices=[252, 3]`, `faces=[180, 4]`, `action=[6]`.
- Existing Stage A, Stage B, and Stage C sanity checks still passed with `direction-mode=fixed`.
- Isaac USD replay exported `sample_000001/replay_isaacsim/isaacsim_replay.usda`.

Remaining limitation: Isaac replay still animates the gray tool marker vertically from `contact_point`; it does not visualize the oblique direction yet. This is acceptable until Stage D D2 records reliable tool poses.

## Open Questions

- Should the initial cone be `45 deg` or `60 deg`? Answer for the first stable config: use `30 deg`; the 45 degree smoke run exceeded the current displacement bound in one sample.
- Should direction sampling be uniform over solid angle or over tilt angle? Prefer uniform over solid angle using uniform `cos(theta)`.
- Should future shear/scrape actions be a separate action type instead of extreme-tilt press? Likely yes.
