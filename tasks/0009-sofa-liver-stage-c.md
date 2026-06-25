# Task: SOFA Liver-Like Stage C Dataset

## Goal

Run Stage C by combining three independent randomization axes: action, material, and geometry. Keep topology fixed so the existing dataset reader can still report fixed array shapes and future direct batching remains possible.

## Design

Stage C keeps fixed:

- tissue shape family: `liver_like`;
- topology: `nx=8`, `ny=6`, `layers=4`;
- solver settings;
- localized probe force approximation;
- density and boundary condition.

Stage C randomizes independently:

- action contact point and depth;
- material Young's modulus, Poisson ratio, and damping;
- geometry `size_x`, `size_y`, and `thickness`.

The independence is intentional: action, material, and geometry can be enabled in different combinations by future configs. `SceneSampler` now samples geometry first, then uses that sampled geometry to sample the action so `contact_point` remains valid after geometry changes.

## Implementation

Changed files:

- `tissue_dataset_v0/src/tissue_dataset_v0/sampling/geometry_sampler.py`
  - Added `FixedGeometrySampler` and `UniformGeometrySampler`.
- `tissue_dataset_v0/src/tissue_dataset_v0/sampling/scene_sampler.py`
  - Samples geometry per sample before material/action; action sees the sampled geometry.
- `tissue_dataset_v0/src/tissue_dataset_v0/config/yaml_loader.py`
  - Geometry fields now accept fixed floats or `[min, max]` ranges.
- `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py`
  - Writes actual per-sample geometry into `meta.geometry`.
- `tissue_dataset_v0/scripts/check_stage_a.py`
  - Added `--geometry-mode fixed|varying`, geometry spread checks, fixed-topology checks, and contact-in-geometry checks.
- `tissue_dataset_v0/configs/sofa_liver_stage_c.yaml`
  - New Stage C config.

## Stage C Config

`tissue_dataset_v0/configs/sofa_liver_stage_c.yaml` uses:

- output directory: `tissue_dataset_v0/outputs/sofa_liver_stage_c`;
- `num_samples: 10`;
- geometry ranges: `size_x=[0.11, 0.13]`, `size_y=[0.078, 0.092]`, `thickness=[0.016, 0.020]`;
- fixed topology: `nx=8`, `ny=6`, `layers=4`;
- material ranges same as Stage B;
- action depth range: `0.004` to `0.008`.

## Commands Run

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_stage_b --material-mode varying --geometry-mode fixed --min-samples 5 --max-max-displacement-mm 7.0 --max-downward-z-mm 6.0 --max-contact-distance-mm 35.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_stage_c.yaml
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_stage_c --material-mode varying --geometry-mode varying --min-samples 5 --max-max-displacement-mm 7.0 --max-downward-z-mm 6.0 --max-contact-distance-mm 35.0
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_stage_c
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_stage_c/sample_000003 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

All ten Stage C samples passed `validate_sample.py` with zero errors and zero warnings.

## Results

The three-axis sanity check passed with zero errors and zero warnings. `read_dataset_smoke.py` also passed and reported fixed array shapes despite geometry variation:

```text
vertices_0: [252, 3], fixed=True
vertices_1: [252, 3], fixed=True
displacement: [252, 3], fixed=True
faces: [180, 4], fixed=True
```

Observed Stage C displacement range in the smoke set:

```text
max displacement: 0.52 mm to 4.75 mm
max downward z displacement: 0.51 mm to 3.12 mm
```

The sanity checker also verified that contact points stayed inside the sampled geometry bounds and topology stayed fixed. Isaac USD replay was exported for `sample_000003` at `tissue_dataset_v0/outputs/sofa_liver_stage_c/sample_000003/replay_isaacsim/isaacsim_replay.usda`.

## Limitations

Stage C randomizes only global geometry dimensions, not topology or anatomical shape parameters. The backend still uses localized force, not real SOFA collision/contact. The checker validates practical consistency, not physical realism.

## Next Step

Inspect Stage C visually/statistically. If accepted, the next major physics task is Stage D: replacing the localized force approximation with real SOFA probe/collision/contact while preserving the dataset schema and randomization-axis independence.
