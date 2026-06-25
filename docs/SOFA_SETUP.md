# SOFA Setup

## Purpose

SOFA is used as the near-term physics backend for deformable tissue simulation. It should remain isolated from the Isaac Sim Python environment. Isaac Sim stays responsible for offline USD replay/export and later camera rendering.

## Local Environment Layout

The recommended local layout is:

```text
$HOME/conda/
  bin/conda
  envs/
    sofa/
    train/
    eval/
```

The current SOFA environment is:

```text
$HOME/conda/envs/sofa
```

Do not install SOFA into `env_isaacsim`.

## Installed Packages

The SOFA environment was created with Miniforge/Conda and includes:

- `python=3.12`
- `sofa-app`
- `sofa-python3`
- `numpy`
- `pillow`
- `pyyaml`
- editable install of `tissue_dataset_v0`

Observed package versions after setup:

```text
python        3.12.13
libsofa       25.06.00
sofa-app      25.06.00
sofa-python3  25.06.00
```

The SOFA packages were installed from:

```text
https://prefix.dev/sofa-framework
conda-forge
```

## Activation

```bash
source $HOME/conda/etc/profile.d/conda.sh
conda activate sofa
```

Or run Python without activating:

```bash
$HOME/conda/bin/conda run -n sofa python -c "import SofaRuntime, Sofa"
```

## Smoke Checks

Verify SofaPython3:

```bash
$HOME/conda/bin/conda run -n sofa python -c "import SofaRuntime, Sofa; print('SOFA OK')"
```

Verify the SOFA application entry point:

```bash
$HOME/conda/bin/conda run -n sofa runSofa --help
```

Verify the project package is visible from the SOFA environment:

```bash
$HOME/conda/bin/conda run -n sofa python -c "import tissue_dataset_v0; print('project OK')"
```

Run the standalone slab smoke test:

```bash
scripts/run_sofa_python.sh scripts/prototype_sofa_slab.py --steps 30
```

Expected behavior: the script prints a JSON summary with nonzero displacement. A successful run observed 75 vertices and `max_displacement` around `6.26e-05` after 30 steps.


## Dataset Backend Smoke Test

Generate one minimal SOFA FEM dataset sample through the normal pipeline:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_slab_v0.yaml
```

Validate and replay the generated sample from the Isaac Sim Python environment, which remains the offline replay/export environment:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --format json
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer summary --stride 1
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_slab_v0/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

Observed result from the first global-force smoke sample: validator passed with zero errors and zero warnings, summary replay reported 19 frames from step `0` to `180`, and Isaac Sim USD replay export wrote `sample_000001/replay_isaacsim/isaacsim_replay.usda`. Use `--stride 1` when exporting the small SOFA smoke sample if all logged frames should appear in the USDA replay. After the backend was changed to localized probe force, a non-overwriting smoke sample at `tissue_dataset_v0/outputs/sofa_probe_smoke/sample_990021` validated and replayed successfully; observed max displacement was about `1.47 mm` and max downward z displacement was about `1.17 mm` for a `10 mm` thick slab.

## Notes

The SOFA environment should be used for future `SofaFemBackend` development and smoke tests. Keep SOFA imports isolated inside SOFA-specific backend code or helper modules.

`scripts/prototype_sofa_slab.py` is a standalone smoke test, not the dataset backend. It applies a simple downward `ConstantForceField` with bottom-surface constraints to verify SOFA FEM stepping and vertex extraction. The minimal `SofaFemBackend` has moved into the dataset pipeline and now uses a localized top-surface probe force around the requested contact point. The next backend version should replace this simplified local load with real SOFA probe/collision/contact behavior.

Stage D0 standalone contact prototype:

```bash
scripts/run_sofa_python.sh scripts/prototype_sofa_probe_contact.py --format json
```

This script runs a simplified FEM slab with a kinematic sphere probe through SOFA's collision/contact pipeline. It writes no dataset files. The default smoke result on 2026-06-24 was valid, with first contact/proximity at step `103`, `58` contact/proximity frames, and max displacement about `4.42 mm`. Use it as the reference before adding `probe_contact` mode to `SofaFemBackend`.

Stage D1 backend contact mode:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d1.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d1/sample_000001
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_contact_d1 --min-samples 1 --min-max-displacement-mm 0.5 --max-max-displacement-mm 5.0 --max-downward-z-mm 5.0 --min-contact-spread-mm 0 --min-depth-spread-mm 0 --max-contact-distance-mm 35.0
```

The D1 config generated `sample_000001` with `sofa_interaction_model: probe_contact`; validation and reader smoke passed, max displacement was about `3.95 mm`, and Isaac USD replay export succeeded. D1 intentionally does not add tool pose or contact summary final artifacts.

Stage D2 tool motion fields:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d2.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_motion.py tissue_dataset_v0/outputs/sofa_liver_contact_d2 --min-samples 1 --min-z-drop-mm 1.0 --max-z-drop-mm 20.0
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py tissue_dataset_v0/outputs/sofa_liver_contact_d2/sample_000001 --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer --stride 1
```

The D2 config uses `sofa_record_tool_motion: true` and generated `sample_000001` with optional `tool_pose_0.npy`, `tool_pose_1.npy`, and `tool_geometry.json` present in the manifest. The tool z drop was `12.5 mm`, logged `tool_position` matched saved poses, and Isaac USD replay now uses saved tool poses for the gray probe when available.

Stage D3 contact summary fields:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d3.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d3 --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_contact.py tissue_dataset_v0/outputs/sofa_liver_contact_d3 --min-samples 1
```

The D3 config uses `sofa_record_contact_summary: true` and generated `sample_000001` with optional `contact_summary.json` present in the manifest. The geometric sphere-to-vertex contact summary detected contact/proximity at step `107`, counted `54` contact/proximity steps, reported min signed gap about `1.924 mm`, and reported no penetration. D3 does not export reliable contact force or contact normal; `contact_summary.json` records `force_available: false`.

Stage D5 boundary and solver metadata:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d5.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/read_dataset_smoke.py tissue_dataset_v0/outputs/sofa_liver_contact_d5 --require tool_pose_0 --require tool_pose_1 --require tool_geometry --require contact_summary --require fixed_node_indices --require free_node_indices --require boundary_mask --require boundary --require solver_summary
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_boundary_solver.py tissue_dataset_v0/outputs/sofa_liver_contact_d5 --min-samples 1
```

The D5 config uses `sofa_record_boundary_solver: true` and generated `sample_000001` with fixed/free node indices, a fixed-node mask, `boundary.json`, and `solver_summary.json` present in the manifest. The sample recorded `63` fixed nodes, `189` free nodes, `0.000000 mm` max fixed-node displacement, `dt=0.005`, `160` total steps, and finite-state solver validity.

Stage D4 directional and small-step probe motion:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d4_directional.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3 --require-nonvertical --min-max-tilt-deg 5.0 --max-angle-error-deg 0.1
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_stage_a.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_directional --min-samples 3 --direction-mode varying --max-tilt-deg 15 --min-direction-spread-deg 2.0 --min-max-displacement-mm 0.5 --max-max-displacement-mm 5.0 --max-downward-z-mm 5.0 --min-contact-spread-mm 1.0 --min-depth-spread-mm 0.0 --max-contact-distance-mm 35.0
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/sofa_liver_contact_d4_small_step.yaml
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/check_tool_direction.py tissue_dataset_v0/outputs/sofa_liver_contact_d4_small_step --min-samples 1 --max-angle-error-deg 0.1 --min-motion-mm 0.05
```

D4 maps saved action direction to actual probe center motion for `probe_contact`. The directional smoke config uses a conservative 15 degree cone near the center region and generated 3 samples with action tilt about `4.9` to `9.4` degrees, direction error below `0.0001` degrees, and bounded max displacement from about `1.06 mm` to `4.10 mm`. The small-step smoke config uses `0.2 mm` depth and zero clearance; the saved tool motion was `0.200 mm` with contact detected from step `0`.

## NJF Mode A Smoke Dataset

The current SOFA NJF smoke path uses the lightweight `tissue_dataset_v0.njf` orchestration layer above the existing single-sample pipeline. It generates Mode A local perturbation samples only; Mode B groups and Mode C trajectories are still planned.

Generate and validate the smoke dataset:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/run_njf_smoke_test.py --overwrite
```

Equivalent separate commands:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/generate_njf_dataset.py --config tissue_dataset_v0/configs/sofa_njf_dataset.yaml --overwrite
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/validate_njf_dataset.py tissue_dataset_v0/outputs/sofa_njf_mode_a_smoke
```

The observed smoke result generated 3 samples with `0.05`, `0.1`, and `0.2` mm probe motions and passed NJF validation, dataset reader smoke, tool-direction check, contact check, and boundary/solver check.

