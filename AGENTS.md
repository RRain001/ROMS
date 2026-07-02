# AGENTS.md

## Project Scope

This repository contains a case-driven ROMS workflow split into three stages:

- `Data_pre`: prepares staged data and ROMS-ready inputs.
- `ROMS_Build`: builds a case-specific ROMS executable.
- `ROMS_Run`: validates and launches case runs.

Use `Data_pre/cases/<case_name>/config` as the authoritative runtime configuration source. Treat `projects/<case_name>/config` as a legacy copy or generated snapshot unless a user explicitly asks otherwise.

## Default Case Contract

- Resolve cases with `--case-name <case_name>` whenever possible.
- Keep generated products under `projects/<case_name>`.
- Default vertical levels are `vertical.N = 30` unless a case explicitly overrides this in `project_parameters.json`.
- Default ocean source is HYCOM. GLORYS12V1 code may remain, but it must be explicit opt-in via configuration or `--ocean-source glorys12v1`.
- Prefer case naming helpers from `Data_pre/core/case_naming.py` over hard-coded filenames.

## FDNPP Notes

- FDNPP research domain:
  - longitude: `140.88` to `142.0`
  - latitude: `37.0` to `37.84`
  - time window: `2025-01-01T00:00:00` to `2025-02-01T00:00:00`
- For FDNPP validation, use its `Data_pre` configuration and data products.
- Do not depend on historical FDNPP build artifacts. Rebuild through `ROMS_Build` when a binary is needed.
- The preferred FDNPP active grid is `input/roms_grid_bathy_500m_maskclean_smoothed.nc`.

## Build And Run Defaults

- Build with 4 parallel jobs by default. The standard command is:
  - `python3 ROMS_Build/scripts/build/build_roms_case.py --case-name <case_name>`
- Run with 4 MPI ranks by default. The standard dry-run command is:
  - `python3 ROMS_Run/scripts/run/run_case.py --case-name <case_name> --mode pilot_1day --dry-run`
- The standard executable location is `projects/<case_name>/bin/<executable>`.
- The standard build directory is `projects/<case_name>/build/Build_romsM`.
- Runtime logs belong in `projects/<case_name>/logs`; ROMS NetCDF outputs belong in `projects/<case_name>/output`.

## Validation Expectations

Before claiming a case is ready, run the relevant lightweight checks:

- `python3 Data_pre/scripts/validation/validate_staged_data.py --case-name <case_name> --ocean-source hycom`
- `python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name <case_name>`
- `python3 ROMS_Build/scripts/build/show_build_plan.py --case-name <case_name>`
- `python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name <case_name> --mode pilot_1day`

For code changes, run:

- `python3 -m py_compile $(find Data_pre ROMS_Build ROMS_Run -path '*/__pycache__' -prune -o -name '*.py' -print)`
- `git diff --check`

## Editing Guidance

- Keep changes case-driven and reusable.
- Do not introduce Fukushima, FDNPP, or other case-specific defaults into shared scripts.
- Preserve existing large data products unless the user explicitly asks to regenerate or replace them.
- Use compatibility aliases only as a transition aid; new standard workflows should generate and reference canonical names.
