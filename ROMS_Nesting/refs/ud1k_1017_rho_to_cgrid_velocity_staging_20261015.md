# UD1K complete ES3K→UD1K wet RHO-boundary mapping staging (2026-10-15)

## Frozen configuration

Current user-approved UD1K **290×438** 1/108° axis-aligned RHO grid, wet domain from native GEBCO 2026 15″ + GSHHG 2.3.7 **High** L1 and connected parent ES3K smoothed real bathymetry. Main branch, active `ud1k_candidate.json` extents, GEBCO/GSHHG masks and ocean connectivity **unchanged**. Keep this Draft PR #3 independent from Kim-2020 Table 1 range.

## Completed native GEBCO/GSHHG read-only evidence

- Original 1,017 wet UD1K RHO perimeter points: **990** geometrically enclosed by full four-wet-parent RHO quads, **27** coastal original quad gaps.
- [Native CI #38670055721](https://github.com/RRain001/ROMS/actions/runs/38670055721) **SUCCESS** for [`ud1k_full_rho_boundary_map.py`](../Data_pre/nesting/ud1k_full_rho_boundary_map.py): all 1,017 points mapped to 990 actual inverse-bilinear projected four-vertex donor stencils + 27 previous coastline-checked wet fallback stencils, with real parent depth sampling. Constant-field maximum error **2.22e−16**. **Important**: 9 of the initial 990 all-wet quads intersect GSHHG Level-1 coastline linework, so four wet vertices do **not** guarantee safe interpolation.
- [Native CI #38670675198](https://github.com/RRain001/ROMS/actions/runs/38670675198) **SUCCESS** for [`ud1k_full_rho_coastline_repair.py`](../Data_pre/nesting/ud1k_full_rho_coastline_repair.py): all **9/9** previously crossing all-wet quads have a target-enclosing, coastline-clear **three-of-four-wet triangle within the same parent quad**. No larger-radius extrapolation was needed for these 9. Nine zero-based child points are `(0,43)`, `(0,44)`, `(0,45)`, `(0,66)`, `(0,67)`, `(0,68)`, `(0,69)`, `(0,403)`, `(0,404)`. After substitution, **1017/1017** RHO receivers have coastline-visible wet donor geometry.
- Parent native C-grid U/V **face availability** is separate: initial source RHO map had **7 receiver positions with at least one donor not collocatable in both U and V**, all child-south-side `(0,9)–(0,15)`, and two offending parent RHO donor centers `(46,259)` and `(46,261)` lack native U wet-face support. [Native CI #38670675198](https://github.com/RRain001/ROMS/actions/runs/38670675198) recorded this evidence on the **pre-coast-repair** full RHO source; the revised source must still be separately audited and, if required, repaired.

## Explicit vector-only remap controls

[`ud1k_boundary_cgrid_velocity.py`](../Data_pre/nesting/ud1k_boundary_cgrid_velocity.py) reconstructs native parent U/V at each chosen parent RHO source using adjacent **wet** native face(s) only, applies local ES3K `angle` pointwise to East/North, uses donor RHO weights, then rotates to **child RHO** native angle. It rejects nonfinite wet faces and missing components rather than inventing zero currents.

New helper `vector_face_supported_stencils` excludes any positive-weight parent RHO donor lacking either native U or V face, then **renormalizes only the separate vector-RHO weights** among remaining coastline-visible qualified donors. Fewer than two remaining sources for an adjusted receiver yields explicit HOLD, not nearest-wet cover-up. Existing scalar RHO `zeta/temp/salt` weights **remain untouched**. This applies to RHO diagnostics only, not child staggered U/V edges.

## Next gates (physical acceptance remains NOT_RUN)

1. Confirm native real-data vector-only remap supports all 1,017 RHO receivers after excluding unsupported donor(s), with report of sites, weights and numerical local-angle smoke, and no scalar mask/weight changes.
2. Construct **independent** coastal-aware donor mappings at actual child U- and V-face locations and source native face grids; do not mistake the RHO vector collocation map for physical boundary `u,v,ubar,vbar`.
3. Transform source time-varying velocity and free surface to geographic frame, interpolate parent sigma in **physical z** to child sigma, close U/V depth averages with ubar/vbar and test section-integrated **normal volume flux**.
4. Only with a genuine ES3K ROMS history or climatology available, generate real `zeta/temp/salt/u/v/ubar/vbar` `bry.nc` and test 1h, 6h, 24h and longer UD1K hydrodynamic integrations. **Such a parent dynamic dataset has not been produced or supplied by these GEBCO/GSHHG static workflows.**

**Risk:** a coastline-clear wet donor *geometry* and positive weights do not prove hydrodynamic accuracy. Four old single-wet-donor scalar extrapolations and other nearshore fallback sites need specific continuity/volume-transport review before promotion.
