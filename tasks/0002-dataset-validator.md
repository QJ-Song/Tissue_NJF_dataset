# Task: Pluggable Dataset Validator

## Background

The project can generate toy tissue samples and replay logged states, but it needs an automatic validation layer before scaling to more materials, actions, objects, or simulator backends. Without validation, repeated generation or schema drift can silently create bad samples that later break replay or training.

## Goal

Implement a pluggable validator that checks current `sample_*` outputs while remaining extensible for future parameter additions, optional fields, Isaac Sim/SOFA migration, and simulator-specific checks.

## Scope

Implement:
- `tissue_dataset_v0.validation` package.
- Rule/plugin abstraction for validation checks.
- Default validator profile for current sample/log layout.
- CLI entry `scripts/validate_sample.py`.
- Text and JSON output.
- Extra rule loading through `--rule module:ClassName`.
- Documentation updates.

Do not implement:
- Isaac Sim simulation backend.
- SOFA simulation backend.
- Training dataset loader.
- Destructive cleanup of existing generated outputs.

## Relevant context

Read first:
- AGENTS.md
- docs/CONTEXT.md
- docs/ARCHITECTURE.md
- docs/DATASET_SCHEMA.md

Likely to modify:
- `tissue_dataset_v0/src/tissue_dataset_v0/validation/`
- `tissue_dataset_v0/scripts/validate_sample.py`
- `docs/DATASET_SCHEMA.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `tissue_dataset_v0/README.md`

## Requirements

- Validator must not depend on Isaac Sim.
- Validator must not hard-code all future fields; it should use manifest/log declarations where possible.
- Missing required artifacts must fail.
- Manifest shape/dtype mismatches must fail.
- Timeline duplicate or non-increasing steps must fail.
- Frame references in timeline must resolve to existing files.
- External simulator-specific rules must be loadable without changing the CLI.

## Acceptance criteria

- A fresh generated sample validates successfully.
- A sample missing a manifest-declared artifact fails with a clear error.
- A sample with duplicate timeline steps fails with a clear error.
- JSON output is available for automation.
- Documentation explains validator usage and extension points.

## Test command

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/validator_smoke/sample_990001
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/validator_smoke/sample_990001 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py /tmp/tissue_validator_bad_sample
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001
```

## Progress

* [x] Plan reviewed
* [x] Implementation done
* [x] Test passed
* [x] Documentation updated
* [x] Notes updated

## Notes

The validator caught an existing issue in `tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001`: repeated generation appended duplicate timeline rows. This is useful as a negative case and also indicates a future task should prevent silent overwrite/append during generation.

A fresh sample at `tissue_dataset_v0/outputs/validator_smoke/sample_990001` validated successfully. A temporary bad sample at `/tmp/tissue_validator_bad_sample` failed because `action.npy` was removed while still declared present in the manifest.
