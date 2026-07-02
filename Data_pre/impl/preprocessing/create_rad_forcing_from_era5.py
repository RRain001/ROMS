#!/usr/bin/env python3
"""Create ROMS radiation forcing from staged ERA5-like data."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_naming import load_case_naming, roms_input_name, staged_atmosphere_name
from roms_preprocessing_utils import (
    ROOT,
    create_time_variable,
    fill_rho_field_2d,
    get_rectilinear_lon_lat,
    infer_variable,
    interpolate_rectilinear_2d,
    load_grid,
    read_dimensional_variable,
    read_time_values,
    resolve_grid_path,
)


DEFAULT_SRC = ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("rad")
DEFAULT_OUT = ROOT / "input" / roms_input_name("rad")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    return parser.parse_args()


def accumulated_to_flux(data: np.ndarray, times: np.ndarray) -> np.ndarray:
    if data.shape[0] <= 1:
        return np.zeros_like(data)
    out = np.zeros_like(data)
    for i in range(1, data.shape[0]):
        dt = max((times[i] - times[i - 1]).total_seconds(), 1.0)
        out[i] = np.maximum((data[i] - data[i - 1]) / dt, 0.0)
    out[0] = out[1]
    return out


def interp_fill(
    lon: np.ndarray,
    lat: np.ndarray,
    values: np.ndarray,
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    wet_mask: np.ndarray,
) -> np.ndarray:
    field = interpolate_rectilinear_2d(lon, lat, values, grid_lon, grid_lat)
    return fill_rho_field_2d(field, wet_mask)


def interp_fill_with_fallback(
    lon: np.ndarray,
    lat: np.ndarray,
    values: np.ndarray,
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    wet_mask: np.ndarray,
    previous: np.ndarray | None,
    label: str,
    time_index: int,
) -> np.ndarray:
    raw = np.ma.filled(values, np.nan).astype(float, copy=False)
    if not np.any(np.isfinite(raw)):
        if previous is not None:
            return previous.copy()
        raise SystemExit(f"{label}: source record {time_index} contains no finite values")
    field = interpolate_rectilinear_2d(lon, lat, raw, grid_lon, grid_lat)
    if not np.any(np.isfinite(field)):
        if previous is not None:
            return previous.copy()
        raise SystemExit(f"{label}: interpolated record {time_index} contains no finite values")
    return fill_rho_field_2d(field, wet_mask)


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
        times, _, _ = read_time_values(src, ("time", "valid_time", "forecast_time"))
        wet_mask = np.ones_like(grid.mask_rho, dtype=bool)
        sw_name = infer_variable(src, ("swrad", "ssrd", "shortwave"))
        lwd_name = infer_variable(src, ("lwrad_down", "strd", "longwave_down"))
        lwn_name = infer_variable(src, ("lwrad", "str", "longwave_net"))

        sw = []
        lwd = []
        lwn = []
        for time_index in range(len(times)):
            sw.append(interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, sw_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, sw[-1] if sw else None, "swrad", time_index))
            lwd.append(interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, lwd_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, lwd[-1] if lwd else None, "lwrad_down", time_index))
            lwn.append(interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, lwn_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, lwn[-1] if lwn else None, "lwrad", time_index))

        sw = np.asarray(sw)
        lwd = np.asarray(lwd)
        lwn = np.asarray(lwn)
        sw = accumulated_to_flux(sw, times) if any(tag in sw_name.lower() for tag in ("ssrd", "accum")) else sw
        lwd = accumulated_to_flux(lwd, times) if any(tag in lwd_name.lower() for tag in ("strd", "accum")) else lwd
        lwn = accumulated_to_flux(lwn, times) if any(tag in lwn_name.lower() for tag in ("str", "accum")) else lwn

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("srf_time", len(times))
        ds.createDimension("lrf_time", len(times))
        ds.createDimension("eta_rho", grid.lon_rho.shape[0])
        ds.createDimension("xi_rho", grid.lon_rho.shape[1])
        ds.title = f"{load_case_naming().title} ROMS radiation forcing from ERA5-like staged data"
        ds.grid_source = str(grid_path)
        ds.source_dataset = str(src_path)
        create_time_variable(ds, "srf_time", list(times), "shortwave radiation time")
        create_time_variable(ds, "lrf_time", list(times), "longwave radiation time")
        swrad = ds.createVariable("swrad", "f8", ("srf_time", "eta_rho", "xi_rho"), zlib=True, complevel=1)
        lwrad = ds.createVariable("lwrad", "f8", ("lrf_time", "eta_rho", "xi_rho"), zlib=True, complevel=1)
        lwrad_down = ds.createVariable("lwrad_down", "f8", ("lrf_time", "eta_rho", "xi_rho"), zlib=True, complevel=1)
        swrad.time = "srf_time"
        lwrad.time = "lrf_time"
        lwrad_down.time = "lrf_time"
        swrad.coordinates = "lon lat"
        lwrad.coordinates = "lon lat"
        lwrad_down.coordinates = "lon lat"
        swrad[:] = sw
        lwrad[:] = lwn
        lwrad_down[:] = lwd
    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"records={len(times)}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
