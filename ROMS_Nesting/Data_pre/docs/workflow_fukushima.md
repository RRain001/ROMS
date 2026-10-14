# Shared Workflow (legacy filename)

This filename is retained for compatibility with older links. The canonical
generic workflow is documented in `Data_pre/docs/workflow_generic.md`; current
framework defaults are GLORYS12V1 and `N=40`.

This document now serves as the shared preprocessing workflow reference for `Data_pre`.

Scope boundary:

- `Data_pre` includes download and staging of upstream datasets
- `Data_pre` ends after validated ROMS inputs and run files are generated
- ROMS compile and actual model execution belong to the downstream run layer

Common workflow chain:

1. Select a case with `--case-name <case_name>`.
2. Download or stage upstream raw data by family:
   - bathymetry: stage from the shared offline GEBCO global file under `/workspace/GEBCO/GEBCO_2026.nc`
   - ocean: `scripts/ocean/download_glorys12v1_staged.py`
     (HYCOM is an explicit fallback via `--ocean-source hycom`)
   - atmosphere: `scripts/atmosphere/download_era5_staged.py`
   - tides: `scripts/tides/stage_tpxo_elevation_atlas.py`
   - source: `scripts/source/stage_source_discharge.py`
3. Validate staged raw coverage and presence with:
   - `scripts/validation/validate_staged_data.py`
   - `scripts/validation/validate_staged_data_deep.py`
4. Build the pilot grid with `scripts/bathymetry/create_grid_from_bathymetry.py`.
5. Clean `mask_rho` with `scripts/bathymetry/clean_roms_mask.py` using GSHHG shoreline assistance plus optional manual edits.
6. Smooth and audit the grid with:
   - `scripts/bathymetry/smooth_bathymetry.py`
   - `scripts/bathymetry/audit_bathymetry_stability.py`
   - `scripts/check_roms_grid_quality.py`
7. Convert staged data into ROMS-ready inputs:
   - ocean: `create_ocean_ini_*`, `create_ocean_bry_*`
   - atmosphere: `create_atm_forcing_from_era5.py`, `create_rad_forcing_from_era5.py`
   - tides: `create_tides_from_tpxo.py`
   - source: `create_source_timeseries.py`, `create_river_source_nc.py`, `create_river_source_production.py`
8. Validate ROMS-ready results with:
   - `scripts/validation/validate_roms_ready_inputs.py`
9. Generate run files with `scripts/run_support/create_pilot_infile.py`.
10. Write a case-level readiness report for handoff to the ROMS run layer.

Notes:

- Public defaults are driven by `cases/<case_name>/config/project_parameters.json`.
- Case-specific procedures should live under `cases/<case_name>/docs/`.
- Fukushima remains a real case, but this document is no longer Fukushima-specific.
- If a cleaned or smoothed grid replaces the previous active grid, regenerate downstream forcing, bry, ini, tide, and source files.
