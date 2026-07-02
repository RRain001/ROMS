# Generic ROMS Case Workflow

This workflow is case-driven. Runtime configuration is read from
`Data_pre/cases/<case_name>/config`; `projects/<case_name>` stores generated
data, inputs, build artifacts, logs, and model outputs.

## Case Setup

1. Copy `Data_pre/cases/_template` to `Data_pre/cases/<case_name>`.
2. Edit `config/project_parameters.json`.
   - Set `case.name`, `case.slug`, `case.cpp_name`, and `naming.roms_prefix`.
   - Keep `vertical.N` at `30` unless the case explicitly needs another level count.
   - Set `ocean.default_source` to `hycom` for the standard workflow.
   - Set `paths.case_root` to `projects/<case_name>`.
3. Edit `config/staged_download_config.json` only for source windows, credentials, and staged raw paths.

Do not edit `projects/<case_name>/config` as a runtime input. If present, it is a
snapshot or legacy copy only.

## Standard Flow

Use `--case-name <case_name>` on all commands.

1. Stage or download source data with the `Data_pre/scripts/*` entrypoints.
2. Generate the grid, mask-cleaned grid, and smoothed grid.
3. Generate HYCOM-derived initial and boundary files.
4. Generate ERA5, tides, and source/river inputs.
5. Generate ROMS `.in` files with `create_pilot_infile.py`.
6. Validate staged and ROMS-ready products.
7. Build with `ROMS_Build/scripts/build/build_roms_case.py`.
8. Validate and run with `ROMS_Run/scripts/*`.

## Defaults

- Ocean source: HYCOM.
- Vertical levels: `N = 30`.
- Build artifacts: `projects/<case_name>/build/Build_romsM`.
- Executables: `projects/<case_name>/bin`.
- Run logs: `projects/<case_name>/logs`.
- Model NetCDF outputs: `projects/<case_name>/output`.

GLORYS12V1 remains available only through explicit `--ocean-source glorys12v1`
commands and should not affect HYCOM validation.
