# Data_pre Overview

`Data_pre` is organized as a general ROMS preprocessing framework:

- `core/`: shared path resolution, schema normalization, and naming rules
- `scripts/`: stable CLI entrypoints
- `cases/`: case metadata and case-specific docs
- `impl/`: implementation modules used by the public entrypoints

Framework defaults:

- case configuration lives in `cases/<case_name>/config/project_parameters.json`
- shared large bathymetry can live outside projects, for example `/workspace/GEBCO/GEBCO_2026.nc`
- output filenames are derived from `case.slug` and `naming.*`, not from hardcoded region names

Framework responsibility boundary:

- `Data_pre` includes upstream data download, offline shared-dataset staging, raw-data subsetting, bathymetry preprocessing, grid generation, forcing generation, validation, and run-file assembly
- `Data_pre` does not include ROMS compilation, cluster submission, actual model runs, or runtime stability tuning

Operational target:

- input: case configuration plus accessible source datasets
- output: a validated ROMS handoff package consisting of `data/raw/...`, ROMS-ready `input/...`, `run/*.in`, and a readiness report
