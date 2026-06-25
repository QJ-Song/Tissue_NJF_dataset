# Project Context

## Research Context

This project aims to build a tool-tissue interaction dataset for future Neural Jacobian Field (NJF) research. The long-term target is an Isaac Sim-based pipeline that can simulate deformable tissue interactions, log synchronized physical states, replay saved episodes offline, and provide training data for action-conditioned deformation models.

The guiding research question is:

```text
Can deformable tissue dynamics be represented as a state-conditioned local action-to-motion Jacobian field, instead of directly predicting deformation or optical/scene flow?
```

## Current Repository Reality

The repository currently contains two related layers:

- An Isaac Sim workspace with setup scripts, environment files, and a generated `scenes/tissue_poke_demo.usda` scene.
- A standalone `tissue_dataset_v0/` module with a pluggable backend interface, a NumPy toy pressing backend, YAML-driven sampling/configuration, simulation-time logging, and offline replay/export tools.

At this stage, Isaac Sim is not yet the default simulation backend for dataset generation. The current backend is `ToyPressBackend`, which exists to stabilize schema, logging, writer, sampler, and replay architecture before replacing or augmenting it with Isaac Sim or SOFA.

## Near-Term Simulator Decision

The next real physics step should prioritize a SOFA backend over a live Isaac Sim physics backend. Isaac Sim remains useful for USD replay/export, camera rendering, synthetic RGB/depth/segmentation, robot assets, and healthcare scene assets, but the immediate research bottleneck is reliable soft-tissue mechanics and synchronized state logging.

The recommended near-term pipeline is:

```text
SOFA FEM tissue simulation
        ->
SimulationBackend protocol
        ->
DirectorySimulationLogger
        ->
saved vertex/tool/contact/material trajectories
        ->
offline replay / Isaac Sim USD export / later RGB rendering
```

Do not build a real-time SOFA-Isaac Sim coupled simulator as the first step. First prove that SOFA can generate a minimal tissue pressing episode that conforms to the existing sample and trajectory schema.

## Current SOFA Environment Status

A Miniforge/Conda installation is available under `$HOME/conda`, with a dedicated `sofa` environment at `$HOME/conda/envs/sofa`. The environment has SOFA 25.06.00 packages (`libsofa`, `sofa-app`, `sofa-python3`) and Python 3.12.13. Smoke checks passed for `import SofaRuntime`, `import Sofa`, `runSofa --help`, importing `tissue_dataset_v0`, and `scripts/run_sofa_python.sh`.

Detailed activation and verification commands live in `docs/SOFA_SETUP.md`. Keep SOFA out of `env_isaacsim`; use the `sofa` environment for future `SofaFemBackend` development.

## First Engineering Goal

The first engineering goal is intentionally simple:

```text
single tissue patch
single probing tool
single fixed camera
synchronized simulation-time logging
offline state replay
minimal dataset schema
```

The first stage should prioritize reliable data generation and replay, not a complete NJF model.

## Intended Pipeline

```text
Isaac Sim scene setup
        ↓
simulation stepping
        ↓
synchronized physical-state logging
        ↓
dataset storage
        ↓
offline label generation
        ↓
offline replay / visualization
        ↓
baseline training
        ↓
future NJF learning
```

## Current Working Pipeline

```text
YAML config
        ↓
SceneSampler / material sampler / action sampler
        ↓
ToyPressBackend simulation
        ↓
DirectorySimulationLogger
        ↓
FileSystemSampleWriter
        ↓
ReplayReader / ReplayRunner
        ↓
summary viewer or Isaac Sim USD export viewer
```

## Development Priority

Near-term work should strengthen the dataset and replay foundation:

- keep simulation, logging, writing, replay, and future model code separate;
- make YAML configuration the normal experiment entry point;
- validate frame counts and metadata;
- keep offline replay possible from saved states;
- add real Isaac Sim or SOFA simulation only behind the existing backend protocol.
