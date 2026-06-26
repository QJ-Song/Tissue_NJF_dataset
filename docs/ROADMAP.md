# Roadmap

## Stage 0: Context System and Repository Organization

Deliverables:

- `AGENTS.md`.
- `docs/`.
- `tasks/`.
- context maintenance skill.

Acceptance criteria:

- Future Codex sessions can understand the project from repository files.

Status: in progress through `tasks/0001-minimal-context-system.md`.

## Stage 1: Minimal Isaac Sim Visual Scene / USD Smoke Test

Deliverables:

- one visual tissue patch;
- one visual probe;
- one fixed camera;
- a generated USD/USDA scene for Isaac Sim inspection and replay/export reference.

Acceptance criteria:

- A short visual/kinematic scene can be generated and opened in Isaac Sim or inspected as USD.
- The scene is treated as an environment/rendering smoke test, not as the current live soft-tissue physics milestone.

Current note: `scripts/create_tissue_poke_scene.py` and `scenes/tissue_poke_demo.usda` exist. This stage is historical/contextual and should be preserved as an Isaac Sim/USD smoke test. Dataset generation currently uses `ToyPressBackend`, and the next real physics milestone is the SOFA backend spike.

Route update: do not make live Isaac Sim deformable simulation the next milestone. Keep Isaac Sim for offline USD replay/export and later camera rendering while the real soft-tissue physics path is proven through a SOFA backend.

## Stage 1.5: Minimal SOFA Physics Backend

Deliverables:

- one SOFA FEM tissue patch;
- one rigid probing tool;
- fixed border or bottom constraint;
- vertical press action from existing action config;
- simulation-time logging through `DirectorySimulationLogger`;
- final artifacts compatible with current `sample_*` layout;
- replay through existing summary and Isaac Sim USD export viewers.

Acceptance criteria:

- A YAML config with `backend.type: sofa_fem` can generate one sample.
- The sample includes `vertices_0`, `vertices_1`, `displacement`, `faces`, `action`, `contact_point`, `material`, `meta`, and `logs/trajectory_summary.json`.
- The existing validator passes or reports only documented SOFA-specific warnings.
- Replay uses saved states and does not rerun SOFA physics.

Current note: the minimum viable `SofaFemBackend` is implemented and can generate, validate, summary-replay, and Isaac-USD-export SOFA samples. It supports both slab and fixed procedural liver-like tissue shapes, uses a localized probe-like top-surface force around `contact_point`, has Stage A/B/C configs for action-only, action-plus-material, and action-plus-material-plus-geometry randomization, and keeps Stage C topology fixed for direct batching. The sanity-check CLI now supports fixed/varying material, geometry, and action-direction modes. Stage A directional action is implemented in `tissue_dataset_v0/configs/sofa_liver_stage_a_directional.yaml`; the stable first config uses a 30 degree upper-hemisphere cone because a 45 degree smoke run produced excessive displacement. Stage B material extensions should be staged according to `tasks/0012-sofa-stage-b-material-extensions.md`: first spatially varying isotropic material, later anisotropy. Stage D0 standalone contact prototype is implemented in `scripts/prototype_sofa_probe_contact.py`; Stage D1 has ported contact into `SofaFemBackend` behind `sofa_interaction_model: probe_contact`; Stage D2 now records optional `tool_pose_0`, `tool_pose_1`, `tool_geometry`, and per-frame `tool_position` for contact samples when `sofa_record_tool_motion: true`. `tissue_dataset_v0/configs/sofa_liver_contact_d2.yaml` generated and validated one bounded contact sample, and Isaac replay now uses saved tool poses when present. Stage D should continue according to `tasks/0010-sofa-stage-d-probe-contact-plan.md`: D3 contact summary/log fields, D5 boundary/solver metadata, and D4 directional small-step probe motion are implemented and validated. The lightweight NJF orchestration layer, Mode A local perturbation path, smoke-sized Mode B response basis groups, and smoke-sized Mode C rollout trajectories are now implemented and smoke-validated; next add larger non-smoke demo generation and analysis scripts.

## Stage 2: Synchronized Data Logging

Deliverables:

- episode logger;
- metadata writer;
- action/tool/tissue/camera data saving.

Acceptance criteria:

- One episode can be saved with consistent frame counts.

Current note: `DirectorySimulationLogger` writes request, summary, timeline, events, and frame arrays for the toy backend. Generation now rejects existing non-empty sample directories by default and requires explicit `--overwrite` to regenerate.

## Stage 3: Offline State Replay

Deliverables:

- replay loader;
- mesh state visualization;
- optional video export.

Acceptance criteria:

- Saved vertex states can be replayed without rerunning physics.

Current note: summary replay and Isaac Sim USD export viewer exist. Replay now uses the trajectory reader compatibility layer, and new samples write `logs/trajectory_summary.json`.

## Stage 4: Dataset Validation

Deliverables:

- schema validator;
- frame consistency check;
- metadata check.

Acceptance criteria:

- Invalid episodes are detected automatically.

Current note: a pluggable sample validator now exists under `validation/`, with CLI entry `scripts/validate_sample.py`. It validates current `sample_*` outputs, checks trajectory summaries when present, and can accept extra simulator-specific rules.

## Stage 5: Label Generation

Deliverables:

- displacement labels;
- action-field labels;
- contact-conditioned labels.

Acceptance criteria:

- Labels can be generated from saved episodes.

## Stage 6: Baseline Model

Deliverables:

- model-agnostic dataset reader;
- simple deformation prediction baseline;
- model-specific batching/collate function;
- training script.

Acceptance criteria:

- Dataset reader can smoke-read Stage A/B samples from manifests.
- Baseline can overfit a small debug dataset.

Current note: `TissueSampleDataset` and `read_dataset_smoke.py` now provide a manifest-driven reader that is intentionally independent of model architecture. Model-specific PyTorch integration is still pending.

## Stage 7: NJF Model

Deliverables:

- first NJF implementation;
- local action-to-motion prediction;
- evaluation against baseline.

Acceptance criteria:

- NJF can be trained and compared with deformation prediction baseline.

Current planning update: before model work, finish SOFA NJF dataset v1. The lightweight NJF orchestration layer, Mode A local perturbation generation, smoke-sized Mode B response basis groups, smoke-sized Mode C rollout trajectories, and Mode A/B/C dataset validator are implemented. Remaining major work is running/validating the larger K/T demo, split policy refinement, rollout evaluation scripts, and eventual training loaders. A non-smoke demo config and response-basis analysis script now exist. See `tasks/0013-controlled-sofa-contact-dataset-v1.md` and `docs/sofa_njf_dataset_design.md`.

## Stage 8: Evaluation and Paper Figures

Deliverables:

- quantitative metrics;
- visualization scripts;
- predicted vs ground-truth figures.

Acceptance criteria:

- Results are suitable for internal report or first conference paper draft.
