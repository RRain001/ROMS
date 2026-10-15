# Japan Sea: real archived Option B donor manifests drive full synthetic ES3K history → UD1K BRY

Date: 2026-10-15. [Draft PR #3](https://github.com/RRain001/ROMS/pull/3). **Full real receiver map + artificial parent history integration PASS; physical one-way nesting NOT READY.**

## Exactly which inputs were real

**REAL** and unchanged: source from previously successful [GitHub Actions #38680030642](https://github.com/RRain001/ROMS/actions/runs/38680030642), ~2.3 MB artifact `ud1k-27-wet-boundary-mapping-small-json`:

- `UD1K_CONNECTED_CORE_SHORELINE_CLEAR_COMPARISON_CANDIDATE.nc`: actual GEBCO2026/GSHHG2.3.7 candidate **290×438**, **96,104 wet RHO**; **not the user's approved active UD1K grid**.
- `ud1k_core_shoreline_clear_1011_rho_map.json`: original certified coastline-visible source mapping for **1,011 RHO perimeter receivers**.
- `ud1k_core_shoreline_clear_native_uv_boundary_map.json`: independently generated native **1,005 U + 1,010 V** wet perimeter receiver maps with previously certified wet-parent-U-and-V-face source donor flags. Real original sources and coast-clear status were separately audited in the earlier full I3 run, not re-certified on actual source mask in this light stage.

**ARTIFICIAL / SYNTHETIC:** deliberately **all-wet 732×464 ES3K RHO grid**, built solely to exercise real donor indices; the source `h=2800 m`, `angle=0.12 rad`, artificial geographic coordinates and two ROMS-like source frames do **not represent the real ES3K hydrography, true source bathymetry, topology or shoreline**. This is not a real ES3K ROMS `his.nc`.

Synthetic parent at 2025-01-01 00:00 and 01:00, stored in seconds since 2025-01-01, parent `N=3, Vtransform=2,Vstretching=4`:

| Field | Source time 0 | Source time 3600 s |
| --- | ---: | ---: |
| zeta [m] | 0.2 | 0.4 |
| temp [°C] | 15 | 16 |
| salt [PSU] | 34 | 34.2 |
| native U / ubar [m s⁻¹] | 0.15 | 0.20 |
| native V / vbar [m s⁻¹] | −0.05 | −0.06 |

Each field is constant per artificial parent depth/location; real target depth, angle and `pm/pn` come from Option B. Every generated input filename and NetCDF title identifies the synthetic status. No weather/GLORYS real forcing files are downloaded, no ES3K/UD1K hydrodynamic integration is attempted, and no existing file is overwritten.

## Actual interface chain executed

[`ud1k_optionb_end_to_end_synthetic_parent.py`](../Data_pre/nesting/ud1k_optionb_end_to_end_synthetic_parent.py) does **not** replace the real remapper with mock interpolation. It calls the same established production-candidate **numerical preview** functions and actual NetCDF writer:

1. `validate_real_candidate_b()` loads the actual candidate B NetCDF and both original donor JSON files, rejects gaps/duplicate or invalid weights, verifies all native wet perimeter receivers and actual **382 south V + 364 north V + 0 west U + 266 east U = 1,012 normal wet faces**.
2. `make_explicitly_artificial_parent()` writes distinct *synthetic* full-size index-compatible C-grid/ROMS history files, 2 frames, 3 vertical levels, native staggering and complete CF vertical sigma metadata, no source-file overwrite.
3. `validate_parent_history(...scan_values=True)` applies strict source wet C-grid, wet time/layer, valid vertical state and CF time checks, but the parent is intentionally all-wet artificial geometry. Therefore passing is **not** true actual parent-mask verification.
4. `prepare_boundary_preview()` receives all real **1,011 RHO/1,005 U/1,010 V independent donor rows** and executes real weights, each donor's depth, native parent velocity collocation, source-angle→geographic→actual child local rotation, target vertical remap and Hz-weighted ubar/vbar. It bridges **target MJD days since 1858-11-17** to parent `0/3600` seconds in CF historical time. Each real target wet receiver is populated and validated.
5. The embedded real child native normal section audit integrates Q2D and Q3D for **1,012 normal wet faces × 2 frames = 2,024 face-time samples** using real `pm,pn,h,angle` child metrics. Only target-face numerical closure is asserted; real parent-child transport conservation is **NOT_RUN**.
6. `write_synthetic_schema_fixture()` stores **28 NetCDF fields on all 4 native sides** with `bry_time` in MJD days, target `N=4` sigma metadata and unmistakable global `SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS` warning. Reopens all 28 fields, checks wet values, NetCDF shape, source remap array equality, time units/calendar and both zeta frames.

Unlike prior independent source/geometry tests, **every actual Option B mapping receiver now traverses the real remapping numerical code in this one integration run**, but with fictitious all-wet parent hydrodynamics.

## Executed CI evidence

[**GitHub Actions #38699786571**](https://github.com/RRain001/ROMS/actions/runs/38699786571): both archived-Option-B interop job and fast synthetic job **SUCCESS**. Logs confirm:

`REAL_OPTIONB_ALL_DONORS_SYNTHETIC_SOURCE_BRY_PASS {"bry_fields":28,"normal_samples":2024,"physical_parent":"NOT_RUN","r_u_v":{"rho":1011,"u":1005,"v":1010}}`

`OPTION_B_REAL_STENCIL_SYNTHETIC_PARENT_2TIMES_28BRY_PASS`

Four additional small offline unit tests for explicit synthetic source C-grid staggering, parent history/vertical metadata admission, MJD dates and safety/overwrite protection passed. Previous **105 tests** retained: total **109** small tests PASS. Real archived integration uses archived small geometry/mappings only, no 157MB native ES3K parent artifact or heavy bathymetry.

The archive-based job is now **workflow_dispatch only**, due to transient artifact expiry and user instruction not to rerun full-grid validation on every code push. The routine small synthetic suite remains automatic. Reports are stored as a separate GitHub Actions artifact `real-optionb-archived-static-donor-report-only`; full synthetic parent files are not uploaded to avoid unnecessary artifact storage.

## Scientific limitations / next gate

- **Do not treat synthetic all-wet parent as original ES3K**; real parent GSHHG and wet native U/V donor support were certified only in the earlier original I3 full-source audit, not revalidated here.
- This test uses simple constant-with-depth/artificial parent time frames; nonconstant shear and 41-layer/3-time *real child geometry only* flux tests were previously passed separately. It does not test authentic source time-varying 3D currents.
- True ES3K hydrodynamic `his.nc` is not available. There is no physically verified **parent→child normal transport equality**, dynamic free-surface storage, tides, output interval/calendar acceptance for actual run, or real UD1K integration.
- `Option B` remains **comparison candidate**. No production date selected, no modifications to frozen official grid, active masks, primary `Data_pre`, parent ES3K model or `main`. PR #3 stays Draft.

**Status:** `REAL_OPTIONB_DONORS_FULL_SYNTHETIC_SOURCE_TO_BRY_PASS` / `PHYSICAL_ONE_WAY_NESTING_READY=FALSE`.
