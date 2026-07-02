# Fukushima ROMS Pilot Smoke Run Results

Run date: 2026-06-25

Remote project path:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## What Was Tested

This was a technical dry-run, not a scientific simulation.

The run tested whether ROMS can compile and advance a Fukushima HTO-like passive tracer pilot with:

- domain: 140E-142E, 36N-38N
- pilot grid: 500 m, `Lm=356`, `Mm=446`
- vertical levels: `N=21`
- runtime tested: 5 baroclinic steps at `DT=60 s`
- MPI layout: `NtileI=2`, `NtileJ=2`, `mpirun -np 4`
- HTO-like source: `22 TBq/year` converted to `695709.370572759 Bq/s`
- nominal source discharge: `1 m3/s`
- source concentration: `695709.370572759 Bq/m3`

## Files

Compiled executable:

- `run/romsM`

Main pilot input:

- `run/ocean_fukushima_202401_pilot.in`

Short smoke input:

- `run/ocean_fukushima_202401_smoke.in`

Generated input files:

- `input/roms_grid_idealized_500m.nc`
- `input/roms_ini_pilot.nc`
- `input/roms_rivers_pilot.nc`

Smoke outputs:

- `output/smoke_run.log`
- `output/his_fukushima_smoke.nc`
- `output/rst_fukushima_smoke.nc`

## Verification Evidence

The smoke run completed successfully. After the HTO metadata patch, the latest log ends with:

```text
ROMS: DONE... Thursday - June 25, 2026 -  4:42:13 PM
```

ROMS read the HTO-like source file:

```text
river runoff dye concentration, type 01
Min = 0.00000000E+00 Max = 6.95709371E+05
```

The history file contains `dye_01`:

```text
dye_01(ocean_time, s_rho, eta_rho, xi_rho)
ocean_time = 2
s_rho = 21
eta_rho = 448
xi_rho = 358
```

The latest history file writes HTO-compatible metadata:

```text
standard_name = activity_concentration_of_HTO_01
long_name = HTO activity concentration, type 01
units = Bq meter-3
```

At the source grid point and surface layer:

```text
dye_01[:, -1, eta=318, xi=184] = [0.0, 802.3632202148438]
```

This confirms that the passive tracer source entered the model output during the smoke run.

## Current Limitations

The result is not scientifically interpretable yet.

- The 500 m grid is idealized, all-water and constant-depth.
- The initial ocean is static: `zeta/u/v/ubar/vbar=0`, `temp=15 C`, `salt=33`.
- Meteorological forcing is replaced by analytical zero fluxes.
- HYCOM/CMEMS ocean boundary forcing is not yet used.
- TPXO9 tide forcing is not yet used.
- The discharge value `1 m3/s` is a placeholder used to convert `Bq/s` to `Bq/m3`.
- The project-local `run/varinfo.yaml` has been patched so new smoke output reports `dye_01` as `Bq meter-3`. Production output should still archive the patched `varinfo.yaml` with the run.

## Reproduction Commands

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/create_idealized_grid.py --resolution pilot --write
python3 preprocessing/create_initial_nc.py
python3 preprocessing/create_pilot_infile.py
python3 preprocessing/create_river_source_nc.py
bash run/build_roms_fukushima.sh -noclean -j 4
bash run/run_smoke.sh
```
