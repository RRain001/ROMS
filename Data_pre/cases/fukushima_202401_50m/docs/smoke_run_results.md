# Fukushima ROMS Stability Audit and Smoke Results

Run date: 2026-06-25

Remote project path:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## Summary

The project now has a documented bathymetry-stability gate, a smoothed 500 m candidate grid, and a passing smoke regression on that candidate grid.

Current candidate grid for follow-on preprocessing:

- `input/roms_grid_bathy_500m_smoothed.nc`

Current blocker for a true external 1-day pilot:

- the required staged raw HYCOM/ERA5/TPXO/source-discharge files are still missing under `data/raw/`

## Stability Audit

Raw real bathymetry grid:

- file: `input/roms_grid_bathy_500m.nc`
- audit JSON: `output/raw_grid_stability_audit.json`
- audit Markdown: `output/raw_grid_stability_audit.md`
- `rx0 = 0.714325`
- `rx1 = 29.275273`
- `grid_acceptable_for_1day = false`

Smoothed candidate grid:

- file: `input/roms_grid_bathy_500m_smoothed.nc`
- audit JSON: `output/smoothed_grid_stability_audit.json`
- audit Markdown: `output/smoothed_grid_stability_audit.md`
- `rx0 = 0.183077`
- `rx1 = 7.503365`
- `grid_acceptable_for_1day = true`

DT trial outcome on the smoothed candidate:

- `10 s`: success
- `20 s`: success
- `30 s`: success
- `60 s`: failed

The current 1-day external pilot input therefore uses:

- `DT = 30 s`

## Active Source Placement

Configured Fukushima source:

- lon/lat: `141.032000`, `37.421000`

Actual injected water cell on the active grid:

- `xi = 186`, `eta = 318`
- lon/lat: `141.042017`, `37.422819`
- depth: `10.692072868347168 m`
- snap distance: `908.430 m`
- placement rule: `configured source on land; snapped to nearest mask_rho=1 rho cell`

The following files now carry both configured and actual placement metadata:

- `input/roms_rivers_pilot.nc`
- `input/fukushima_hto_source_202401_hourly.csv`

## Smoke Regression

Smoke input:

- `run/ocean_fukushima_202401_smoke.in`
- `GRDNAME == ../input/roms_grid_bathy_500m_smoothed.nc`
- `DT == 10 s`

Smoke outputs:

- `output/smoke_run.log`
- `output/his_fukushima_smoke.nc`
- `output/rst_fukushima_smoke.nc`

Verified smoke result:

```text
Input Grid File:  ../input/roms_grid_bathy_500m_smoothed.nc
ROMS: DONE... Thursday - June 25, 2026 - 11:21:59 PM
```

Tracer metadata remains correct:

```text
units = Bq meter-3
```

Largest tracer signal at the first post-injection history record:

- history index: `ocean_time=1`, `s_rho=20`, `eta=318`, `xi=186`
- lon/lat: `141.0420168067227`, `37.422818791946305`
- depth: `10.692072868347168 m`
- `dye_01 = 419.2820129394531 Bq meter-3`

This confirms that the smoke regression is injecting tracer at the snapped water cell on the smoothed candidate grid.

## Current External-Run Status

The external 1-day input template is ready:

- `run/ocean_fukushima_202401_pilot_1day.in`
- `run/romsM_external`

Current verified settings:

- `GRDNAME == ../input/roms_grid_bathy_500m_smoothed.nc`
- `DT == 30 s`
- `NTIMES == 2880`
- `BRYNAME == ../input/roms_bdy_202401.nc`
- `SSFNAME == ../input/roms_rivers_production.nc`
- `TIDENAME == ../input/roms_tides_202401.nc`
- `FRCNAME == ../input/roms_atm_202401.nc | ../input/roms_rad_202401.nc`
- open-boundary mode uses `Cha`, `Fla`, and `RadNud`

However, the run is not yet executable with real project data because these staged raw inputs are still missing:

- `data/raw/ocean/ocean_initial_20240101.nc`
- `data/raw/ocean/ocean_boundary_202401.nc`
- `data/raw/atmosphere/era5_atm_202401.nc`
- `data/raw/atmosphere/era5_rad_202401.nc`
- `data/raw/tides/tpxo9_fukushima_202401.nc`
- `data/raw/source/fukushima_discharge_202401.csv`

## Reproduction Commands

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/audit_bathymetry_stability.py \
  --grid input/roms_grid_bathy_500m.nc \
  --dt-list 10,20,30,60 \
  --report-json output/raw_grid_stability_audit.json \
  --report-md output/raw_grid_stability_audit.md

python3 preprocessing/smooth_bathymetry.py \
  --grid input/roms_grid_bathy_500m.nc \
  --output input/roms_grid_bathy_500m_smoothed.nc \
  --rx0-target 0.35 \
  --rx1-target 8.0 \
  --max-iter 200

python3 preprocessing/audit_bathymetry_stability.py \
  --grid input/roms_grid_bathy_500m_smoothed.nc \
  --dt-list 10,20,30,60 \
  --report-json output/smoothed_grid_stability_audit.json \
  --report-md output/smoothed_grid_stability_audit.md

python3 preprocessing/create_initial_nc.py
python3 preprocessing/create_river_source_nc.py
python3 preprocessing/create_source_timeseries.py
python3 preprocessing/create_pilot_infile.py --mode smoke
bash run/run_smoke.sh
```
