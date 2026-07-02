# NJF Theory Summary

## Scope

This summary closes the current NJF theory task. It only uses controlled SOFA diagnostics to discuss the theoretical motivation for a Neural Jacobian Field style local response model.

Out of scope:

```text
- real phantom or real tissue experiment design;
- NJF neural network training;
- comparison against SOTA deformation models;
- clinical realism claims;
- all-action coverage claims;
- complex surgical tools, grasping, cutting, puncture, tearing, or frictional sliding.
```

The theoretical form under discussion is:

```text
delta_X = J_phi(X, p, theta, B) * delta_a
```

where:

```text
X: current tissue state
p: contact/action point condition
theta: material parameters
B: boundary condition
delta_a: small local tool action
delta_X: tissue response
```

## Final Limited Claim

Current SOFA controlled diagnostics support this limited theory claim:

```text
Within the tested single-contact normal, oblique, and shear-like action family, fixed-condition soft-tissue responses are locally low-dimensional. However, response bases and coefficients are not globally fixed: they depend on contact/material conditions and rollout state. Fixed response, fixed coefficient, global shared basis, and simple depth/scalar rules are insufficient. This gives theoretical motivation for a conditioned local Jacobian representation J_phi(X, p, theta, B), without claiming that a trained NJF is superior to other deformation models.
```

## Evidence By Assumption

| ID | Assumption | Status | Main evidence |
|---|---|---|---|
| H1 | Local response exists under controlled small tool actions. | Supported | SOFA liver surface-collision samples and Mode B groups produce stable nonzero responses under fixed contact/material/boundary settings. |
| H2 | Fixed-condition responses are low-dimensional. | Strongly supported | Mode B per-group SVD: `basis_v1` top2 explained mean about `0.987973`; `basis_v2` top2 explained mean about `0.997322`, effective-rank mean about `1.071`. |
| H3 | Response basis is condition-dependent. | Supported for contact/material and initially supported for simplified boundary conditions | Cross-group reconstruction is substantially worse than per-group reconstruction; `basis_v2` rank4 off-diagonal cross reconstruction mean about `0.426280`. Paired boundary Mode B v1 shows same-contact/material different-boundary rank4 cross reconstruction mean about `0.742796`. |
| H4 | Rollout responses depend on current state `X_t`. | Supported | Multi-direction rollout fixed-first response diagnostic has final relative L2 mean about `0.567206`, showing first response cannot be reused through rollout. |
| H5 | Fixed first-step coefficients are insufficient. | Supported | B2 fixed first coefficient is close to B0; multi-direction rank4 final relative L2 mean about `0.566936`. |
| H6 | Simple scalar/depth/local-ridge rules are insufficient. | Supported for tested hand-crafted features | B3 depth trend is unstable; R1/R2/R3 fitted ridge diagnostics do not close the expression gap to B1. |
| H7 | Action coverage is broad enough for the limited claim. | Supported with boundary | `basis_v2` covers normal, oblique, and shear-like single-contact actions. Pure tangent, retraction, sliding, rotation, multi-contact, cutting, and puncture are excluded. |
| H8 | One fixed global shared basis is insufficient. | Supported | Rank4 group-local error mean `0.007662` versus leave-one-group-out shared error mean `0.196617`; rank2 shows the same trend. |

## Key Diagnostic Results

### Local Low-Rank Response

Fixed-condition Mode B groups are strongly low-dimensional:

```text
basis_v1 top2 explained mean=0.987973
basis_v2 top2 explained mean=0.997322
basis_v2 effective_rank_mean=1.071
```

Interpretation: when `X`, `p`, `theta`, `B`, tool geometry, and solver are fixed, different small local actions produce responses that lie in a compact response subspace.

### Condition Dependence

Cross-group basis transfer is much worse than within-group expression:

```text
basis_v2 rank4 offdiag_cross_reconstruction_error_mean=0.426280
same_contact_diff_material_cross_err=0.278777
same_material_diff_contact_cross_err=0.425404
diff_contact_diff_material_cross_err=0.500469
```

Interpretation: contact point changes are especially important, material changes also affect response pattern, and the paired boundary Mode B v1 diagnostic shows that simplified fixed-node boundary changes can strongly alter response patterns. This supports conditioning `J_phi` on `p`, `theta`, and `B`, while still treating realistic anatomical boundary modeling as outside the current claim.


Boundary paired Mode B v1 adds initial evidence for `B`:

Detailed boundary diagnostic table: `docs/NJF_BOUNDARY_DIAGNOSTIC_SUMMARY.md`.


```text
same_contact_same_material_diff_boundary rank4 cross_err_mean=0.742796
boundary_pattern normalized_cross_error_mean=0.736558
boundary_pattern normalized_projection_similarity_mean=0.427186
```

Interpretation: simplified boundary changes are not only scale changes; response basis pattern changes remain after response normalization.

### Rollout State Dependence

A response observed at the first rollout step does not remain valid over the full rollout:

```text
multi-direction B0 repeat-first final relative L2 mean=0.567206
multi-direction B2 fixed-coefficient rank4 final relative L2 mean=0.566936
```

Interpretation: rollout response changes with state. NJF should be treated as a local transition model over `X_t -> X_{t+1}`, not as a one-shot final-deformation predictor.

### Basis Expression Versus Coefficient Prediction

The matched Mode B basis can express rollout responses much better than fixed-response diagnostics:

```text
multi-direction B1 oracle basis projection rank4 final relative L2 mean=0.293901
```

But simple coefficient rules are insufficient:

```text
B3 linear 5-step depth trend rank4 final relative L2 mean=0.640908
R1/R2/R3 ridge diagnostics do not outperform the fixed-response references robustly.
```

Interpretation: the response subspace is useful, but the coefficient or local Jacobian must be conditioned on richer state/contact/material/action information.

### Shared Basis

H8 shared-basis diagnostic on existing Mode B `basis_v2` data:

```text
rank2:
  local_group_basis_error_mean=0.049785
  pooled_shared_basis_error_mean=0.239098
  leave_one_group_out_shared_basis_error_mean=0.284659
  nearest_group_basis_error_mean=0.237405

rank4:
  local_group_basis_error_mean=0.007662
  pooled_shared_basis_error_mean=0.126482
  leave_one_group_out_shared_basis_error_mean=0.196617
  nearest_group_basis_error_mean=0.183859
```

Interpretation: one held-out global shared basis is much weaker than group-local basis. The evidence favors condition-specific/local basis behavior, consistent with predicting `J_phi(X, p, theta, B)` rather than using a single fixed response basis.

### Action Coverage

Current action coverage is sufficient only for the limited tested family:

```text
covered: normal press, small-cone press, oblique press, shear-like press
not covered: pure tangent, retraction/unload, frictional sliding, tool rotation, multi-contact, grasping, cutting, puncture, tearing
```

Interpretation: the project can claim multi-direction behavior within the tested `basis_v2` family, but cannot claim all possible tool actions. See `docs/NJF_ACTION_COVERAGE_H7.md`.

### Basis Versus Coefficient Factor Interpretation

A separate factor-analysis note records the current interpretation of whether each variable mainly affects the response basis or action coefficients:

```text
docs/NJF_BASIS_COEFFICIENT_FACTOR_ANALYSIS.md
```

Short version: target point `q` parameterizes the basis field; action direction and magnitude primarily affect coefficients; state, contact point, material, and boundary condition all condition the local response basis, with state and material also affecting coefficients.


## What This Supports

The current evidence supports:

```text
1. Local response modeling is meaningful under controlled single-contact SOFA simulation.
2. Fixed-condition responses have low-dimensional structure.
3. Response basis and coefficients are condition-dependent.
4. Rollout requires per-step local transition reasoning.
5. A fixed global basis or simple depth/scalar coefficient rule is insufficient.
6. The NJF form J_phi(X, p, theta, B) * delta_a has clear theory motivation.
```

## What This Does Not Support

The current evidence does not support:

```text
1. NJF outperforms existing deformation models.
2. A trained NJF will generalize outside simulation.
3. The response basis is low-dimensional for all possible tool actions.
4. The current SOFA scene is clinically realistic.
5. Pure tangent, sliding, grasping, cutting, puncture, or tearing interactions are covered.
6. Boundary-condition effects are fully characterized.
```

## Stop Condition

The current NJF theory task can stop here.

H1-H8 have enough status for the bounded theory claim:

```text
H1-H6: supported by existing SOFA diagnostics.
H7: closed by the action coverage boundary.
H8: closed by shared-basis diagnostics.
```

The next action should be documentation or project management, not new SOFA simulation, NJF training, or real-experiment planning, unless the research question is explicitly expanded.
