# Remote Codex CLI Handoff

Updated: 2026-06-25

## Objective

Continue the Fukushima ROMS project under:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

Scientific target requested by the user:

- domain: 140E-142E, 36N-38N
- vertical levels: `N=21`
- nominal target resolution: 50 m
- time range: 2024-01-01 to 2024-01-31
- source term: Fukushima, `22 TBq/year`

Current practical strategy:

- do not run 50 m full-domain production yet
- first complete a scientifically structured 500 m real-bathymetry workflow
- then add real ocean, atmosphere, tide, and discharge inputs
- reserve 50 m for later nested or sensitivity work

## What Is Already Done

Study notes remain available as legacy reference under:

- `/home/lhy/ROMS/archive/legacy_study/ROMS_study`

Project scaffolding and technical ROMS pilot exist:

- `run/romsM` built successfully
- idealized 500 m smoke run completed
- output tracer metadata was corrected to `Bq meter-3`

Project-level preprocessing already exists:

- `create_grid_from_bathymetry.py`
- `validate_staged_data.py`
- `stage_and_subset_bathymetry.py`

Bathymetry staging is now partially complete:

- raw global ETOPO file exists:
  - `data/raw/bathymetry/ETOPO_2022_v1_60s_N90W180_bed.nc`
- Fukushima subset has been generated:
  - `data/raw/bathymetry/gebco_fukushima.nc`

Verified bathymetry subset properties:

- variables: `lon`, `lat`, `elevation`
- lon range: `139.75833333333333` to `142.24166666666667`
- lat range: `35.758333333333326` to `38.241666666666674`
- elevation min/max: `-4724.5` to `1907.6904296875`

Real 500 m ROMS bathymetry grid has been generated:

- `input/roms_grid_bathy_500m.nc`

Verified grid properties:

- dimensions: `xi_rho=358`, `eta_rho=448`
- `h_min=10.0`, `h_max=3408.71142578125`
- `water_fraction=0.5831753790901836`

## Current Status

The earlier land-source issue has been fixed in preprocessing.

Configured source from `config/project_parameters.json`:

- lon: `141.032`
- lat: `37.421`

Current snapped water cell on the active candidate grid:

- index: `xi=186`, `eta=318`
- lon/lat: `141.0420168067227`, `37.422818791946305`
- depth: `10.692072868347168`
- snap distance: `908.430416977328 m`

Placement metadata is now recorded in:

- `input/roms_rivers_pilot.nc`
- `input/fukushima_hto_source_202401_hourly.csv`

The current active candidate grid is:

- `input/roms_grid_bathy_500m_smoothed.nc`

Why this matters:

- the raw real bathymetry grid audited at `rx0=0.714325`, `rx1=29.275273`, which is not acceptable for a 1-day external pilot
- the smoothed candidate audited at `rx0=0.183077`, `rx1=7.503365`
- DT smoke trials on the smoothed candidate passed at `10 s`, `20 s`, and `30 s`, and failed at `60 s`
- the 1-day external pilot input therefore defaults to `DT=30 s`

The smoothed-grid smoke regression now completes with:

- `ROMS: DONE`

The present hard blocker for a true external 1-day run is no longer source placement. It is missing staged forcing data under `data/raw/`.

## Recommended Next Actions

1. Stage the missing external-forcing source files.
   - `data/raw/ocean/ocean_initial_20240101.nc`
   - `data/raw/ocean/ocean_boundary_202401.nc`
   - `data/raw/atmosphere/era5_atm_202401.nc`
   - `data/raw/atmosphere/era5_rad_202401.nc`
   - `data/raw/tides/tpxo9_fukushima_202401.nc`
   - `data/raw/source/fukushima_discharge_202401.csv`

2. Generate ROMS-ready forcing products.
   - `input/roms_ini_20240101.nc`
   - `input/roms_bdy_202401.nc`
   - `input/roms_atm_202401.nc`
   - `input/roms_rad_202401.nc`
   - `input/roms_tides_202401.nc`
   - `input/roms_rivers_production.nc`

3. Validate the ROMS-ready inputs.
   - use `preprocessing/validate_roms_ready_inputs.py`

4. Build and run the external 1-day pilot.
   - external header: `run/fukushima_202401_external.h`
   - run script: `run/run_pilot_1day.sh`

## Commands Already Proven

Bathymetry subset from existing global ETOPO file:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/stage_and_subset_bathymetry.py \
  --work-dir data/raw/bathymetry \
  --global-file ETOPO_2022_v1_60s_N90W180_bed.nc \
  --output gebco_fukushima.nc
```

Real grid generation:

```bash
python3 preprocessing/create_grid_from_bathymetry.py \
  --bathymetry data/raw/bathymetry/gebco_fukushima.nc \
  --resolution-key pilot
```

Staged data validation:

```bash
python3 preprocessing/validate_staged_data.py
```

## What Not To Assume

- Do not assume the old idealized source index is still valid on the real grid.
- Do not treat ETOPO 60s as final paper-grade bathymetry.
- Do not treat the current `1 m3/s` discharge as physical truth.
- Do not start a 50 m full-domain production run before real forcing and storage costs are resolved.

## Files To Read Before Editing

Project:

- `/home/lhy/ROMS/projects/fukushima_202401_50m/config/project_parameters.json`
- `/home/lhy/ROMS/projects/fukushima_202401_50m/docs/production_preprocessing_requirements.md`
- `/home/lhy/ROMS/projects/fukushima_202401_50m/docs/metadata_units_patch.md`

Notes (legacy only):

- `/home/lhy/ROMS/archive/legacy_study/ROMS_study/07_fukushima_pilot/real_preprocessing_entrypoints.md`
- `/home/lhy/ROMS/archive/legacy_study/ROMS_study/07_fukushima_pilot/smoke_run_results.md`
- `/home/lhy/ROMS/archive/legacy_study/ROMS_study/07_fukushima_pilot/production_preprocessing_requirements.md`
