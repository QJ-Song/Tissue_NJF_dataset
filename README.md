# Tissue NJF Dataset

This repository is an Isaac Sim workspace plus a standalone SOFA/tissue dataset module for Neural Jacobian Field (NJF) research.

The current project stage is **NJF theory diagnostics using controlled SOFA simulation**. It is not a trained NJF benchmark, not a real-tissue experiment, and not a clinical-realism claim.

## Current Status

The current bounded theory stage is closed. The main conclusion is:

```text
Within the tested single-contact normal, oblique, and shear-like action family,
fixed-condition soft-tissue responses are locally low-dimensional.

Response bases and coefficients are condition- and state-dependent.
Fixed response, fixed coefficient, global shared basis, and simple depth/scalar
rules are insufficient.

This motivates a conditioned local Jacobian representation:

delta_X = J_phi(X, p, theta, B) * delta_a
```

This conclusion is limited to controlled SOFA diagnostics. It does **not** show that a trained NJF outperforms existing deformation models, and it does **not** cover all possible tool actions.

The latest boundary diagnostic adds initial evidence that simplified fixed-node boundary conditions can strongly change response basis patterns:

```text
same contact/material, different boundary rank4 cross reconstruction error mean ~= 0.742796
normalized cross-boundary reconstruction error mean ~= 0.736558
```

The current basis/coefficient interpretation is:

```text
delta_x(q) = U(q | S, p, M, B) @ c(a | S, p, M, B)

S, p, M, B, and q condition the local response basis field.
Action direction and magnitude mainly condition the coefficients in the local small-step regime.
```

## Start Here

Read these documents first:

```text
docs/NJF_THEORY_SUMMARY.md
  Final bounded theory summary and supported/unsupported claims.

docs/NJF_THEORETICAL_ASSUMPTIONS_MATRIX.md
  H1-H8 assumption matrix mapping diagnostics to NJF theory claims.

docs/NJF_ACTION_COVERAGE_H7.md
  Explicit action-family boundary for the current claim.

docs/CONTROLLED_SOFA_DATASET_V1.md
  Controlled SOFA liver surface dataset commands, datasets, and reference results.

docs/NJF_MECHANISM_DIAGNOSTICS.md
  Diagnostic layer overview and interpretation rules.

docs/NJF_BOUNDARY_DIAGNOSTIC_SUMMARY.md
  Boundary-condition diagnostic table, metrics, and interpretation.

docs/NJF_BASIS_COEFFICIENT_FACTOR_ANALYSIS.md
  Working decomposition of basis versus coefficient factors for future NJF structure.
```

For broader project context:

```text
docs/CONTEXT.md
docs/ARCHITECTURE.md
docs/DATASET_SCHEMA.md
docs/SOFA_SETUP.md
docs/ISAAC_SIM_SETUP.md
```

## Repository Layout

```text
scripts/
  Isaac Sim setup helpers and standalone SOFA liver surface-collision scripts.

scenes/
  Scene definitions such as the SOFA liver surface-collision scene.
  Runtime logs and generated scene artifacts are ignored.

tissue_dataset_v0/
  Standalone dataset generator, SOFA/NJF readers, validators, analysis scripts,
  and replay/export utilities.

docs/
  Durable project context, architecture notes, dataset schema, theory summary,
  and controlled-dataset documentation.

tasks/
  Historical and active task notes. The current NJF theory stage converged in
  tasks/0021-njf-theoretical-assumptions-matrix.md.
```

Generated data is written under:

```text
tissue_dataset_v0/outputs/
```

This directory is ignored by Git and should not be committed.

## Common Commands

Run SOFA Python commands through the project wrapper:

```bash
scripts/run_sofa_python.sh -c "import SofaRuntime, Sofa; print('SOFA OK')"
```

Run the controlled dataset dry-run:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --dry-run \
  --reuse-existing \
  --stages all
```

Run analysis against existing generated outputs:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --reuse-existing \
  --stages analyze
```

Regenerate the standard controlled outputs:

```bash
python3 tissue_dataset_v0/scripts/run_liver_surface_controlled_v1.py \
  --overwrite \
  --stages all
```

Regeneration runs SOFA and can take time. Generated outputs stay outside Git.

## Current Task Boundary

In scope for the just-completed stage:

```text
- local response existence;
- fixed-condition low-rank response;
- contact/material/state condition dependence;
- rollout state dependence;
- coefficient instability;
- insufficiency of simple scalar/depth/local-ridge diagnostics;
- bounded action-family coverage for basis_v2;
- shared/global basis insufficiency;
- simplified boundary-condition influence on response basis;
- basis-versus-coefficient factor interpretation for future NJF structure.
```

Out of scope for this stage:

```text
- NJF neural network training;
- real phantom or real tissue experiment design;
- SOTA deformation-model benchmark;
- clinical realism claims;
- all-action coverage claims;
- grasping, cutting, puncture, tearing, or frictional sliding.
```

## Git And Data Policy

Commit source code, configs, docs, and task notes.

Do not commit:

```text
tissue_dataset_v0/outputs/
large logs
videos
checkpoints
local environment directories
private credentials or machine-specific secrets
```

The repository should remain reproducible from source plus documented commands, while large generated datasets remain local artifacts.

## Isaac Sim Setup

Isaac Sim is currently used for environment setup, initial scene exploration, and offline USD/USDA replay/export. It is not the default physics backend for current SOFA diagnostics.

The original Isaac Sim setup path is documented in:

```text
docs/ISAAC_SIM_SETUP.md
```

The helper script remains:

```bash
bash scripts/runisaacsim.sh
```

The workspace directory is currently named `issacsim`; NVIDIA's product name is `Isaac Sim`.
