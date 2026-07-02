# Remote Data Inventory for Fukushima ROMS Project

Date: 2026-06-25

Host:

- `lhy-desktop`

Search scope:

- `/home/lhy/ROMS`
- `/home/lhy`

Search patterns:

- `*gebco*`, `*etopo*`
- `*hycom*`, `*cmems*`
- `*era5*`, `*ncep*`, `*fnl*`
- `*tpxo*`
- `*.nc`, `*.grib`, `*.grib2`

## Findings

No reusable production forcing or bathymetry dataset was found for the Fukushima ROMS project.

Relevant files found:

- Current project pilot files:
  - `/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_grid_idealized_500m.nc`
  - `/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_ini_pilot.nc`
  - `/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_rivers_pilot.nc`
  - `/home/lhy/ROMS/projects/fukushima_202401_50m/output/his_fukushima_smoke.nc`
  - `/home/lhy/ROMS/projects/fukushima_202401_50m/output/rst_fukushima_smoke.nc`
- Existing ROMS UPWELLING outputs:
  - `/home/lhy/ROMS/roms_work/roms_his.nc`
  - `/home/lhy/ROMS/roms_work/roms_avg.nc`
  - `/home/lhy/ROMS/roms_work/roms_dia.nc`
  - `/home/lhy/ROMS/roms_work/roms_rst.nc`
- MITgcm tutorial/example NCEP-like binary files under `/home/lhy/MITgcm`, not directly reusable for this ROMS Fukushima domain.

## Missing Data for Next Scientific Step

- Real bathymetry/coastline for 140E-142E, 36N-38N.
- Ocean initial/boundary fields for January 2024: `zeta`, `u`, `v`, `ubar`, `vbar`, `temp`, `salt`.
- Atmospheric forcing for January 2024: `Uwind`, `Vwind`, `Pair`, `Tair`, `Qair`, `rain`, `EminusP`.
- Radiation forcing: `swrad`, `lwrad`, `lwrad_down`.
- Tide forcing compatible with the real grid.
- Defensible source discharge or effective mixing flow for converting 22 TBq/year to concentration.

## Consequence

The next implementation step cannot be a scientific January 2024 run until external data are acquired or staged on the remote host. Work can still continue by building download/preprocessing scripts and testing them on small subsets.
