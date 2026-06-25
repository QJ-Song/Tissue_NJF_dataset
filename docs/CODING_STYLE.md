# Coding Style

## General Rules

- Use config files instead of hard-coded parameters.
- Keep functions small and readable.
- Keep Isaac Sim imports isolated when possible.
- Keep simulation, logging, replay, dataset loading, and model training separate.
- Use type hints when practical.
- Prefer dataclasses or typed dictionaries for structured data.
- Avoid unnecessary dependencies.
- Write minimal tests for non-Isaac utility code.
- Keep generated datasets out of source directories.
- Do not commit large generated data, checkpoints, videos, or logs.
- Do not store secrets or private credentials in repository files.

## Repository-Specific Guidance

- Prefer YAML configs under `tissue_dataset_v0/configs/` for experiment parameters.
- New simulation implementations should go under `tissue_dataset_v0/src/tissue_dataset_v0/backends/` and implement the backend protocol.
- New sampling logic should go under `tissue_dataset_v0/src/tissue_dataset_v0/sampling/`.
- New replay tools should go under `tissue_dataset_v0/src/tissue_dataset_v0/replay/` and implement the viewer interface.
- Keep `tissue_dataset_v0/outputs/` as generated data; do not treat it as source.
- Do not make model code depend on Isaac Sim APIs; use saved datasets and loaders.

## Documentation Maintenance

Update docs when changing:

- architecture or module boundaries;
- dataset schema;
- run commands;
- YAML config semantics;
- replay behavior;
- assumptions about Isaac Sim, SOFA, or NJF.

Update `tasks/` after non-trivial implementation work.
