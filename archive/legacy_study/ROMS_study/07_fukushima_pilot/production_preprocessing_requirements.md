# Fukushima 2024-01 Production Preprocessing Requirements

Generated: 2026-06-25

Remote project:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## Current Status

The remote project has passed a technical ROMS smoke run with:

- domain: 140E-142E, 36N-38N
- pilot grid: 500 m idealized all-water grid
- vertical levels: `N=21`
- source: 22 TBq/year converted to `695709.370572759 Bq/s`
- passive tracer output metadata: `dye_01` now writes `Bq meter-3`

This proves the executable, input-file wiring, source-file format and tracer output path. It does not yet prove a scientifically defensible Fukushima transport simulation.

## Required Data Before Scientific Runs

| Priority | File to generate | Required external data | ROMS variables | Current status |
| --- | --- | --- | --- | --- |
| 1 | `input/roms_grid_real_*.nc` | bathymetry and coastline/land mask | `h`, `mask_rho`, `pm`, `pn`, `angle`, lon/lat grids | missing; current grid is constant 100 m all-water |
| 2 | `input/roms_ini_20240101.nc` | ocean analysis/reanalysis | `zeta`, `u`, `v`, `ubar`, `vbar`, `temp`, `salt`, `dye_01` | placeholder idealized initial file only |
| 3 | `input/roms_bdy_202401.nc` | ocean open-boundary time series | boundary `zeta`, `u`, `v`, `ubar`, `vbar`, `temp`, `salt`, `dye_01` | missing |
| 4 | `input/roms_clm_202401.nc` | optional ocean climatology/forcing | `zeta`, `u`, `v`, `ubar`, `vbar`, `temp`, `salt` | missing |
| 5 | `input/roms_atm_202401.nc` | atmospheric forcing | `Uwind`, `Vwind`, `Pair`, `Tair`, `Qair`, `rain`, optionally `EminusP` | missing |
| 6 | `input/roms_rad_202401.nc` | radiation/heat flux forcing | `swrad`, `lwrad`, `lwrad_down` | missing |
| 7 | `input/roms_tides_202401.nc` | tidal atlas | tidal elevation and current constituents | missing |
| 8 | `input/roms_rivers_pilot.nc` or production replacement | source discharge/effective mixing flow | `river_transport`, `river_dye_01`, `river_temp`, `river_salt` | format works, discharge is placeholder |

## Data Classification

Atmospheric fields:

- Wind speed and direction must be converted to `Uwind` and `Vwind`.
- Air pressure is `Pair`.
- Air temperature and humidity are `Tair` and `Qair`.
- Precipitation and evaporation/freshwater flux are `rain` and `EminusP` or equivalent forcing variables.
- Radiation is `swrad`, `lwrad` and/or `lwrad_down`.

Ocean fields:

- Sea temperature and salinity are `temp` and `salt`.
- Ocean currents are `u`, `v`, `ubar`, `vbar`.
- Sea surface height is `zeta`.
- These belong to initial, boundary and optional climatology files, not to meteorological forcing.

## Resolution Recommendation

Use the current 500 m grid for workflow checks. For a first full-domain production candidate, use 250-500 m after real forcing is prepared. The requested 50 m grid over 140E-142E and 36N-38N should be treated as a later nested-domain target unless high-resolution bathymetry, open-boundary forcing and validation data are available.

The script `preprocessing/estimate_grid_cost.py` quantifies the approximate cell count and output burden for 50 m, 250 m and 500 m.

## Next Remote Implementation Steps

1. Acquire and document real bathymetry/coastline for 140E-142E, 36N-38N.
2. Generate a real masked grid at 500 m or 250 m and rerun smoke.
3. Generate ocean initial and boundary files for 2024-01-01 to 2024-01-31.
4. Generate atmospheric and radiation forcing for the same period.
5. Add tide forcing.
6. Replace the `1 m3/s` source discharge placeholder with a measured discharge or explicit sensitivity cases.
7. Run 1-day stability test before attempting the full January run.

## Verification Gates

- `python3 preprocessing/estimate_grid_cost.py` runs from the project directory.
- Every NetCDF input can be opened by Python `netCDF4.Dataset`.
- All time axes cover `2024-01-01 00:00:00` through `2024-02-01 00:00:00` or the exact ROMS stop convention used in the input file.
- Output `dye_01` attributes are `long_name = HTO activity concentration, type 01` and `units = Bq meter-3`.
- Source concentration and transport are archived with the conversion from `22 TBq/year`.
