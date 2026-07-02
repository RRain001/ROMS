#!/usr/bin/env python3
"""Create a pilot ROMS river/source NetCDF for HTO-like passive tracer."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import get_case_config_path, get_case_root
from case_naming import load_case_naming
from pilot_grid_utils import locate_source_on_grid, resolve_active_pilot_grid


ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")
OUT = ROOT / "input" / "roms_rivers_pilot.nc"


def modified_julian_day(dt: datetime) -> float:
    mjd0 = datetime(1858, 11, 17)
    return (dt - mjd0).total_seconds() / 86400.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(OUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    p = json.loads(PARAMS.read_text())
    d = p["domain"]
    s = p["source"]
    t = p["time"]
    v = p["vertical"]
    grid_path = resolve_active_pilot_grid(args.grid)
    out_path = Path(args.output)
    discharge = s.get("nominal_discharge_m3_s")
    if discharge is None or discharge <= 0:
        raise SystemExit("Set source.nominal_discharge_m3_s before creating ROMS river concentration.")

    start = datetime.fromisoformat(t["start"])
    stop = datetime.fromisoformat(t["stop"])
    step = timedelta(hours=t["source_interval_hours"])
    annual_bq = s["annual_release_TBq_per_year"] * 1e12
    release_bq_s = annual_bq / (s["calendar_year_days"] * 24 * 3600)
    concentration_bq_m3 = release_bq_s / discharge
    placement = locate_source_on_grid(grid_path, d["source_lon"], d["source_lat"])

    times = []
    cur = start
    while cur < stop:
        times.append(modified_julian_day(cur))
        cur += step
    times = np.array(times, dtype="f8")
    nt = len(times)
    nz = int(v["N"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("s_rho", nz)
        ds.createDimension("river", 1)
        ds.createDimension("river_time", nt)
        ds.title = f"Pilot source file on active real grid for {load_case_naming().title}"
        ds.warning = "Uses nominal 1 m3/s discharge for pilot concentration conversion"
        ds.grid_source = str(grid_path)
        ds.release_Bq_s = release_bq_s
        ds.nominal_discharge_m3_s = discharge
        ds.concentration_Bq_m3 = concentration_bq_m3
        ds.source_lon = placement.snapped_lon
        ds.source_lat = placement.snapped_lat
        ds.configured_source_lon = placement.configured_lon
        ds.configured_source_lat = placement.configured_lat
        ds.nearest_xi_rho_index_zero_based = placement.nearest_xi
        ds.nearest_eta_rho_index_zero_based = placement.nearest_eta
        ds.nearest_rho_xi = placement.nearest_xi
        ds.nearest_rho_eta = placement.nearest_eta
        ds.nearest_rho_lon = placement.nearest_lon
        ds.nearest_rho_lat = placement.nearest_lat
        ds.nearest_rho_is_water = int(placement.nearest_is_water)
        ds.snapped_xi_rho_index_zero_based = placement.snapped_xi
        ds.snapped_eta_rho_index_zero_based = placement.snapped_eta
        ds.snapped_source_xi = placement.snapped_xi
        ds.snapped_source_eta = placement.snapped_eta
        ds.snapped_source_lon = placement.snapped_lon
        ds.snapped_source_lat = placement.snapped_lat
        ds.snapped_source_depth_m = placement.snapped_depth_m
        ds.source_snap_distance_m = placement.snapped_distance_m
        ds.source_placement_rule = placement.placement_rule
        ds.source_location_note = (
            "source_lon/source_lat are the actual injection coordinates on the active grid; "
            "configured_source_lon/configured_source_lat retain the requested point"
        )

        def var(name, dtype, dims):
            return ds.createVariable(name, dtype, dims, zlib=True, complevel=1)

        river_time = var("river_time", "f8", ("river_time",))
        river_time.long_name = "river runoff time"
        river_time.units = "days since 1858-11-17 00:00:00"
        river_time[:] = times

        river = var("river", "f8", ("river",))
        river.long_name = "river runoff identification number"
        river[:] = [1]

        x = var("river_Xposition", "f8", ("river",))
        x.long_name = "river XI-position at RHO-points"
        x[:] = [placement.snapped_xi]

        e = var("river_Eposition", "f8", ("river",))
        e.long_name = "river ETA-position at RHO-points"
        e[:] = [placement.snapped_eta]

        direction = var("river_direction", "f8", ("river",))
        direction.long_name = "river runoff direction"
        direction[:] = [2]

        vshape = var("river_Vshape", "f8", ("s_rho", "river"))
        vshape.long_name = "river runoff mass transport vertical profile"
        profile = np.zeros((nz, 1), dtype="f8")
        profile[-1, 0] = 1.0
        vshape[:, :] = profile

        transport = var("river_transport", "f8", ("river_time", "river"))
        transport.long_name = "river runoff vertically integrated mass transport"
        transport.units = "meter3 second-1"
        transport.time = "river_time"
        transport[:, :] = discharge

        temp = var("river_temp", "f8", ("river_time", "s_rho", "river"))
        temp.long_name = "river runoff potential temperature"
        temp.units = "Celsius"
        temp.time = "river_time"
        temp[:, :, :] = 15.0

        salt = var("river_salt", "f8", ("river_time", "s_rho", "river"))
        salt.long_name = "river runoff salinity"
        salt.time = "river_time"
        salt[:, :, :] = 33.0

        dye = var("river_dye_01", "f8", ("river_time", "s_rho", "river"))
        dye.long_name = "HTO-like passive tracer concentration"
        dye.units = "Bq meter-3"
        dye.time = "river_time"
        dye[:, :, :] = 0.0
        dye[:, -1, :] = concentration_bq_m3

    print(f"grid={grid_path}")
    print(
        "configured_source_lon_lat="
        f"({placement.configured_lon:.6f}, {placement.configured_lat:.6f})"
    )
    print(
        "nearest_rho_index_zero_based="
        f"(xi={placement.nearest_xi}, eta={placement.nearest_eta}, water={int(placement.nearest_is_water)})"
    )
    print(
        "snapped_source_index_zero_based="
        f"(xi={placement.snapped_xi}, eta={placement.snapped_eta})"
    )
    print(
        "snapped_source_lon_lat="
        f"({placement.snapped_lon:.6f}, {placement.snapped_lat:.6f})"
    )
    print(f"snapped_source_depth_m={placement.snapped_depth_m:.3f}")
    print(f"source_snap_distance_m={placement.snapped_distance_m:.3f}")
    print(f"release_Bq_s={release_bq_s:.9f}")
    print(f"discharge_m3_s={discharge:.6f}")
    print(f"river_dye_01_Bq_m3={concentration_bq_m3:.9f}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
