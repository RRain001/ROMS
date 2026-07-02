# Data Sources

The framework currently supports these upstream source families:

- Bathymetry: offline GEBCO global NetCDF, default `/workspace/GEBCO/GEBCO_2026.nc`
- Ocean forcing: `HYCOM` and `GLORYS12v1`
- Atmospheric forcing: `ERA5`
- Tides: `TPXO9 atlas`
- Source discharge: staged CSV input

Responsibility rule:

- data download and offline shared-dataset preparation are part of `Data_pre`
- upstream access can be online download, authenticated API retrieval, or offline shared-file staging
- all source families should land in the case `data/raw/...` tree before conversion to ROMS-ready inputs

Bathymetry workflow:

- use the shared offline global file
- subset the active case domain from `domain.lon_*` and `domain.lat_*`
- write `data/raw/bathymetry/<naming.grid_subset_name>`

Raw download coverage rule:

- Ocean and atmosphere downloads should usually use a coverage box larger than the scientific study region.
- Default framework convention: derive the staged raw-download box from `project_parameters.json:domain.*`, then expand by source type.
- `HYCOM` default margin is `0.08°` on each side because the source grid is relatively fine.
- `ERA5` default margin is `0.25°` on each side because the source coverage itself is coarser.
- Use `staged_download_config.json:hycom_bbox_buffer_deg` or `era5_bbox_buffer_deg` to change those defaults when needed.
- Legacy `bbox_buffer_deg` is still accepted as a shared fallback override for older cases.
- Use an explicit `staged_download_config.json:bbox` only when a case needs a manually fixed download area.
- This buffer reduces edge-interpolation failures when converting staged data into ROMS boundary and forcing files.

The public entrypoints are grouped under `scripts/` by source family and workflow stage:

- bathymetry staging: `scripts/bathymetry/stage_and_subset_bathymetry.py`
- ocean downloads: `scripts/ocean/download_*.py`
- atmosphere downloads: `scripts/atmosphere/download_*.py`
- tides staging: `scripts/tides/stage_*.py`
- source staging: `scripts/source/stage_*.py`

Download completion inside `Data_pre` is not the final goal by itself. Raw products must still pass staged validation and then be converted into ROMS-ready files.
