# Task: Git Initial Import

## Background

The project needs a safe Git baseline that can be pushed to a remote repository without committing local environments, generated datasets, logs, caches, or platform metadata files.

## Goal

Initialize Git for the current workspace, add repository ignore rules, stage only source/config/docs/task/context files and required smoke assets, and create a clean initial commit.

## Scope

Implement:
- Initialize Git if the workspace is not already a repository.
- Add root `.gitignore`.
- Stage source, configs, docs, task notes, scripts, context skill, and optional `scenes/tissue_poke_demo.usda`.
- Exclude `env_isaacsim/`, generated outputs, caches, logs, egg-info metadata, macOS `._*` files, and temporary files.
- Add GitHub remote `origin` for `https://github.com/QJ-Song/Tissue_NJF_dataset`.

Do not implement:
- Code logic changes.
- Dataset cleanup or deletion.
- Environment cleanup or deletion.
- Generated output deletion.

## Acceptance Criteria

- `git status --short` is reviewed before commit.
- `git diff --cached --name-only` contains only intended project files.
- Ignored generated paths are verified with `git check-ignore`.
- Initial commit is created with no generated dataset, virtual environment, cache, egg-info, or private credential files staged.

## Progress

* [x] Plan reviewed
* [x] Git repository initialized
* [x] `.gitignore` added
* [x] Safe staging reviewed
* [x] Initial commit created

## Notes

The Git remote target is `https://github.com/QJ-Song/Tissue_NJF_dataset`. Generated datasets and local environments remain on disk and are excluded only through ignore rules. Initial staging was reviewed with `git status --short`, `git diff --cached --stat`, and `git diff --cached --name-only`.
