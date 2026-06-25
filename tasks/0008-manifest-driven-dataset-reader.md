# Task: Manifest-Driven Dataset Reader

## Goal

Add a model-agnostic loader that can read generated `sample_*` directories before the final model architecture is designed. The loader must be extensible for future geometry changes and optional artifact additions/removals.

## Design

The reader is manifest-driven. It reads `sample_manifest.json` and loads artifacts declared as `present`, rather than assuming a hard-coded fixed field list. Artifacts are exposed by name in `SampleRecord.artifacts`, with convenience accessors for arrays and metadata.

This is intentionally not yet a PyTorch Dataset. It does not define batching, normalization, train/val splits, or model-specific input tensors. Those should be added after choosing a baseline/NJF model family.

## Implementation

Changed files:

- `tissue_dataset_v0/src/tissue_dataset_v0/dataset/__init__.py`
  - Exports `SampleRecord` and `TissueSampleDataset`.
- `tissue_dataset_v0/src/tissue_dataset_v0/dataset/sample_dataset.py`
  - Adds manifest-driven `TissueSampleDataset`.
  - Supports loading all present artifacts or a selected subset via `artifact_names`.
  - Supports `require_artifacts` for experiment-specific required fields.
  - Reports array shapes, dtypes, loaded artifacts, material keys, and fixed-shape status through `summary()`.
- `tissue_dataset_v0/scripts/read_dataset_smoke.py`
  - Adds CLI smoke test for full or selected artifact loading.
- `tissue_dataset_v0/README.md`, `docs/DATASET_SCHEMA.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
  - Document reader behavior and boundaries.

## Commands Run

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_stage_a
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_stage_b
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_stage_b --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_stage_b --artifact vertices_0 --artifact action --artifact material --artifact meta --require vertices_0 --require action --require material --require meta
```

## Results

Stage A read smoke passed for 5 samples. Stage B read smoke passed for 10 samples. Full-read mode loaded `vertices_0`, `vertices_1`, `displacement`, `faces`, `action`, `contact_point`, `material`, and `meta`. Selected-artifact mode loaded only `vertices_0`, `action`, `material`, and `meta` and passed after checking only explicitly required artifacts.

For Stage B, current fixed-shape summary reports:

```text
vertices_0: [252, 3], fixed=True
vertices_1: [252, 3], fixed=True
displacement: [252, 3], fixed=True
faces: [180, 4], fixed=True
action: [6], fixed=True
contact_point: [3], fixed=True
```

## Limitations

The reader supports extensible artifact loading, but it does not solve batching for variable topology. If Stage C introduces variable vertex/face counts, model-specific collate logic will be required. Image loading is supported through Pillow but has not been exercised because current SOFA samples do not include RGB/depth artifacts.

## Next Step

Use this reader as the stable input boundary for either a tiny baseline-read notebook/script or Stage C planning. For Stage C, keep topology fixed at first if direct batching is desired.
