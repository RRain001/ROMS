# Real Preprocessing Entrypoints

Date: 2026-06-25

Remote project:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## What Was Added

The project now has entrypoints for moving from an idealized plumbing pilot toward a real-data ROMS setup:

- `preprocessing/validate_staged_data.py`
- `preprocessing/create_grid_from_bathymetry.py`
- `config/staged_data_manifest.csv`
- `docs/staged_data_layout.md`
- `data/raw/` staging directories

These scripts do not download external data. They assume external datasets are staged on the remote host first.

## Staged Data Validation

Command:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/validate_staged_data.py
```

Current verified result:

```text
required_missing=7
optional_missing=0
VALIDATE_EXIT=2
```

The missing required groups are:

- bathymetry
- ocean initial
- ocean boundary
- atmosphere
- radiation
- tides
- source discharge

This is expected because no real GEBCO/HYCOM/CMEMS/ERA5/TPXO/source-discharge files are currently staged on the remote host.

## Bathymetry Grid Generation

Default command after staging GEBCO-style bathymetry:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/create_grid_from_bathymetry.py --resolution-key pilot
```

Expected default input:

- `data/raw/bathymetry/gebco_fukushima.nc`

Default output:

- `input/roms_grid_bathy_500m.nc`

250 m candidate:

```bash
python3 preprocessing/create_grid_from_bathymetry.py --resolution-m 250
```

Requested 50 m target:

```bash
python3 preprocessing/create_grid_from_bathymetry.py --resolution-key target
```

Use 50 m only after the forcing chain and storage budget are resolved.

## Verified Script Behavior

No-data case:

```text
bathymetry file not found: /home/lhy/ROMS/projects/fukushima_202401_50m/data/raw/bathymetry/gebco_fukushima.nc
Stage GEBCO/ETOPO-style NetCDF first, or pass --bathymetry /path/to/file.nc
GRID_EXIT=1
```

Synthetic bathymetry functional test:

```text
bathymetry=/tmp/synthetic_gebco_fukushima.nc
bathymetry_variable=elevation
resolution_m=1000.0
Lm=178 Mm=223 xi_rho=180 eta_rho=225
water_fraction=1.0000
h_min=50.014 h_max=109.986
output=/tmp/roms_grid_synthetic_1000m.nc
wrote /tmp/roms_grid_synthetic_1000m.nc
grid 180 225
h 50.01422882080078 109.98638916015625
mask_mean 1.0
```

The synthetic test wrote to `/tmp`, not to project `input/`, so it does not replace the current pilot grid.

## Next Real-Data Step

Stage bathymetry first. Once `data/raw/bathymetry/gebco_fukushima.nc` exists and passes validation, generate `input/roms_grid_bathy_500m.nc`, inspect the land mask near Fukushima, then update downstream scripts to use the real grid instead of `input/roms_grid_idealized_500m.nc`.
