# UD1K coastal boundary: physically justified, minimal mask alternatives

**Date:** 2026-10-15. **Scope:** read-only candidate comparison in Draft PR #3; `main`, original frozen `UD1K_GEBCO2026_GSHHG237_I3_CANDIDATE.nc`, `ud1k_candidate.json`, geographic extent and bathymetric values **unchanged**.

## Why the previous V-face "unresolvable waterway" was misleading

The sole previously unresolved native UD1K V wet boundary face `(eta_v=0, xi_v=30)` lies at **128.643305556 E / 34.970101852 N**. Original child RHO locations `(0,30)` and `(1,30)` are each wet, but both are in a **2-RHO-cell component disconnected from all other wet RHO cells by 4-neighbor C-grid connectivity**, not a connected part of the intended Japan Sea hydrodynamic ocean.

Native ES3K parent V face no-shoreline-crossing tests with 2.5, 3, 3.5, 4 and 5 ES3K cell radii all found **zero** qualified parent V donor faces; respectively **3, 7, 12, 16 and 30 nearby wet parent V faces** have blocked direct shoreline sight lines; see [native CI #38675153191](https://github.com/RRain001/ROMS/actions/runs/38675153191), SUCCESS. Merely extending the source search distance is unsafe.

Using the **original native GEBCO 2026 15″ / GSHHG 2.3.7 High** NetCDF, four-connected `mask_rho` has **7 disconnected wet components**:

| Component | Native wet RHO count | Selection |
|---|---:|---|
| Dominant Japan Sea continuous wet area | **96,107** | keep |
| Isolated wet pool | 12 | exclude from new comparison candidate only |
| Isolated wet pool | 3 | exclude |
| Isolated wet pool | **2** | exclude; equals RHO `(0,30)`, `(1,30)` |
| Three one-RHO isolated pools | 1+1+1 | exclude |
| **All original wet RHO** | **96,127** | no deletion in frozen original |
| **Core-only comparison RHO** | **96,107** | 20 disconnected wet cells removed **only from separate output** |

Because ROMS uses four-connected native wet U/V faces (not diagonal adjacency), retaining 20 truly disconnected RHO puddles as part of an **open ocean** simulation does not improve physical hydrodynamics. This is a stronger justification than masking wet grid points just because interpolation is difficult.

## Option A: keep only the 4-connected dominant ocean

[`ud1k_connected_core_candidate.py`](../Data_pre/nesting/ud1k_connected_core_candidate.py) writes a **distinct NetCDF** candidate `UD1K_CONNECTED_CORE_ONLY_COMPARISON_CANDIDATE.nc`. Source read-only, all original `h`, `pm`, `pn`, `lon_rho`, `lat_rho`, `angle` bytewise/numerically unchanged; only canonical `mask_rho`, `mask_u`, `mask_v`, `mask_psi` recomputed from the retained **largest 4-neighbor wet RHO component**. It fails closed if this user's grid shape, disconnected component totals or post-filter U/V perimeter sizes drift.

**Expected verified source-mask difference** based on original native 15″ grid:

| Wet C-grid points | Original | Core-only |
|---|---:|---:|
| All RHO wet | 96,127 | **96,107** |
| Wet perimeter RHO | 1,017 | **1,014** |
| Wet perimeter U | 1,010 | **1,009** |
| Wet perimeter V | 1,015 | **1,013** |
| V(0,30) missing parent donor | YES | **not a wet face** |

No GSHHG crossing real physical ocean channel is artificially added. Existing 1,017 RHO coastline-safe donor records can be filtered deterministically to the **remaining 1,014** RHO perimeter receivers. The native U/V target face mapping is **rerun** on the new candidate geometry, not inherited from RHO weights.

**Important:** Four original `mask_u/v=1` child wet-face RHO-segment GSHHG coastline crossings were previously found even in the dominant connected water. They remain risks under Option A, not removed automatically.

## Option B: additional minimal GSHHG-consistency repair at peripheral face crossings

[`ud1k_perimeter_shoreline_consistency_candidate.py`](../Data_pre/nesting/ud1k_perimeter_shoreline_consistency_candidate.py) accepts only the separately generated Option A as input and independently reads the **real GSHHG 2.3.7 L1 coastline crossing** report. It solves a small **minimum perimeter RHO vertex cover** for the four known crossing native U/V faces, with one hard condition: remaining dominant ocean must stay 4-connected. It cannot delete an interior RHO point, and does not touch bathymetry or the frozen original input.

Four parent target wet-face landline intersections:
- East boundary U `(eta_u=23,xi_u=436)`, source adjacent RHO `(23,436)`--`(23,437)`.
- South boundary V `(eta_v=0,xi_v=40)`, adjacent RHO `(0,40)`--`(1,40)`.
- South boundary V `(eta_v=0,xi_v=42)`, adjacent RHO `(0,42)`--`(1,42)`.
- East boundary V `(eta_v=23,xi_v=437)`, adjacent RHO `(23,437)`--`(24,437)`.

**Minimum boundary endpoints** (zero-based `eta_rho,xi_rho`): **`(0,40), (0,42), (23,437)`**. These three RHO cells in the **second separate candidate only** remove all four coastline-crossing wet-face connections while keeping one connected ocean. This is a constrained conservative coastal topology correction, not wholesale coastline simplification.

Expected native ocean sizes after Option B:

| C-grid wet geometry | Option A core-only | Option B core+shoreline |
|---|---:|---:|
| RHO wet total | 96,107 | **96,104** |
| RHO wet perimeter | 1,014 | **1,011** |
| U wet perimeter | 1,009 | **1,005** |
| V wet perimeter | 1,013 | **1,010** |
| GSHHG-crossing perimeter U/V wet segments | 1 U + 3 V | **0** |

Option B therefore changes **just 23 RHO wet cells from the original 96,127** (20 disconnected plus 3 coastal boundary endpoints) and leaves the geographical rectangular extent identical. This is a **static candidate**; its actual influence on normal transport, coastline topology, local currents and stability cannot be judged without numerical hydrodynamics.

## Explicit acceptance gates

1. GitHub Actions native-15″ run must reproduce Option A's component counts and *separately demonstrate* zero source donor holds on all **1,014 RHO / 1,009 U / 1,013 V** candidate wet perimeter points.
2. Option B must prove U/V still has no donor holds, all **1,011 RHO / 1,005 U / 1,010 V** wet perimeter points retain positive weights and none of the existing **four** GSHHG-crossing source-to-source segment flags remain; original and Option A unchanged.
3. Only after independent real coastline/detailed geography scrutiny should Option A/B be considered for hydrodynamic boundary. A negative source-donor condition MUST remain a **HOLD**; do not invent V=0 or source velocities across real land.
4. Add real source ROMS history time series, corresponding `zeta/temp/salt/u/v/ubar/vbar` one-way `bry.nc`, actual physical z remap and U/V normal-flux/volume checks. Run continuous hydrodynamic time integration (1h/6h/24h/7d) before any production decision. **NOT_RUN at time of this report.**

**Scientific interpretation:** Small disconnected near-coast puddles and a few locally inconsistent wet-face shore connectors are common artifacts of applying independent high-resolution coastline and bathymetry masks to grids with different spacings. A discrete wet-connectivity/topology-corrected mask is defensible *when the mask changes are explicitly audited*; silently overriding the source grid or hiding changed ocean boundaries is not.
