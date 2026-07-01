# Task: NJF Mechanism Diagnostics Framing

## Goal

Correct the current SOFA analysis framing. The SOFA work should be described as controlled mechanism diagnostics for NJF theory and dataset design, not as the final deformation-model benchmark and not as evidence that NJF outperforms existing models.

## Rationale

Simulation is not real tissue. Current fixed-response, basis-projection, coefficient, fitted-ridge, and state-local analyses are useful because they reveal which variables affect local tissue response:

```text
- contact point;
- action direction and step size;
- material parameters;
- boundary condition;
- rollout state X_t;
- contact status/distance;
- response-basis coordinate stability.
```

These results should guide NJF theoretical interpretation inside the current task. Real/phantom acquisition and model benchmarking are explicitly outside the active task boundary.

## Changes Made

```text
docs/NJF_MECHANISM_DIAGNOSTICS.md
  New primary context document for the current diagnostic layer.

docs/NJF_BASELINES.md
  Retained as a compatibility pointer to the new mechanism-diagnostics document.

docs/CONTROLLED_SOFA_DATASET_V1.md
  Reworded coefficient, fitted ridge, and state-local sections as diagnostics.

docs/CONTEXT.md
docs/EXPERIMENT_DESIGN.md
  Tightened language to avoid treating SOFA-only work as the final benchmark.

tasks/0010-sofa-stage-d-probe-contact-plan.md
tasks/0014-basis-v2-action-family.md
tasks/0015-basis-v2-rollout.md
tasks/0016-coefficient-baseline-v1.md
tasks/0017-multidirection-coefficient-baseline.md
tasks/0018-fitted-coefficient-predictor-v1.md
tasks/0019-state-local-ridge-feature-v1.md
  Reworded historical task notes to clarify diagnostic purpose.

docs/liver_surface_collision_notes.md
  Reworded the Mode C basis-projection section as a diagnostic rather than a baseline.

tissue_dataset_v0/scripts/evaluate_coefficient_baseline.py
tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/baselines.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/fitted.py
  Updated user-facing report and interpretation strings. Internal names such as baseline_id and predictor_id are retained for compatibility with existing outputs.
```

## Current Interpretation Rule

Use this language:

```text
SOFA controlled diagnostics indicate that fixed local response is insufficient, Mode B basis can express much of rollout response, coefficients change with state/action/material/contact, and simple hand-designed scalar/local ridge features do not explain this change well.
```

Avoid this language:

```text
SOFA results prove NJF is better than other deformation models.
Current ridge diagnostics are final baselines.
Simulation-only comparisons are sufficient reviewer-facing benchmarks.
```

## Updated Task Boundary

The active task is NJF theory only. Do not plan real/phantom experiments and do not start NJF training inside this task.

## Next Step

Do not add more scalar ridge diagnostics by default. Next work should:

```text
1. maintain docs/NJF_THEORETICAL_ASSUMPTIONS_MATRIX.md as the convergence document;
2. decide whether the shared/local-aligned basis diagnostic is necessary for H8;
3. decide whether the existing basis_v2 action family is sufficient for H7;
4. stop the theory stage once H1-H8 have clear supported/partial/untested status.
```
