# Japan Sea nested UD1K: parent CF time bridge, actual wet U/V support and wrap-safe child angle

**Date**: 2026-10-15. **Scope**: [Draft PR #3](https://github.com/RRain001/ROMS/pull/3), test-only, no production year required. Frozen real ES3K/UD1K grid coordinates, original user active grids, no-nesting `Data_pre` and `main` are not modified. The previously validated actual Option B 290×438 static geometry and RHO 1,011 / U 1,005 / V 1,010 real coastline-certified donor manifests remain **comparison-only**; actual time-dependent ES3K ROMS history is still **NOT AVAILABLE**.

## 1. CF time bridge: no accidental MJD-days-as-source-seconds

Previously, `prepare_boundary_preview` required the caller to provide raw child timestamps in native ES3K `ocean_time` numeric units. ROMS `bry_time` will often use MJD `days since 1858-11-17`, while the ES3K synthetic fixture or another real history can use `seconds since ...` or `hours since ...`. Feeding the same numeric axis values into both datasets is physically invalid.

[`ud1k_cf_time_bridge.py`](../Data_pre/nesting/ud1k_cf_time_bridge.py) now converts explicit **target CF times, units and calendar** to **source history CF numeric timestamps** by decoding actual calendar instants using `netCDF4.num2date` and re-encoding into parent units using `netCDF4.date2num`. Supported parent/target Gregorian aliases `standard`/`gregorian` are equivalent. Other CF calendars (including proleptic Gregorian) are supported only when the source and target calendars explicitly match; cross-calendar re-interpretation is prohibited.

- Source and target arrays must be finite, strictly increasing, and contain at least two timestamps.
- Target interval must be fully bracketed by ES3K history; no temporal extrapolation.
- Default maximum parent frame gap is **3 hours**, configurable with `max_parent_gap_hours`. It checks the entire supplied source time vector; a 4-hour gap is rejected under the default test gate. This is a preliminary test-only admission policy, not a claim about the future approved production output interval.
- The optional `target_time_units=None` compatibility path continues to interpret requested values as **source-native** numeric timestamps, but is explicitly labeled `SOURCE_NATIVE_CF_UNITS_NO_TARGET_CALENDAR_CONVERSION` and cannot silently masquerade as a converted MJD target.
- The report stores **both axes** `source_target_CF_time_bridge.bry_time_values` and `source_target_CF_time_bridge.parent_time_values`, as well as calendar, epochs, maximum source frame gap, target conversion status and `temporal_extrapolation=FORBIDDEN`.
- The 28-field synthetic-only NetCDF writer `ud1k_bry_schema_contract.py` now takes `time_calendar` explicitly and writes it into `bry_time.calendar` rather than hardcoding `gregorian`. It rejects invalid calendars before opening output.

**Numerical fixture**: a synthetic source history at 2025-01-01 00:00 and 01:00 stored as `0,3600` seconds from the source epoch; target 00:00/00:30/01:00 stored as `MJD` day values. The bridge returns `0,1800,3600` **source seconds** while preserving MJD numerical output values for `bry_time`; nonconstant `temp/u` source fields remap accordingly and successfully write/reopen an explicitly synthetic 28-field ROMS BRY NetCDF.

## 2. Independently validate actual parent-mask native U/V donor support at runtime

Earlier coast-clear U/V donor manifests include `native_parent_U_and_V_wet_face_support: true` source certification from the original I3 native GEBCO/GSHHG construction. This flag cannot replace checking the actual grid used with a future ES3K history.

The [existing experimental remapper](../Data_pre/nesting/ud1k_boundary_remap_preview.py) now runs `validate_source_donor_native_support` against the **actual supplied ES3K `mask_rho`**, for each distinct independently-mapped child U/V source donor RHO node. For **both** native C-grid source velocity components:

```
parent wet U neighbor at (j,i): (j,i-1) or (j,i), both adjacent parent RHO wet
parent wet V neighbor at (j,i): (j-1,i) or (j,i), both adjacent parent RHO wet
```

If *either* support set is empty for *any* listed parent RHO donor (including a zero-weight listed donor), source admission fails, despite a positive JSON coast-visibility flag. This check runs after the strict ES3K history/grid C-grid dimensional, wet-mask and full-wet-value audit. It independently validates topology against the **actual parent input**, not the old flag alone. The remapper also refuses invalid/nonbinary child masks, mismatched native U/V mask derivations, nonfinite bathymetry/angle and nonpositive wet child RHO depth.

**Important limit:** testing this logic on the small synthetic parent does **not independently certify original archived ES3K source donor wetness**, because the ~157MB original parent artifact was not downloaded here. Original GSHHG L1 line-intersection tests are not redone; report explicitly says `coastline_l1_intersection_recomputed=NOT_RUN_RELY_ON_GSHHG_MANIFEST`.

## 3. Correct wrap-around for native child U/V face angle

The prior child `_face_target` used `0.5*(angle_left+angle_right)`. This fails near angle ±π: RHO angles **+179° and −179°** were incorrectly averaged to 0° instead of the physical face direction 180°. This can reverse interpolated normal U/V components.

Native child face angle now uses a **circular mean**:

```
alpha_face = atan2( sin(alpha_a)+sin(alpha_b), cos(alpha_a)+cos(alpha_b) )
```

An exactly antipodal pair with no unique circular mean fails closed. Tests cover direct native U/V geometry and the full 3D rotated-source-to-child interpolation: actual geographic eastward u=+0.15 m/s and northward v=−0.05 m/s turn into child local **u=−0.15** and **v=+0.05 m/s** at wrapped ±179° face angles.

This correction is isolated to the preview remapper; the real Option B synthetic-only target normal-flux audit already used wrap-safe circular angles.

## Regression evidence and interpretation

Fast unit tests include the previous **85** independent contracts (real-option-B manifest synthetic guard tests, history, complete BRY schema, source-driven physical-z RHO/U/V, angle, native normal face 2D/3D integration, ERA5 and GLORYS/TPXO interfaces) and **20** added tests: 18 target time epoch/parent wet source U/V/angle checks plus 2 explicit CF calendar writer tests, **105 total** when all pass.

[`test_ud1k_cf_time_and_source_face_support.py`](../Data_pre/tests/test_ud1k_cf_time_and_source_face_support.py) covers source second/hour vs target MJD date equality, default 3h source history gap, calendar mismatch, target endpoint/monotonicity rejection, real child mask corruption, actual parent native wet V face lost despite accepted JSON flag, native U/V face angle +179°/−179° including full remapped velocity and antipodal failure.

[`test_ud1k_bry_schema_contract.py`](../Data_pre/tests/test_ud1k_bry_schema_contract.py) additionally verifies an explicitly requested `proleptic_gregorian` time calendar survives in the file, and invalid calendar is rejected.

The inexpensive GitHub-hosted CI workflow `.github/workflows/japan-sea-ud1k-bry-schema-contract.yml` runs the synthetic source/time/wet-mask unit suite without CDS secrets, network data downloads or ROMS model runs. Full archived real grid geometry/mapping jobs, prior 15/30-inch native GEBCO/GSHHG rebuilds and ROMS dynamics remain manual-only.

**Scientific/approval boundary:** neither actual ES3K time-dependent `his.nc` nor production UD1K `bry.nc` was generated. Even when a real parent file passes the admission, authoritative physical acceptance still needs ES3K source U/V time-series, source-to-target normal transport comparability, sea-level/free-surface storage, tidal phase and a real UD1K ROMS numerical run. `PHYSICAL_ONE_WAY_NESTING_READY=FALSE`, candidate B remains **COMPARISON ONLY**, PR remains **Draft**.
