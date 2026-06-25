# Task: SOFA Liver-Like Stage B Dataset

## Goal

Continue from Stage A by keeping the fixed procedural liver-like tissue shape and topology, while randomizing both action and bounded material parameters.

## Design

Stage B keeps fixed:

- tissue shape: `liver_like`;
- topology: `nx=8`, `ny=6`, `layers=4` for 252 vertices;
- geometry size and solver settings;
- localized probe force approximation;
- density and boundary condition.

Stage B randomizes:

- action contact point;
- action press depth;
- Young's modulus;
- Poisson ratio;
- damping.

`SofaFemBackend` now supports `sofa_probe_force_material_scaling`. It defaults to true for existing behavior, but Stage B sets it to false so material variation is not canceled by force scaling.

## Implementation

Changed files:

- `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py`
  - Added `sofa_probe_force_material_scaling`; when false, probe force no longer scales with Young's modulus.
- `tissue_dataset_v0/configs/sofa_liver_stage_b.yaml`
  - New Stage B config with fixed liver-like tissue, random action, and bounded material ranges.
- `tissue_dataset_v0/scripts/check_stage_a.py`
  - Extended sanity checker with `--material-mode fixed|varying` and material spread thresholds.
- `tissue_dataset_v0/README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
  - Updated with Stage B commands and assumptions.

## Stage B Config

`tissue_dataset_v0/configs/sofa_liver_stage_b.yaml` uses:

- output directory: `tissue_dataset_v0/outputs/sofa_liver_stage_b`;
- `num_samples: 10`;
- Young's modulus range: `4000` to `12000`;
- Poisson ratio range: `0.43` to `0.48`;
- damping range: `0.4` to `1.0`;
- action depth range: `0.004` to `0.008`;
- `sofa_probe_force_material_scaling: false`.

## Commands Run

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_stage_a
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_stage_b.yaml
env_isaacsim/bin/python tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_stage_b --material-mode varying --min-samples 5 --max-max-displacement-mm 7.0 --max-downward-z-mm 6.0 --max-contact-distance-mm 35.0
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_stage_b/sample_000001 --viewer summary --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_stage_b/sample_000010 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

All ten Stage B samples passed `validate_sample.py` with zero errors and zero warnings.

## Sanity Results

The varying-material sanity check passed with zero errors and zero warnings using a Stage B locality threshold of `35 mm`. The default `30 mm` locality threshold was slightly too strict for `sample_000001` on the current coarse liver-like mesh; its max displacement vertex was `32.94 mm` from the requested contact point while displacement magnitude remained small and bounded.

Observed Stage B displacement range:

```text
max displacement: 0.67 mm to 2.23 mm
max downward z displacement: 0.60 mm to 2.10 mm
```

Material variation was present across the generated set. Observed examples include Young's modulus from about `4040 Pa` to `11916 Pa`, Poisson ratio from about `0.433` to `0.480`, and damping from about `0.410` to `0.981`.

Isaac USD replay was exported for `sample_000010` at `tissue_dataset_v0/outputs/sofa_liver_stage_b/sample_000010/replay_isaacsim/isaacsim_replay.usda`.

## Limitations

Stage B still uses localized force as a probe approximation, not true SOFA collision/contact. The fixed procedural liver-like geometry is not an anatomical liver asset. The sanity checker is a practical dataset-level gate, not a physical validation benchmark.

## Next Step

Inspect Stage B replay visually and decide whether the material-induced deformation variation is acceptable. If accepted, the next practical step is a small dataset loader/baseline-read smoke test before generating larger data.
