#!/usr/bin/env python3
"""Create ROMS atmospheric forcing from staged ERA5-like data."""

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


DEFAULT_SRC = ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("atm")
DEFAULT_OUT = ROOT / "input" / roms_input_name("atm")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    return parser.parse_args()


def convert_pressure(values: np.ndarray, units: str | None) -> np.ndarray:
    if units and "pa" in units.lower() and "milli" not in units.lower():
        return values / 100.0
    if np.nanmean(values) > 2000.0:
        return values / 100.0
    return values


def convert_air_temperature(values: np.ndarray, units: str | None) -> np.ndarray:
    if units and "kelvin" in units.lower():
        return values - 273.15
    if np.nanmean(values) > 100.0:
        return values - 273.15
    return values


def convert_humidity(values: np.ndarray) -> np.ndarray:
    if np.nanmax(values) <= 1.5:
        return values * 100.0
    return values


def accumulated_to_rate(data: np.ndarray, times: np.ndarray) -> np.ndarray:
    if data.shape[0] <= 1:
        return np.zeros_like(data)
    out = np.zeros_like(data)
    for i in range(1, data.shape[0]):
        dt = max((times[i] - times[i - 1]).total_seconds(), 1.0)
        out[i] = np.maximum((data[i] - data[i - 1]) / dt, 0.0)
    out[0] = out[1]
    return out


def fill_time_missing_fields(values: np.ndarray, label: str) -> np.ndarray:
    """Carry the last finite spatial field across ERA5 expver gaps."""
    out = np.asarray(values, dtype=float).copy()
    if out.ndim < 1 or out.shape[0] == 0:
        raise SystemExit(f"{label}: empty time series")
    finite = np.isfinite(out)
    if not np.any(finite):
        raise SystemExit(f"{label}: no finite values in the complete time series")
    first = int(np.flatnonzero(finite.reshape(out.shape[0], -1).any(axis=1))[0])
    for index in range(first):
        out[index] = out[first]
    for index in range(first + 1, out.shape[0]):
        missing = ~np.isfinite(out[index])
        if np.any(missing):
            out[index][missing] = out[index - 1][missing]
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

        uwind_name = infer_variable(src, ("Uwind", "u10", "u10m"))
        vwind_name = infer_variable(src, ("Vwind", "v10", "v10m"))
        pair_name = infer_variable(src, ("Pair", "sp", "msl", "surface_pressure"))
        tair_name = infer_variable(src, ("Tair", "t2m", "air_temperature"))
        qair_name = infer_variable(src, ("Qair", "r2", "rh", "relative_humidity"))
        rain_name = infer_variable(src, ("rain", "tp", "precipitation"))
        eminusp_name = infer_variable(src, ("EminusP", "e", "evaporation", "swflux"))

        uwind = []
        vwind = []
        pair = []
        tair = []
        qair = []
        rain = []
        eminusp = []
        rain_raw = []
        evap_raw = []
        for time_index in range(len(times)):
            uwind_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, uwind_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, uwind[-1] if uwind else None, "Uwind", time_index)
            vwind_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, vwind_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, vwind[-1] if vwind else None, "Vwind", time_index)
            pair_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, pair_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, pair[-1] if pair else None, "Pair", time_index)
            tair_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, tair_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, tair[-1] if tair else None, "Tair", time_index)
            qair_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, qair_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, qair[-1] if qair else None, "Qair", time_index)
            rain_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, rain_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, rain_raw[-1] if rain_raw else None, "rain", time_index)
            evap_field = interp_fill_with_fallback(lon, lat, read_dimensional_variable(src, eminusp_name, lon_name, lat_name, None, time_index), grid.lon_rho, grid.lat_rho, wet_mask, evap_raw[-1] if evap_raw else None, "EminusP", time_index)
            uwind.append(uwind_field)
            vwind.append(vwind_field)
            pair.append(convert_pressure(pair_field, getattr(src.variables[pair_name], "units", "")))
            tair.append(convert_air_temperature(tair_field, getattr(src.variables[tair_name], "units", "")))
            qair.append(convert_humidity(qair_field))
            rain_raw.append(rain_field)
            evap_raw.append(evap_field)

        uwind = np.asarray(uwind)
        vwind = np.asarray(vwind)
        pair = np.asarray(pair)
        tair = np.asarray(tair)
        qair = np.asarray(qair)
        rain_raw = fill_time_missing_fields(np.asarray(rain_raw), "rain")
        evap_raw = fill_time_missing_fields(np.asarray(evap_raw), "EminusP")
        rain_units = getattr(src.variables[rain_name], "units", "")
        evap_units = getattr(src.variables[eminusp_name], "units", "")
        rain = accumulated_to_rate(rain_raw, times) if "tp" in rain_name.lower() or "accum" in rain_units.lower() else rain_raw
        # The staged ERA5 downloader already converted EminusP / swflux to
        # signed evaporation-minus-precipitation in m/s. Do not take abs()
        # or subtract rain a second time: that changes the physics/sign.
        if eminusp_name in {"EminusP", "swflux"}:
            if evap_units.strip().lower().replace(" ", "") not in {"ms-1", "m/s", "ms**-1"}:
                raise ValueError("staged EminusP must be signed m/s, not accumulated raw evaporation")
            eminusp = fill_time_missing_fields(evap_raw, "EminusP")
        else:
            # Backward-compatible *raw* evaporation path. Raw e can be
            # negative accumulated evaporation; preserve legacy handling,
            # but do not run it on already-normalized EminusP.
            evap_rate = accumulated_to_rate(np.abs(evap_raw), times) if eminusp_name.lower() in {"e", "evaporation"} or "accum" in evap_units.lower() else np.abs(evap_raw)
            eminusp = fill_time_missing_fields(evap_rate - rain / 1000.0, "EminusP")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("wind_time", len(times))
        ds.createDimension("pair_time", len(times))
        ds.createDimension("tair_time", len(times))
        ds.createDimension("qair_time", len(times))
        ds.createDimension("rain_time", len(times))
        ds.createDimension("swf_time", len(times))
        ds.createDimension("eta_rho", grid.lon_rho.shape[0])
        ds.createDimension("xi_rho", grid.lon_rho.shape[1])
        ds.title = f"{load_case_naming().title} ROMS atmospheric forcing from ERA5-like staged data"
        ds.grid_source = str(grid_path)
        ds.source_dataset = str(src_path)
        create_time_variable(ds, "wind_time", list(times), "surface wind time")
        create_time_variable(ds, "pair_time", list(times), "surface air pressure time")
        create_time_variable(ds, "tair_time", list(times), "surface air temperature time")
        create_time_variable(ds, "qair_time", list(times), "surface humidity time")
        create_time_variable(ds, "rain_time", list(times), "surface rain time")
        create_time_variable(ds, "swf_time", list(times), "surface freshwater flux time")

        def var(name: str, time_name: str):
            out = ds.createVariable(name, "f8", (time_name, "eta_rho", "xi_rho"), zlib=True, complevel=1)
            out.time = time_name
            out.coordinates = "lon lat"
            return out

        var("Uwind", "wind_time")[:] = uwind
        var("Vwind", "wind_time")[:] = vwind
        var("Pair", "pair_time")[:] = pair
        var("Tair", "tair_time")[:] = tair
        var("Qair", "qair_time")[:] = qair
        var("rain", "rain_time")[:] = rain
        var("EminusP", "swf_time")[:] = eminusp
        var("swflux", "swf_time")[:] = eminusp
    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"records={len(times)}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
