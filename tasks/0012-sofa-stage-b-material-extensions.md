# Task: SOFA Stage B Material Extensions

## Goal

Plan extensions to Stage B material randomization. Current Stage B randomizes one homogeneous isotropic material per sample. Future extensions should support spatially varying tissue properties and, later, anisotropic tissue properties while preserving compatibility with the current dataset schema, manifest-driven loader, and sanity checks.

## Current Stage B Baseline

Current `sofa_liver_stage_b.yaml` uses sample-level homogeneous isotropic material:

```text
youngs_modulus: scalar per sample
poisson_ratio: scalar per sample
density: scalar per sample
damping: scalar per sample
boundary_condition: scalar/string per sample
```

The whole tissue uses the same material values for a generated sample. This should remain as a baseline and regression config. Do not overwrite or remove it.

## Motivation

Real soft tissue is not perfectly homogeneous. Liver-like tissue may have:

- regional stiffness variation;
- local softer/stiffer zones;
- vessel/pathology-related material changes;
- surface/deep-layer differences;
- direction-dependent behavior caused by fibers, membranes, or structural constraints.

For learning action-conditioned deformation, material heterogeneity may be important because the same action can produce different responses depending on where and how tissue properties vary.

## Recommended Staging

### B1: Homogeneous Isotropic Material

This is the current Stage B. Keep it unchanged. It is useful for baseline comparisons and for testing whether sample-level material parameters affect deformation.

### B2: Spatially Varying Isotropic Material

Do this before anisotropy. The material is still isotropic at each location, but parameters vary spatially in a controlled way.

Possible approaches:

1. Low-frequency field:

```text
E(x) = E_base * field(x)
field(x) in [0.7, 1.3]
```

2. Ellipsoid/region patches:

```text
region_0: stiffer lobe
region_1: softer local area
```

Randomized B2 parameters could include:

- base Young's modulus;
- heterogeneity amplitude;
- region count;
- region center;
- region radius;
- stiffness multiplier;
- damping variation.

Avoid early randomization of:

- Poisson ratio spatial fields, because near-incompressible values may cause numerical issues;
- density spatial fields, because short-term value is limited;
- high-frequency noise fields, because they may be numerically unstable or physically unrealistic.

### B3: Anisotropic Material

Do this only after B2 is stable and after confirming SOFA support. Anisotropy requires a constitutive model, material frame/fiber direction, and validation of direction-dependent response.

Potential fields:

```text
fiber_direction.npy       # [N, 3] or [elements, 3]
anisotropy_ratio.npy      # scalar, per vertex, or per element
material_anisotropy.json
```

Start with a simple fixed global fiber direction or small set of directions before randomizing a spatial direction field.

## SOFA Feasibility Questions

Before implementing B2/B3, inspect the installed SOFA components and examples for support of:

- per-element Young's modulus or material parameters;
- multiple FEM force fields over disjoint ROIs;
- mesh/element region IDs;
- anisotropic FEM force fields or plugins;
- stable headless use of these components in SofaPython3.

Do not assume per-element material is easy in the current `TetrahedronFEMForceField`. If SOFA support is limited, prototype first before changing the dataset pipeline.

## Dataset Field Strategy

Keep current scalar `material.json` compatible. Add optional fields only when physically used or clearly needed.

Recommended B2 additions:

```text
material_region_ids.npy       # optional, [N] or [elements]
material_youngs_modulus.npy   # optional, [N] or [elements]
material_damping.npy          # optional, [N] or [elements]
```

Recommended `material.json` extension:

```json
{
  "youngs_modulus": 5000.0,
  "poisson_ratio": 0.45,
  "density": 1000.0,
  "damping": 0.5,
  "heterogeneity": {
    "type": "ellipsoid_regions",
    "seed": 123,
    "base_youngs_modulus": 5000.0,
    "scale_range": [0.7, 1.3],
    "region_count": 2
  }
}
```

Recommended B3 additions:

```text
fiber_direction.npy
anisotropy_ratio.npy
material_anisotropy.json
```

All of these should be optional manifest-declared artifacts. Do not make them required for Stage A/B/C or old data.

## Loader / Validator Compatibility

The manifest-driven `TissueSampleDataset` can read optional material fields if they are present. No loader redesign should be needed for basic loading.

Default validator should not require B2/B3 fields. Add either:

- optional validation rules; or
- a dedicated material-field sanity script.

Potential checks:

- material field shape matches vertices or elements;
- no NaN/Inf;
- values are within configured range;
- region IDs are integer and valid;
- at least two regions or nonzero field variation when heterogeneity is enabled;
- anisotropy directions are unit length;
- anisotropy ratios are within configured bounds.

## Suggested Config Names

Do not modify `sofa_liver_stage_b.yaml` in-place. Add new configs:

```text
tissue_dataset_v0/configs/sofa_liver_stage_b2_heterogeneous.yaml
tissue_dataset_v0/configs/sofa_liver_stage_b3_anisotropic.yaml
```

## Implementation Order

1. Create a SOFA/material feasibility spike: inspect whether current SOFA components can support per-region or per-element material values.
2. If feasible, implement B2 spatially varying isotropic material in a small prototype or backend mode.
3. Add optional material field artifacts and manifest entries only when those fields are actually produced.
4. Add material-field sanity checks.
5. Generate a small B2 dataset and validate with existing validator, material sanity, and dataset reader.
6. Defer B3 anisotropy until B2 is stable and SOFA support is understood.

## Acceptance Criteria for B2

- Homogeneous Stage B remains unchanged and still passes existing checks.
- B2 config generates at least 5 samples.
- Material heterogeneity is present and bounded.
- Generated samples pass `validate_sample.py`.
- Material sanity check passes.
- `read_dataset_smoke.py` can read optional material fields.
- If optional material arrays are present, their shapes are documented as vertex-based or element-based.

## Open Questions

- Does the installed SOFA package support per-element material parameters for the FEM force field currently used?
- If not, is multiple ROI force fields a practical approximation?
- Should B2 material fields be vertex-based or tetra-element-based? FEM material is naturally element-based, but current saved geometry is vertex/surface oriented.
- Should material heterogeneity be physically used immediately, or merely recorded? Prefer physically used; recording unused random fields is not a strong mainline dataset.
- What is the smallest sanity check that demonstrates material heterogeneity changes response in a controlled way?
