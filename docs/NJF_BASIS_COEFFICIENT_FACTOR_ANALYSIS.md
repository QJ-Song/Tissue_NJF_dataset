# NJF Basis And Coefficient Factor Analysis

## Purpose

This note records a working interpretation of which variables primarily affect the response basis versus the response coefficients in the current NJF theory framing.

The goal is not to define the final neural architecture. The goal is to use current controlled SOFA diagnostics to guide later model-structure decisions.

## Working Decomposition

For a queried target point `q`, write the local response as:

```text
delta_x(q) = sum_k U_k(q | S, p, M, B) * c_k(a | S, p, M, B)
```

where:

```text
q: target predicted point
S: current tissue state X_t
p: contact point / action anchor
M: material parameters theta
B: boundary condition
a: action, including contact point, direction, and magnitude
U_k: response basis field
c_k: action-dependent coefficient
```

Equivalently:

```text
delta_x(q) = U(q | S, p, M, B) @ c(a | S, p, M, B)
```

In this view:

```text
basis U: what deformation modes are available under the current physical condition;
coefficient c: how the current action activates those modes.
```

## Summary Table

| Variable | Main Effect | Secondary Effect | Current Interpretation |
|---|---|---|---|
| target predicted point `q` | basis field | little direct coefficient effect | `q` selects where the response field is queried, so it parameterizes spatial basis values `U_k(q)`. |
| state `S` / `X_t` | basis and coefficient | strong on both | current deformation, geometry, local normal, contact state, and pre-stress can change both available modes and their activation. |
| contact point `p` | basis | coefficient | contact point sets the response center, propagation geometry, and local coordinate frame; cross-contact transfer is poor. |
| material `M` | coefficient and basis | both should be retained | stiffness intuition suggests scale/coefficients, but experiments show material also changes response pattern. |
| boundary `B` | basis | coefficient | constraints reshape deformation propagation and available degrees of freedom; paired boundary results show strong pattern changes. |
| action direction | coefficient | can reveal additional basis directions | under fixed `S,p,M,B`, direction mostly changes how basis modes are combined. Broad action families are needed to observe the local subspace. |
| action magnitude | coefficient scale | can change state/basis if too large | in the small-step local regime magnitude should scale coefficients; beyond local range it changes state and may invalidate a fixed basis. |

## Evidence By Variable

### Target Predicted Point `q`

Claim:

```text
q mainly affects the basis field U(q | S,p,M,B), not the action coefficient by itself.
```

Reasoning:

```text
The coefficient vector c is attached to an action under a fixed physical condition. The same action response is evaluated at every tissue node or surface point, so the spatial variation across predicted points is represented by U(q). If q directly changed c, the coefficient would no longer be a global action activation for one response field.
```

Current evidence status:

```text
This is a modeling/representation inference, not yet an isolated SOFA experiment. Existing datasets save full response fields over all nodes, which makes this decomposition possible, but no dedicated q-ablation has been run.
```

Implication:

```text
A later model can encode q through a spatial/basis field branch. Coefficients should normally be shared across target points for one action and condition.
```

### State `S` / `X_t`

Claim:

```text
S affects both basis and coefficients.
```

Supporting results:

```text
multi-direction B0 repeat-first final relative L2 mean = 0.567206
multi-direction B2 fixed-coefficient rank4 final relative L2 mean = 0.566936
multi-direction B1 oracle basis projection rank4 final relative L2 mean = 0.293901
```

Interpretation:

```text
Repeating the first response across rollout fails, so the local response changes as the tissue state evolves. Fixed first-step coefficients also fail, meaning the action's activation of the basis changes with state. The oracle projection into a matched basis is better, but still leaves residual rollout error, suggesting that state can also shift the useful local response subspace or at least the projection target.
```

Strength of evidence:

```text
Supported for rollout state dependence. The current data shows state changes matter, but does not fully separate basis drift from coefficient drift because both can occur during rollout.
```

Implication:

```text
Later NJF structure should condition both basis and coefficient prediction on X_t or local state features.
```

### Contact Point `p`

Claim:

```text
p mainly affects basis, with possible secondary coefficient effects.
```

Supporting results:

```text
same_material_diff_contact cross reconstruction error ~= 0.425404
basis_v2 rank4 off-diagonal cross reconstruction error mean ~= 0.426280
```

Interpretation:

```text
When material/action family are controlled, changing contact point makes one group's basis reconstruct another group's responses poorly. This means contact point changes the spatial response pattern and local subspace, not only the action coefficient. This is expected because contact point changes the response center, distance-to-boundary geometry, local normal/tangent frame, and deformation propagation path.
```

Strength of evidence:

```text
Supported by cross-group basis comparison across contact points.
```

Implication:

```text
p should condition the basis field. It can also condition coefficients because the same action direction/magnitude may activate modes differently at different locations.
```

### Material `M`

Claim:

```text
M affects coefficient scale and can also affect basis pattern.
```

Supporting results:

```text
same_contact_diff_material cross reconstruction error ~= 0.278777
material analysis conclusion: material changes are not treated as pure scale-only effects in the current theory summary
```

Interpretation:

```text
A simple linear-elastic intuition would say stiffness mainly rescales displacement magnitude. However, the cross-material reconstruction error is not negligible, so material changes also affect spatial response patterns in the current SOFA setup. This may come from stiffness interacting with contact constraints, nonlinear geometry, solver settling, and boundary constraints.
```

Strength of evidence:

```text
Supported, but weaker than contact and boundary in current reported metrics. More systematic normalized material-pair analysis can refine scale-vs-pattern separation.
```

Implication:

```text
M should not be used only as a scalar gain after prediction. It should be available to both coefficient and basis branches, although coefficient scaling may be its dominant role in simpler regimes.
```

### Boundary `B`

Claim:

```text
B strongly affects basis, with secondary coefficient effects.
```

Supporting results from paired boundary Mode B v1:

```text
same_contact_same_material_diff_boundary rank4 cross_err_mean = 0.742796
same_contact_same_material_diff_boundary projection_similarity_mean = 0.427059
same_contact_same_material_diff_boundary principal_angle_mean = 49.970 deg
boundary_pattern normalized_cross_error_mean = 0.736558
boundary_pattern normalized_projection_similarity_mean = 0.427186
pattern_changes = 10 / 12 paired boundary comparisons
```

Interpretation:

```text
Boundary changes transfer very poorly across bases even when contact, material, and action family are fixed. The normalized cross-boundary error remains high, so this is not just a response magnitude effect. The boundary condition changes available degrees of freedom and the global propagation path of deformation, which is a basis-level change.
```

Strength of evidence:

```text
Strong initial evidence for simplified fixed-node boundary conditions. It does not prove realistic anatomical boundary characterization.
```

Implication:

```text
B should condition the basis field. It can also affect coefficients because the same action may activate different modes when constraints change.
```

### Action Direction

Claim:

```text
action direction mainly affects coefficients under fixed S,p,M,B, but a richer direction family is needed to reveal the local basis.
```

Supporting results:

```text
basis_v1 top2 explained mean ~= 0.987973
basis_v2 top2 explained mean ~= 0.997322
basis_v2 effective_rank_mean ~= 1.071
basis_v2 covers normal, oblique, and shear-like single-contact actions
```

Interpretation:

```text
Within a fixed Mode B group, only action direction and magnitude vary. The responses remain low-dimensional, which supports the idea that different actions mostly select different combinations of a compact local response basis. However, vertical-only actions were judged insufficient because they do not expose the multi-direction local Jacobian structure.
```

Strength of evidence:

```text
Supported for the tested normal, oblique, and shear-like single-contact family. Not supported for pure tangent, retraction, sliding, multi-contact, cutting, or puncture.
```

Implication:

```text
Action direction should enter the coefficient head. It may also be used when learning basis implicitly, but conceptually it should not be the primary determinant of the physical basis under fixed S,p,M,B.
```

### Action Magnitude

Claim:

```text
action magnitude mainly affects coefficient scale in the local small-step regime, but can affect state and indirectly basis when the step is too large.
```

Supporting results:

```text
Mode B uses magnitudes 0.05, 0.1, and 0.2 mm inside fixed groups.
Fixed-condition responses remain low-dimensional across these magnitudes and directions.
Rollout diagnostics show larger accumulated motion cannot be treated as one unchanged first-step response.
```

Interpretation:

```text
For local perturbation, magnitude should approximately scale the activation of response modes. But accumulated or larger motion changes X_t and contact geometry, so a fixed first-step coefficient or response is insufficient. This is why the dataset stores per-step rollout states rather than only final deformation.
```

Strength of evidence:

```text
Supported for small local magnitudes and rollout accumulation. Exact local linearity thresholds remain configuration-dependent and should not be overgeneralized.
```

Implication:

```text
Magnitude should enter the coefficient head. For rollout, state must be updated after each step so magnitude does not silently become a large secant-response predictor.
```

## Model-Structure Implication

A reasonable later architecture hypothesis is:

```text
U = BasisField(q, S, p, M, B)
c = CoefficientHead(a_direction, a_magnitude, S, p, M, B)
delta_x(q) = U @ c
```

Minimal interpretation:

```text
q: query coordinate for the basis field
S: conditions both basis and coefficients
p: strongly conditions basis
M: conditions both scale/coefficient and basis pattern
B: strongly conditions basis
action direction/magnitude: primarily conditions coefficients
```

## Current Limits

This table is a theory guide, not a final architecture proof.

Current unsupported or only partially supported items:

```text
- q-specific ablation has not been run;
- state effects are shown through rollout but not cleanly decomposed into separate basis drift vs coefficient drift;
- material scale-vs-pattern separation could be strengthened with a dedicated normalized material diagnostic;
- action conclusions are limited to the tested single-contact normal/oblique/shear-like family;
- boundary conclusions are for simplified fixed-node SOFA constraints, not realistic anatomical support.
```
