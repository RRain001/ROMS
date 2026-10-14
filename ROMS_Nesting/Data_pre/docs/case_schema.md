# Case Schema

Each case is defined by `cases/<case_name>/config/project_parameters.json`.

Top-level sections:

- `case`: identity, title, CPP name, description
- `domain`: horizontal domain and source point
- `time`: simulation window and pilot timing controls
- `vertical`: ROMS sigma-coordinate settings
- `physics`: standard online physics profile settings such as MY25/k-kl
  vertical mixing, Smagorinsky mixing, and background mixing coefficients
- `tides`: tide forcing switches; `SSH_TIDES` and `UV_TIDES` are enabled by
  default and UV tide generation must be blocked rather than fabricated when
  TPXO current ellipses are missing
- `output`: history, average, and diagnostic output cadence
- `source`: source-kind and tracer/source metadata
- `naming`: filenames and prefixes for generated products
- `paths`: project root, ROMS source path, shared dataset paths

Source amount and placement:

- Define exactly one of `source.annual_release_PBq_per_year` or
  `source.annual_release_TBq_per_year`; shared source helpers convert either
  form to `Bq` and `Bq s-1`.
- `source.source_model = nearest_final_roms_wet_cell` means the configured
  `domain.source_lon/source_lat` is only a reference coordinate. Source files
  are generated after the final grid and use the nearest eligible
  `mask_rho=1` cell satisfying `h >= vertical.Hmin_m`.
- Generated source metadata records the snapped grid index, coordinates,
  depth, distance, placement rule, and grid path. A snap distance above the
  case warning threshold should be reported for review.

Spatial staging rule:

- `domain.*` defines the scientific study region used by ROMS grid generation.
- Raw-download coverage is normally derived automatically from `project_parameters.json:domain.*`.
- Source-specific coverage rule: when HYCOM is explicitly selected, it expands
  the study-region west/east/south/north boundaries by `0.08°`; ERA5 expands by
  `0.25°`.
- Put `hycom_bbox_buffer_deg` or `era5_bbox_buffer_deg` in `staged_download_config.json` when you want to override those source-specific defaults.
- Legacy `bbox_buffer_deg` is still accepted as a shared fallback override for older cases.
- Keep an explicit `bbox.*` in `staged_download_config.json` only for cases that need a nonstandard fixed download box.
- If a source product is coarse or the boundary interpolation is sensitive, increase the raw-download margin further instead of shrinking it to the exact study-region edge.

For a minimal starting point, copy `cases/_template/`.

Framework defaults and precedence:

- New cases default to `ocean.default_source = glorys12v1`.
- New cases default to `vertical.N = 40`, `Vtransform=2`, `Vstretching=4`,
  `theta_s=7.0`, `theta_b=0.1`, and `Tcline_m=200.0`.
- An explicit case value in `project_parameters.json` overrides a framework
  fallback. `--ocean-source` overrides the selected ocean source for one command.
- HYCOM is supported as an explicit fallback and is not the default source.

Lifecycle rule:

- `project_parameters.json` and the staged-download config together define a full `Data_pre` case lifecycle
- that lifecycle begins at data download or offline shared-dataset staging
- it ends when the case has validated ROMS-ready inputs, a generated `.in` file, and a readiness report for the ROMS run layer

Out of scope:

- case schema should not encode solver build recipes, MPI launch commands, or runtime stabilization procedures

Default online profile:

- New cases default to `N=40`, `Vtransform=2`, `Vstretching=4`,
  `theta_s=7.0`, `theta_b=0.1`, and `Tcline_m=200.0`.
- New cases default to MY25/k-kl vertical mixing, Smagorinsky horizontal
  mixing with ROMS source-level `SmagorCoef = 0.2`, and SSH+UV tides.
