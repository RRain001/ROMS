# Staged External Data Layout

Date: 2026-06-25

Remote project:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## Purpose

The current remote project can run a technical ROMS smoke test, but it does not yet have real external data. To avoid mixing raw data, derived ROMS inputs and outputs, stage external data under `data/raw/` and write derived files under `input/`.

## Directory Convention

```text
data/
├── raw/
│   ├── bathymetry/
│   │   └── gebco_fukushima.nc
│   ├── ocean/
│   │   ├── ocean_initial_20240101.nc
│   │   └── ocean_boundary_202401.nc
│   ├── atmosphere/
│   │   ├── era5_atm_202401.nc
│   │   └── era5_rad_202401.nc
│   ├── tides/
│   │   └── tpxo9_fukushima_202401.nc
│   └── source/
│       └── fukushima_discharge_202401.csv
└── processed/
```

Manifest:

- `config/staged_data_manifest.csv`

Validation command:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/validate_staged_data.py
```

Expected current result:

- non-zero exit
- missing required data

That is correct until the real data files are staged.

## Real Bathymetry Grid Entry

Once `data/raw/bathymetry/gebco_fukushima.nc` exists, generate a real grid with:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
python3 preprocessing/create_grid_from_bathymetry.py --resolution-key pilot
```

For a 250 m candidate:

```bash
python3 preprocessing/create_grid_from_bathymetry.py --resolution-m 250
```

For the requested 50 m target, run only after storage and forcing feasibility are resolved:

```bash
python3 preprocessing/create_grid_from_bathymetry.py --resolution-key target
```

## Notes

- The bathymetry script assumes rectilinear lon/lat bathymetry and GEBCO-style elevation by default: positive land, negative ocean.
- If the staged bathymetry uses depth positive downward, pass `--depth-positive-down`.
- The output grid is `input/roms_grid_bathy_<resolution>m.nc`.
- This only solves grid/bathymetry. Ocean boundary, atmosphere, radiation, tide and source discharge still need separate preprocessing.
