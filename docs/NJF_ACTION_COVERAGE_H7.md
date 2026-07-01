# H7 Action Coverage Note

## Purpose

This note defines the action-family boundary for the current NJF theory task. It is not a proposal to expand simulation.

Current H7 question:

```text
Is the tested action family broad enough to support a limited multi-direction local-response theory claim?
```

The answer is yes for the current limited claim, with explicit exclusions.

## Covered Action Families

| Action family | Covered now | Evidence | Theory use |
|---|---:|---|---|
| Vertical/normal press | Yes | `basis_v1` and `basis_v2` include normal press actions. | Establishes basic local response and low-rank behavior under normal contact. |
| Small-cone press | Yes | `basis_v1` uses small-cone press directions. | Earlier response-basis reference. |
| Oblique press | Yes | `basis_v2` includes oblique directions around the surface normal. | Shows the result is not vertical-only. |
| Shear-like press | Yes | `basis_v2` includes 40-60 degree shear-like directions while using normal probe approach. | Tests broader local action direction without changing to frictional sliding. |
| Multiple contact points | Yes | `basis_v2` factorial data uses top-left, top-center, and top-right contacts. | Supports contact-dependent basis conclusions. |
| Multiple material settings | Yes | `basis_v2` factorial data uses Young modulus 1000, 3000, and 10000. | Supports material-conditioned basis conclusions. |

## Not Covered

| Action family | Status | Reason |
|---|---|---|
| Pure tangent displacement | Optional, not required now | In frictionless or low-friction contact, response may be weak or ambiguous. Useful only if the theory claim expands to tangential-only local motion. |
| Retraction / unload | Optional, not required now | Useful for loading/unloading asymmetry, but not necessary for the current local response-basis claim. |
| Frictional sliding | Deferred | Introduces friction/path dependence and changes the theory question. |
| Tool rotation | Deferred | Can change contact patch and tool geometry effects; not needed for current `delta_a` translation-family claim. |
| Multi-contact / grasping | Out of scope | Changes from local single-contact response to multi-contact interaction. |
| Cutting / puncture / tearing | Out of scope | Leaves elastic local-response regime. |

## Current Claim Boundary

Allowed claim:

```text
Within the tested normal, oblique, and shear-like single-contact action family, fixed-condition tissue responses remain low-dimensional, while response bases and coefficients are condition-dependent.
```

Disallowed claim:

```text
Response basis is low-dimensional for all possible tool actions.
The current action family covers sliding, grasping, cutting, puncture, or all tangential contact regimes.
```

## Decision

No new SOFA action simulation is required for the current theory stage.

The existing `basis_v2` action family is sufficient for H7 if the final theory summary preserves this boundary. A `basis_v2_plus` spike with pure tangent and retraction actions should only be added if the project explicitly expands the claim beyond the current normal/oblique/shear-like single-contact family.
