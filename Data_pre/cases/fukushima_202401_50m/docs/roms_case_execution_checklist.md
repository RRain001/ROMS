# Fukushima 2024-01 ROMS Case Execution Checklist

Date: 2026-06-27

Project root:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

Case window:

- start: `2024-01-01T00:00:00`
- stop: `2024-01-31T23:00:00`

Active pilot grid:

- `/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_grid_bathy_500m_smoothed.nc`

## 1. Download HYCOM raw ocean data

Run from:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m/preprocessing
```

Command:

```bash
python3 download_hycom_staged.py \
  --source gofs31_standard \
  --source-key analysis_93_0_glby \
  --start 2024-01-01T00:00:00 \
  --stop 2024-01-31T23:00:00
```

Expected outputs:

- `data/raw/ocean/ocean_boundary_202401.nc`
- `data/raw/ocean/ocean_initial_20240101.nc`

Gate:

- `zeta`, `temp`, `salt`, `u`, `v` exist and contain finite values on open boundaries
- west boundary may remain all-NaN if the active grid west edge is all land

## 2. Validate staged raw inputs

Run from project root:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/validate_staged_data_deep.py
```

Expected required groups:

- bathymetry
- ocean initial
- ocean boundary
- atmosphere
- radiation
- tides
- source discharge

Gate:

- no required failures
- time coverage spans the January 2024 case window

## 3. Prepare non-ocean forcing if needed

Atmosphere staging:

```bash
python3 preprocessing/download_era5_staged.py
```

Atmosphere forcing:

```bash
python3 preprocessing/create_atm_forcing_from_era5.py
python3 preprocessing/create_rad_forcing_from_era5.py
```

Tides:

```bash
python3 preprocessing/create_tides_from_tpxo.py
```

River/source forcing:

```bash
python3 preprocessing/stage_source_discharge.py
```

Gate:

- `data/raw/atmosphere/era5_atm_202401.nc`
- `data/raw/atmosphere/era5_rad_202401.nc`
- `data/raw/tides/tpxo9_fukushima_202401.nc`
- `data/raw/source/fukushima_discharge_202401.csv`

## 4. Convert ocean raw data to ROMS-ready input files

Initial file:

```bash
python3 preprocessing/create_ocean_ini_from_hycom.py
```

Boundary file:

```bash
python3 preprocessing/create_ocean_bry_from_hycom.py \
  --start 2024-01-01T00:00:00 \
  --stop 2024-01-31T23:00:00
```

Expected outputs:

- `input/roms_ini_20240101.nc`
- `input/roms_bdy_202401.nc`

Gate:

- source times recorded in file metadata are reasonable
- dimensions match the active 500 m smoothed grid

## 5. Validate ROMS-ready inputs

Run:

```bash
python3 preprocessing/validate_roms_ready_inputs.py
```

Gate:

- no missing variables
- time ranges print cleanly for `ini`, `bry`, `atm`, `rad`, `river`
- `river_dye_01` units remain `Bq meter-3`

## 6. Regenerate the run infile if forcing changed

1-day pilot:

```bash
python3 preprocessing/create_pilot_infile.py \
  --mode pilot_1day \
  --forcing-mode external
```

Monthly pilot:

```bash
python3 preprocessing/create_pilot_infile.py \
  --mode pilot_month \
  --forcing-mode external
```

Expected outputs under `run/`:

- `ocean_fukushima_202401_pilot_1day.in`
- `ocean_fukushima_202401_pilot.in`

## 7. Build ROMS executable for the external-forcing case

Run:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m/run
bash build_roms_fukushima.sh --external -noclean -j 4
```

Expected executable:

- `run/romsM_external`

## 8. Run a 1-day pilot before the monthly case

Run:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
bash run/run_pilot_1day.sh
```

Gate:

- ROMS starts and finishes without boundary, forcing, or tracer input errors
- log tail looks clean in `output/pilot_1day_run.log`

## 9. Run the monthly January pilot

Run from `run/` after the 1-day pilot is stable:

```bash
./romsM_external ocean_fukushima_202401_pilot.in
```

Recommended:

- redirect stdout/stderr to `output/` or `logs/`
- monitor CFL, open-boundary warnings, NaN blow-up, and tracer extrema

## 10. Final acceptance before moving beyond the pilot

- January pilot completes for the full configured window
- output files are readable with `netCDF4.Dataset`
- passive tracer remains finite
- any remaining masked regions are explainable by coastline and open-boundary geometry
- only after this should the workflow be cloned to a finer-resolution case
