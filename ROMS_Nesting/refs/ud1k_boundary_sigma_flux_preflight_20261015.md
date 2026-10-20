# UD1K candidate B ROMS C-grid sigma and normal-flux numerical preflight

**Date:** 2026-10-15. **Evidence:** [native GEBCO/GSHHG Actions #38680030642](https://github.com/RRain001/ROMS/actions/runs/38680030642), conclusion **SUCCESS**. Linked artifacts `ud1k-27-wet-boundary-mapping-small-json` (30-day retention) contain both filtered UD1K NetCDF candidates, full RHO/U/V geometry audit and the numerical JSON `ud1k_core_shoreline_clear_sigma_normal_flux_smoke.json`.

## Scope

Use the **separate** `UD1K_CONNECTED_CORE_SHORELINE_CLEAR_COMPARISON_CANDIDATE.nc`, derived from original native GEBCO2026 15″ + GSHHG 2.3.7 High Level1, with unchanged 290×438 RHO geometry, no revised coastline or bathymetry array, 96,104 RHO wet cells in one connected component. Perimeter static source mapping: 1,011 RHO, 1,005 U and 1,010 V receivers, **zero** unsupported wet U/V face points and **zero** detected GSHHG shoreline intersections between connected adjacent RHO centers. Original frozen candidate **unchanged**, no PR merge.

## Real source grid geometry checked with explicit synthetic velocities

[`ud1k_boundary_vertical_flux_geometry_smoke.py`](../Data_pre/nesting/ud1k_boundary_vertical_flux_geometry_smoke.py) uses actual ROMS native `h,pm,pn,mask_u,mask_v`; local U face water depth `h_u=(h_L+h_R)/2`, local V `h_v=(h_S+h_N)/2`; true metric water widths are `1/pn` at U faces and `1/pm` at V faces, interpolated from adjacent RHO metrics. Only **normal** open-boundary faces enter net horizontal transport (south/north V; west/east U). Tangential U on south/north and V on west/east are not counted as normal transport.

| Normal boundary | Native wet face points | Outward sign |
| --- | ---: | ---: |
| South V | **382** | -1 |
| North V | **364** | +1 |
| West U | **0** | -1 |
| East U | **266** | +1 |
| **Total native normal wet open boundary faces** | **1,012** | |

Synthetic `zeta=0`, `Vtransform=2`, `Vstretching=4`, `N=41`, `hc=50m`, `theta_s=5`, `theta_b=1`. **These are explicitly numerical diagnostic settings; they DO NOT establish the user-approved production physics vertical configuration**, which remains to be frozen when actual ES3K and UD1K run configs are finalized.

Checks:
- Sigma `z_w` bottom `-h`, surface `zeta`, `z_r` strictly inside successive interfaces, layer `Hz>0`, all layers sum back to physical water column depth within tolerance.
- Synthetic depth-varying velocity at actual normal faces: `ubar/vbar = sum(velocity_k * Hz_k)/sum(Hz_k)`; check independently calculated 3D layer-integrated normal transport against 2D depth-mean volume transport at each side, using actual face width and outward sign. Max absolute reported side difference **7.450580596923828e-09 m³/s** (north; other sides zero at display precision). PASS.
- Independent synthetic `N=30` parent-column sigma-z sampled onto `N=41` child-column physical depths: a constant field is preserved; out-of-range depth targets are counted explicitly rather than extrapolated silently.
- These checks cover **real shape, local depth and horizontal metric arrays**, but **not** true source history, true external time-dependent mass conservation or nontrivial ROMS boundary relaxation scheme. `zeta,temp,salt,u,v,ubar,vbar` actual `bry.nc` **NOT_RUN**.

## Real physical boundary integration remaining

1. Produce or retrieve a real, time-dependent **ES3K ROMS solution** with consistent `zeta,temp,salt,u,v,ubar,vbar` arrays and actual physics metadata. Validate time axes, free-surface, native U/V angle, parent/child sigma depths and wet source masks.
2. Use existing coastline-safe 1,011 RHO scalar stencils and independent actual 1,005 U/1,010 V face receiver stencils to remap source velocity vectors, rotate local source East/North to local child U/V, and perform **physical-z remapping** with appropriate endpoint policy. Ensure parent/source face component support from actual ROMS fields.
3. Integrate 3D velocity layer thicknesses to the boundary normal flux per side, compare source and target normal flow and barotropic components. Account for local ocean volume storage and tides; **do not artificially impose zero global flux** in place of valid dynamic `zeta`.
4. Write ROMS-compliant `bry.nc` with correct time variable(s), dimensions, attributes and all required boundary sections, and run contiguous 1h→6h→24h→7d hydrodynamics stability / transport regression. This final physics stage is **NOT_RUN**.

**Status:** `STATIC_CGRID_COASTAL_TOPOLOGY_READY_AND_SYNTHETIC_SIGMA_FLUX_NUMERICS_PASS`; **not** `PRODUCTION_ONE_WAY_NESTING_ACCEPTED`.
