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

Study notes exist on the remote host:

- `/home/lhy/ROMS/ROMS_study`

Project scaffolding and technical ROMS pilot exist:

- `run/romsM` built successfully
- idealized 500 m smoke run completed
- output tracer metadata was corrected to `Bq meter-3`

Project-level preprocessing already exists:

- `create_grid_from_bathymetry.py`
- `validate_staged_data.py`
- `fetch_and_subset_etopo.py`

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

## Critical Current Issue

The configured Fukushima source point is on land in the new real-bathymetry 500 m grid.

Configured source from `config/project_parameters.json`:

- lon: `141.032`
- lat: `37.421`

Nearest grid cell to configured source:

- index: `xi=184`, `eta=318`
- `mask_rho=0`
- depth: `10.0`

Nearest water cell found:

- index: `xi=186`, `eta=318`
- lon/lat: `141.0420168067227`, `37.422818791946305`
- depth: `10.0`
- distance from configured source in degree space: `0.010180590408402301`

Consequence:

- do not regenerate `roms_rivers_pilot.nc` against the real grid until the source placement rule is updated
- the next implementation decision is to snap the source to the nearest water cell, or redefine the discharge point offshore using a documented rule

## Recommended Next Actions

1. Update the source placement logic.
   - Modify the source-generation path so the project documents both:
     - configured source lon/lat
     - actual snapped water-cell index and lon/lat
   - Prefer snapping to nearest `mask_rho=1` cell for the current 500 m workflow.

2. Regenerate pilot inputs against the real grid.
   - `roms_ini_pilot.nc`
   - `roms_rivers_pilot.nc`
   - smoke `.in` if any hard-coded grid references need updating

3. Re-run smoke with the real bathymetry grid.
   - confirm `ROMS: DONE`
   - confirm `dye_01` remains `Bq meter-3`
   - confirm tracer enters output at the snapped water source point

4. After real-grid smoke succeeds, continue staged-data completion.
   - ocean initial/boundary forcing
   - atmosphere/radiation forcing
   - tides
   - real or scenario-based discharge/effective mixing flow

## Commands Already Proven

Bathymetry subset from existing global ETOPO file:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/fetch_and_subset_etopo.py \
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

Notes:

- `/home/lhy/ROMS/ROMS_study/07_fukushima_pilot/real_preprocessing_entrypoints.md`
- `/home/lhy/ROMS/ROMS_study/07_fukushima_pilot/smoke_run_results.md`
- `/home/lhy/ROMS/ROMS_study/07_fukushima_pilot/production_preprocessing_requirements.md`
