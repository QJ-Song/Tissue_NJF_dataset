# Task: Multi-Direction Coefficient Diagnostic Check

## Goal

Extend coefficient diagnostics v1 from a single `basis_v2/shear60_pos_x` rollout to a small multi-direction rollout set. This tests whether coefficient behavior is action-direction dependent.

## Datasets

Generated/used rollout datasets:

```text
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_normal_3x3_v1
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_oblique30_x_3x3_v1
tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_shear60_x_3x3_v1
```

Common design:

```text
contact_set: top_three
material_set: young_three
direction_set: basis_v2
trajectories: 9 per direction
steps: 10
step_size_mm: 1.17
total_displacement_mm: 11.7
```

Mode B basis dataset:

```text
tissue_dataset_v0/outputs/liver_surface_mode_b_factorial_3x3_basis_v2_v1
```

## Commands

Normal rollout generation:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_rollout.py   --overwrite   --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_normal_3x3_v1   --steps 10   --step-size-mm 1.17   --contact-set top_three   --material-set young_three   --direction-set basis_v2   --direction-id normal   --preload-steps 0   --action-substeps 40   --settle-steps-per-step 20
```

Oblique rollout generation:

```bash
scripts/run_sofa_python.sh scripts/generate_liver_surface_rollout.py   --overwrite   --output tissue_dataset_v0/outputs/liver_surface_mode_c_rollout_basis_v2_oblique30_x_3x3_v1   --steps 10   --step-size-mm 1.17   --contact-set top_three   --material-set young_three   --direction-set basis_v2   --direction-id oblique30_pos_x   --preload-steps 0   --action-substeps 40   --settle-steps-per-step 20
```

Validation/analysis run for each dataset:

```text
read_njf_dataset.py --require-mode rollout_trajectory --min-trajectories 9
analyze_rollout_trajectories.py DATASET --output DATASET/analysis/rollout_drift_summary.json
evaluate_coefficient_baseline.py --basis-dataset MODE_B --rollout-dataset DATASET --ranks 2 3 4 --trend-degree 1 --trend-train-steps 3 --output EVAL_DIR
```

Additional sensitivity check:

```text
evaluate_coefficient_baseline.py ... --trend-degree 1 --trend-train-steps 5
```

## Results

Read checks: PASS for `normal` and `oblique30_pos_x` with `9` trajectories each. Existing `shear60_pos_x` had already passed. Rollout trajectory analysis: PASS for all three directions. Contact was active for all `10/10` steps in all trajectories.

Rollout drift summary:

```text
direction        final_max_mean_mm  adjacent_cos_mean  adjacent_rel_change_mean  B0_final_rel_L2
normal           15.634             0.902345           0.403812                  0.417490
oblique30_pos_x  13.396             0.906898           0.441277                  0.680118
shear60_pos_x     7.277             0.877623           0.523788                  0.604011
```

Coefficient diagnostic final relative L2 mean:

```text
direction        B0_repeat  B1_oracle_rank4  B2_fixed_coeff_rank4  B3_linear3_rank4  B3_linear5_rank4
normal           0.417490   0.249987         0.417742              0.952569          0.780563
oblique30_pos_x  0.680118   0.379538         0.680483              1.066296          0.686794
shear60_pos_x    0.604011   0.252178         0.602582              0.829939          0.455366
```

## Interpretation

```text
- B1 rank4 consistently improves over B0 across all tested action directions.
- B2 stays almost equal to B0, so first-step coefficients are not stable enough for rollout.
- B3 simple depth trend is not robust. It helps shear60 with 5 prefix steps but fails on normal and barely helps oblique30.
- The result indicates that future NJF data and representation should preserve action direction, contact/material, and state/depth information.
```

## Next Step

Implement a first fitted coefficient diagnostic interface. It should explicitly encode action direction and group metadata, and it should report against B0/B1/B2/B3 as diagnostic references. Because per-group basis coordinates are not globally aligned yet, start with within-group or matched-basis diagnostics and avoid claiming cross-group coefficient generalization.
