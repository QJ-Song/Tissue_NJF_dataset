# Task: State Local Ridge Feature v1

## Goal

Test whether adding simple local `X_t` state statistics around the contact point explains coefficient evolution better than scalar depth/action/material/contact-distance features.

## Implemented Files

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/features.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/fitted.py
tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py
```

`features.py` provides:

```text
LocalPatchSpec
build_local_patch_spec
local_state_features
```

`R3_state_local_ridge` is added to the fitted diagnostic list.

## Feature Design

```text
patch: nearest K nodes to the contact point in X_0
K tested: 64 and 32
state: X_t - X_0 on local patch
features:
  mean displacement [3]
  inverse-distance weighted displacement [3]
  displacement norm mean/max/std
  z displacement mean/min/max
  xy displacement mean/max
  current patch distance mean/std
  change in patch distance mean/std
  patch covariance eigenvalues [3]
```

## Commands

Primary stable run:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py   --basis-dataset tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1   --rollout-datasets     tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_normal_3x3_v1     tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_oblique30_x_3x3_v1     tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1   --ranks 2 3 4   --ridge-alpha 100.0   --prefix-train-steps 5   --local-patch-size 64   --output tissue_dataset_v0/outputs/evaluations/fitted_coefficient_predictor_v1_state_local_alpha100
```

Sensitivity runs:

```text
fitted_coefficient_predictor_v1_state_local_alpha100_patch32
fitted_coefficient_predictor_v1_state_local_alpha1
fitted_coefficient_predictor_v1_state_local_alpha1e-2
```

## Results

Rank-4 final relative L2 means:

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

## Interpretation

```text
- R3 local-state statistics do not explain coefficient evolution better than R1 scalar ridge in the stable alpha=100 setting.
- K=32 is slightly better than K=64, but still worse than R1.
- Lower regularization makes R3 unstable and worse.
- The negative result is useful: future NJF representation design needs richer state/local-geometry information, not more hand-designed linear scalar statistics.
```

## Next Step

Do not continue adding scalar ridge features. Next choose between:

```text
1. shared/local-aligned basis diagnostic, if coefficient coordinate comparability must be clarified;
2. NJF representation planning for richer local state/contact encoding, leaving real model benchmark work for the later phantom/tissue stage.
```
