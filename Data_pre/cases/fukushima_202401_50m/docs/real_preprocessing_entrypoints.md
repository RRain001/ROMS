# Real Preprocessing Entrypoints

Date: 2026-06-25

Remote project:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## Current Stage

The project has moved past the old idealized-only pilot.

What is now in place:

- raw real 500 m grid: `input/roms_grid_bathy_500m.nc`
- smoothed 500 m candidate grid: `input/roms_grid_bathy_500m_smoothed.nc`
- bathymetry stability audit entrypoint
- bathymetry smoothing entrypoint
- HYCOM/ERA5/TPXO/source-discharge to ROMS-ready conversion entrypoints
- ROMS-ready validation entrypoint
- smoke and external 1-day `.in` generation from one script

What is not yet in place:

- the actual staged raw HYCOM/ERA5/TPXO/source-discharge files required for a real external 1-day run

## Staged Data Validation

Command:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/validate_staged_data.py
```

Current verified result:

```text
required_missing=6
optional_missing=0
```

Currently present:

- `data/raw/bathymetry/gebco_fukushima.nc`

Currently missing required groups:

- ocean initial
- ocean boundary
- atmosphere
- radiation
- tides
- source discharge

## Bathymetry Stability Gate

Raw-grid audit:

```bash
python3 preprocessing/audit_bathymetry_stability.py \
  --grid input/roms_grid_bathy_500m.nc \
  --dt-list 10,20,30,60 \
  --report-json output/raw_grid_stability_audit.json \
  --report-md output/raw_grid_stability_audit.md
```

Current verified raw-grid result:

- `rx0 = 0.714325`
- `rx1 = 29.275273`
- `grid_acceptable_for_1day = false`

Smoothing step:

```bash
python3 preprocessing/smooth_bathymetry.py \
  --grid input/roms_grid_bathy_500m.nc \
  --output input/roms_grid_bathy_500m_smoothed.nc \
  --rx0-target 0.35 \
  --rx1-target 8.0 \
  --max-iter 200
```

Current verified smoothed-grid result:

- `rx0 = 0.183077`
- `rx1 = 7.503365`
- `grid_acceptable_for_1day = true`
- successful smoke DTs: `10 s`, `20 s`, `30 s`
- failed smoke DT: `60 s`

Current active candidate grid:

- `input/roms_grid_bathy_500m_smoothed.nc`

## Active Source Placement

The configured Fukushima point is still on land, but the preprocessing path now snaps it to the nearest water rho cell and records both configured and actual positions.

Current snapped source:

- configured lon/lat: `141.032000`, `37.421000`
- actual xi/eta: `186`, `318`
- actual lon/lat: `141.042017`, `37.422819`
- snap distance: `908.430 m`

Updated products:

- `input/roms_rivers_pilot.nc`
- `input/fukushima_hto_source_202401_hourly.csv`

## ROMS-Ready Conversion Entrypoints

These scripts convert already staged raw files into ROMS-ready `input/` products:

- `preprocessing/create_ocean_ini_from_hycom.py`
- `preprocessing/create_ocean_bry_from_hycom.py`
- `preprocessing/create_atm_forcing_from_era5.py`
- `preprocessing/create_rad_forcing_from_era5.py`
- `preprocessing/create_tides_from_tpxo.py`
- `preprocessing/create_river_source_production.py`
- `preprocessing/validate_roms_ready_inputs.py`

Current status:

- implementation complete
- synthetic functional test completed in `/tmp`
- project-local real-data run still blocked by missing `data/raw/` forcing files

## Input Generation Entrypoint

The unified `.in` generator is:

- `preprocessing/create_pilot_infile.py`

Supported modes:

- `--mode smoke`
- `--mode pilot_1day`
- `--mode pilot_month`

Supported forcing styles:

- `--forcing-mode analytical`
- `--forcing-mode external`

Current verified outputs:

- smoke input uses `GRDNAME == ../input/roms_grid_bathy_500m_smoothed.nc`
- smoke input uses `DT == 10 s`
- external 1-day input uses `GRDNAME == ../input/roms_grid_bathy_500m_smoothed.nc`
- external 1-day input uses `DT == 30 s`

## Smoke Regression

Command:

```bash
bash run/run_smoke.sh
```

Current verified result:

```text
Input Grid File:  ../input/roms_grid_bathy_500m_smoothed.nc
ROMS: DONE
```

The smoke regression confirms:

- the active candidate grid is usable for continued preprocessing work
- tracer metadata remains `Bq meter-3`
- the dominant first injected tracer signal is at `xi=186`, `eta=318`

## Next Real-Data Step

Stage the six missing required raw forcing groups under `data/raw/`, then run:

1. `create_ocean_ini_from_hycom.py`
2. `create_ocean_bry_from_hycom.py`
3. `create_atm_forcing_from_era5.py`
4. `create_rad_forcing_from_era5.py`
5. `create_tides_from_tpxo.py`
6. `create_river_source_production.py`
7. `validate_roms_ready_inputs.py`
8. `create_pilot_infile.py --mode pilot_1day --forcing-mode external`
9. `bash run/build_roms_fukushima.sh --external -noclean -j 4`
10. `bash run/run_pilot_1day.sh`
