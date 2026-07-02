# Pilot ROMS Input File Notes

`run/ocean_fukushima_202401_pilot.in` is a draft input file generated from the working `roms_upwelling.in` template.

## Locked Pilot Settings

| Field | Value |
| --- | --- |
| `MyAppCPP` | `FUKUSHIMA_202401` |
| `Lm`, `Mm` | `356`, `446` |
| `N` | `21` |
| `NPT` | `1` |
| `DT`, `NTIMES` | `60 s`, `44640` |
| Output interval | `NHIS=NAVG=NDIA=60`, hourly |
| MPI tiling | `NtileI=4`, `NtileJ=4` |
| `GRDNAME` | `../input/roms_grid_bathy_500m.nc` |

## Locked Smoke Settings

`preprocessing/create_pilot_infile.py` now writes both:

- `run/ocean_fukushima_202401_pilot.in`
- `run/ocean_fukushima_202401_smoke.in`

The smoke file inherits the same real-grid input paths and overrides only the short-run settings needed for stability and fast validation:

- `DT = 10 s`
- `NTIMES = 5`
- `NtileI = 2`, `NtileJ = 2`
- `NRST = NHIS = 5`
- `NXTR = NAVG = NDIA = 0`
- smoke-specific `RSTNAME`, `HISNAME`, `AVGNAME`, `DIANAME`

## Passive Tracer Settings

The pilot enables one HTO-like inert tracer:

- CPP header: `#define T_PASSIVE`
- ROMS input: `NPT = 1`
- Source switches: `LwSrc = T`, `LtracerSrc = F F T`
- Output: `Hout(inert) == T`, `Aout(inert) == T`

The current pilot uses a nominal `1 m3/s` discharge to create `roms_rivers_pilot.nc`. This is a plumbing/sensitivity assumption, not a verified Fukushima discharge value.
The generated source file uses a surface-layer vertical profile and stores `river_dye_01` in `Bq/m3`; the value is derived from `release_Bq_s / discharge_m3_s`.

## Not Ready For Production

The input files still point to placeholder/pilot file names for everything except the bathymetry grid:

- `../input/roms_grid_bathy_500m.nc`
- `../input/roms_ini_pilot.nc`
- `../input/roms_bdy_pilot.nc`
- `../input/roms_clm_pilot.nc`
- `../input/roms_frc_pilot.nc`
- `../input/roms_tides_pilot.nc`
- `../input/roms_rivers_pilot.nc`

Only the bathymetry grid, static pilot initial file, and snapped-source file are currently real-grid aware. The boundary, climatology, forcing and tide files must still be generated from real ocean, meteorological and tide data before running a scientific case.
