# Isaac Sim Setup

## Detected Environment

Observed from repository files:

- Isaac Sim installation method: Python/pip workflow inside the workspace-local `env_isaacsim/` environment.
- Target Isaac Sim version documented by the root README: `6.0.0.1`.
- Python version documented by the root README and environment: Python 3.12.
- Startup helper: `scripts/runisaacsim.sh`.
- Compatibility/helper scripts: `scripts/check_host.sh`, `scripts/checkcompat.sh`, `scripts/fixfuse.sh`, `scripts/install_isaacsim.sh`, `scripts/install_extscache.sh`.

Do not copy private host names, user-specific absolute paths, or machine-specific credentials into context docs. Keep setup commands relative to the repository root.

## Expected Startup Commands

From the repository root:

```bash
source env_isaacsim/bin/activate
export OMNI_KIT_ACCEPT_EULA=YES
isaacsim isaacsim.exp.compatibility_check
bash scripts/runisaacsim.sh
```

Set `OMNI_KIT_ACCEPT_EULA=YES` only after reviewing and accepting NVIDIA Omniverse license terms.

## Minimal Scene Generation

The original scene-generation script is:

```bash
env_isaacsim/bin/python scripts/create_tissue_poke_scene.py
```

It generates a USDA scene under `scenes/`. This script is useful for scene/export debugging, but it is separate from the `tissue_dataset_v0` dataset pipeline.

## Dataset Generation Command

The current recommended data-generation path is YAML-driven:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/slab_v0.yaml
```

This currently uses `ToyPressBackend`, not Isaac Sim physics.

## Offline Replay Export Command

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py   tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001   --viewer tissue_dataset_v0.replay.isaacsim:IsaacSimReplayViewer   --stride 10
```

This exports a USD/USDA replay file from saved logged states without rerunning physics.

## Headless Simulation

Headless simulation support should be added through a future Isaac Sim backend. The current docs and scripts indicate GUI startup support and compatibility checks, but no dedicated headless dataset-generation command has been verified yet.

## USD/USDA Assets

Current generated scene assets are under `scenes/`, including `tissue_poke_demo.usda`. Replay exports are written under each generated sample directory, for example:

```text
tissue_dataset_v0/outputs/.../sample_000001/replay_isaacsim/isaacsim_replay.usda
```

Generated data should stay under `tissue_dataset_v0/outputs/` or another configured output directory, not under source code directories.

## USD File Formats

`.usda` is a human-readable OpenUSD ASCII scene file. It can describe scene hierarchy, geometry references, materials, cameras, lights, physics properties, and simulation assets. It is useful for inspecting and editing scene structure.

- `.usda` is text-based and human-readable.
- `.usdc` is binary and more efficient.
- `.usd` may refer to either general USD format.

## Common Pitfalls

- Interactive Isaac Sim may require a real desktop session or supported remote visualization method.
- Isaac Sim imports should stay isolated from general dataset/model code.
- Do not hard-code local absolute paths to Isaac Sim assets or output directories.
- Avoid mixing live visualization into simulation-time data logging; it can slow collection and couple unrelated code.
- Treat generated logs, datasets, USD exports, videos, and checkpoints as artifacts, not source.
