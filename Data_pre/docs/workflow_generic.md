# Generic ROMS Case Workflow

This workflow is case-driven. Runtime configuration is read from
`Data_pre/cases/<case_name>/config`; `projects/<case_name>` stores generated
data, inputs, build artifacts, logs, and model outputs.

## Case Setup

1. Copy `Data_pre/cases/_template` to `Data_pre/cases/<case_name>`.
2. Edit `config/project_parameters.json`.
   - Set `case.name`, `case.slug`, `case.cpp_name`, and `naming.roms_prefix`.
   - The standard online profile uses `vertical.N = 40`, `theta_s = 7.0`,
     `theta_b = 0.1`, and `Tcline_m = 200.0` unless the case explicitly
     overrides these values.
   - Set `ocean.default_source` to `glorys12v1` for the standard workflow.
   - Set `paths.case_root` to `projects/<case_name>`.
3. Edit `config/staged_download_config.json` only for source windows, credentials, and staged raw paths.
4. Leave `config/staged_download_config.json` in place when HYCOM should be available as an explicit ocean-source fallback. `config/glorys12v1_download_config.json` controls the default GLORYS12V1 path; its time window defaults to `project_parameters.json:time` when `time_start` and `time_stop` are omitted.

Do not edit `projects/<case_name>/config` as a runtime input. If present, it is a
snapshot or legacy copy only.

## Standard Flow

Use `--case-name <case_name>` on all commands.

1. Stage or download source data with the `Data_pre/scripts/*` entrypoints.
2. Generate the grid, mask-cleaned grid, and smoothed grid.
3. Generate GLORYS12V1-derived initial and boundary files.
4. Generate ERA5, tides, and source/river inputs.
5. Generate ROMS `.in` files with `create_pilot_infile.py`.
6. Validate staged and ROMS-ready products.
7. Build with `ROMS_Build/scripts/build/build_roms_case.py`.
8. Validate and run with `ROMS_Run/scripts/*`.

## Defaults

- Ocean source: GLORYS12V1.
- Vertical levels: `N = 40`.
- Standard online physics profile: MY25/k-kl vertical mixing, Smagorinsky
  horizontal mixing with `C = 0.2`, `SSH_TIDES`, and `UV_TIDES`.
- Build artifacts: `projects/<case_name>/build/Build_romsM`.
- Executables: `projects/<case_name>/bin`.
- Run logs: `projects/<case_name>/logs`.
- Model NetCDF outputs: `projects/<case_name>/output`.

HYCOM remains available only through explicit `--ocean-source hycom` commands
and should not affect GLORYS12V1 validation.

## GLORYS12V1 Standard Flow

GLORYS12V1 uses the external `copernicusmarine` command-line tool. HYCOM remains available only when a command explicitly opts into HYCOM.

1. Download staged GLORYS subsets:
   `python3 Data_pre/scripts/ocean/download_glorys12v1_staged.py --case-name <case_name> --resume`
2. Convert staged GLORYS data to ROMS-ready ocean files:
   `python3 Data_pre/scripts/ocean/create_ocean_ini_from_glorys.py --case-name <case_name>`
   `python3 Data_pre/scripts/ocean/create_ocean_bry_from_glorys.py --case-name <case_name>`
3. Generate a GLORYS-backed ROMS input file:
   `python3 Data_pre/scripts/run_support/create_pilot_infile.py --case-name <case_name> --forcing-mode external --mode pilot_1day`
4. Validate GLORYS products:
   `python3 Data_pre/scripts/validation/validate_staged_data.py --case-name <case_name>`
   `python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name <case_name>`
