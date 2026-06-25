# Repository Instructions

## Project Overview

This repository is an Isaac Sim workspace plus a standalone tissue dataset module. The intended project direction is Isaac Sim-based tool-tissue interaction simulation, synchronized simulation-time data logging, offline replay/visualization, and future Neural Jacobian Field (NJF) research.

The current working data module is `tissue_dataset_v0/`. Its default simulation backend is a NumPy toy backend (`ToyPressBackend`), not Isaac Sim physics. Isaac Sim is currently used for environment setup, initial scene exploration, and offline USD/USDA replay/export.

## Important Directories

- `scripts/`: Isaac Sim installation, host checks, startup helpers, and the original tissue poke scene script.
- `scenes/`: generated USD/USDA scenes and local run logs. Treat logs as generated artifacts.
- `tissue_dataset_v0/`: standalone tissue dataset generator, logging pipeline, YAML configs, and replay tools.
- `tissue_dataset_v0/configs/`: YAML experiment configs.
- `tissue_dataset_v0/src/tissue_dataset_v0/backend/`: simulation backend protocol definitions.
- `tissue_dataset_v0/src/tissue_dataset_v0/backends/`: concrete backend implementations.
- `tissue_dataset_v0/src/tissue_dataset_v0/config/`: default config and YAML loader.
- `tissue_dataset_v0/src/tissue_dataset_v0/sampling/`: action, material, and scene samplers.
- `tissue_dataset_v0/src/tissue_dataset_v0/replay/`: offline replay reader/runner/viewer plugins.
- `tissue_dataset_v0/outputs/`: generated datasets and replay exports. Do not delete without explicit confirmation.
- `docs/`: layered project context for future Codex sessions.
- `tasks/`: active and historical task notes.
- `.codex/skills/project-context-maintainer/`: local skill for maintaining this context system.

## Core Engineering Principle

Simulation-time data logging and offline replay/visualization must remain separated.

Simulation code should synchronously record physical states during simulation. Offline replay should visualize saved states directly, without rerunning physics, unless the explicit goal is reproducibility testing.

## Coding Rules

- Prefer small, testable modules.
- Do not hard-code absolute paths.
- Keep Isaac Sim-specific code isolated from general data/model code.
- Do not mix visualization logic into simulation stepping code.
- Use config files for material parameters, camera parameters, episode settings, paths, and random seeds.
- Keep dataset writing independent from replay and model training.
- Never delete datasets, logs, checkpoints, or generated results without explicit confirmation.
- Never expose API keys, access tokens, credentials, or private machine-specific paths.

## Data Rules

- Log data during simulation steps.
- Save enough state for offline replay.
- Each episode should include metadata, actions, tool poses, tissue states, and camera data when available.
- All time-dependent arrays should have consistent frame counts.
- Metadata should include seed, config path, scene version, material parameters, generation timestamp, and software version if detectable.
- Dataset generation should not silently overwrite existing episodes.

## Context Maintenance Rule

After every project file change, write the necessary persistent information into the context system before finishing the turn. Use `tasks/` for active work and acceptance status, `docs/` for architecture, setup, commands, schema, and durable assumptions, and keep `AGENTS.md` limited to concise operating rules.

## Safety and Privacy

Do not write the following into context files: API keys, access tokens, private credentials, private machine-specific absolute paths, large logs, generated datasets, model checkpoints, or private personal information.

If sensitive values are present in existing files, do not copy them into documentation. Use environment variables, ignored config files, or local-only files for sensitive settings.

## Before Finishing Checklist

Every future Codex session should:

1. Summarize changed files.
2. Mention whether tests or smoke checks were run.
3. Update relevant task files under `tasks/`.
4. Update docs if architecture, dataset schema, commands, setup, environment, or assumptions changed.
5. For every project file change, record the necessary persistent context in `docs/` or `tasks/` before finishing.
6. Avoid bloating `AGENTS.md`; put detailed explanations in `docs/`.
