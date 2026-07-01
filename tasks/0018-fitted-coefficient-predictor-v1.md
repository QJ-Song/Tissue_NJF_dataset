# Task: Fitted Coefficient Diagnostic v1

## Goal

Implement a first NumPy ridge fitted diagnostic for Mode B basis coefficients on Mode C rollout data. The purpose is to determine whether simple engineered features explain coefficients before designing NJF state/contact representations.

## Implemented Files

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/fitted.py
tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py
```

`FittedCoefficientConfig` and `evaluate_fitted_coefficient_predictor` are exported from `tissue_dataset_v0.njf`.

## Diagnostic Variants

```text
R1_non_autoregressive:
  step/depth/action direction/action magnitude/material/contact-distance/contact-status features.

R2_autoregressive:
  R1 features plus previous coefficient vector and previous coefficient norm.
  Test rollout uses recursive predicted coefficients after the first test step.
```

## Splits

```text
prefix_per_trajectory:
  fit first 5 steps of each trajectory and predict remaining 5 steps.

heldout_direction_within_group:
  train within the same contact/material/basis group on two directions and test the held-out direction.
  This avoids mixing coefficient coordinates across different Mode B groups.
```

## Primary Command

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/evaluate_fitted_coefficient_predictor.py   --basis-dataset tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1   --rollout-datasets     tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_normal_3x3_v1     tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_oblique30_x_3x3_v1     tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1   --ranks 2 3 4   --ridge-alpha 1e-4   --prefix-train-steps 5   --output tissue_dataset_v0/outputs/evaluations/fitted_coefficient_predictor_v1_basis_v2_3dir
```

Sensitivity runs:

```text
tissue_dataset_v0/outputs/evaluations/fitted_coefficient_predictor_v1_basis_v2_3dir_alpha1e-2
tissue_dataset_v0/outputs/evaluations/fitted_coefficient_predictor_v1_basis_v2_3dir_alpha1
tissue_dataset_v0/outputs/evaluations/fitted_coefficient_predictor_v1_basis_v2_3dir_alpha100
```

## Results

Reference diagnostics averaged across `normal`, `oblique30_pos_x`, and `shear60_pos_x`:

```text
B0 repeat first response final relative L2 mean=0.567206
B1 oracle basis projection rank4 final relative L2 mean=0.293901
B2 fixed first coefficient rank4 final relative L2 mean=0.566936
B3 linear 5-step trend rank4 final relative L2 mean=0.640908
```

Rank-4 fitted ridge final relative L2 means:

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

## Interpretation

```text
- Low-regularization linear ridge is unstable, especially recursive R2.
- Strong regularization stabilizes the fitted diagnostic but it still does not explain coefficients as well as the B1 expression reference.
- Previous-coefficient recursion does not help in this simple linear form.
- The useful signal is still the B1 gap: the basis can express rollout responses, but coefficient prediction needs richer state/local-geometry features or nonlinear modeling.
```

## NJF Implication

The next NJF-related step should not be another scalar/depth-only linear regressor. The useful conclusion is that state/contact/material/action information is required and that hand-designed scalar features are insufficient. A shared-basis or local-alignment diagnostic is only needed if the project needs to reason about cross-group coefficient-coordinate comparability.
