# ES3K → UD1K ROMS source-based horizontal/time/physical-z boundary remap PREVIEW

Date: 2026-10-15. Branch: `codex/es3k-i3-wet-domain-audit-20261014`, Draft [PR #3](https://github.com/RRain001/ROMS/pull/3); frozen original ES3K/UD1K, `main`, and actual GEBCO2026/GSHHG shoreline untouched.

## Purpose and physical context

Static geometry is verified independently on real 15″ data for candidate B: UD1K RHO 290×438, 96,104 ocean wet RHO cells in one 4-neighbor connected component, perimeter receivers **RHO=1,011 / U=1,005 / V=1,010**, zero missing parent static source stencils and zero GSHHG-crossing native child open wet faces. Real-grid sigma and synthetic 2D/3D normal-flux diagnostics for 1,012 normal wet faces also passed.

[Source-based preview engine](../Data_pre/nesting/ud1k_boundary_remap_preview.py) is a **distinct** numerical step beyond the previous NetCDF shape-only fixture. It reads 7 fields from the parent ROMS `ocean_time` history, independently audited RHO/U/V source-row maps and explicit child `h/angle/mask` geometry, and calculates `zeta,temp,salt,u,v,ubar,vbar` for each wet perimeter receiver and four ROMS side orientations.

Inputs are the **separate frozen 1,011-RHO candidate-B subset** of coast-clear scalar weights and the **independent** 1,005-U/1,010-V face-target source mapping. Never copy RHO source indices/weights into child U/V receivers.

## Actual numerical algorithm

1. **Strict ES3K source admission first:** `validate_parent_history(...,scan_values=True)`. Require actual wet parent source fields finite on all times and sigma levels, exact C-grid stagger/masks, chronological CF history times, matching depth physics metadata `Vtransform=2`/`Vstretching=4`, `h+zeta>0`. Explicit target times must be inside the source coverage in **source history native numeric ocean_time units**. No temporal extrapolation.
2. **Resolve one source frame:** For target time between two physical parent history frames, linearly interpolate source `zeta,temp,salt,u,v,ubar,vbar` fields on their native parent C-grid positions. Preserve frame endpoint fields exactly.
3. **Wet RHO `zeta` and tracers:** Interpolate `zeta` using approved coast-clear positive scalar weights. For each actual donor `(j,i)`, compute its own physical sigma `z_r` from **local parent h and zeta** (not sigma index matching). Interpolate the donor's `temp/salt` profile onto the **child receiver's physical sigma-z positions**, with explicit bottom/surface clamp counts, then combine the horizontal coast-clear donor weights. Thus vertical interpolation precedes horizontal mixing.
4. **Child native U/V velocity face receivers:** At every parent RHO donor in the independently audited child-face source map, use adjacent genuinely wet parent **native U faces and V faces**. Each parent native face uses its local half-RHO bathymetry and interpolated free surface to compute its own physical sigma-z profile, interpolated onto the child's **actual U/V face physical z** and averaged at that donor RHO position. Rotate parent grid U/V to geographic East/North using that donor's parent RHO `angle`; combine the coast-clear horizontal donor weights; rotate East/North to actual child face U or V using its local child angle, not simply geographic components.
5. **Barotropic consistency:** On child U/V wet face receiver, calculate full child `z_w`, positive `Hz` and derive `ubar/vbar = Σ(U/V_k * Hz_k)/ΣHz_k`; do not independently interpolate parent `ubar/vbar` as if they were the same vertically averaged quantities. Also explicitly compute `max_parent_native_barotropic_mismatch_mps` comparing each accessed parent native `ubar/vbar` and vertical average of their 3D source velocity. This source comparison is **diagnostic only** and is not automatically accepted as mass-flux conservation.
6. **Four complete sides:** Populate each `zeta,temp,salt,u,v,ubar,vbar` variable on ROMS correct RHO, U, V side length; build complete `{side:{field:array}}` dictionary. Dry perimeter positions currently have **internal finite placeholders** and must not be interpreted as physically valid ROMS water. Refuse a missing wet RHO/U/V receiver, duplicate or uncertified coast-clear source, dry/out-of-range donor, missing native face support, nonfinite sigma, missing history field, out-of-range timestamp or unsupported vertical coordinate formula.

Returned status: **`EXPERIMENTAL_NOT_PRODUCTION_BRY`**; no physical source normal transport matching, no tides/free-surface storage closure, no actual numerical ROMS run.

## Synthetic end-to-end tests, evidence and restrictions

[Tests](../Data_pre/tests/test_ud1k_boundary_remap_preview.py) construct **small synthetic ES3K history** with source U/V staggered arrays, complete CF ocean times, normal/rotated velocities, wet/dry masks and `N_parent=3`; a separate small child C-grid uses `N_child=4`. Cases include:
- Four-side field coverage and constant field invariance;
- parent `ocean_time` interpolation at 0/1,800/3,600 seconds;
- parent local rotation to East/North and independently rotated child local axes;
- recomputed child barotropic velocity and parent native 3D/2D discrepancy diagnostic;
- wet source missing values, wrong GSHHG certification, dry source donors, unavailable U/V face support, missing wet child face receiver, invalid requested time, invalid sigma metadata;
- one complete numerical end-to-end **synthetic source history → physical-z remap/rotation → all 28 synthetic ROMS bry variables saved in NetCDF → read back compare fields and CF timestamps**. It uses the fixture writer `ud1k_bry_schema_contract.py` with `workflow_status=SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS`, not a production writer.

CI: [Japan Sea UD1K ROMS History and BRY Schema Contract](https://github.com/RRain001/ROMS/actions/workflows/japan-sea-ud1k-bry-schema-contract.yml), fast Ubuntu unit tests; the parallel job reuses the **real candidate B grid** from the previously passed native Actions #38680030642 to validate the actual 290×438×41 NetCDF shape. Do not call the synthetic history generated by tests a simulated ES3K ROMS solution.

## Confirmed synthetic regression results

[**GitHub Actions #38687508257**](https://github.com/RRain001/ROMS/actions/runs/38687508257) completed **SUCCESS** in both jobs:

- **10** strict source-history contract tests PASS.
- **7** ROMS four-side/28-field NetCDF schema tests PASS.
- **15** experimental source-to-child interpolation tests PASS, including the full **synthetic ES3K history → source frame time interpolation → physical-z/parent native wet U/V components → child angle rotation → four-side field arrays → saved/reopened 28-variable synthetic NetCDF** test.
- The second CI job independently re-used the previously validated **actual native GEBCO2026/GSHHG UD1K candidate B** and rechecked 290×438×41/28-variable NetCDF dimensions. **No real ES3K hydrodynamic history was used.**
- `full_source_history_admission=PASS` applies to the small synthetic fixture only; `parent_native_barotropic_mismatch_acceptance=DIAGNOSTIC_ONLY`; `real_roms_bry_nc=NOT_RUN`; `actual_roms_model_integration=NOT_RUN`.

Total **32 tests PASS** in the source/scientific schema suite. All above field data are synthetic, **not model-forecast-derived ROMS boundaries**.

## Known blockers / next stages

- No actual time-dependent ES3K ROMS history from a run covering the UD1K target period. **No real parent zeta/temp/salt/u/v/ubar/vbar solution.**
- Source velocity reconstruction collocates actual native U and V wet-face samples at RHO donor positions; not a conservative face-to-face remap. Need independent **actual normal parent-child transport** and barotropic/free-surface volume checks using true ES3K history. Small coastal single-donor extrapolation remains an uncertainty.
- Current source frame interpolation loads entire parent time slices into memory. Future sustained simulation should stream chunks and time slices, cache native face projected depths/angles, and persist precomputed source stencil metadata.
- Source and target must use the same understood CF time basis; current preview target values are expressed in **parent `ocean_time` units**, with no calendar-conversion wrapper yet. Production pipeline must define epochs rigorously across source history, `bry_time` and child run config.
- Profile endpoint values clamp to the nearest parent valid depth. Counts of clamped sigma locations are provided; physical acceptability of extensive coastal bottom/surface clamping must be quantitatively reviewed.
- No tracer, density, turbulence closure, actual ROMS-compatible runtime `bry.nc`, dynamically tested open-boundary algorithm, or 1h/6h/24h/7d stability/normal-flux verification. `PHYSICAL_ONE_WAY_NESTING=HOLD`.

**Release rule:** no promotion of Option B as the user's formally active grid, no merge of PR #3 and no claim that the ocean/HTO nesting works until actual ES3K and UD1K physics acceptance is completed.
