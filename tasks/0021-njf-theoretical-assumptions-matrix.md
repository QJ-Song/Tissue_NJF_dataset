# Task: NJF Theoretical Assumptions Matrix

## Goal

Converge the current work to NJF theory analysis only. This task maps existing SOFA controlled diagnostics to explicit NJF theoretical assumptions and identifies the minimum remaining diagnostics, if any.

## Scope

In scope:

```text
- local response existence;
- fixed-condition low-rank response;
- condition dependence across contact/material/boundary;
- rollout state dependence;
- coefficient instability;
- insufficiency of simple depth/scalar/local ridge rules;
- action-family coverage for multi-direction local response;
- optional shared/local-aligned basis diagnostics.
```

Out of scope:

```text
- real experiment design;
- NJF model training;
- SOTA benchmark planning;
- clinical realism claims;
- adding complex contact/tool scenarios without a theory question.
```

## Work Done

Created:

```text
docs/NJF_THEORETICAL_ASSUMPTIONS_MATRIX.md
```

Updated:

```text
docs/NJF_MECHANISM_DIAGNOSTICS.md
docs/CONTEXT.md
tasks/0020-njf-mechanism-diagnostics-framing.md
```

## Current Matrix Status

```text
H1 local response: supported within current SOFA setup.
H2 fixed-condition low-rank response: strongly supported.
H3 condition-dependent basis: supported for contact/material; boundary less explored.
H4 rollout state dependence: supported.
H5 fixed coefficient insufficiency: supported.
H6 scalar/depth/local ridge insufficiency: supported for tested features.
H7 action-family coverage: supported for the current limited `basis_v2` normal/oblique/shear-like single-contact theory claim; boundary documented in docs/NJF_ACTION_COVERAGE_H7.md.
H8 shared/global basis insufficiency: supported by rank2/rank4 shared-basis diagnostics on existing Mode B basis_v2 data.
```

## Next Decision

Before running any new experiment, decide whether H7 and H8 are already sufficient for the theory claim. If not, add exactly one narrowly scoped diagnostic:

```text
Option A: shared/local-aligned basis diagnostic for H8.
Option B: action-family completeness summary for H7 using existing basis_v2 data.
```

No NJF training and no real-experiment planning should be added under this task.

## Initial Decision

H7 is sufficient for the current limited theory claim if the wording stays precise: `basis_v2` covers the tested normal/oblique/shear-like family, not all possible tool motions. Do not expand action families now.

H8 is the best remaining diagnostic because it can use existing Mode B `basis_v2` data without new SOFA simulation. The next implementation should compare group-local, pooled/shared, leave-one-group-out shared, and nearest-group basis reconstruction. Optional local/contact alignment should only be added if it is cleanly supported by existing metadata.

## H8 Shared-Basis Diagnostic Completed

Implemented in:

```text
tissue_dataset_v0/scripts/analyze_basis_across_groups.py
```

Generated outputs:

```text
tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/analysis/basis_across_groups_h8_rank2
tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1/analysis/basis_across_groups_h8_rank4
```

Rank-2 result:

```text
local_group_basis_error_mean=0.049785
pooled_shared_basis_error_mean=0.239098
leave_one_group_out_shared_basis_error_mean=0.284659
nearest_group_basis_error_mean=0.237405
```

Rank-4 result:

```text
local_group_basis_error_mean=0.007662
pooled_shared_basis_error_mean=0.126482
leave_one_group_out_shared_basis_error_mean=0.196617
nearest_group_basis_error_mean=0.183859
```

Interpretation: the response basis is clearly low-dimensional within each fixed group, but a held-out global shared basis is much weaker than group-local reconstruction. This supports condition-specific/local basis behavior and strengthens the theory motivation for conditioning `J_phi` on `X, p, theta, B`.

## Updated Stop Condition

H1-H8 now have enough status for the current theory boundary. H7 is closed by the action coverage note, and H8 is closed by the shared-basis diagnostic. The next step should be a final theory summary, not new simulation, NJF training, or real-experiment planning. Optional local-aligned basis analysis should only be added if the claim is expanded to distinguish global-coordinate mismatch from contact-centered local-shape mismatch.

## H7 Action Coverage Note Completed

Created:

```text
docs/NJF_ACTION_COVERAGE_H7.md
```

Decision:

```text
No new SOFA action simulation is required for the current theory stage. The existing `basis_v2` action family is sufficient if the final claim is limited to tested normal, oblique, and shear-like single-contact actions. Pure tangent, retraction/unload, frictional sliding, rotation, multi-contact, grasping, cutting, and puncture are outside the current claim.
```

Updated status: H7 is closed for the current bounded task.

## Final Theory Summary Completed

Created:

```text
docs/NJF_THEORY_SUMMARY.md
```

Final bounded claim:

```text
Within the tested single-contact normal, oblique, and shear-like action family, fixed-condition soft-tissue responses are locally low-dimensional. Response bases and coefficients are condition- and state-dependent. Fixed response, fixed coefficient, global shared basis, and simple depth/scalar rules are insufficient. This motivates a conditioned local Jacobian representation J_phi(X, p, theta, B) * delta_a, without claiming NJF performance superiority.
```

Task status: converged for the current theory boundary. Next work should be project management, cleanup, or commit/sync. Do not add new SOFA simulation, NJF training, or real-experiment planning under this task.
