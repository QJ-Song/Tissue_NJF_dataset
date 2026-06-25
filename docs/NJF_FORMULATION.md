# Neural Jacobian Field Formulation

## High-Level Idea

The long-term research goal is to learn a local action-to-motion response model for deformable tissue. Instead of directly predicting an entire deformation field from scratch, the model should represent how a small action perturbation affects each tissue point conditioned on the current state.

## Notation

```text
s_t: current state
a_t: action
x_i: tissue point or vertex
Delta a: small action perturbation
Delta x_i: displacement of tissue point i
J_theta(s_t, x_i): Neural Jacobian Field
```

Local response approximation:

```text
Delta x_i ~= J_theta(s_t, x_i) Delta a
```

Here `J_theta(s_t, x_i)` maps an action perturbation into the local motion response of tissue point `x_i`, conditioned on the current state.

## First-Stage Dataset Requirements

The first-stage dataset should prepare:

- state trajectories;
- action labels;
- tissue vertex trajectories;
- contact information;
- material parameters;
- camera observations;
- displacement labels.

The current `tissue_dataset_v0` module already records final vertex displacement labels and per-frame vertex states for toy pressing. Future Isaac Sim or SOFA backends should preserve the same conceptual fields.

## What Is Not Required Yet

The first-stage implementation does not need to solve the full NJF learning problem. It only needs to make the data pipeline reliable:

- stable scene/action/material configuration;
- synchronized logging;
- validated frame counts;
- replay from saved states;
- small debug datasets suitable for baseline experiments.

## Future Label Directions

Potential NJF-oriented labels include:

- per-point displacement under action perturbations;
- finite-difference response estimates from paired actions;
- local contact-conditioned action vectors;
- material-conditioned response fields;
- camera-space observations aligned with mesh-space labels.
