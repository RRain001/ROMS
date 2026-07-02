#!/usr/bin/env python3
"""Create ROMS tide forcing from staged TPXO-like data."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_naming import case_start_datetime, load_case_naming, roms_input_name, staged_tides_name
from roms_preprocessing_utils import ROOT, get_rectilinear_lon_lat, infer_variable, interpolate_rectilinear_2d, load_grid, resolve_grid_path


DEFAULT_SRC = ROOT / "data" / "raw" / "tides" / staged_tides_name()
DEFAULT_OUT = ROOT / "input" / roms_input_name("tides")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    src_path = Path(args.src)
    if not src_path.exists():
        raise SystemExit(f"source file not found: {src_path}")
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    out_path = Path(args.output)
    grid = load_grid(grid_path)

    with Dataset(src_path) as src:
        lon, lat, lon_name, lat_name = get_rectilinear_lon_lat(src)
        tide_dim_name = None
        for name in src.dimensions:
            lowered = name.lower()
            if "tide" in lowered or "const" in lowered:
                tide_dim_name = name
                break
        if tide_dim_name is None:
            tide_period = np.asarray([12.42], dtype=float)
            tide_axis = [None]
        else:
            tide_period_name = infer_variable(src, ("tide_period", tide_dim_name))
            tide_period = np.asarray(src.variables[tide_period_name][:], dtype=float)
            tide_axis = list(range(len(tide_period)))

        required_var_names = {
            "tide_Eamp": infer_variable(src, ("tide_Eamp", "Eamp")),
            "tide_Ephase": infer_variable(src, ("tide_Ephase", "Ephase")),
        }
        optional_var_names = {}
        for out_name, candidates in {
            "tide_Cmax": ("tide_Cmax", "Cmax"),
            "tide_Cmin": ("tide_Cmin", "Cmin"),
            "tide_Cangle": ("tide_Cangle", "Cangle"),
            "tide_Cphase": ("tide_Cphase", "Cphase"),
        }.items():
            try:
                optional_var_names[out_name] = infer_variable(src, candidates)
            except KeyError:
                continue
        var_names = required_var_names | optional_var_names

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with Dataset(out_path, "w", format="NETCDF4") as ds:
            ds.createDimension("tide_period", len(tide_axis))
            ds.createDimension("eta_rho", grid.lon_rho.shape[0])
            ds.createDimension("xi_rho", grid.lon_rho.shape[1])
            ds.title = f"{load_case_naming().title} ROMS tide forcing from TPXO-like staged data"
            ds.grid_source = str(grid_path)
            ds.source_dataset = str(src_path)
            tide_period_var = ds.createVariable("tide_period", "f8", ("tide_period",), zlib=True, complevel=1)
            tide_period_var.units = "hours"
            tide_period_var[:] = tide_period
            zero_phase = ds.createVariable("zero_phase_date", "f8")
            zero_phase.assignValue(float(case_start_datetime().strftime("%Y%m%d")))

            outputs = {
                name: ds.createVariable(name, "f8", ("tide_period", "eta_rho", "xi_rho"), zlib=True, complevel=1)
                for name in var_names
            }
            for out_index, tide_index in enumerate(tide_axis):
                for out_name, src_name in var_names.items():
                    var = src.variables[src_name]
                    data = np.asarray(var[:], dtype=float)
                    if tide_index is not None and tide_dim_name in var.dimensions:
                        axis = list(var.dimensions).index(tide_dim_name)
                        data = np.take(data, tide_index, axis=axis)
                    outputs[out_name][out_index] = interpolate_rectilinear_2d(lon, lat, data, grid.lon_rho, grid.lat_rho)
    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
