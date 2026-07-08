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
- `GLORYS12V1` default margin is configured in `glorys12v1_download_config.json` and should normally be larger than the active ROMS grid because the source is daily 1/12-degree data.
- `GLORYS12V1` boundary staging defaults to `boundary_download_strategy: "domain"`, so the downloader retrieves the buffered active-domain subset and the ROMS boundary generator slices the four open boundaries from that staged file.
- Set `boundary_download_strategy: "edge_bands"` only when a large domain needs the legacy four-edge strip downloads; in that mode `boundary_band_buffer_points` controls the strip width.
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

GLORYS12V1 notes:

- GLORYS12V1 is the default ocean source. HYCOM is used only through HYCOM-specific scripts or `--ocean-source hycom`.
- The GLORYS downloader uses the `copernicusmarine` CLI and the `GLOBAL_MULTIYEAR_PHY_001_030` product by default.
- `time_start` and `time_stop` may be omitted from `glorys12v1_download_config.json`; in that case the case time window from `project_parameters.json` is used.
- Staged GLORYS files live under `data/raw/ocean/glorys12v1` by default and are converted to source-suffixed ROMS files such as `roms_ini_<prefix>_glorys12v1_<date>.nc` and `roms_bdy_<prefix>_glorys12v1_<window>.nc`.
- Legacy GLORYS products can be bridged with explicit `paths.staged_initial`, `paths.staged_boundary`, `paths.staged_static`, `paths.roms_ini`, or `paths.roms_bdy` overrides in `glorys12v1_download_config.json`; new workflows should prefer canonical names.
