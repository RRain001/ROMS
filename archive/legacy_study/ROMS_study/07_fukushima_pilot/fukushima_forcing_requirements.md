# Fukushima ROMS Pilot Forcing Requirements

Source date: 2026-06-25

Project path on remote host:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## Key Answer

Yes, a realistic ROMS project needs more than wind speed and wind direction. The forcing should be separated into four categories:

1. Atmospheric forcing: wind, pressure, air temperature, humidity, radiation, precipitation and evaporation/freshwater flux.
2. Ocean initial and boundary forcing: sea surface height, temperature, salinity, 3D current and depth-integrated current.
3. Tide forcing: tidal elevation and tidal current constituents.
4. Source forcing: HTO release converted to a tracer concentration or tracer flux through a water discharge/effective volume flux.

Wind, pressure, precipitation and evaporation are meteorological fields. Sea temperature, salinity and ocean current are ocean state variables, not meteorology, but they are essential for ROMS initial and boundary conditions.

## Minimum Production Inputs

Atmospheric forcing:

- `Uwind`, `Vwind`
- `Pair`
- `Tair`
- `Qair`
- `swrad`
- `lwrad` or `lwrad_down`
- `rain`
- `EminusP` or evaporation derived through ROMS bulk flux settings

Operational interpretation for this project:

- Wind speed and direction should be converted to ROMS eastward/northward wind components (`Uwind`, `Vwind`). Do not store only scalar wind speed and direction in the forcing file.
- Air pressure (`Pair`) is needed for inverse-barometer and surface pressure effects if the chosen ROMS CPP options use it.
- Precipitation and evaporation affect surface freshwater flux and therefore salinity. If the first production run omits them, this must be recorded as a sensitivity/limitation rather than treated as physically complete.
- Air temperature, humidity, shortwave radiation and longwave radiation are needed when surface heat flux is computed or prescribed.
- For the January 2024 Fukushima pilot, hourly or 3-hourly atmospheric forcing is a practical first target. The ROMS time step can remain much shorter; forcing is interpolated in time by ROMS.

Ocean initial and boundary forcing:

- `zeta`
- `ubar`, `vbar`
- `u`, `v`
- `temp`
- `salt`

Operational interpretation for this project:

- Sea water temperature and salinity are not meteorological variables. They belong in `roms_ini.nc`, `roms_bdy.nc` and, if used, `roms_clm.nc`.
- Ocean currents are also not meteorological forcing. ROMS needs both 3D currents (`u`, `v`) and depth-integrated currents (`ubar`, `vbar`) at initial and open-boundary files.
- For pollutant transport, realistic currents are more important than extremely fine grid spacing in the first production phase. A 50 m grid over 140E-142E and 36N-38N is too expensive and is not scientifically useful without equally strong bathymetry, boundary forcing and validation data.
- Recommended staged resolution: keep the current 500 m pilot for workflow testing, then consider 250-500 m for the first full-domain production run. Use 50 m only for a later nested coastal/subdomain experiment near the source.
- Vertical levels are set to `N=21` as the current working choice.

Tide forcing:

- `tide_Eamp`, `tide_Ephase`
- `tide_Cmax`, `tide_Cmin`, `tide_Cangle`, `tide_Cphase`

HTO source forcing:

- annual activity release: 22 TBq/year
- release rate for 2024 calendar year: `695709.370572759 Bq/s`
- discharge/effective volume flux: currently pilot placeholder `1 m3/s`
- resulting pilot `river_dye_01`: `695709.370572759 Bq/m3`

## Current Pilot Choices

The 50 m grid was judged too large for a first technical run. The current pilot uses:

- domain: 140E-142E, 36N-38N
- horizontal resolution: 500 m pilot grid
- vertical levels: `N=21`
- period: 2024-01-01 to 2024-02-01
- source time step: 1 hour, 744 records
- ROMS time step draft: 60 s

Generated remote files:

- `input/roms_grid_idealized_500m.nc`
- `input/fukushima_hto_source_202401_hourly.csv`
- `input/roms_rivers_pilot.nc`
- `run/ocean_fukushima_202401_pilot.in`

Validated source-file structure on 2026-06-25:

- dimensions: `s_rho=21`, `river=1`, `river_time=744`
- `river_transport(river_time, river)`
- `river_Vshape(s_rho, river)`
- `river_dye_01(river_time, s_rho, river)`
- nearest source grid point: `xi=318`, `eta=184`
- source switches in `.in`: `LwSrc=T`, `LtracerSrc=F F T`

## Data Priority for the Next Implementation Step

| Priority | Data group | Variables | Why it matters | First-stage choice |
| --- | --- | --- | --- | --- |
| 1 | Bathymetry and land mask | `h`, `mask_rho`, coastline | Determines whether source, coast and shelf geometry are meaningful | Replace idealized 100 m depth with real bathymetry before scientific runs |
| 2 | Ocean initial/boundary | `zeta`, `u`, `v`, `ubar`, `vbar`, `temp`, `salt` | Controls transport pathway and dilution | Use HYCOM/CMEMS-like ocean analysis/reanalysis for Jan 2024 |
| 3 | Atmospheric forcing | `Uwind`, `Vwind`, `Pair`, `Tair`, `Qair`, `swrad`, `lwrad`, `rain`, `EminusP` | Controls surface stress, heat and freshwater fluxes | Use ERA5 or NCEP/ERA5 products, hourly or 3-hourly |
| 4 | Tide forcing | elevation and current constituents | Important near coast and shelf/open-boundary water level | Add TPXO9 after real grid is ready |
| 5 | Source forcing | discharge/effective volume flux, `dye_01` concentration | Converts 22 TBq/year to ROMS tracer source | Replace current `1 m3/s` placeholder with defensible discharge or sensitivity cases |

## Simplification Rules

For the next run, do not spend effort on 50 m resolution until the forcing chain is real. The defensible sequence is:

1. Keep `N=21`.
2. Use 500 m or 250 m for the 140E-142E, 36N-38N full domain.
3. Add real bathymetry and land mask.
4. Add ocean initial/boundary fields: `zeta`, `u`, `v`, `ubar`, `vbar`, `temp`, `salt`.
5. Add atmospheric forcing: wind components, air pressure, air temperature, humidity, radiation, precipitation and evaporation/freshwater flux.
6. Add tide forcing.
7. Re-run smoke, then 1-day, then full January.

## Important Limitation

The current setup is not yet a scientific ROMS run. It is a plumbing pilot. The grid is idealized, bathymetry is constant, all ocean and meteorological forcing files are still placeholders, and `1 m3/s` discharge is only a sensitivity placeholder. Production work still needs real bathymetry, land mask, HYCOM/CMEMS initial and boundary data, ERA5 or NCEP/ERA5 atmospheric forcing, TPXO9 tides and a defensible Fukushima discharge/effective mixing flux.
