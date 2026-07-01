# NJF Theoretical Assumptions Matrix

## Scope

This document is the convergence target for the current NJF theory task. The task is limited to SOFA controlled diagnostics and theoretical interpretation of NJF assumptions.

Out of scope for this task:

```text
- real phantom or real tissue experiment design;
- NJF neural network training;
- SOTA deformation-model benchmarking;
- clinical realism claims;
- complex surgical tools, cutting, puncture, grasping, or multi-contact scenes unless needed for a specific theory question;
- adding more hand-crafted coefficient predictors without a clear theoretical hypothesis.
```

The current question is:

```text
Do controlled tissue-tool simulations support the theoretical motivation for a state/contact/material/boundary-conditioned local Jacobian response model?
```

The intended NJF form is:

```text
delta_X = J_phi(X, p, theta, B) * delta_a
```

where `X` is the current tissue state, `p` is the contact/action point condition, `theta` is material, `B` is boundary condition, and `delta_a` is a small tool action.

## Convergence Target

This stage should stop when the project can clearly state:

```text
1. which NJF assumptions are supported by current SOFA diagnostics;
2. which assumptions are only partially supported;
3. which assumptions remain untested;
4. what each diagnostic fixes and varies;
5. why the NJF formulation is theoretically motivated without claiming performance superiority.
```

## Assumption Matrix

| ID | Theoretical assumption | Why it matters for NJF | Current diagnostic evidence | Status |
|---|---|---|---|---|
| H1 | Local tissue response exists under controlled small tool actions. | NJF requires a meaningful local map from small `delta_a` to `delta_X`. | Surface-collision liver samples and Mode B groups produce stable nonzero responses under fixed contact/material/boundary conditions. | Supported, within current SOFA setup. |
| H2 | Fixed-condition local responses are low-dimensional. | If response fields are locally low-rank, a compact local Jacobian/basis view is plausible. | Mode B per-group SVD: `basis_v1` top2 explained mean about `0.987973`; `basis_v2` top2 explained mean about `0.997322`, effective-rank mean about `1.071`. | Strongly supported for tested action families. |
| H3 | The local response basis is condition-dependent. | If basis changes with contact/material/boundary, `J_phi` must be conditioned on `p, theta, B` rather than fixed globally. | Cross-group basis diagnostics show higher reconstruction error across different contact/material groups; `basis_v2` rank4 off-diagonal cross reconstruction mean about `0.426280`, with contact changes harder than material-only changes. | Supported for contact/material. Boundary variation remains less explored in current liver surface batch. |
| H4 | Rollout responses depend on current state `X_t`. | NJF is a local transition model; response should be evaluated as `X_t -> X_{t+1}`, not just `X_0 -> X_T`. | Mode C rollout drift and fixed-first-step diagnostics show response changes over steps. Multi-direction average: B0 repeat-first final relative L2 mean about `0.567206`. | Supported. |
| H5 | A fixed first-step basis coefficient is insufficient. | Even if a basis expresses responses, coefficients may need state/action/contact conditioning. | B2 fixed first coefficient is close to B0 across normal, oblique30, and shear60; multi-direction rank4 mean about `0.566936`. | Supported. |
| H6 | Simple scalar depth/action/material/contact-distance rules are insufficient. | Supports the need for richer `J_phi(X, p, theta, B)` conditioning rather than a scalar depth trend. | B3 depth-trend is unstable across directions; fitted ridge R1/R2 and R3 state-local hand features do not close the B1 expression gap. | Supported for tested hand-crafted features. |
| H7 | Action-family coverage affects the observed response basis. | A vertical-only action set cannot justify a multi-direction Jacobian field. | `basis_v2` expands from small-cone press to normal, oblique, and shear-like directions while retaining strong within-group low-rank structure. The action boundary is documented in `docs/NJF_ACTION_COVERAGE_H7.md`. | Supported for the current limited theory claim: tested normal/oblique/shear-like single-contact actions. Not a claim about all possible tool motions. |
| H8 | A shared global basis may be insufficient, while locally aligned or condition-specific bases may work. | This determines whether NJF should predict a global coefficient map or a condition-dependent local Jacobian/basis. | H8 shared-basis diagnostic on existing Mode B `basis_v2` data: rank4 group-local error mean `0.007662`, pooled shared error mean `0.126482`, leave-one-group-out shared error mean `0.196617`, nearest-group error mean `0.183859`; rank2 shows the same trend. | Supported at the current theory level: a single held-out global shared basis is much weaker than group-local basis, favoring condition-specific/local basis behavior. |

## Existing Diagnostics And What They Answer

| Diagnostic | Fixed variables | Varied variables | Question answered | Current conclusion |
|---|---|---|---|---|
| Mode B per-group response basis | initial state, contact point, material, boundary, tool geometry, solver | action direction and magnitude within one group | Are local responses low-dimensional under fixed conditions? | Yes, strongly in current liver surface datasets. |
| Cross-group basis comparison | action-family design and solver | contact point and/or material | Is one basis shared across conditions? | Not fully; response basis is condition-dependent. |
| Mode C rollout drift | contact point, material, action direction family, solver | rollout state step `X_t` | Does the local response change during rollout? | Yes; repeated first response drifts. |
| Fixed Mode B basis projection | matched contact/material/boundary basis | rollout step response | Can a fixed local basis express rollout responses? | Much better than fixed first response, but residual remains. |
| Fixed first coefficient | matched basis and first coefficient | rollout step | Are coefficients stable over rollout? | No. |
| Depth-trend coefficient diagnostic | matched basis and early prefix | cumulative depth | Is depth alone enough to explain coefficients? | No; unstable and direction-dependent. |
| Fitted scalar/local ridge diagnostics | matched basis, simple engineered features | split direction or prefix step | Do simple hand-crafted features explain coefficients? | No; useful as negative evidence only. |
| `basis_v2` action family | contact/material/boundary/state | broader normal/oblique/shear-like directions | Does multi-direction action destroy local low-rank structure? | No for tested directions; still low-dimensional within group. |

## Initial Gap Decision

The current matrix suggests the theory stage is already strong for H1-H6. The remaining work should be constrained as follows:

```text
H7 action-family coverage:
  Treat `basis_v2` as sufficient for the limited current claim: the tested action family is broader than vertical-only and includes normal, oblique, and shear-like actions. The boundary is documented in `docs/NJF_ACTION_COVERAGE_H7.md`. Do not claim coverage of all possible tool motions. Do not add pure tangent, retraction, frictional sliding, or multi-contact actions unless the theory claim is expanded.

H8 shared/global basis:
  Completed using existing Mode B `basis_v2` data. Leave-one-group-out shared basis reconstruction is much worse than group-local reconstruction, while nearest-group is only modestly better than LOO shared. This supports condition-specific/local basis behavior rather than one fixed global basis.
```

Completed H8 diagnostic:

```text
Dataset: tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
Rank 2 output: analysis/basis_across_groups_h8_rank2
Rank 4 output: analysis/basis_across_groups_h8_rank4

Rank 2:
  local_group_basis_error_mean=0.049785
  pooled_shared_basis_error_mean=0.239098
  leave_one_group_out_shared_basis_error_mean=0.284659
  nearest_group_basis_error_mean=0.237405

Rank 4:
  local_group_basis_error_mean=0.007662
  pooled_shared_basis_error_mean=0.126482
  leave_one_group_out_shared_basis_error_mean=0.196617
  nearest_group_basis_error_mean=0.183859
```

H8 conclusion:

```text
The response basis is not well explained by one fixed global shared basis under leave-one-group-out reconstruction. The evidence favors condition-specific/local basis behavior. This supports conditioning `J_phi` on contact/material/state/boundary variables rather than using a single global response basis. This is a theory diagnostic only, not a model benchmark.
```

## Current Theory-Level Conclusion

Current SOFA diagnostics support this limited claim:

```text
Under controlled FEM liver surface-collision simulation, local tissue responses are low-dimensional when contact, material, boundary, and state are fixed. However, the response basis and coefficients are condition- and state-dependent. Fixed response, fixed coefficient, and simple depth/scalar rules are insufficient. This gives theoretical motivation for a conditioned local Jacobian representation J_phi(X, p, theta, B), without claiming that a trained NJF is superior to other deformation models.
```

## Remaining Theory Gaps

No required gap remains before summarizing this theory stage. The remaining items are optional and should not expand the task unless the theory claim changes:

```text
1. Local-aligned basis diagnostic:
   Optional only if the project wants to separate global coordinate mismatch from contact-centered local response-shape mismatch. Not required for the current limited claim.

2. Action-family completeness diagnostic:
   The current boundary is documented in `docs/NJF_ACTION_COVERAGE_H7.md`. Optional only if the project wants to expand beyond the current `basis_v2` normal/oblique/shear-like theory claim. Do not add pure tangent, retraction, sliding, or multi-contact actions under the current task boundary.
```

Do not start NJF training or real experiment planning inside this task.


## Final Summary

The bounded NJF theory stage is summarized in:

```text
docs/NJF_THEORY_SUMMARY.md
```

This matrix should now be treated as supporting evidence for that summary. Do not expand the task with new simulation, NJF training, or real-experiment planning unless the theory claim changes.
