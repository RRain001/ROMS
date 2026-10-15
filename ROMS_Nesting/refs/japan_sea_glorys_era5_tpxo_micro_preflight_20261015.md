# Japan Sea external GLORYS/ERA5/TPXO staged data: small offline test gate

**Date**: 2026-10-15. **Scope**: test-only Japanese Sea ES3K -> UD1K nesting, [Draft PR #3](https://github.com/RRain001/ROMS/pull/3). Do not select a production simulation period, download large ocean/atmosphere volumes, replace the original frozen grids, edit main or run ocean hydrodynamics in routine CI.

## What was reused

The existing *non-nested* workflow implementation was already copied into the isolated `ROMS_Nesting/Data_pre` tree. Its data sources/format are retained:

| Upstream source | Existing staging code / validation contract |
| --- | --- |
| GLORYS12V1 Copernicus Marine | `impl/preprocessing/download_glorys12v1_staged.py`, `core/ocean_source_utils.py`: staged CF `time,depth,latitude,longitude`, variables `thetao,so,uo,vo,zos`. Daily mean source time is centered at 12:00 UTC; the model-time normalization is an explicit separate step. |
| ERA5 atmospheric single levels | `impl/preprocessing/download_era5_staged.py`: staged hourly `Uwind,Vwind,Pair,Tair,Qair,rain,EminusP` on `time,lat,lon`; pressure converted Pa→mbar, temperature K→°C, humidity to %, cumulative precipitation/evaporation to m/s. `CDSAPI_KEY` is read from GitHub Secrets by the downloader but **no secret is tested or printed here**. |
| ERA5 radiation | same ERA5 downloader: staged hourly `swrad,lwrad_down,lwrad` in `W m-2`. |
| TPXO9 atlas | `impl/preprocessing/create_tides_from_tpxo.py`: harmonic `tide_period` (hours) plus either elevation amplitude/phase (`tide_Eamp/Ephase`) or raw complex elevation (`tide_ERe/EIm`), and for `UV_TIDES` a complete current ellipse (`tide_Cmax/Cmin/Cangle/Cphase`) or native U/V complex quartet. A real atlas-derived tide reference epoch is separately required for later model runs. |

## Implemented data-interface micro preflight

[`ROMS_Nesting/Data_pre/nesting/japan_sea_forcing_micro_preflight.py`](../Data_pre/nesting/japan_sea_forcing_micro_preflight.py) accepts **four existing staged NetCDF files**, a bounded test coordinate and a *maximum* 72-hour test window. The gate validates:

1. Exact recognized source variables and staggered/staged dimensions, monotonic rectilinear latitude/longitude; the **single test point** must be within each product's source coordinate extent. This is explicitly **not a proof that the full ES3K domain is covered**.
2. Valid CF time units and calendars, strictly increasing samples, source coverage bracketing both test interval endpoints. GLORYS source gaps must be ≤36 h, ERA5 atmosphere/radiation ≤2 h. This explicitly permits GLORYS daily mean centered at noon and ERA5 hourly samples without falsely demanding identical time grids.
3. Field units (ocean temperature/salinity/velocity/zeta and normalized ERA5 atmospheric and radiation fields); no silent Pa→mbar or Kelvin→C conversion at admission. GLORYS source vertical `depth` must be finite, nonnegative and increasing. Near-site first/last time, surface/bottom and 3×3 finite sample is checked in bounded memory; land-masked samples are tolerated only when at least one near-site sample is valid.
4. TPXO harmonic periods positive and in hours; elevation and, for current-tide mode, complete U/V constituent groups. Partial or missing tidal current harmonic fields fail closed.
5. The preflight itself is **pure read-only**: no network, credential retrieval, GEBCO download, model execution, destination mesh write, production `ini.nc` or `bry.nc` generation.

Test-only example (using files **explicitly labeled synthetic**):

```bash
python ROMS_Nesting/Data_pre/nesting/japan_sea_forcing_micro_preflight.py \
  --ocean /path/SYNTHETIC_GLORYS_daily.nc \
  --atmosphere /path/SYNTHETIC_ERA5_atm_hourly.nc \
  --radiation /path/SYNTHETIC_ERA5_rad_hourly.nc \
  --tides /path/SYNTHETIC_TPXO9_harmonics.nc \
  --start 2018-01-02T00:00:00 \
  --stop 2018-01-03T00:00:00 --lon 130 --lat 37 \
  --report /path/OFFLINE_ONLY_staged_source_contract.json
```

The dates and coordinate are **technical fixtures only**. They do **not** approve the JAPAN_SEA case's historical 2018 pilot date or the commented 2024–2025 long-run placeholder.

## Confirmed CI evidence

[**GitHub Actions #38692070272**](https://github.com/RRain001/ROMS/actions/runs/38692070272), fast job SUCCESS. [`test_japan_sea_forcing_micro_preflight.py`](../Data_pre/tests/test_japan_sea_forcing_micro_preflight.py) contributes **12 new offline unit tests**, all passed. The existing full source-history/schema/remap/ERA5-credential suite also passed in the same small test job. The test fixture generator builds <1MB (order-of-magnitude) small mock staged GLORYS daily/ERA5 hourly/TPXO harmonic files and invokes the CLI end-to-end. CI output:

`JAPAN_SEA_OFFLINE_MICRO_SOURCE_CONTRACT_PASS` for four source interfaces, 24-hour test interval, API calls **NONE**, ROMS model **NOT_RUN**.

The fixture archive `japan-sea-SYNTHETIC-only-glorys-era5-tpxo-micro-interface` is retained for 7 days, and all evidence carries explicit synthetic/not-run markers.

## Reduced GitHub Actions cost

The following previously automatic potentially time-consuming workflows on the *working PR branch* are now **workflow_dispatch only**:

- `.github/workflows/japan-sea-es3k-online-native.yml` (native 15″ bathymetry/shoreline, <=55 minutes).
- `.github/workflows/japan-sea-es3k-online-real.yml` (preliminary 30″ bathymetry/shoreline, <=55 minutes).
- `.github/workflows/japan-sea-es3k-wet-domain.yml` (full ES3K geometry and topology, <=10 minutes).

The `japan-sea-ud1k-bry-schema-contract.yml` workflow remains automatically limited to small synthetic tests on scoped branch/PR changes. Its full candidate B 41-level real-grid shape fixture and optional Secret *presence-only* job are now manual. There is no CDS/ERA5 credential check or download in the automatic workflow. **Already launched GitHub Actions runs cannot be cancelled by the connector**, so old runs may have continued to completion during the trigger edits.

## Future gated tasks (not authorized for long computation)

1. When desired, exercise **real staged** GLORYS/ERA5/TPXO products over a very small spatial/temporal sample, first using cached authorized source files if already available. This is not yet done by the synthetic test.
2. Test existing `create_ocean_ini_from_glorys.py`, `create_ocean_bry_from_glorys.py`, `create_atm_forcing_from_era5.py` and `create_tides_from_tpxo.py` against tiny source fixtures and a small synthetic ES3K ROMS C-grid, using explicit time/datum and tide phase checks. Keep it separate from the previous ESP3K-history→UD1K full 28-field synthetic boundary preview.
3. Only after a future production date is chosen: true ES3K hydrodynamic spinup/history, actual native parent-child time/spatial/sigma-z/flux matching, and test UD1K 1h/6h/24h/7d runs. **ALL NOT_RUN**.

**Status**: `EXTERNAL_STAGED_INTERFACE_OFFLINE_MICRO_PASS`; real forcing download and physical nested ROMS acceptance remain **NOT_RUN**.
