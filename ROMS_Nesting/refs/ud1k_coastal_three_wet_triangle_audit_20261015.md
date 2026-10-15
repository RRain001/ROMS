# Current UD1K coastal 27-point wet triangle feasibility audit

## Motivation

Current user-approved 1/108° UD1K domain (freeze `ROMS_Nesting/configs/ud1k_user_20261014_frozen.json`) has 1,017 wet perimeter RHO points. In the real GEBCO 2026 native 15″ / GSHHG 2.3.7 high Level 1 stage, 27 have no **complete four-wet-vertex ES3K RHO quadrilateral**. This does **not** mean each has no physically valid nearshore interpolation.

## Controlled algorithm (strict but not exhaustive)

[ud1k_wet_triangle_review.py](../Data_pre/nesting/ud1k_wet_triangle_review.py) and [CLI](../Data_pre/scripts/nesting/review_ud1k_wet_triangles.py) apply the following conditions **only to the original 27**, never overwriting any grid:

1. Use the existing connected, smoothed, independently projected ES3K RHO grid and exact user UD1K wet perimeter points from the same native 15″ CI preflight JSON.
2. Restrict the donor triangle to **three wet vertices of one logically adjacent parent 2×2 RHO quadrilateral**, never unconstrained 3-nearest wet points across a bay/peninsula. With exactly one dry parent vertex, the other three are connected through two shared wet RHO edges inside that quad.
3. Require a nondegenerate triangle containing the child target in projected metres; weights are computed by linear barycentric inversion, sum to one and must all be nonnegative.
4. Inspect GSHHG 2.3.7 **high L1 polygon coastline linework**. Reject any triangle touching/intersecting this coastline (conservative), even if the parent vertices themselves are wet according to GEBCO and GSHHG.
5. Choose the closest max-distance among coastline-clear triangles, and preserve full donor `(eta_rho,xi_rho)` indexes, geographic coordinates, three weights, nearest distances, rejection counts and each child coordinate in JSON.

### Exactly three exclusive geometric categories

- `COASTLINE_CLEAR_LOCAL_TRIANGLE_STATIC_CANDIDATE`: a GSHHG-clear, enclosing 3-wet triangular donor stencil **exists**. No ROMS physical acceptance is claimed.
- `ENCLS_THREE_WET_TRIANGLE_BUT_CROSSES_GSHHG_L1_COAST`: enclosing 3-wet triangle geometry exists but GSHHG coastline intersects every such candidate; **do not interpolate across land**.
- `NO_ENCLOSING_LOCAL_THREE_WET_PARENT_RHO_TRIANGLE`: this **limited local-stencil family** contains no triangle including the target. Not proof the parent cannot represent the waterway; inspect accurate shoreline/wet topology, alternatives with explicit connectivity, and optional carefully justified local domain adjustment.

**Important distinction:** The earlier four-wet quad preliminary cover check does not itself test GSHHG coastline. The new restricted triangular test is an optional read-only audit, *not* a drop-in replacement for actual ROMS one-way `bry.nc` interpolation. Real open boundary conditions must still verify RHO scalars and staggered U/V, local grid-angle rotation, sigma ↔ physical-z remapping, tidal/time axes, volume/salt transport and mass conservation. If a donor quad/triangle bridges an actual narrow land barrier, it must not be accepted merely because its vertices are wet. The land test here uses the available GSHHG L1 coastline; finer coastline and true wet-channel topology need further independent analysis.

### Evidence and CI

- [GitHub native 15″ GEBCO / GSHHG workflow](../../.github/workflows/japan-sea-es3k-online-native.yml).
- [Synthetic regression tests](../Data_pre/tests/test_ud1k_wet_triangle_review.py): triangle containment, non-extrapolation, separated wet nodes, shoreline intersection, degeneracy.
- Native results written to workflow artifact `ud1k_current_27_coastal_triangle_review.json`. This document must be updated with *actual CI counts* and permanent per-point evidence before any acceptance decision. No inferred or synthetic counts are scientific outcomes.

**Scope protection:** Keep `main`, user `ud1k_candidate.json`, frozen config, reference paper trial and committed grids unchanged; Draft PR #3 only. No ROMS physics launched.
