# Japan Sea offline end-to-end tests of five existing ROMS forcing converters

**Date:** 2026-10-15. **Working PR:** [#3](https://github.com/RRain001/ROMS/pull/3), Draft, base `feature/japan-sea-nesting`. **Status:** `SYNTHETIC_EXTERNAL_FORCING_CONVERTERS_PASS`, `REAL_ES3K_HISTORY_NOT_RUN`, `TRUE_UD1K_HYDRODYNAMICS_NOT_RUN`.

## What was executed

The previous staged external-source contract only inspected small staged GLORYS12V1, ERA5 and TPXO NetCDF files. The new [`test_japan_sea_forcing_converter_micro.py`](../Data_pre/tests/test_japan_sea_forcing_converter_micro.py) now executes `main()` from **five existing real preprocessing implementations**, not substitute interpolation functions:

- [`create_ocean_ini_from_glorys.py`](../Data_pre/impl/preprocessing/create_ocean_ini_from_glorys.py): staged GLORYS `thetao/so/uo/vo/zos` -> actual file writing for `zeta/temp/salt/u/v/ubar/vbar/dye_01`, sigma-z conversion including actual synthetic `zeta`, ROMS rotation and `ubar/vbar` depth averaging, one chosen daily source record.
- [`create_ocean_bry_from_glorys.py`](../Data_pre/impl/preprocessing/create_ocean_bry_from_glorys.py): the **outer ES3K** GLORYS ocean boundary with four sides and time-varying `zeta/u/v/temp/salt/ubar/vbar`, staggered `xi_rho/xi_u/xi_v/eta_rho/eta_u/eta_v`; GLORYS daily 12:00 source times mapped according to the explicitly configured `daily_mean_to_day_start` test policy. **This is not the UD1K embedded parent-history boundary.**
- [`create_atm_forcing_from_era5.py`](../Data_pre/impl/preprocessing/create_atm_forcing_from_era5.py): normalized ERA5 hourly winds, Pair, Tair, Qair, rain, **signed EminusP/swflux** into real ROMS forcing.
- [`create_rad_forcing_from_era5.py`](../Data_pre/impl/preprocessing/create_rad_forcing_from_era5.py): normalized ERA5 hourly `swrad/lwrad/lwrad_down` onto ROMS RHO grid, without treating already-normalized radiation fluxes as accumulation totals.
- [`create_tides_from_tpxo.py`](../Data_pre/impl/preprocessing/create_tides_from_tpxo.py): elevation amplitude/phase plus all required current ellipse harmonics for `UV_TIDES`, `tide_period` and explicit synthetic `zero_phase_date`. Partial UV tidal inputs are rejected, not manufactured.

The test isolates only **case configuration and grid resolution** using Python mocks; the existing production-module `main()`, actual spatial/vertical interpolation, angle rotation, rho→U/V averaging, normal NetCDF writing/reading and quality checks execute unmocked. It creates a tiny **4×5 RHO rotated C-grid**, 4 sigma layers, 3 GLORYS depths, four GLORYS daily records, **73 ERA5 hourly samples**, and two TPXO constituents; a 24-hour interval is deliberately used instead of any user-approved production year.

All test inputs and outputs are named `SYNTHETIC_only` in the test workspace; no real ocean/dynamical fluxes should be inferred from the constant test fields.

## Physics-relevant bug fixed only in isolated nested preprocessor

The ERA5 stage [`download_era5_staged.py`](../Data_pre/impl/preprocessing/download_era5_staged.py) already computes **signed**, **rate-normalized**, **m s−1** `EminusP = evaporation - precipitation`. Previously, the downstream nested ROMS atmospheric converter executed `abs(EminusP) - rain/1000` a second time. A negative source `EminusP` could therefore silently become positive, changing surface freshwater physics.

This PR changes **only `ROMS_Nesting/Data_pre/impl/preprocessing/create_atm_forcing_from_era5.py`**:
- If the source field is `EminusP` or `swflux`, require signed `m s-1` units, preserve the source exactly and reject incompatible units.
- Retain legacy handling **only for raw source evaporation `e/evaporation`**.
- Unit test verifies `EminusP=−1e−6 m/s` remains **−1e−6 m/s** in both ROMS `EminusP` and `swflux`, never changed to a positive flux.

The original single-grid `Data_pre` source tree is **not changed**.

## Test gates and results

[**GitHub Actions #38693369192**](https://github.com/RRain001/ROMS/actions/runs/38693369192): **SUCCESS**. The existing lightweight history/bry/source contract suite remains PASS. New `test_japan_sea_forcing_converter_micro.py` comprises **6 tests PASS**:

1. All five real converter `main()` methods produce finite, correctly shaped ROMS files and exact values expected under synthetic rotated constant fields: initial and boundary temperature, salinity, sea-level, true U/V, barotropic U/V, dye initialization, atmospheric/radiation variables and tidal amplitude/current ellipse.
2. Staged negative ERA5 `EminusP` remains negative in ROMS output; `swflux` equals signed `EminusP`.
3. Reject incorrectly labeled staged `EminusP` units rather than guessing a conversion.
4. Reject incomplete TPXO UV tide harmonics; do not produce an apparently valid `tide_C*` replacement.
5. Preserve independent ERA5 hourly pressure changes.
6. Preserve independent ERA5 hourly radiation changes.

All outputs are small and temporary; no Copernicus, CDS API, TPXO network access, large GEBCO/GSHHG recomputation, actual ES3K water dynamics, actual UD1K `bry.nc`, or HTO dispersion was run.

## Remaining scientific boundary

**The executable GLORYS initial/outer-boundary converters here are for an ES3K directly driven by an external ocean reanalysis.** A nested child UD1K must instead use **real time-dependent ES3K ROMS history** as parent, with its own shoreline-safe 1,011 RHO/1,005 U/1,010 V candidate B donor map, C-grid angle rotation, physical-z remapping and normal-flux audits (existing synthetic numerical preview already passed). This last physical interface is not exercised by these five converters. Real ES3K source forcing samples, reanalysis time cover and actual ROMS hydrodynamic source series are still unavailable to this test-only stage.

**Future limited tests** may introduce physically meaningful nonconstant small fields and a two-file mock parent/child coupling, but never claim model validity without a real parent ES3K solution and actual ROMS numerical integrations. Original frozen ES3K/UD1K grids, `main` and PR draft state remain unchanged.
