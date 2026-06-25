# Task: Episode Trajectory Schema

## Background

The project already writes final `sample_*` artifacts and simulation-time logs. Replay and validation previously parsed `logs/timeline.jsonl` and `logs/frames/*` directly. Before adding Isaac Sim or SOFA backends, the project needs a stable trajectory interface so downstream code can read frame sequences without depending on storage details.

## Goal

Implement a pluggable episode/trajectory reader and summary writer without breaking existing `sample_*` outputs. Replay and validator should be able to rely on this trajectory interface.

## Scope

Implement:
- `tissue_dataset_v0.trajectory` package.
- `TrajectoryFrame` with frame id, simulation step, time code, arrays, scalars, and source paths.
- `TrajectoryTransition` for `(frame_t, frame_t_plus_1)` access.
- `EpisodeTrajectoryReader` over current `logs/timeline.jsonl` and `logs/frames/*`.
- `trajectory_summary.json` writer.
- `write_trajectory_summary.py` CLI.
- Pipeline hook to write trajectory summary for new samples.
- Replay compatibility wrapper over the trajectory reader.
- Validator rule for trajectory summary consistency.
- Documentation updates.

Do not implement:
- New storage backend such as HDF5 or Zarr.
- Isaac Sim simulation backend.
- SOFA simulation backend.
- Training model code.
- Breaking changes to existing `sample_*` artifacts.

## Relevant context

Read first:
- AGENTS.md
- docs/CONTEXT.md
- docs/ARCHITECTURE.md
- docs/DATASET_SCHEMA.md
- tasks/0002-dataset-validator.md
- tasks/0003-prevent-silent-overwrite.md

Likely to modify:
- `tissue_dataset_v0/src/tissue_dataset_v0/trajectory/`
- `tissue_dataset_v0/src/tissue_dataset_v0/pipeline.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/replay/core.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/validation/rules.py`
- `tissue_dataset_v0/scripts/write_trajectory_summary.py`
- `docs/ARCHITECTURE.md`
- `docs/DATASET_SCHEMA.md`
- `docs/ROADMAP.md`
- `tissue_dataset_v0/README.md`

## Requirements

- Existing `sample_*` artifacts must remain unchanged.
- New samples should write `logs/trajectory_summary.json`.
- Old samples without trajectory summary should remain readable and should validate with a warning rather than an error.
- Replay should keep its public API but use the trajectory reader underneath.
- The trajectory reader should support future backend migration through `module:ClassName` loading.
- Validator should compare trajectory summary against logs when the summary exists.

## Acceptance criteria

- A new sample includes `logs/trajectory_summary.json`.
- `EpisodeTrajectoryReader.iter_frames()` returns expected frames.
- `EpisodeTrajectoryReader.iter_transitions()` returns frame pairs.
- `write_trajectory_summary.py` can rebuild and print the summary.
- `validate_sample.py` checks trajectory summary and passes for a fresh sample.
- `replay_sample.py --viewer summary` still works.
- Old samples without trajectory summary validate with warning only.

## Test command

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts tissue_dataset_v0/__init__.py
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_sample_v0.py --output-dir tissue_dataset_v0/outputs/trajectory_smoke --sample-id 990004 --overwrite
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/trajectory_smoke/sample_990004 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/trajectory_smoke/sample_990004 --viewer summary --stride 90
env_isaacsim/bin/python tissue_dataset_v0/scripts/write_trajectory_summary.py tissue_dataset_v0/outputs/trajectory_smoke/sample_990004 --print
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/overwrite_guard/sample_990003
```

## Progress

* [x] Plan reviewed
* [x] Implementation done
* [x] Test passed
* [x] Documentation updated
* [x] Notes updated

## Notes

`ReplayReader` remains available for compatibility, but it now subclasses `EpisodeTrajectoryReader`. New code should prefer importing `EpisodeTrajectoryReader` from `tissue_dataset_v0.trajectory`.

The old sample `tissue_dataset_v0/outputs/overwrite_guard/sample_990003` validates with one warning because it lacks `logs/trajectory_summary.json`; this is expected compatibility behavior.
