# Task: Prevent Silent Sample Overwrite or Log Append

## Background

The validator exposed an existing bad sample where repeated generation of the same `sample_000001/` appended duplicate `timeline.jsonl` rows. This can make replay and training unreliable because final artifacts may be newly written while logs still contain old frames.

## Goal

Make sample generation fail by default when the target `sample_xxxxxx/` directory already exists and is non-empty. Allow regeneration only through an explicit overwrite option.

## Scope

Implement:
- Add an existing-sample policy to `DatasetPipeline.generate()`.
- Default policy: `error`.
- Explicit policy: `overwrite`, which deletes the existing sample directory and regenerates it.
- Add `--overwrite` to `generate_sample_v0.py`.
- Add `--overwrite` to `generate_from_yaml.py`.
- Return a clear CLI error instead of a traceback when a sample already exists.
- Update documentation.

Do not implement:
- Resume/append mode.
- Partial episode recovery.
- Dataset garbage collection.
- Automatic deletion of old outputs without explicit overwrite.

## Relevant context

Read first:
- AGENTS.md
- docs/CONTEXT.md
- docs/ARCHITECTURE.md
- docs/DATASET_SCHEMA.md
- tasks/0002-dataset-validator.md

Likely to modify:
- `tissue_dataset_v0/src/tissue_dataset_v0/pipeline.py`
- `tissue_dataset_v0/scripts/generate_sample_v0.py`
- `tissue_dataset_v0/scripts/generate_from_yaml.py`
- `tissue_dataset_v0/README.md`
- `docs/ARCHITECTURE.md`
- `docs/DATASET_SCHEMA.md`
- `docs/ROADMAP.md`

## Requirements

- Existing non-empty sample directories must fail by default.
- Failure message must tell the user to use `--overwrite` for explicit regeneration.
- `--overwrite` must delete and regenerate only the target sample directory.
- Generated samples after overwrite must pass validator.
- YAML generation must use the same default safety behavior.

## Acceptance criteria

- First generation of a new sample succeeds.
- Repeating the same generation without `--overwrite` exits non-zero with a clear error.
- Repeating with `--overwrite` succeeds.
- The regenerated sample validates successfully.
- Existing YAML output rejects duplicate generation without `--overwrite`.

## Test command

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts tissue_dataset_v0/__init__.py
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_sample_v0.py --output-dir tissue_dataset_v0/outputs/overwrite_guard --sample-id 990003 --overwrite
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_sample_v0.py --output-dir tissue_dataset_v0/outputs/overwrite_guard --sample-id 990003
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_sample_v0.py --output-dir tissue_dataset_v0/outputs/overwrite_guard --sample-id 990003 --overwrite
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/overwrite_guard/sample_990003 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/slab_v0.yaml
```

## Progress

* [x] Plan reviewed
* [x] Implementation done
* [x] Test passed
* [x] Documentation updated
* [x] Notes updated

## Notes

The default duplicate-generation test intentionally exits with code 2. That is the expected safe behavior.

The regenerated sample `tissue_dataset_v0/outputs/overwrite_guard/sample_990003` validated successfully with 181 timeline frames and no validation errors.
