# Next Remote Bathymetry Commands

This folder is a staging artifact created locally because the current Codex
session could not request more network/write escalations.

When approvals/network are available again, copy
`fetch_and_subset_etopo.py` to the remote project and run:

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m
mkdir -p data/raw/bathymetry
python3 preprocessing/fetch_and_subset_etopo.py \
  --work-dir data/raw/bathymetry \
  --output gebco_fukushima.nc
python3 preprocessing/validate_staged_data.py
python3 preprocessing/create_grid_from_bathymetry.py \
  --bathymetry data/raw/bathymetry/gebco_fukushima.nc \
  --resolution-key pilot
```

Expected first output:

- `data/raw/bathymetry/gebco_fukushima.nc`
- `input/roms_grid_bathy_500m.nc`

Then inspect:

```bash
python3 - <<'PY'
from netCDF4 import Dataset
p = "input/roms_grid_bathy_500m.nc"
with Dataset(p) as ds:
    h = ds.variables["h"][:]
    m = ds.variables["mask_rho"][:]
    print("dims", len(ds.dimensions["xi_rho"]), len(ds.dimensions["eta_rho"]))
    print("h_min_max", float(h.min()), float(h.max()))
    print("water_fraction", float(m.mean()))
PY
```

Notes:

- The helper currently uses NOAA ETOPO 2022 60 arc-second bathymetry mirrors.
- ETOPO 60s is coarser than the 500 m grid. It is acceptable only for testing
  the real-data grid chain. Replace with higher-resolution GEBCO before
  production or any 50 m nested run.
