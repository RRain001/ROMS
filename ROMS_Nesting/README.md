# ROMS_Nesting — isolated Japan Sea workflow

Status: **I0 copied source scaffolding; numerical nesting NOT implemented or validated.**

This directory contains independent copies of the proven single-grid `Data_pre/`, `ROMS_Build/`, `ROMS_Run/`, and `roms_src/roms/`, plus a dedicated `JAPAN_SEA` case. It must not import or execute the corresponding original code outside `ROMS_Nesting/`. External read-only GEBCO/GSHHG/GLORYS12V1/ERA5/TPXO9 inputs may be shared; generated artifacts must remain under `ROMS_Nesting/projects/`.

**Development branch:** `feature/japan-sea-nesting`. **Baseline:** `main` commit `e8ab4486922ce340b710012e7a795ffa5cb8db43`. Original build/preprocess/run/source trees must remain untouched. The scientific ES3K rotated corners and L3 domain remain unresolved. No production simulation has been launched.

CI runs `scripts/check_isolation.py` and the copied WGS84 grid-metric regressions in an isolated directory. Run locally (from this directory):

```sh
python3 -m pip install numpy scipy netCDF4 pyproj pillow pytest
python3 scripts/check_isolation.py
python3 -m unittest discover -s Data_pre/tests -p 'test_grid_metrics.py' -v
```

The active `JAPAN_SEA` case settings are under `Data_pre/cases/JAPAN_SEA/config/`. During I0, the case domain is a **reference envelope only**, not an actual rotated ES3K grid. The date and nominal release location in that config are **non-scientific placeholders** that cannot be used for production releases.

Next stages: freeze MATLAB .m tool reference/algorithm inventory (I1); implement true rotated ROMS grids in this tree only (I2); ES3K/UD1K meshes (I3); meteorological, oceanic and tidal forcing and physical verification (I4 onward). See repository-root `嵌套实施计划.md`.
