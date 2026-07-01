# Task: Coefficient Diagnostics v1

## Goal

Implement and run the first lightweight mechanism diagnostic layer above the controlled SOFA datasets. The experiment should answer what NJF-style formulation and data collection need to capture, not prove NJF superiority.

## Implemented Files

```text
tissue_dataset_v0/src/tissue_dataset_v0/njf/basis.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/metrics.py
tissue_dataset_v0/src/tissue_dataset_v0/njf/baselines.py
tissue_dataset_v0/scripts/evaluate_coefficient_baseline.py
docs/NJF_MECHANISM_DIAGNOSTICS.md
```

`__init__.py` also exports `CoefficientBaselineConfig` and `evaluate_coefficient_baselines`.

## Diagnostic References

```text
B0_repeat_first_response:
  repeat the first rollout step response.

B1_oracle_basis_projection:
  project each true rollout response into the matched Mode B basis.
  This is an expression upper bound, not a prediction model.

B2_fixed_first_coefficient:
  compute the first-step coefficients and reuse them for all rollout steps.

B3_prefix_depth_trend_coefficient:
  fit early-step coefficients as a polynomial of cumulative depth and extrapolate.
```

## Primary Experiment

Command:

```bash
scripts/run_sofa_python.sh tissue_dataset_v0/scripts/evaluate_coefficient_baseline.py \
  --basis-dataset tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1 \
  --rollout-dataset tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1 \
  --ranks 2 3 4 \
  --trend-degree 1 \
  --trend-train-steps 3 \
  --output tissue_dataset_v0/outputs/evaluations/coefficient_baseline_v1_basis_v2_shear60
```

Result: PASS. `9` trajectories, `90` diagnostic/rank trajectory results, `0` errors.

Primary metrics:

```text
B0 final relative L2 mean=0.604011
B1 rank4 final relative L2 mean=0.252178
B2 rank4 final relative L2 mean=0.602582
B3 rank4 final relative L2 mean=0.829939
```

## Sensitivity Checks

Linear trend fit on first 5 steps:

```text
output: tissue_dataset_v0/outputs/evaluations/coefficient_baseline_v1_basis_v2_shear60_train5
B3 rank2 final relative L2 mean=0.470512
B3 rank3 final relative L2 mean=0.478617
B3 rank4 final relative L2 mean=0.455366
```

Quadratic trend fit on first 5 steps:

```text
output: tissue_dataset_v0/outputs/evaluations/coefficient_baseline_v1_basis_v2_shear60_train5_quad
B3 rank2 final relative L2 mean=0.596354
B3 rank3 final relative L2 mean=0.751517
B3 rank4 final relative L2 mean=0.840647
```

## Interpretation

```text
- B1 << B0: Mode B basis can express a significant part of rollout responses.
- B2 ~= B0: first-step coefficients are not stable through rollout.
- B3 is sensitive and can be worse than B0: coefficient evolution is not captured by a simple depth trend.
- More informative state/contact/material/action-conditioned coefficient prediction is the correct next modeling target.
```

## Limitations

- B3 currently fits a prefix within each trajectory, so it is a diagnostic, not a generalization result.
- Current rollout data only covers `basis_v2/shear60_pos_x`.
- Cross-group coefficient prediction is not well-defined until basis coordinates are aligned or shared-basis/local-alignment logic is added.

## Next Step

Generate a small multi-direction `basis_v2` rollout set, for example `normal`, `oblique30_pos_x`, and `shear60_pos_x`, then rerun coefficient diagnostics. This shows whether coefficient behavior is action-direction dependent before deciding what information a future NJF representation must encode.
