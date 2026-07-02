# ROMS_Build

`ROMS_Build` is the shared ROMS compilation layer that sits beside `Data_pre`.

Responsibilities:

- resolve cases with the same `--case-name` / `--case-root` style used by `Data_pre`
- load build settings from `Data_pre/cases/<case_name>/config/roms_build_config.json`
- check compiler and library prerequisites
- compile ROMS into case-local `build/` and `bin/` directories
- inspect and clean case build artifacts

Non-goals:

- generating ROMS-ready forcing files
- launching model runs
- cluster scheduling or runtime tuning

Case products remain under `projects/<case_name>/`.
