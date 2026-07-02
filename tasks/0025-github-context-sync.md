# Task: GitHub Context Sync

## Goal

Make the GitHub repository self-explanatory for a fresh reader or ChatGPT instance that only sees repository contents. The repository should clearly state the project purpose, method, current conclusions, and limitations.

## Work

Updated `README.md` so the first-page project entry includes:

```text
- current controlled SOFA NJF theory-diagnostic purpose;
- latest boundary diagnostic result;
- current basis/coefficient decomposition;
- links to the boundary diagnostic summary;
- links to the basis/coefficient factor analysis;
- updated in-scope list for boundary and basis/coefficient interpretation.
```

This task also includes the uncommitted theory-context document from the previous step:

```text
docs/NJF_BASIS_COEFFICIENT_FACTOR_ANALYSIS.md
```

## Verification

Before commit, run:

```bash
git diff --check
python3 -m py_compile tissue_dataset_v0/scripts/analyze_basis_across_groups.py \
  tissue_dataset_v0/scripts/check_boundary_solver.py \
  tissue_dataset_v0/src/tissue_dataset_v0/backends/sofa_fem.py \
  tissue_dataset_v0/src/tissue_dataset_v0/njf/plan.py
```

## Status

Ready to commit and push.
