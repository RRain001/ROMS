# Remote ROMS Directory Map

Updated: 2026-06-25

## Canonical Paths

- Active Fukushima ROMS project:
  - `/home/lhy/ROMS/projects/fukushima_202401_50m`
- Study/notes archive copied from local thesis directory:
  - `/home/lhy/ROMS/ROMS_study`
- ROMS source tree:
  - `/home/lhy/ROMS/roms_src/roms`
- Existing working UPWELLING case:
  - `/home/lhy/ROMS/roms_work`

## Canonical Use Rules

- Treat `/home/lhy/ROMS/projects/fukushima_202401_50m` as the only write-active project directory for the Fukushima implementation.
- Treat `/home/lhy/ROMS/ROMS_study` as read-mostly notes, audit trail, and methods material.
- Treat `/home/lhy/ROMS/roms_src/roms` as upstream source, not as the place to edit project-specific inputs.
- Treat `/home/lhy/ROMS/roms_work` as reference environment only.

## Fukushima Project Layout

Project root:

- `config/`
  - `project_parameters.json`
  - `data_sources_required.csv`
  - `staged_data_manifest.csv`
- `preprocessing/`
  - `create_idealized_grid.py`
  - `create_initial_nc.py`
  - `create_river_source_nc.py`
  - `create_pilot_infile.py`
  - `create_grid_from_bathymetry.py`
  - `validate_staged_data.py`
  - `fetch_and_subset_etopo.py`
- `data/raw/`
  - `bathymetry/ETOPO_2022_v1_60s_N90W180_bed.nc`
  - `bathymetry/gebco_fukushima.nc`
  - other raw forcing directories prepared but still empty
- `input/`
  - `roms_grid_idealized_500m.nc`
  - `roms_grid_bathy_500m.nc`
  - `roms_ini_pilot.nc`
  - `roms_rivers_pilot.nc`
- `run/`
  - `fukushima_202401.h`
  - `ocean_fukushima_202401_pilot.in`
  - `ocean_fukushima_202401_smoke.in`
  - `build_roms_fukushima.sh`
  - `run_smoke.sh`
  - `romsM`
  - `varinfo.yaml`
- `output/`
  - smoke outputs from idealized-grid run
- `docs/`
  - current project-level findings and handoff docs

## Duplicate Top-Level Files

These top-level files exist under `/home/lhy/ROMS/` but are not the canonical working copies:

- `/home/lhy/ROMS/ETOPO_2022_v1_60s_N90W180_bed.nc`
- `/home/lhy/ROMS/fetch_and_subset_etopo.py`
- `/home/lhy/ROMS/NEXT_REMOTE_COMMANDS.md`

Canonical replacements already exist inside the project:

- `data/raw/bathymetry/ETOPO_2022_v1_60s_N90W180_bed.nc`
- `preprocessing/fetch_and_subset_etopo.py`
- project `docs/` and `ROMS_study/07_fukushima_pilot/` for instructions

Recommendation:

- Leave the top-level duplicates untouched for now.
- Use the project-local copies going forward.

## Notes Archive Layout

`/home/lhy/ROMS/ROMS_study` mirrors the local thesis note tree:

- `00_source_inventory/` to `06_preprocessing_tools/`: ROMS and `my_roms_tools` study notes
- `07_fukushima_pilot/`: Fukushima-specific pilot, preprocessing, metadata, and validation notes

For remote Codex CLI, read in this order:

1. `/home/lhy/ROMS/ROMS_study/07_fukushima_pilot/real_preprocessing_entrypoints.md`
2. `/home/lhy/ROMS/ROMS_study/07_fukushima_pilot/production_preprocessing_requirements.md`
3. `/home/lhy/ROMS/projects/fukushima_202401_50m/docs/REMOTE_CODEX_CLI_HANDOFF.md`
