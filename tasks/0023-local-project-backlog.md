# Task: Local Project Backlog

## Purpose

Track local project-management follow-up after the NJF theory diagnostics stage converged and the README project entry was updated.

This backlog is local repository management only. It is not a request to start new SOFA simulation, NJF training, real-experiment planning, or GitHub issue management.

## Current Required Work

```text
None.
```

The current NJF theory stage is closed:

```text
H1-H6: supported by existing SOFA diagnostics.
H7: closed by docs/NJF_ACTION_COVERAGE_H7.md.
H8: closed by shared-basis diagnostics.
Final summary: docs/NJF_THEORY_SUMMARY.md.
README entrypoint: updated and pushed.
```

## Optional Local Follow-Up

These are optional and should only be done if they answer a concrete project-management need.

```text
1. Fresh-reader reproducibility dry-run
   Command:
     python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py --dry-run --reuse-existing --stages all
   Purpose:
     Check that README command entry points still parse and that expected generated-output roots are named clearly.
   Constraint:
     Do not regenerate datasets unless explicitly requested.

2. Local generated-output index
   Purpose:
     Write a small local-only or docs-level index of important generated output roots and which experiment they correspond to.
   Constraint:
     Do not commit generated arrays, videos, logs, or large outputs.

3. Optional local-aligned basis diagnostic planning
   Purpose:
     Only if the theory claim expands to distinguish global-coordinate mismatch from contact-centered local response-shape mismatch.
   Constraint:
     Do not run new diagnostics under the current closed theory task.
```

## Explicitly Deferred

```text
- NJF neural network training;
- real phantom or real tissue experiment design;
- SOTA deformation-model benchmark planning;
- GitHub milestone/issue creation until gh is installed and authenticated or the user chooses to manage GitHub manually;
- new SOFA action families beyond current basis_v2 unless the theory claim is expanded;
- complex tool interaction such as grasping, cutting, puncture, tearing, or frictional sliding.
```

## Recommended Next Action

If continuing locally, do the fresh-reader dry-run only:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --dry-run \
  --reuse-existing \
  --stages all
```

If no further local management is needed, stop here. The repository is in a clean, pushed state as of the README entry update.
