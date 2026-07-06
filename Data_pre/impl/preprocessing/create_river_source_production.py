#!/usr/bin/env python3
"""Create a production-style river/source NetCDF using staged discharge."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_naming import load_case_naming
from pilot_grid_utils import locate_source_on_grid
from roms_preprocessing_utils import ROOT, load_project_params, load_vertical_config, resolve_grid_path, to_mjd


DEFAULT_CSV = ROOT / "data" / "raw" / "source" / load_case_naming().source_csv_name
DEFAULT_OUT = ROOT / "input" / "roms_rivers_production.nc"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--discharge-csv", default=str(DEFAULT_CSV))
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--profile", default=None)
    return parser.parse_args()


def read_discharge_csv(path: Path) -> tuple[list[datetime], np.ndarray, str]:
    if not path.exists():
        raise SystemExit(f"discharge csv not found: {path}")
    times: list[datetime] = []
    discharge: list[float] = []
    scenario_tag = "measured_or_unspecified"
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if "time" not in reader.fieldnames or "discharge_m3_s" not in reader.fieldnames:
            raise SystemExit("discharge csv must contain time and discharge_m3_s columns")
        for row in reader:
            times.append(datetime.fromisoformat(row["time"]))
            discharge.append(float(row["discharge_m3_s"]))
            if row.get("scenario"):
                scenario_tag = row["scenario"].strip()
    values = np.asarray(discharge, dtype=float)
    if np.any(values <= 0):
        raise SystemExit("all discharge_m3_s values must be positive")
    return times, values, scenario_tag


def main() -> None:
    args = parse_args()
    params = load_project_params()
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    out_path = Path(args.output)
    if args.profile and args.output == str(DEFAULT_OUT):
        out_path = out_path.with_name(f"{out_path.stem}_{args.profile}{out_path.suffix}")
    discharge_path = Path(args.discharge_csv)
    vertical = load_vertical_config()
    times, discharge, scenario_tag = read_discharge_csv(discharge_path)
    placement = locate_source_on_grid(grid_path, params["domain"]["source_lon"], params["domain"]["source_lat"])
    release_bq_s = params["source"]["annual_release_TBq_per_year"] * 1e12 / (
        params["source"]["calendar_year_days"] * 24 * 3600
    )
    concentration = release_bq_s / discharge
    scenario_key = scenario_tag.lower()
    if scenario_key == "derived_release_carrier":
        discharge_note = (
            "river_transport = 1 m3/s numerical carrier; not measured discharge; "
            "derived from annual HTO release rate"
        )
    elif scenario_key == "scenario_baseline":
        discharge_note = "scenario, not measured"
    else:
        discharge_note = "staged discharge time series"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("s_rho", vertical.N)
        ds.createDimension("river", 1)
        ds.createDimension("river_time", len(times))
        ds.title = f"{load_case_naming().title} source file using staged discharge time series"
        ds.grid_source = str(grid_path)
        ds.discharge_source_csv = str(discharge_path)
        ds.discharge_scenario = scenario_tag
        ds.discharge_note = discharge_note
        ds.carrier_transport_m3_s = float(np.nanmedian(discharge))
        ds.not_measured_discharge = "true" if scenario_key in {"derived_release_carrier", "scenario_baseline"} else "false"
        ds.annual_release_TBq_per_year = float(params["source"]["annual_release_TBq_per_year"])
        ds.annual_release_TBq_per_year_note = "case-specific source value from project_parameters.json"
        ds.release_rate_note = "derived from annual HTO release rate"
        ds.release_Bq_s = release_bq_s
        ds.source_profile = args.profile or "default"
        ds.source_mode = params["source"].get("release_mode", "constant_rate")
        ds.source_vertical_location = "surface_layer"
        ds.s_rho_surface_index_zero_based = int(vertical.N - 1)
        ds.river_Vshape_sum_expected = 1.0
        ds.tracer_meaning = "dye_01 represents dissolved passive tracer concentration increment"
        ds.configured_source_lon = placement.configured_lon
        ds.configured_source_lat = placement.configured_lat
        ds.nearest_source_xi = placement.nearest_xi
        ds.nearest_source_eta = placement.nearest_eta
        ds.nearest_source_lon = placement.nearest_lon
        ds.nearest_source_lat = placement.nearest_lat
        ds.nearest_source_is_water = "true" if placement.nearest_is_water else "false"
        ds.snapped_source_lon = placement.snapped_lon
        ds.snapped_source_lat = placement.snapped_lat
        ds.snapped_source_xi = placement.snapped_xi
        ds.snapped_source_eta = placement.snapped_eta
        ds.snapped_source_depth_m = placement.snapped_depth_m
        ds.source_snap_distance_m = placement.snapped_distance_m
        ds.source_placement_rule = placement.placement_rule

        def var(name: str, dtype: str, dims: tuple[str, ...]):
            return ds.createVariable(name, dtype, dims, zlib=True, complevel=1)

        river_time = var("river_time", "f8", ("river_time",))
        river_time.long_name = "river runoff time"
        river_time.units = "days since 1858-11-17 00:00:00"
        river_time.calendar = "gregorian"
        river_time[:] = to_mjd(times)

        river = var("river", "f8", ("river",))
        river[:] = [1.0]

        xpos = var("river_Xposition", "f8", ("river",))
        xpos.long_name = "river XI-position at RHO-points"
        xpos[:] = [placement.snapped_xi]

        epos = var("river_Eposition", "f8", ("river",))
        epos.long_name = "river ETA-position at RHO-points"
        epos[:] = [placement.snapped_eta]

        direction = var("river_direction", "f8", ("river",))
        direction.long_name = "river runoff direction"
        direction[:] = [2.0]

        vshape = var("river_Vshape", "f8", ("s_rho", "river"))
        profile = np.zeros((vertical.N, 1), dtype=float)
        profile[-1, 0] = 1.0
        if not np.isclose(float(profile.sum()), 1.0):
            raise SystemExit("river_Vshape profile sum is not 1")
        vshape[:] = profile

        transport = var("river_transport", "f8", ("river_time", "river"))
        transport.long_name = "river runoff vertically integrated mass transport"
        transport.units = "meter3 second-1"
        transport.time = "river_time"
        transport[:, 0] = discharge

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
        dye.long_name = "HTO activity concentration, source term"
        dye.units = "Bq meter-3"
        dye.time = "river_time"
        dye[:, :, :] = 0.0
        dye[:, -1, 0] = concentration

    print(f"grid={grid_path}")
    print(f"discharge_csv={discharge_path}")
    print(f"records={len(times)}")
    print(f"scenario={scenario_tag}")
    print(f"snapped_source_index_zero_based=(xi={placement.snapped_xi}, eta={placement.snapped_eta})")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
