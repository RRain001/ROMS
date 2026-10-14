# Adding a New ROMS Case

This is the canonical onboarding guide for a new research region. Runtime
configuration belongs in `Data_pre/cases/<case_name>/config`; generated data,
inputs, binaries, logs, and outputs belong in `projects/<case_name>`.

For a complete worked example of spatial design, time windows, GLORYS time
conversion, cold/spin-up/hot-start sequencing, source placement, and readiness
pitfalls, see `Data_pre/docs/fdnpp_case_reference.md`. Treat its Fukushima
domain, source amount, grid size, and 56-core layout as case-specific examples,
not defaults to copy unchanged.

For a second worked example focused on real-coastline/bathymetry correction,
500 m grid construction, TPXO longitude conventions, PBq source conversion,
staged downloads, and restart handoff checks, see
`Data_pre/docs/lahague_case_build_experience.md`.

## 1. Create the case configuration

Copy the template and use a case name that is stable, descriptive, and unique:

```bash
cp -a Data_pre/cases/_template Data_pre/cases/<case_name>
```

Edit `config/project_parameters.json` and set at least:

- `case.name`, `case.slug`, `case.cpp_name`, and `case.title`
- `domain.lon_min`, `domain.lon_max`, `domain.lat_min`, `domain.lat_max`
- `domain.target_resolution_m` and `domain.pilot_resolution_m`
- `time.start` and `time.stop`
- `paths.case_root` to `/home/lhy/ROMS/projects/<case_name>`
- `naming.grid_subset_name` and `naming.roms_prefix`
- `domain.source_lon/source_lat` as a reference coordinate only when the case
  has a point source; the final model source must be snapped on the final wet
  ROMS grid.

Unless the case has a documented scientific reason to override them, use:

- `ocean.default_source = "glorys12v1"`
- `vertical.N = 40`
- `Vtransform = 2`, `Vstretching = 4`
- `theta_s = 7.0`, `theta_b = 0.1`, `Tcline_m = 200.0`

The command-line `--ocean-source` selection has highest precedence, followed by
the case value, followed by the framework fallback. HYCOM is supported with an
explicit `--ocean-source hycom` selection.

## 2. Configure source-specific staging

Keep `glorys12v1_download_config.json` for the default ocean chain. Its time
window inherits `project_parameters.json:time` unless explicitly set.

Keep `staged_download_config.json` only when the case needs the HYCOM fallback
chain, ERA5 settings, or legacy staged paths. Its HYCOM paths must not be
described as the active default for a GLORYS case.

Configure the remaining source families for the same domain and time window:

1. GEBCO bathymetry and GSHHG shoreline data
2. GLORYS12V1 ocean initial, boundary, and static data
3. ERA5 atmosphere and radiation data
4. TPXO tidal elevation/current data required by the selected CPP options
5. Source-discharge CSV and passive-tracer settings, if applicable

For annual activity, use exactly one of
`source.annual_release_PBq_per_year` or
`source.annual_release_TBq_per_year`. The shared conversion helper accepts
both units and writes the resulting `Bq s-1` value to generated metadata.

## 3. Prepare the grid and ROMS-ready inputs

Run the workflow in order:

```bash
python3 Data_pre/scripts/bathymetry/stage_and_subset_bathymetry.py --case-name <case_name>
python3 Data_pre/scripts/bathymetry/create_grid_from_bathymetry.py --case-name <case_name>
python3 Data_pre/scripts/bathymetry/clean_roms_mask.py --case-name <case_name>
python3 Data_pre/scripts/bathymetry/smooth_bathymetry.py --case-name <case_name>
python3 Data_pre/scripts/ocean/download_glorys12v1_staged.py --case-name <case_name> --resume
python3 Data_pre/scripts/ocean/create_ocean_ini_from_glorys.py --case-name <case_name>
python3 Data_pre/scripts/ocean/create_ocean_bry_from_glorys.py --case-name <case_name>
python3 Data_pre/scripts/atmosphere/download_era5_staged.py --case-name <case_name>
python3 Data_pre/scripts/atmosphere/create_atm_forcing_from_era5.py --case-name <case_name>
python3 Data_pre/scripts/atmosphere/create_rad_forcing_from_era5.py --case-name <case_name>
python3 Data_pre/scripts/tides/stage_tpxo_elevation_atlas.py --case-name <case_name>
python3 Data_pre/scripts/tides/create_tides_from_tpxo.py --case-name <case_name>
python3 Data_pre/scripts/run_support/create_pilot_infile.py --case-name <case_name> --forcing-mode external --mode pilot_1day
```

If the case uses source discharge or passive tracers, generate and validate
those products before assembling the final run files. When a new active grid is
created by mask cleaning or smoothing, regenerate all downstream forcing files.

For formal spin-up/production cases, generate each phase's GLORYS initial and
boundary products explicitly. The spin-up `.in` file must use the spin-up
window products, while production must hot-start from the final spin-up
restart.

## 4. Validate, build, and run

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py --case-name <case_name>
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name <case_name>
python3 ROMS_Build/scripts/build/show_build_plan.py --case-name <case_name>
python3 ROMS_Build/scripts/build/build_roms_case.py --case-name <case_name>
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name <case_name> --mode pilot_1day
python3 ROMS_Run/scripts/run/run_case.py --case-name <case_name> --mode pilot_1day --dry-run
```

Use the real MPI launch only after the dry-run and prerequisite checks pass.
Record the source, vertical configuration, generated products, validation
results, and remaining limitations in the case readiness report.

## Completion checklist

- Case configuration is under `Data_pre/cases/<case_name>/config`.
- Generated products are under `projects/<case_name>`.
- Effective source and `N` are recorded in the readiness report.
- The active grid has passed mask and bathymetry checks.
- ROMS-ready initial, boundary, atmosphere, radiation, tide, and source files
  have passed validation.
- Generated `.in` files reference canonical source-aware filenames.
- Build plan and run prerequisites pass for the selected mode.
