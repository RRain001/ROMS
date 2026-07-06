#!/usr/bin/env python3
"""Create a minimal idealized ROMS initial file for the active pilot case."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import get_case_config_path, get_case_root
from case_naming import load_case_naming
from pilot_grid_utils import resolve_active_pilot_grid
from radioactive_decay import radioactive_decay_attrs


ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")
OUT = ROOT / "input" / "roms_ini_pilot.nc"


def days_since_year1(dt: datetime) -> float:
    origin = datetime(1, 1, 1)
    return (dt - origin).total_seconds() / 86400.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(OUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    p = json.loads(PARAMS.read_text())
    start = datetime.fromisoformat(p["time"]["start"])
    n = int(p["vertical"]["N"])
    grid_path = resolve_active_pilot_grid(args.grid)
    out_path = Path(args.output)

    with Dataset(grid_path) as grid:
        eta_rho = len(grid.dimensions["eta_rho"])
        xi_rho = len(grid.dimensions["xi_rho"])
        eta_u = len(grid.dimensions["eta_u"])
        xi_u = len(grid.dimensions["xi_u"])
        eta_v = len(grid.dimensions["eta_v"])
        xi_v = len(grid.dimensions["xi_v"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("ocean_time", 1)
        ds.createDimension("s_rho", n)
        ds.createDimension("eta_rho", eta_rho)
        ds.createDimension("xi_rho", xi_rho)
        ds.createDimension("eta_u", eta_u)
        ds.createDimension("xi_u", xi_u)
        ds.createDimension("eta_v", eta_v)
        ds.createDimension("xi_v", xi_v)
        ds.title = f"Static pilot initial conditions for {load_case_naming().title}"
        ds.warning = "Static technical dry-run fields on the active pilot grid; not scientific forcing."
        ds.grid_source = str(grid_path)
        for name, value in radioactive_decay_attrs(p).items():
            setattr(ds, name, value)

        def var(name: str, dtype: str, dims: tuple[str, ...]):
            return ds.createVariable(name, dtype, dims, zlib=True, complevel=1)

        ocean_time = var("ocean_time", "f8", ("ocean_time",))
        ocean_time.long_name = "time since initialization"
        ocean_time.units = "days since 0001-01-01 00:00:00"
        ocean_time.calendar = "gregorian"
        ocean_time[:] = [days_since_year1(start)]

        zeta = var("zeta", "f8", ("ocean_time", "eta_rho", "xi_rho"))
        zeta.long_name = "free-surface"
        zeta.units = "meter"
        zeta[0, :, :] = 0.0

        ubar = var("ubar", "f8", ("ocean_time", "eta_u", "xi_u"))
        ubar.long_name = "vertically integrated u-momentum component"
        ubar.units = "meter second-1"
        ubar[0, :, :] = 0.0

        vbar = var("vbar", "f8", ("ocean_time", "eta_v", "xi_v"))
        vbar.long_name = "vertically integrated v-momentum component"
        vbar.units = "meter second-1"
        vbar[0, :, :] = 0.0

        u = var("u", "f8", ("ocean_time", "s_rho", "eta_u", "xi_u"))
        u.long_name = "u-momentum component"
        u.units = "meter second-1"
        u[0, :, :, :] = 0.0

        v = var("v", "f8", ("ocean_time", "s_rho", "eta_v", "xi_v"))
        v.long_name = "v-momentum component"
        v.units = "meter second-1"
        v[0, :, :, :] = 0.0

        temp = var("temp", "f8", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        temp.long_name = "potential temperature"
        temp.units = "Celsius"
        temp[0, :, :, :] = 15.0

        salt = var("salt", "f8", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        salt.long_name = "salinity"
        salt[0, :, :, :] = 33.0

        dye = var("dye_01", "f8", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        dye.long_name = "HTO-like passive tracer concentration"
        dye.units = "Bq meter-3"
        dye[0, :, :, :] = 0.0

    print(f"grid={grid_path}")
    print(f"wrote {out_path}")
    print(f"dims: xi_rho={xi_rho}, eta_rho={eta_rho}, s_rho={n}")


if __name__ == "__main__":
    main()
