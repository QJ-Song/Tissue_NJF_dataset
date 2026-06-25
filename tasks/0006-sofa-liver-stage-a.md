# Task: SOFA Liver-Like Stage A Dataset

## Goal

Run Stage A for SOFA tissue simulation: keep tissue geometry and material fixed, randomize only the press action, and use a fixed organ-like tissue shape instead of a rectangular slab.

## Design

Stage A intentionally does not randomize material, mesh topology, solver settings, or tissue shape. The only per-sample random variables are `ActionSpec.contact_point` and press `depth` from the YAML action sampler.

The tissue is not imported from an external anatomical asset. `SofaFemBackend` now supports `sofa_tissue_shape: liver_like`, which procedurally warps the regular grid positions into an asymmetric rounded organ-like volume while keeping topology and vertex count fixed. This keeps the dataset easy to validate and train on while avoiding the plain rectangular slab appearance.

## Implementation

Changed files:

- `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py`
  - Added `sofa_tissue_shape` support with default `slab` and optional `liver_like`.
  - Added procedural liver-like initial vertex positions.
  - Changed bottom constraint to direct bottom-layer indices, so non-planar organ-like bottom surfaces remain fixed.
  - Kept localized probe force around `ActionSpec.contact_point`.
- `tissue_dataset_v0/src/tissue_dataset_v0/config/yaml_loader.py`
  - Added `backend.extra` parsing into `GenerationConfig.backend_extra`.
- `tissue_dataset_v0/scripts/generate_from_yaml.py`
  - Applies `backend.extra` to `SampleConfig.extra` for each generated request.
- `tissue_dataset_v0/configs/sofa_liver_stage_a.yaml`
  - New Stage A config: fixed liver-like tissue, fixed material, random action.
- `tissue_dataset_v0/scripts/check_stage_a.py`
  - New reusable Stage A sanity-check CLI.

## Stage A Config

`tissue_dataset_v0/configs/sofa_liver_stage_a.yaml` uses:

- `backend.type: sofa_fem`
- `backend.extra.sofa_tissue_shape: liver_like`
- fixed material: `youngs_modulus=5000`, `poisson_ratio=0.45`, `density=1000`, `damping=0.5`
- fixed topology: `nx=8`, `ny=6`, `layers=4`, yielding 252 vertices
- random action: `contact_margin=0.026`, `depth=[0.004, 0.009]`
- output directory: `tissue_dataset_v0/outputs/sofa_liver_stage_a`

## Smoke Results

Commands run:

```bash
scripts/run_sofa_python.sh -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_stage_a.yaml
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_stage_a/sample_000001 --viewer summary --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_stage_a/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_stage_a
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_stage_a --format json
```

Validation was run for all five generated samples. All passed with zero errors and zero warnings. The reusable Stage A sanity checker also passed with zero errors and zero warnings.

Observed Stage A sanity checks:

```text
sample_000001 max displacement 3.78 mm, max downward z 2.81 mm
sample_000002 max displacement 1.66 mm, max downward z 1.64 mm
sample_000003 max displacement 2.16 mm, max downward z 1.67 mm
sample_000004 max displacement 2.39 mm, max downward z 2.37 mm
sample_000005 max displacement 2.91 mm, max downward z 2.15 mm
```

The material tuple was identical for all five samples: `(5000.0, 0.45, 1000.0, 0.5)`. The action contact point and depth changed per sample. Max displacement locations were within the configured probe radius in the coarse mesh sanity check. `sample_000001` was exported to Isaac USD replay at `tissue_dataset_v0/outputs/sofa_liver_stage_a/sample_000001/replay_isaacsim/isaacsim_replay.usda`.

## Limitations

The liver-like shape is a fixed procedural approximation, not an anatomical liver mesh. It preserves fixed topology for Stage A. The probe is still a localized force approximation, not full SOFA collision/contact. The replay tool sphere remains a visual marker and does not need to contact the tissue surface.

## Stage A Sanity Checker

`check_stage_a.py` accepts one or more dataset roots or `sample_*` directories. It checks:

- minimum sample count;
- fixed material across samples;
- action variation through contact-point spread and depth spread;
- visible but bounded displacement range;
- distance from maximum displacement vertex to requested contact point.

Default thresholds used for the current Stage A smoke set:

```text
min samples: 2
max displacement range: 0.3 mm to 6.0 mm
max downward z displacement: 5.0 mm
minimum contact spread: 1.0 mm
minimum depth spread: 0.5 mm
locality limit: max(30 mm, 1.25 * sofa_probe_radius)
```

Observed command output:

```text
Stage A sanity check: PASS
samples=5 errors=0 warnings=0
```

## Next Step

Inspect `sample_000001` in Isaac Sim and decide whether the fixed procedural liver-like shape is sufficient for Stage A. If accepted, the next engineering task is Stage B: keep the same tissue shape/topology and random action while adding bounded material randomization.
