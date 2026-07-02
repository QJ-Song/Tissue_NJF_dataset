# NJF Boundary Diagnostic Summary

## Purpose

This document summarizes the first boundary-condition diagnostic for the controlled SOFA NJF theory stage.

Question:

```text
Does boundary condition B affect the local response basis under fixed contact, material, and action family?
```

This is a controlled simulation diagnostic only. It does not claim realistic anatomical boundary modeling.

## Dataset

Config:

```text
tissue_dataset_v0/configs/sofa_njf_boundary_basis_v1.yaml
```

Generated output, not committed:

```text
tissue_dataset_v0/outputs/sofa_njf_boundary_basis_v1
```

Design:

| Factor | Values | Role |
|---|---:|---|
| contact point | 2 | controlled pairing axis |
| material | 1 | fixed, Young's modulus 5000, Poisson ratio 0.45 |
| boundary condition | 4 | varied variable |
| action directions | 8 | within-group varied actions |
| action magnitudes | 3 | within-group varied actions |
| actions per group | 24 | Mode B response basis |
| groups | 8 | 2 contact x 1 material x 4 boundary |
| samples | 192 | full paired boundary dataset |

Boundary conditions:

| boundary type | fixed nodes | selection |
|---|---:|---|
| `bottom_fixed` | 63 | regular grid bottom layer |
| `back_fixed` | 36 | regular grid back side, y-min |
| `bottom_and_back_fixed` | 90 | union of bottom and back |
| `small_bottom_patch_fixed` | 3 | bottom center patch |

## Validation

| Check | Result |
|---|---|
| dataset validation | PASS, 192 samples, 8 groups, 0 errors |
| boundary/solver check | PASS, 192 samples, 0 errors |
| read smoke | PASS |
| fixed-node displacement | 0.000000 mm in checked samples |
| rank-2 basis analysis | PASS |
| rank-4 basis analysis | PASS |

## Main Result Table

Rank-4 analysis:

| Comparison | Fixed Variables | Varied Variable | Metric | Result | Interpretation |
|---|---|---|---|---:|---|
| group-local basis | contact, material, boundary | action direction/magnitude | local basis error mean | 0.047787 | each fixed boundary group remains expressible by a compact local basis |
| same contact/material, different boundary | contact, material, action family | boundary | cross reconstruction error mean | 0.742796 | boundary changes transfer poorly across bases |
| same contact/material, different boundary | contact, material, action family | boundary | projection similarity mean | 0.427059 | boundary bases are not strongly aligned |
| same contact/material, different boundary | contact, material, action family | boundary | principal angle mean | 49.970 deg | subspace orientation changes substantially |
| normalized response boundary comparison | contact, material, action family | boundary | normalized cross error mean | 0.736558 | effect is not only response magnitude scaling |
| normalized response boundary comparison | contact, material, action family | boundary | normalized projection similarity mean | 0.427186 | response pattern changes remain after normalization |

Per-pair boundary pattern summary:

| Pair Classification | Count |
|---|---:|
| `pattern_changes` | 10 / 12 |
| `mostly_scale_with_some_pattern_change` | 2 / 12 |
| `scale_only_like` | 0 / 12 |

## Interpretation

The paired boundary diagnostic gives initial controlled-SOFA evidence that simplified fixed-node boundary conditions can strongly change local response basis patterns.

The strongest observation is that normalized cross-boundary reconstruction error remains high. This means boundary changes are not explained only by response amplitude; they alter the spatial response pattern itself.

For the NJF theory formulation:

```text
delta_X = J_phi(X, p, theta, B) * delta_a
```

this supports keeping `B` as an explicit conditioning variable in `J_phi`, at least for controlled SOFA settings where fixed-node constraints differ.

## Limits

This result does not prove:

```text
- realistic anatomical boundary behavior;
- table contact or abdominal support realism;
- adhesion, organ suspension, or interaction with surrounding anatomy;
- that boundary effects are fully characterized;
- that a trained NJF outperforms other deformation models.
```

The supported claim is narrower:

```text
Under the current simplified SOFA liver setup, changing fixed-node boundary constraints changes the local response basis enough that B should be retained in the theoretical NJF conditioning set.
```
