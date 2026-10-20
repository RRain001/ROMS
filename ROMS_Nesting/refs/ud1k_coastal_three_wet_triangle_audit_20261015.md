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

## Native GEBCO/GSHHG real-data results: 2026-10-15

Both workflows **SUCCESS** on GitHub-hosted Ubuntu:

- [Run #38664676402](https://github.com/RRain001/ROMS/actions/runs/38664676402): exact 3-wet vertices of one ES3K 2×2 RHO quad, triangular barycentric containment + GSHHG L1 coastline: **5 / 27 static candidates**, other 22 unsupported by **that strictly local** stencil.
- [Run #38665674215](https://github.com/RRain001/ROMS/actions/runs/38665674215): among the remaining 22, a larger but still index-local 3×3 wet patch can furnish **2 further coastline-clear, wet-connected static triangles**. **9** have enclosing triangles but every eligible candidate intersects at least one GSHHG L1 coastline segment or contains a dry ES3K RHO point; **11** have no connected enclosing 3×3 donor triangle.
- Permanent machine-readable point-level audit including coordinates and all seven donor 0-based indices / barycentric weight triples: [ud1k_current_27_two_tier_triage_20261015.json](ud1k_current_27_two_tier_triage_20261015.json); unabridged native 15″ output JSON and grids are in the two run artifacts (14-day retention).

| Exclusive result | Count | What it does **not** prove |
| --- | ---: | --- |
| Same-quad exactly-three-wet, no GSHHG shoreline crossing | **5** | Not validated 3D physics |
| Wider locally connected 3×3, no GSHHG crossing and no enclosed dry RHO node | **2** | Not automatically superior to higher-order/conservative mapped BC |
| Parent 3×3 triangular geometry present but conflicts with GSHHG coastline or dry RHO node | **9** | Land/wet mask conflicts cannot be bypassed by naive interpolation |
| No wet-graph-connected enclosing 3×3 candidate | **11** | Does **not** establish unresolvable waterways without topology/circulation/geospatial review |
| **Total original boundary stencil gaps** | **27** | Neither the 20 residuals nor the 7 candidates should be called ROMS PASS/FAIL |

**Seven static candidate child coordinates (zero-based eta,xi)**: `(0,10)`, `(0,21)`, `(0,42)`, `(0,49)`, `(26,437)` using one-parent-quad triangles; and `(0,11)`, `(0,20)` using connected 3×3 wet donors. Remaining **20** are not solved by these two limited algorithms. In the nine land/shoreline-conflict cases, dry-cell containment and shoreline intersection counts are stored separately for each target in the JSON.

**Next scientific work**: for each unresolved region, inspect the native ES3K wet mask/GEBCO depth and true shoreline segments; determine whether the child is representing real wet water inaccessible to ES3K and whether a physically valid interpolation path exists. Do not force land or blindly expand interpolation to pass tests. Before any acceptance run full boundary RHO/U/V, local vector-angle conversion, sigma-z vertical transfers, free-surface/velocity consistency and net-normal-flux tests and then continuous ROMS dynamical regression.

**Scope protection:** Keep `main`, user `ud1k_candidate.json`, frozen config, reference paper trial and committed grids unchanged; Draft PR #3 only. No ROMS physics launched.
