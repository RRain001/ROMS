# Current UD1K: targeted 27-boundary-RHO coastal-stencil resolution

**2026-10-15, Draft PR #3, scientific scope: STATIC GEOMETRY/MAPPING ONLY.**

## Fixed decisions

- Keep the user-approved `ud1k_candidate.json` 290×438 RHO grid, exact `1/108°`, and the source GEBCO 2026 native-15″ + GSHHG 2.3.7 high coastline; do not move the perimeter or force any wet/dry cell changes to obtain 100% stencil count.
- Preserve the standalone `main` and draft Japan-Sea PR. Retain ES3K Japan-Sea connected wet-component filtering, no invented coast-spanning walls.
- The 27 problems arise among **1,017 actual current UD1K wet perimeter RHO points**; 990 had complete 4-wet ES3K-parent RHO quads in the initial *geometry* preflight, not yet a validated 3D hydrodynamic/ROMS boundary map.

## Verified three-tier handling of 27 original points

| Mode | Points | Interpretation / restrictions |
|---|---:|---|
| Enclosing strictly local parent 2×2 3-wet triangle | **5** | 3 nonnegative barycentric weights; GSHHG coastline-free geometry |
| Enclosing 4-neighbor wet-connected 3×3 3-wet triangle | **2** | GSHHG coastline-free; no dry parent RHO inside |
| Non-enclosing inverse-distance weighted 2–4 visible connected parent wet donors | **16** | **Extrapolation**, hard radius `2.5*median(ES3K physical cell size)`, no GSHHG coastline crossing |
| Non-enclosing nearest single visible parent wet donor | **4** | **One-point extrapolation**, highest scientific caution, no shoreline crossing and bounded range |
| No coastline-visible donor mapping found under the staged rules | **0** | **Does not** imply all coastal physics is solved |

**Final full 27-point mapping and numeric smoke CI:** [GitHub-hosted native 15″ run #38669015010](https://github.com/RRain001/ROMS/actions/runs/38669015010), **SUCCESS**. Published lightweight workflow artifact `ud1k-27-wet-boundary-mapping-small-json` (30-day retention) contains the full 27-point `ud1k_27_rho_wet_boundary_stencil_manifest.json`, both earlier triangle reports and the 20-point water-visible fallback; this must remain the canonical auditable numerical record. Exact counts **5/2/16/4**, all 27 source and receiver RHO nodes wet, all weights nonnegative and sum to one. Using parent GEBCO-smoothed `h`, all 27 sampled values finite and nonnegative; constant field worst absolute deviation **2.22×10⁻¹⁶**; additional leading time/sigma array sampling smoke PASS. Longest selected donor distance **6,579.463 m**. Physical time-series and `bry.nc` **NOT_RUN**.

**Four single-wet-donor special review cases (0-based child `eta_rho,xi_rho`):** `(0,27)` ~6,579 m; `(0,28)` ~4,831 m; `(0,30)` ~6,468 m along the **south** boundary, and `(23,437)` ~4,804 m on the **east** boundary. Maintain special caution in time-dependent normal-flux and T/S boundary comparisons before promoting these four; single donor sampling is extrapolation, not source-resolved 2D interpolation.

**Actual Actions evidence:** [7 triangle static candidates #38665674215](https://github.com/RRain001/ROMS/actions/runs/38665674215) and [all remaining 20 wet-visible donor candidates #38668506641](https://github.com/RRain001/ROMS/actions/runs/38668506641); both workflows **SUCCESS**, with GEBCO native 15″ and GSHHG 2.3.7 high L1. The 16/4 breakdown is real, not an assumed rate. The 4 one-donor cases are supported by a single visible wet donor within the defined radius; they are **not** an excuse to write zero, use dry parent nodes, or interpolate across coastlines.

### Static scalar RHO mapping interface

Independent script [ud1k_boundary_rho_fallback_map.py](../Data_pre/nesting/ud1k_boundary_rho_fallback_map.py) assembles all 27 original `eta_rho,xi_rho` receiver points using the three native JSON reports, retains `donor_eta_xi_zero_based` and weights, confirms source/receiver masks wet and weight sum = 1, and can apply to generic finite RHO scalar arrays with leading time/sigma dimensions. The manifest is not itself a `bry.nc` creator and **does not change** model input files. The full current and Kim-paper trial comparison remain separate.

### Why not simply remove "unimportant edge cells"?

A ROMS **wet open-boundary** point needs a defined `zeta,u/v,temp,salt` (and possibly tracer) forcing even if distant from the target nuclear station. Setting it land, supplying 0 or dropping the point changes boundary geometry and may cause spurious circulation. A safe, scientifically explicit, low-order coastal stencil with small spatial reach is preferable to an invisible mask repair.

### Requirements before promoting this map to production

1. **Expose real open-boundary flags:** distinguish open-water RHO perimeter from closed coasts in actual ROMS grid configuration. Never generate wet boundary forcing on segments not configured as open.
2. **Build parent scalar/vector and time interface:** 990 4-wet quads need coastline-safe checked weights too. Staggered U/V and `ubar/vbar` require correct physical-location remap and local ES3K-grid ↔ East/North ↔ UD1K-grid rotation; never simply apply RHO stencils to staggered velocities.
3. **Depth/temporal remapping:** interpolate at actual physical `z_r/z_w`, local `h+zeta`, correct barotropic depth averages, tides/time consistency and sigma layers. Apply candidate coastal fallback at every layer/time with explicit land and NaN gates.
4. **Mass/water budget:** compare inward/outward section-integrated normal volume flux (also salinity/heat), especially around the 4 single-donor source points. Construct monotonic edge-safe blending/limited transition into interior boundary sections if the produced fields show sharp jumps; do not assume pointwise source copy is physically sound.
5. **Hydrodynamic validation:** continuous ES3K and UD1K 1h / 6h / 24h / 7d and longer runs, `zeta`, currents, T/S, CFL and sea level; nearshore snapshot/mean transport diagnostics. Hydrodynamics acceptance remains **NOT_RUN**.

**Bottom line:** under the current GEBCO/GSHHG and static wet-only safety criteria, the 27 *source-availability* gaps have been mapped without changing any ocean/land cell or shifting the domain. That is a targeted preprocessor readiness result only, not a `ROMS` model completed/accepted result.
