# ROMS Data Preprocessing Hub

`/home/lhy/ROMS/Data_pre` is a multi-case preprocessing framework for ROMS.

Its scope is:

- included: source-data download or offline dataset staging, raw-data organization, bathymetry and grid preprocessing, ROMS forcing/input generation, validation, and run-file assembly
- excluded: ROMS source-code compilation, MPI/job submission, actual model integration, and runtime stability tuning

In other words, `Data_pre` starts from case configuration and upstream datasets, and ends at a validated handoff package for the ROMS run layer.

Directory roles:

- `core/`: shared case resolution, naming, and reusable utilities
- `scripts/`: public entrypoints grouped by workflow family
- `cases/`: per-case configs, manifests, docs, and handoff conventions
- `impl/preprocessing/`: shared implementation backing the public scripts

Main workflow:

1. Download or stage upstream data into `data/raw/...`
2. Subset bathymetry with `stage_and_subset_bathymetry.py`
3. Build the raw ROMS grid with `create_grid_from_bathymetry.py`
4. Clean `mask_rho` with shoreline-assisted checks and optional manual edits via `clean_roms_mask.py`
5. Smooth bathymetry with `smooth_bathymetry.py` without changing mask
6. Audit bathymetry stability and grid quality with `audit_bathymetry_stability.py` and `check_roms_grid_quality.py`
7. Convert staged data into ROMS-ready `input/*.nc` and related CSV products
8. Validate staged and ROMS-ready products
9. Generate `run/*.in` and case-level readiness outputs

Grid-change note:

- If `clean_roms_mask.py` or `smooth_bathymetry.py` produces a new active grid, regenerate downstream forcing, boundary, initial, tides, and source files before running ROMS.

Run-support note:

- `scripts/ocean/create_ocean_ini_from_hycom.py` and `scripts/ocean/create_ocean_ini_from_glorys.py` are the scientific initial-condition entrypoints for real cases.
- `scripts/run_support/create_initial_nc.py` is `technical fallback only`: it writes a static placeholder `roms_ini_pilot.nc` for smoke tests and plumbing checks when real ocean initial fields are not yet staged.
- Do not treat `roms_ini_pilot.nc` as a scientific replacement for HYCOM/GLORYS-derived initial conditions.

Usage patterns:

- `python3 /home/lhy/ROMS/Data_pre/scripts/bathymetry/stage_and_subset_bathymetry.py --case-name <case_name>`
- `python3 /home/lhy/ROMS/Data_pre/scripts/ocean/download_hycom_staged.py --case-name <case_name>`
- `python3 /home/lhy/ROMS/Data_pre/scripts/validation/validate_staged_data.py --case-name <case_name>`
- `python3 /home/lhy/ROMS/Data_pre/scripts/run_support/create_pilot_infile.py --case-name <case_name>`

Case selection:

- prefer `--case-name <case_name>`
- optional `--case-root /home/lhy/ROMS/projects/<case_name>`
- fallback default case is read from `cases/default_case.txt`

Configuration source:

- runtime configuration is read from `Data_pre/cases/<case_name>/config`
- `projects/<case_name>/config`, when present, is a legacy snapshot and is not used by the shared entrypoints
- the standard ocean source is HYCOM unless a command explicitly opts into another source

To add a new region, start from `cases/_template/` and create a matching project directory under `/home/lhy/ROMS/projects/`.
