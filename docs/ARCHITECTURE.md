# Architecture

## Current Observed Structure

The repository root is an Isaac Sim workspace. The main reusable code lives in `tissue_dataset_v0/`.

Current module layout:

```text
tissue_dataset_v0/
├── configs/                         # YAML experiment configs
├── scripts/                         # generation and replay CLI entry points
└── src/tissue_dataset_v0/
    ├── backend/                     # backend protocols
    ├── backends/                    # backend implementations: toy_press and minimal sofa_fem
    ├── config/                      # defaults and YAML loader
    ├── sampling/                    # material/action/scene samplers
    ├── replay/                      # replay core and Isaac Sim USD export viewer
    ├── trajectory/                  # episode trajectory reader and summary writer
    ├── validation/                  # pluggable dataset validator rules and profiles
    ├── logger.py                    # simulation-time logging
    ├── pipeline.py                  # backend + logger + writer orchestration
    ├── schema.py                    # dataclasses for requests/results/config
    └── writer.py                    # sample artifact writing
```

Compatibility wrapper modules such as `toy_backend.py`, `backend.py`, `config.py`, `replay.py`, and `isaacsim_replay.py` may still exist. Prefer the package directories for new code.

## Target System Architecture

### Near-Term Simulator Strategy

For the next implementation stage, SOFA should be treated as the preferred physics backend for deformable tissue. Isaac Sim should remain isolated as an offline replay/export and rendering backend until the SOFA-generated physical trajectories are reliable.

The intended separation is:

```text
SOFABackend
  owns FEM scene setup, probe motion, physics stepping, and physical state extraction

DirectorySimulationLogger
  owns simulation-time logging of vertices, tool pose, contact data, material, and timing

Replay/IsaacSimReplayViewer
  owns offline USD replay and later RGB/depth/segmentation rendering from saved states
```

Avoid putting Isaac Sim imports or rendering code inside the SOFA backend. A future hybrid backend may be considered only after the SOFA backend can generate validated samples through the existing pipeline.

### Simulation Module

Responsible for:

- Isaac Sim scene loading;
- tissue object setup;
- tool/probe setup;
- camera setup;
- physics stepping;
- action execution;
- physical state extraction.

Current status: represented by the `SimulationBackend` protocol, `ToyPressBackend`, and a minimal `SofaFemBackend`. A real Isaac Sim backend should be added as a new backend implementation, not mixed into replay or writer code.

`SofaFemBackend` currently emits the same core artifacts as `ToyPressBackend` and records SOFA vertex states during simulation. It applies a localized probe-like force to a top-surface ROI around `ActionSpec.contact_point`, scaled by press depth and optionally by material stiffness. The localized force now follows normalized `ActionSpec.vector[2:5]`; existing Stage A/B/C configs keep the backward-compatible vertical direction, while `sofa_liver_stage_a_directional.yaml` enables a bounded upper-hemisphere cone. This is still a force approximation, not rigid probe contact. `sofa_probe_force_material_scaling` defaults to true for backward compatibility, but Stage B sets it to false so material randomization changes the deformation response. The backend supports fixed procedural tissue shapes through `SampleConfig.extra`, currently `slab` and `liver_like`; `liver_like` warps the regular grid into an asymmetric rounded organ-like volume while preserving fixed topology and vertex count. `SofaFemBackend` now also supports `sofa_interaction_model: probe_contact`, which uses a kinematic sphere collision model and SOFA contact pipeline. Contact samples can now emit optional `tool_pose_0`, `tool_pose_1`, and `tool_geometry` artifacts, plus per-frame `tool_position`/`tool_radius` scalars, when `sofa_record_tool_motion: true`. `localized_probe_force` remains available for Stage A/B/C regression and omits these optional fields. Stage D0 remains available as `scripts/prototype_sofa_probe_contact.py` for isolated contact testing. Field expansion should continue with contact summary/logs next, then sequence-level contact artifacts if stable. See `tasks/0010-sofa-stage-d-probe-contact-plan.md`. The offline replay tool sphere now uses saved tool poses when present and falls back to action/contact-derived visualization otherwise.

### Logging Module

Responsible for:

- synchronized data collection;
- episode directory creation;
- metadata saving;
- array/image writing;
- frame count consistency.

Current status: `DirectorySimulationLogger` writes request snapshots, summaries, timeline JSONL, events JSONL, and per-frame arrays/metadata.

### Dataset Module

Responsible for:

- loading saved episodes;
- validating schema;
- providing model/replay-friendly data access.

Current status: final sample artifacts are written by `FileSystemSampleWriter`; replay reads logged frames through `ReplayReader`; `validation/` provides a pluggable sample validator; `dataset/` provides a manifest-driven, model-agnostic `TissueSampleDataset` reader for `sample_*` artifacts. Optional future material-field artifacts for Stage B2/B3 should be manifest-declared and remain compatible with this reader. A model-specific PyTorch Dataset, collate function, normalization layer, and train/val split are still needed after the model family is chosen.

### Trajectory Module

Responsible for:

- exposing a stable `EpisodeTrajectoryReader` over saved logs;
- yielding frame-level records with `frame_id`, `step_index`, `time_code`, arrays, scalars, and source paths;
- yielding transition pairs for future training loaders;
- writing `logs/trajectory_summary.json`;
- allowing future simulator-specific readers through `module:ClassName` loading.

Current status: `trajectory/` reads the existing `logs/timeline.jsonl` and `logs/frames/*` layout. `DatasetPipeline.generate()` writes `trajectory_summary.json` for new samples. Replay now uses `ReplayReader` as a compatibility wrapper over `EpisodeTrajectoryReader`.

### Validation Module

Responsible for:

- checking sample directory structure;
- checking manifest-to-file consistency;
- validating core array shapes, dtypes, and displacement consistency;
- validating metadata/request/material consistency;
- validating timeline and frame references;
- allowing simulator-specific validation through extra rule plugins.

Current status: `validate_sample.py` uses the default validator profile and supports additional rules via `--rule module:ClassName`. The default profile also checks `trajectory_summary.json` when present and warns for older samples where it has not yet been written.

### Replay/Visualization Module

Responsible for:

- loading saved states;
- reconstructing tissue mesh states from saved vertex positions;
- visualizing tool pose, contact point, force/action vector, and deformation;
- generating debug videos or figures.

Important rule: replay should use saved states directly. It should not rerun physics unless the explicit purpose is reproducibility testing.

Current status: `ReplayReader`, `ReplayRunner`, a summary viewer, and an Isaac Sim USD export viewer are available. `ReplayReader` is now a compatibility wrapper around `EpisodeTrajectoryReader`, so replay depends on the trajectory interface rather than directly owning log parsing.

### Model Module

Responsible for:

- baseline deformation prediction;
- future NJF model;
- dataset loaders;
- metrics;
- evaluation scripts.

Current status: no model/training module is present yet. A model-agnostic artifact reader exists, but model-specific tensors, batching, normalization, and train/val splits are not defined. Do not let future model code import Isaac Sim APIs directly; models should consume dataset readers/loaders.

### Configuration Module

Responsible for:

- material parameters;
- camera parameters;
- action sampling;
- seeds;
- dataset output paths;
- scene paths.

Current status: `tissue_dataset_v0/configs/slab_v0.yaml` is the default toy backend config, `tissue_dataset_v0/configs/sofa_slab_v0.yaml` is the first SOFA FEM slab smoke config, `tissue_dataset_v0/configs/sofa_liver_stage_a.yaml` is the fixed liver-like tissue / randomized-action Stage A config, `tissue_dataset_v0/configs/sofa_liver_stage_b.yaml` is the fixed liver-like tissue / randomized-action-plus-material Stage B config, and `tissue_dataset_v0/configs/sofa_liver_stage_c.yaml` combines randomized geometry, material, and action while keeping topology fixed. These are loaded through `config/yaml_loader.py`, which forwards `backend.extra` into `SampleConfig.extra` and now supports fixed or `[min, max]` geometry values through the geometry sampler. Randomization axes are intentionally independent so later configs can combine action, material, and geometry in different ways.

## Dependency Direction

Preferred dependency flow:

```text
configs → sampling → backend protocol → backend implementation → logger/writer → replay/dataset/model consumers
```

Replay and model code should depend on saved data formats, not on live simulator objects.

### Generation Safety

`DatasetPipeline.generate()` rejects existing non-empty `sample_xxxxxx/` directories by default. Callers must pass `existing_policy="overwrite"`, exposed as `--overwrite` in generation scripts, to delete and regenerate a sample. This prevents timeline logs from being silently appended and prevents final artifacts from being mixed with stale logs.
