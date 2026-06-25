# Experiment Design

## Experiment 1: Minimal Tissue Pressing

- Single tissue patch.
- Single probe.
- Fixed camera.
- One contact location.
- One action magnitude.
- Record vertex displacement.
- Replay saved state.

Purpose: verify that simulation, logging, storage, and replay work end to end.

## Experiment 2: Contact-Location Variation

- Multiple contact locations.
- Same material.
- Same action magnitude.
- Compare displacement fields.

Purpose: test spatial generalization and ensure action/contact metadata is useful.

## Experiment 3: Action-Magnitude Variation

- Same contact location.
- Multiple action magnitudes.
- Check approximate local linearity.

Purpose: measure whether the local response can be approximated by a Jacobian-like map for small actions.

## Experiment 4: Material Variation

- Different Young's modulus values.
- Different Poisson ratio values, if supported.
- Check whether material parameters affect deformation response.

Purpose: determine whether material metadata is logged well enough for material-conditioned learning.

## Future Baseline Experiments

- Displacement-field prediction baseline.
- Action-conditioned dynamics baseline.
- NJF model baseline.

## Possible Evaluation Metrics

- Vertex displacement error.
- Endpoint error.
- Deformation field error.
- Local linearity residual.
- Generalization to unseen contact locations.
- Generalization to unseen material parameters.
- Visual comparison between predicted and ground-truth deformation.

## Current Practical Entry Point

Use the YAML config path first:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/generate_from_yaml.py tissue_dataset_v0/configs/slab_v0.yaml
```

Then verify replay:

```bash
env_isaacsim/bin/python tissue_dataset_v0/scripts/replay_sample.py   tissue_dataset_v0/outputs/yaml_slab_v0/sample_000001   --viewer summary   --stride 10
```
