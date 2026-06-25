# Task: Minimal Context System

## Background

Future Codex sessions need to understand this repository without the user repeatedly explaining the Isaac Sim workspace, `tissue_dataset_v0` module, synchronized logging design, offline replay design, and future NJF direction.

## Goal

Create a layered context system that captures global project rules, detailed architecture/research context, dataset schema expectations, roadmap, coding style, active tasks, and a local Codex skill for maintaining the context over time.

## Scope

Implement:
- Inspect repository structure before editing.
- Create root `AGENTS.md`.
- Create project context docs under `docs/`.
- Create `tasks/TEMPLATE.md`.
- Create this current task file.
- Create `.codex/skills/project-context-maintainer/SKILL.md`.
- Add documentation maintenance and safety/privacy policy.

Do not implement:
- Feature code changes.
- Isaac Sim backend implementation.
- Dataset validator implementation.
- Model/training code.
- Deletion or cleanup of generated outputs, logs, scenes, or environment files.

## Relevant context

Read first:
- AGENTS.md
- docs/CONTEXT.md
- docs/ARCHITECTURE.md
- docs/DATASET_SCHEMA.md
- docs/ROADMAP.md

Likely to modify:
- `AGENTS.md`
- `docs/*.md`
- `tasks/*.md`
- `.codex/skills/project-context-maintainer/SKILL.md`

## Requirements

- Context files must be project-specific and non-empty.
- Existing files must not be blindly overwritten.
- Sensitive values, generated datasets, large logs, checkpoints, and machine-private absolute paths must not be copied into context files.
- Root `AGENTS.md` must stay concise; detailed explanations belong in `docs/`.
- Future task state belongs in `tasks/`.

## Acceptance criteria

- A future Codex session can read `AGENTS.md`, `docs/CONTEXT.md`, `docs/ARCHITECTURE.md`, and this task file to understand the current project direction.
- Dataset schema and replay rules are documented.
- Isaac Sim setup notes are documented without copying private local paths.
- Roadmap captures the staged path from context system to NJF evaluation.
- The local skill explains how to maintain the context system.

## Test command

```bash
env_isaacsim/bin/python -m compileall -q tissue_dataset_v0/src/tissue_dataset_v0 tissue_dataset_v0/scripts
```

## Progress

* [x] Plan reviewed
* [x] Implementation done
* [x] Test passed
* [x] Documentation updated
* [x] Notes updated

## Notes

Repository inspection found no existing root `AGENTS.md`, `docs/`, `tasks/`, or `.codex/` context files. Optional module-level `sim/AGENTS.md`, `src/data/AGENTS.md`, `src/replay/AGENTS.md`, and `src/models/AGENTS.md` were intentionally skipped because those exact root-level module directories do not currently exist.

Current dataset generation still uses `ToyPressBackend`; Isaac Sim is currently setup/replay/export context rather than the default simulation backend.
