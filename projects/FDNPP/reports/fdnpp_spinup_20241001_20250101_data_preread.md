# FDNPP Spin-up Data Preread

- case: `FDNPP`
- profile: `online_my25_uvtide`
- audit_window: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00`
- production_window_remains: `2025-01-01T00:00:00` -> `2025-02-01T00:00:00`
- generated_from: read-only audit of `Data_pre`, case config, and existing case products

## Summary

- Current FDNPP staged/raw/input products are still centered on the production January 2025 window.
- Existing `Data_pre` flow can already stage HYCOM for an arbitrary window when `--start/--stop` and custom output paths are passed.
- Existing HYCOM ROMS boundary generation can already subset an arbitrary time window when `--start/--stop` are passed.
- Existing ERA5 staging, HYCOM initial generation, source generation, and tide zero-phase handling are still tied to case-config time unless extended.
- Existing `online_my25_uvtide` January 2025 files are at overwrite risk if default output names are reused; custom spin-up filenames are required.

## Required Spin-up Inputs

- ocean initial at `2024-10-01T00:00:00`
- ocean boundary covering `2024-10-01T00:00:00` -> `2025-01-01T00:00:00`
- atmospheric forcing covering `2024-10-01T00:00:00` -> `2025-01-01T00:00:00`
- radiation forcing covering `2024-10-01T00:00:00` -> `2025-01-01T00:00:00`
- tide forcing compatible with spin-up `TIME_REF/TIDE_START`
- zero-release river/source file for spin-up while preserving `dye_01`

## Existing Coverage

- raw HYCOM initial: `projects/FDNPP/data/raw/ocean/hycom_initial_20250101.nc`
  coverage: `2025-01-01T00:00:00`
- raw HYCOM boundary: `projects/FDNPP/data/raw/ocean/hycom_boundary_202501.nc`
  coverage: `2025-01-01T00:00:00` -> `2025-02-01T00:00:00`
- raw ERA5 atm: `projects/FDNPP/data/raw/atmosphere/era5_atm_fdnpp_202501.nc`
  coverage: `2025-01-01T00:00:00` -> `2025-02-01T00:00:00`
- raw ERA5 rad: `projects/FDNPP/data/raw/atmosphere/era5_rad_fdnpp_202501.nc`
  coverage: `2025-01-01T00:00:00` -> `2025-02-01T00:00:00`
- staged TPXO with UV tides: `projects/FDNPP/data/raw/tides/tpxo9_fdnpp_202501_online_my25_uvtide.nc`
  coverage: atlas-based, not month-limited
- production discharge CSV: `projects/FDNPP/data/raw/source/fdnpp_source_discharge.csv`
  coverage: `2025-01-01T00:00:00` -> `2025-02-01T00:00:00`
- existing ROMS input files:
  - `projects/FDNPP/input/roms_ini_fdnpp_20250101_online_my25_uvtide.nc`
  - `projects/FDNPP/input/roms_bdy_fdnpp_202501_online_my25_uvtide.nc`
  - `projects/FDNPP/input/roms_atm_fdnpp_202501.nc`
  - `projects/FDNPP/input/roms_rad_fdnpp_202501.nc`
  - `projects/FDNPP/input/roms_tides_fdnpp_202501_online_my25_uvtide.nc`
  - `projects/FDNPP/input/roms_rivers_production_online_my25_uvtide.nc`

## Missing Months

- HYCOM raw/input: missing `2024-10`, `2024-11`, `2024-12`
- ERA5 raw/input: missing `2024-10`, `2024-11`, `2024-12`
- source discharge CSV for production-style release: missing `2024-10`, `2024-11`, `2024-12`
- tide atlas data: no missing months, but ROMS tide file zero-phase should be reviewed for spin-up start

## Capability Audit

- HYCOM ocean download/staging:
  - reusable now: `Data_pre/scripts/ocean/download_hycom_staged.py`
  - reason: already supports `--start`, `--stop`, `--initial-output`, `--boundary-output`
- HYCOM initial generation:
  - needs extension
  - reason: `create_ocean_ini_from_hycom.py` selects the snapshot nearest `project_parameters.time.start`
- HYCOM boundary generation:
  - reusable now: `Data_pre/scripts/ocean/create_ocean_bry_from_hycom.py`
  - reason: already supports `--start`, `--stop`, `--output`
- ERA5 download/staging:
  - needs extension
  - reason: `download_era5_staged.py` only reads the time window from `staged_download_config.json`
- ERA5 ROMS forcing generation:
  - reusable now with custom output paths after raw staging exists
  - note: current workflow produces separate `atm` and `rad` files, not a merged `frc` file
- TPXO stage:
  - reusable now
  - note: atlas is effectively year-independent for this task
- TPXO ROMS tide generation:
  - needs extension for explicit spin-up zero-phase date
  - reason: `create_tides_from_tpxo.py` writes `zero_phase_date` from case start in `project_parameters.json`
- river/source generation:
  - needs extension
  - reason: current production script requires a discharge CSV and generates non-zero `river_dye_01`
- validation:
  - needs extension
  - reason: current validators focus on default case-window filenames and do not enforce spin-up-specific time coverage or zero-release checks

## Naming And Overwrite Risk

- Current naming helpers derive labels from `project_parameters.time`.
- Default FDNPP case time is still January 2025, so default output names resolve to the existing production/test files.
- Overwrite-sensitive files:
  - `projects/FDNPP/input/roms_ini_fdnpp_20250101_online_my25_uvtide.nc`
  - `projects/FDNPP/input/roms_bdy_fdnpp_202501_online_my25_uvtide.nc`
  - `projects/FDNPP/input/roms_tides_fdnpp_202501_online_my25_uvtide.nc`
  - `projects/FDNPP/input/roms_rivers_production_online_my25_uvtide.nc`
- Safe approach:
  - use explicit spin-up filenames containing `20241001` or `20241001_20250101`
  - do not modify existing January 2025 `online_my25_uvtide` products in place

## Preliminary Conclusion

- Spin-up data preparation is feasible without redesigning the workflow.
- The minimal safe implementation path is:
  - add explicit time-window overrides where missing
  - add zero-release source generation
  - add spin-up-specific validation/reporting
  - generate all spin-up products under distinct filenames
- `online_spinup_3mo_my25_uvtide` should not be declared ready until those products exist and validation passes.
