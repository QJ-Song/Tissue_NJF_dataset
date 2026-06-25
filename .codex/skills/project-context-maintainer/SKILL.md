---
name: project-context-maintainer
description: Maintain this repository's layered context system for Isaac Sim tissue simulation, dataset logging, offline replay, and future NJF work. Use when starting work in this repository, adding a subsystem, changing dataset schema or architecture, adding experiments, adding replay/visualization tools, adding NJF or baseline models, or finishing a non-trivial task.
---

# Project Context Maintainer

## Purpose

Maintain the layered context system so future Codex sessions can understand the project structure, research goal, engineering plan, current tasks, and active assumptions without relying on conversation history.

## Files to Read First

Read in this order:

1. `AGENTS.md`
2. `docs/CONTEXT.md`
3. `docs/ARCHITECTURE.md`
4. Relevant `docs/*.md` for the task
5. Relevant `tasks/*.md`
6. Local `AGENTS.md` if working inside a module that has one

## Maintenance Rules

- Keep `AGENTS.md` concise and operational.
- Put long explanations in `docs/`.
- Put active work, status, and acceptance criteria in `tasks/`.
- Put local rules in module-level `AGENTS.md` only when a module directory exists and has stable responsibilities.
- Do not duplicate the same background across many files.
- Update docs when architecture, dataset schema, run commands, setup, environment, replay behavior, config semantics, or assumptions change.
- Update task files after implementation.
- After every project file change, record the necessary persistent context in `docs/` or `tasks/` before finishing the turn.
- Never store secrets, credentials, private paths, generated datasets, logs, videos, or checkpoints as context.

## Safety and Privacy

Do not write the following into context files:

- API keys
- access tokens
- private credentials
- private machine-specific absolute paths
- large logs
- generated datasets
- model checkpoints
- private personal information

If such information appears in existing files, do not copy it into documentation. Say that sensitive values should be managed through environment variables, ignored config files, or local-only files.

## After Each Non-Trivial Task

1. Update the relevant task file.
2. Update docs if assumptions changed.
3. Summarize changed files.
4. Mention tests or smoke checks.
5. Mention uncertain or outdated docs.
6. Propose the next small task.

## Context Placement Guide

- Global rules and must-follow repository policies: `AGENTS.md`.
- Research and engineering background: `docs/CONTEXT.md`.
- Module boundaries and dependency direction: `docs/ARCHITECTURE.md`.
- Episode/sample fields and validation rules: `docs/DATASET_SCHEMA.md`.
- Isaac Sim setup and known commands: `docs/ISAAC_SIM_SETUP.md`.
- NJF notation and learning target: `docs/NJF_FORMULATION.md`.
- Experiment ideas and metrics: `docs/EXPERIMENT_DESIGN.md`.
- Staged project plan: `docs/ROADMAP.md`.
- Coding conventions: `docs/CODING_STYLE.md`.
- Active work and acceptance criteria: `tasks/*.md`.

## Working Rule

When a change affects generated data format, replay behavior, backend responsibilities, or run commands, update both the relevant docs and the active task note before final response.
