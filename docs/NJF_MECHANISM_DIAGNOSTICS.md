# NJF Mechanism Diagnostics

## Purpose

This document tracks the lightweight diagnostic layer above the controlled SOFA datasets. The goal is not to prove NJF superiority and not to define the final benchmark. The goal is to understand the mechanics that a future NJF-style model must capture:

```text
- Can a local response basis express rollout step responses?
- Are basis coefficients stable during rollout?
- Are coefficients explainable by simple action depth or scalar metadata?
- Do hand-designed local state features expose enough information?
- Which variables must be recorded in later simulated and real datasets?
```

The current diagnostic layer is implemented without PyTorch or training-framework dependencies. These scripts are analysis tools, not final model baselines.


## Current Task Boundary

The current task is narrower than general NJF development. It only discusses NJF theoretical foundations using controlled SOFA diagnostics.

Out of scope for this task:

```text
- real phantom or real tissue experiment design;
- NJF neural network training;
- SOTA deformation-model benchmarking;
- clinical realism claims;
- complex surgical tool simulation unless required by a specific theory question;
- more hand-crafted predictor variants without a clear theoretical hypothesis.
```

The convergence document for this stage is:

```text
docs/NJF_THEORETICAL_ASSUMPTIONS_MATRIX.md
```

The final summary for this bounded theory stage is:

```text
docs/NJF_THEORY_SUMMARY.md
```

## Code Layout

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/basis.py
  Loads Mode B response-basis groups, computes uncentered SVD basis rows, and provides projection/coefficient helpers.

tissue_dataset_v0/src/tissue_dataset_v0/njf/metrics.py
  Shared relative L2, cosine, final accumulated error, and summary-stat helpers.

tissue_dataset_v0/src/tissue_dataset_v0/njf/baselines.py
  Historical module name. Implements coefficient diagnostics for matched Mode B basis and Mode C rollout data.

tissue_dataset_v0/src/tissue_dataset_v0/njf/fitted.py
  Implements fitted coefficient diagnostics using NumPy ridge regression.

tissue_dataset_v0/scripts/evaluate_coefficient_baseline.py
  Historical script name. Writes coefficient diagnostic summaries and reports.

tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py
  Historical script name. Writes fitted coefficient diagnostic summaries and reports.
```

## Diagnostic References

```text
B0_repeat_first_response
  Repeats the first observed rollout response for every future step.
  Answers: is one fixed local response enough for the whole rollout?

B1_oracle_basis_projection
  Projects every true rollout step response into the matched Mode B basis.
  This is an expression upper bound, not a predictive model.
  Answers: can the saved basis represent rollout responses?

B2_fixed_first_coefficient
  Projects the first response into the basis and reuses those coefficients for every future step.
  Answers: are basis coefficients stable during rollout?

B3_prefix_depth_trend_coefficient
  Fits coefficients from the first few rollout steps as a polynomial of cumulative depth and extrapolates.
  This is a diagnostic model, not a cross-group generalization result.
  Answers: are coefficients explainable by a simple depth trend?

R1_non_autoregressive
  NumPy ridge diagnostic using step/depth/action/material/contact-distance features.

R2_autoregressive
  R1 plus previous coefficient features, recursively predicted at test time.

R3_state_local_ridge
  R1 plus hand-designed local X_t patch statistics around the contact point.
```

## Current Main Results

Multi-direction reference averages across `normal`, `oblique30_pos_x`, and `shear60_pos_x`:

```text
B0 repeat first response final relative L2 mean=0.567206
B1 oracle basis projection rank4 final relative L2 mean=0.293901
B2 fixed first coefficient rank4 final relative L2 mean=0.566936
B3 linear 5-step depth trend rank4 final relative L2 mean=0.640908
```

Interpretation:

```text
1. B1 is consistently better than B0, so the Mode B basis has real expression value for rollout step responses.
2. B2 is almost identical to B0, so rollout behavior is not explained by a fixed first-step coefficient vector.
3. B3 is direction-sensitive and not robust, so cumulative depth alone is not enough.
```

Fitted ridge coefficient diagnostics, rank-4 final relative L2:

```text
run        split                         R1_non_autoregressive  R2_autoregressive
alpha1e-4  heldout_direction_within_group 1.422308              1616.606803
alpha1e-4  prefix_per_trajectory          2.126414              1.522574
alpha1e-2  heldout_direction_within_group 1.421575              669.163446
alpha1e-2  prefix_per_trajectory          2.103671              1.476092
alpha1     heldout_direction_within_group 1.357203              15.921540
alpha1     prefix_per_trajectory          1.563915              1.038837
alpha100   heldout_direction_within_group 0.699563              0.738773
alpha100   prefix_per_trajectory          0.827004              0.827190
```

State-local ridge diagnostics, rank-4 final relative L2:

```text
run               split                         R1_scalar  R2_autoreg  R3_state_local
state64_alpha100  heldout_direction_within_group 0.699563  0.738773    0.711574
state64_alpha100  prefix_per_trajectory          0.827004  0.827190    0.896943
state32_alpha100  heldout_direction_within_group 0.699563  0.738773    0.707538
state32_alpha100  prefix_per_trajectory          0.827004  0.827190    0.880351
state64_alpha1    heldout_direction_within_group 1.357203  15.921540   1.070288
state64_alpha1    prefix_per_trajectory          1.563915  1.038837    1.535840
state64_alpha1e-2 heldout_direction_within_group 1.421575  669.163446  2.191145
state64_alpha1e-2 prefix_per_trajectory          2.103671  1.476092    3.376615
```

Interpretation:

```text
1. Simple scalar/action/depth/material/contact-distance features do not explain coefficients well.
2. Recursive coefficient feedback is unstable in this linear fitted diagnostic.
3. Hand-designed local X_t statistics do not improve the stable ridge setting.
4. The current result does not prove a learned NJF will outperform alternatives; it only identifies that state/contact/material/action conditioning is necessary and that the representation likely needs to be richer than scalar hand-crafted features.
```



H7 action coverage boundary:

```text
Current conclusion covers the tested single-contact `basis_v2` family: normal press, oblique press, and shear-like press. It does not claim coverage of pure tangent, retraction, frictional sliding, multi-contact, cutting, puncture, or all possible tool motions. The detailed boundary is documented in docs/NJF_ACTION_COVERAGE_H7.md.
```

H8 shared-basis diagnostic on Mode B `basis_v2` data:

```text
rank2 local_group_basis_error_mean=0.049785
rank2 leave_one_group_out_shared_basis_error_mean=0.284659
rank4 local_group_basis_error_mean=0.007662
rank4 leave_one_group_out_shared_basis_error_mean=0.196617
rank4 nearest_group_basis_error_mean=0.183859
```

Interpretation: one fixed global shared basis is much weaker than group-local basis under held-out group reconstruction. This supports condition-specific/local basis behavior, which is consistent with conditioning `J_phi` on `X, p, theta, B`.

## Research Positioning

Current SOFA diagnostics should be used to support NJF theory analysis and controlled dataset-shape reasoning:

```text
- which variables affect local response;
- why Mode B fixed-condition groups are useful;
- why Mode C per-step rollout transitions are needed;
- why action family, contact point, material, boundary, state, and contact metadata must be saved;
- which variables are theoretically necessary in `J_phi(X, p, theta, B)`.
```

They should not be used as the final reviewer-facing benchmark. Real/phantom experiment design and model benchmarking are outside the current task boundary.

## Next Work

Recommended next steps:

```text
1. Stop adding more scalar ridge diagnostics unless they answer a specific mechanism question.
2. Use the current diagnostic results to define which variables are required by the NJF theoretical form.
3. Treat the current H8 shared-basis diagnostic as sufficient for the limited claim that a single global basis is not enough.
4. The final theory summary is now written in docs/NJF_THEORY_SUMMARY.md. Do not add new simulation, NJF training, or real-experiment planning unless the theory claim is explicitly expanded.
```
