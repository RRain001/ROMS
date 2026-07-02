# Case Template

Create a new case by copying this directory to `cases/<case_name>/`.

Required minimum:

- `config/project_parameters.json`
- `config/roms_build_config.json`
- `config/roms_run_config.json`
- Optional case docs under `docs/`
- Optional manifests under `manifests/`
- A case-level readiness report should be produced once preprocessing is complete

Key fields:

- `case.name`: canonical case directory name
- `case.slug`: short prefix used in output filenames
- `case.cpp_name`: ROMS CPP app name
- `naming.grid_subset_name`: subset bathymetry filename
- `paths.case_root`: target project directory under `/home/lhy/ROMS/projects/`

Case lifecycle:

1. Download or stage upstream data into `data/raw/...`
2. Generate ROMS-ready files under `input/...`
3. Generate run files under `run/`
4. Compile case-local executables into `bin/` through `ROMS_Build`
5. Launch smoke or pilot runs through `ROMS_Run`
6. Record handoff status in a readiness report

Out of scope for the case template:

- ROMS executable build instructions
- MPI launch commands
- runtime stability tuning notes
