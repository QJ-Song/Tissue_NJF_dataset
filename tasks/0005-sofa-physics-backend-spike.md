# Task: SOFA Physics Backend Spike

## Background

The project currently has a stable dataset/logging/replay skeleton with `ToyPressBackend`. Isaac Sim is useful for USD replay/export, camera rendering, robot assets, and healthcare scenes, but the immediate research bottleneck is reliable deformable tissue physics for action-conditioned trajectory data. SOFA is the preferred next physics engine to test because it is focused on FEM, biomechanics, contact, and probe-tissue interaction workflows.

The first SOFA step should not attempt real-time SOFA-Isaac Sim coupling. SOFA should generate physical trajectories through the existing backend protocol, and Isaac Sim should remain an offline replay/rendering consumer of saved states.

## Goal

Implement a minimal `SofaFemBackend` spike that generates one tissue pressing sample through the existing `DatasetPipeline`, logger, writer, validator, and replay tools.

## Scope

Implement:
- `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py`.
- YAML registration for `backend.type: sofa_fem`.
- `tissue_dataset_v0/configs/sofa_slab_v0.yaml`.
- A minimal SOFA tissue patch with fixed boundary, one rigid probe, and vertical press action.
- Simulation-time logging of at least `vertices` per logged frame.
- Final artifacts compatible with the current `sample_*` layout: `vertices_0`, `vertices_1`, `displacement`, `faces`, `action`, `contact_point`, `material`, and `meta`.
- Clear handling for missing optional SOFA outputs such as contact force or tool pose.

Do not implement:
- Real-time SOFA-Isaac Sim coupling.
- Isaac Sim live deformable physics.
- RGB/depth/segmentation generation.
- New model training code.
- New storage backend such as HDF5 or Zarr.
- Destructive cleanup of existing outputs.

## Relevant context

Read first:
- `AGENTS.md`
- `docs/CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DATASET_SCHEMA.md`
- `docs/ROADMAP.md`
- `docs/SOFA_SETUP.md`
- `tissue_dataset_v0/README.md`
- `tasks/0004-episode-trajectory-schema.md`

Likely to modify:
- `scripts/prototype_sofa_slab.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/backends/__init__.py`
- `tissue_dataset_v0/src/tissue_dataset_v0/config/yaml_loader.py`
- `tissue_dataset_v0/configs/sofa_slab_v0.yaml`
- `docs/ISAAC_SIM_SETUP.md` only if run commands change
- `docs/DATASET_SCHEMA.md` only if new logged fields become required
- this task file

## Requirements

- Keep SOFA imports isolated inside the SOFA backend or small SOFA-specific helper modules.
- Preserve the `SimulationBackend.simulate(request, logger)` interface.
- Log states during simulation with `logger.record_frame()`, not by reconstructing trajectory after the run.
- Keep replay offline: replay must read saved states and must not rerun SOFA.
- Use config values for geometry, material, action, logging interval, and output paths.
- If SOFA is unavailable in the local environment, fail with a clear dependency message and keep non-SOFA tests runnable.
- Avoid hard-coded absolute paths and do not delete generated outputs without explicit user confirmation.

## Acceptance criteria

- `backend.type: sofa_fem` builds a backend from YAML.
- One SOFA-generated sample is written under a configured output directory.
- The generated sample has the current core artifacts and `logs/trajectory_summary.json`.
- `validate_sample.py` passes for the generated sample, or any warnings are documented and non-fatal.
- `replay_sample.py --viewer summary` can replay the SOFA-generated sample.
- Isaac Sim USD replay export can consume the saved SOFA vertex trajectory without rerunning SOFA physics.
- Documentation and this task file are updated with actual setup notes and test results.

## Suggested first implementation plan

1. Inspect the local Python environment for SOFA/SofaPython3 availability.
2. Prototype a tiny standalone SOFA scene outside the dataset pipeline only if needed to learn the API.
3. Move the working scene into `SofaFemBackend`.
4. Emit the same artifact names as `ToyPressBackend` before adding optional fields.
5. Register `sofa_fem` in the YAML loader and create `sofa_slab_v0.yaml`.
6. Generate one sample, validate it, and replay it with the summary viewer.
7. Export the saved trajectory through the existing Isaac Sim USD replay viewer.

## Prompt for the next Codex session

```text
Use the project-context-maintainer skill. Read AGENTS.md, docs/CONTEXT.md, docs/ARCHITECTURE.md, docs/DATASET_SCHEMA.md, docs/ROADMAP.md, docs/SOFA_SETUP.md, tissue_dataset_v0/README.md, and tasks/0005-sofa-physics-backend-spike.md.

Continue from the implemented minimal SofaFemBackend. Do not rebuild the environment, do not delete existing outputs, and do not attempt real-time SOFA-Isaac coupling. The current backend can generate and validate one SOFA slab sample, but it uses a simplified downward ConstantForceField rather than localized probe/contact physics.

The next task is to move beyond the current localized probe-force approximation: add real SOFA probe/collision/contact driven by the existing ActionSpec contact_point and depth, preserve SimulationBackend.simulate(request, logger), keep logger.record_frame() inside SOFA stepping, and only add tool_pose/contact_force/contact_normal fields when they are reliable.

After changes, run SOFA and Isaac compile checks, generate a new non-overwriting smoke sample or use an explicitly approved output path, validate it, summary-replay it, and export Isaac Sim USD replay. Update docs and this task note with actual commands, results, and limitations.
```

## Test command

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts
scripts/run_sofa_python.sh -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_slab_v0.yaml
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer summary --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

If SOFA is not installed, record the dependency failure in the progress notes instead of forcing installation.

## Progress

* [x] Plan reviewed
* [x] SOFA environment prepared
* [x] Standalone SOFA slab smoke test passed
* [x] Implementation done
* [x] Test passed
* [x] Documentation updated
* [x] Notes updated

## Notes

Decision recorded: use SOFA for the next real deformable tissue physics spike; keep Isaac Sim as offline replay/export and later RGB/depth/segmentation rendering. Do not attempt real-time SOFA-Isaac coupling until validated SOFA samples exist.

Environment setup completed with Miniforge/Conda under `$HOME/conda`. The `sofa` environment includes `python=3.12`, `sofa-app`, `sofa-python3`, `pillow`, `pyyaml`, and an editable install of `tissue_dataset_v0`. Smoke checks passed for `import SofaRuntime`, `import Sofa`, `runSofa --help`, and importing `tissue_dataset_v0` from the `sofa` environment. See `docs/SOFA_SETUP.md`.

Standalone smoke test added at `scripts/prototype_sofa_slab.py`. It creates a small SOFA FEM slab from `RegularGridTopology`, fixes the bottom surface, applies a simple downward `ConstantForceField`, steps the simulation headlessly, and reads vertex positions back into NumPy. Command run:

```bash
scripts/run_sofa_python.sh -m py_compile scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh scripts/prototype_sofa_slab.py --steps 30
```

Observed result: 75 vertices, nonzero deformation, `max_displacement` about `6.26e-05`, `min_z_displacement` about `-3.51e-05`. This validates SOFA scene creation, FEM stepping, constraints, load application, and vertex extraction. It is not yet the final backend and does not yet model a probe/contact action or write dataset logs.

Minimal backend implementation completed in `tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py` and registered as `backend.type: sofa_fem`. The first backend version creates a SOFA FEM slab from `RegularGridTopology`, fixes the bottom surface, applies a request-driven downward `ConstantForceField`, records `vertices` during SOFA stepping through `DirectorySimulationLogger`, and writes the same core artifacts as `ToyPressBackend`: `vertices_0`, `vertices_1`, `displacement`, `faces`, `action`, `contact_point`, `material`, and `meta`.

The first config is `tissue_dataset_v0/configs/sofa_slab_v0.yaml`. It writes one sample to `tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001` when run through the SOFA environment:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_slab_v0.yaml
```

Smoke checks completed:

```bash
scripts/run_sofa_python.sh -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts scripts/prototype_sofa_slab.py
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_slab_v0.yaml
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer summary --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

Observed backend sample result: validator passed with zero errors and zero warnings; trajectory frame count is 19 with steps `0` through `180`; summary replay reports backend and simulator as `sofa_fem`; displacement shape is `(108, 3)`, max displacement is about `2.43e-05`, and minimum z displacement is about `-7.61e-06`. Isaac Sim replay exported `sample_000001/replay_isaacsim/isaacsim_replay.usda` with 19 frames.

Limitation: this is a minimum viable SOFA physics backend, not a real probe-contact model. The original smoke sample used a simplified global downward force derived from press depth and material stiffness. The backend was then changed to a localized top-surface probe force around `ActionSpec.contact_point`, while the Isaac replay tool sphere remains a visual marker and intentionally does not need to touch the tissue surface. The next physics task should replace the simplified local `ConstantForceField` approximation with real SOFA probe/collision/contact behavior and log reliable tool pose/contact force/contact normal fields.

Localized probe-force update: `SofaFemBackend` now creates a `probe_roi` BoxROI around the action contact point on the slab top surface and applies `ConstantForceField` only to those ROI indices. Defaults recorded in `meta.extra` are `sofa_load_model=localized_probe_force`, `sofa_probe_radius=0.024`, `sofa_probe_force_scale=4.0`, and `sofa_probe_max_force=6.0`. This keeps the replay sphere as a non-contact visual cue while making the tissue deformation depend on the sampled contact point and press depth.

Non-overwriting smoke sample generated at `tissue_dataset_v0/outputs/sofa_probe_smoke/sample_990021`. Validation passed with zero errors and zero warnings; summary replay reported 19 frames from step `0` to `180`; Isaac USD replay export wrote `sample_990021/replay_isaacsim/isaacsim_replay.usda`. Observed displacement for a `10 mm` thick slab: max displacement about `1.47 mm`, max downward z displacement about `1.17 mm`. This is intentionally visible but bounded, and much larger than the original global-force smoke sample's sub-0.1 mm deformation.

