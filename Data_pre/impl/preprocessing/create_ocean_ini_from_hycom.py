#!/usr/bin/env python3
"""Create ROMS initial conditions from staged HYCOM-like data."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, date2num

from case_naming import load_case_naming, roms_input_name, staged_ocean_name
from roms_preprocessing_utils import (
    PREPROCESSING_VERSION,
    ROOT,
    create_time_variable,
    depth_average,
    fill_rho_field_2d,
    fill_rho_field_3d,
    get_rectilinear_lon_lat,
    hz_to_u,
    hz_to_v,
    infer_variable,
    interpolate_rectilinear_2d,
    interpolate_vertical_vectorized,
    load_grid,
    load_project_params,
    load_vertical_config,
    read_dimensional_variable,
    read_time_values,
    resolve_grid_path,
    rho_to_u,
    rho_to_v,
    rotate_to_grid,
    sigma_depths,
    zero_masked_uv,
)


DEFAULT_SRC = ROOT / "data" / "raw" / "ocean" / staged_ocean_name("hycom", "initial")
DEFAULT_OUT = ROOT / "input" / roms_input_name("ini")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--profile", default=None)
    return parser.parse_args()


def days_since_mjd(dt: datetime) -> float:
    return float(date2num(dt, units="days since 1858-11-17 00:00:00", calendar="gregorian"))


def source_depth_to_z(depth: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth, dtype=float)
    return depth if np.nanmax(depth) <= 0.0 else -np.abs(depth)


def interpolate_3d(lon, lat, depth, values, target_lon, target_lat, target_z):
    nz_src = len(depth)
    horizontal = np.empty((nz_src, *target_lon.shape), dtype=float)
    for k in range(nz_src):
        horizontal[k] = interpolate_rectilinear_2d(lon, lat, values[k], target_lon, target_lat)
    return interpolate_vertical_vectorized(source_depth_to_z(depth), horizontal, target_z)


def convert_temperature(values: np.ndarray, units: str | None) -> np.ndarray:
    if units and "kelvin" in units.lower():
        return values - 273.15
    if np.nanmean(values) > 100.0:
        return values - 273.15
    return values


def ensure_finite_wet(name: str, values: np.ndarray, wet_mask: np.ndarray) -> None:
    wet = np.asarray(wet_mask, dtype=bool)
    data = np.asarray(values, dtype=float)
    expanded = wet if data.ndim == wet.ndim else np.broadcast_to(wet, data.shape)
    if np.isnan(data[expanded]).any():
        raise SystemExit(f"{name} still contains NaN on wet points after fill")


def main() -> None:
    args = parse_args()
    src_path = Path(args.src)
    if not src_path.exists():
        raise SystemExit(f"source file not found: {src_path}")
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    out_path = Path(args.output)
    if args.profile and args.output == str(DEFAULT_OUT):
        out_path = ROOT / "input" / roms_input_name("ini", profile=args.profile)
    grid = load_grid(grid_path)
    vertical = load_vertical_config()
    params = load_project_params()
    start_time = datetime.fromisoformat(params["time"]["start"])
    z_r, _, hz = sigma_depths(grid.h, vertical)
    mask_rho = grid.mask_rho == 1
    mask_u = mask_rho[:, :-1] & mask_rho[:, 1:]
    mask_v = mask_rho[:-1, :] & mask_rho[1:, :]

    with Dataset(src_path) as src:
        lon, lat, lon_name, lat_name = get_rectilinear_lon_lat(src)
        depth_name = infer_variable(src, ("depth", "lev", "level", "z"))
        depth = np.asarray(src.variables[depth_name][:], dtype=float)
        time_values, _, _ = read_time_values(src, ("time", "ocean_time", "mt"))
        time_index = int(np.argmin([abs((t - start_time).total_seconds()) for t in time_values]))
        selected_time = time_values[time_index]

        zeta_name = infer_variable(src, ("zeta", "ssh", "surf_el"))
        temp_name = infer_variable(src, ("temp", "water_temp", "temperature"))
        salt_name = infer_variable(src, ("salt", "salinity"))
        u_name = infer_variable(src, ("u", "water_u", "u_velocity"))
        v_name = infer_variable(src, ("v", "water_v", "v_velocity"))

        zeta_src = read_dimensional_variable(src, zeta_name, lon_name, lat_name, None, time_index)
        temp_src = read_dimensional_variable(src, temp_name, lon_name, lat_name, depth_name, time_index)
        salt_src = read_dimensional_variable(src, salt_name, lon_name, lat_name, depth_name, time_index)
        u_src = read_dimensional_variable(src, u_name, lon_name, lat_name, depth_name, time_index)
        v_src = read_dimensional_variable(src, v_name, lon_name, lat_name, depth_name, time_index)

        temp_src = convert_temperature(temp_src, getattr(src.variables[temp_name], "units", ""))

    zeta_rho = interpolate_rectilinear_2d(lon, lat, zeta_src, grid.lon_rho, grid.lat_rho)
    temp_rho = interpolate_3d(lon, lat, depth, temp_src, grid.lon_rho, grid.lat_rho, z_r)
    salt_rho = interpolate_3d(lon, lat, depth, salt_src, grid.lon_rho, grid.lat_rho, z_r)
    u_rho_east = interpolate_3d(lon, lat, depth, u_src, grid.lon_rho, grid.lat_rho, z_r)
    v_rho_north = interpolate_3d(lon, lat, depth, v_src, grid.lon_rho, grid.lat_rho, z_r)
    zeta_rho = fill_rho_field_2d(zeta_rho, mask_rho)
    temp_rho = fill_rho_field_3d(temp_rho, mask_rho)
    salt_rho = fill_rho_field_3d(salt_rho, mask_rho)
    u_rho_east = fill_rho_field_3d(u_rho_east, mask_rho)
    v_rho_north = fill_rho_field_3d(v_rho_north, mask_rho)
    u_rho, v_rho = rotate_to_grid(u_rho_east, v_rho_north, grid.angle[None, :, :])
    u = rho_to_u(u_rho)
    v = rho_to_v(v_rho)
    ubar = depth_average(u, hz_to_u(hz))
    vbar = depth_average(v, hz_to_v(hz))
    u = zero_masked_uv(u, mask_u)
    v = zero_masked_uv(v, mask_v)
    ubar = zero_masked_uv(ubar, mask_u)
    vbar = zero_masked_uv(vbar, mask_v)

    ensure_finite_wet("zeta", zeta_rho, mask_rho)
    ensure_finite_wet("temp", temp_rho, mask_rho)
    ensure_finite_wet("salt", salt_rho, mask_rho)
    ensure_finite_wet("u", u, mask_u)
    ensure_finite_wet("v", v, mask_v)
    ensure_finite_wet("ubar", ubar, mask_u)
    ensure_finite_wet("vbar", vbar, mask_v)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("ocean_time", 1)
        ds.createDimension("s_rho", vertical.N)
        ds.createDimension("eta_rho", grid.lon_rho.shape[0])
        ds.createDimension("xi_rho", grid.lon_rho.shape[1])
        ds.createDimension("eta_u", grid.lon_u.shape[0])
        ds.createDimension("xi_u", grid.lon_u.shape[1])
        ds.createDimension("eta_v", grid.lon_v.shape[0])
        ds.createDimension("xi_v", grid.lon_v.shape[1])
        ds.title = f"{load_case_naming().title} ROMS initial conditions from HYCOM-like staged data"
        ds.grid_source = str(grid_path)
        ds.source_dataset = str(src_path)
        ds.preprocessing_version = PREPROCESSING_VERSION
        ds.source_time_index = time_index
        ds.source_time = selected_time.isoformat()
        ds.requested_model_start = start_time.isoformat()

        ocean_time = ds.createVariable("ocean_time", "f8", ("ocean_time",), zlib=True, complevel=1)
        ocean_time.long_name = "time since reference date"
        ocean_time.units = "days since 1858-11-17 00:00:00"
        ocean_time.calendar = "gregorian"
        ocean_time[:] = [days_since_mjd(selected_time)]

        def var(name: str, dims: tuple[str, ...]):
            return ds.createVariable(name, "f8", dims, zlib=True, complevel=1)

        var("zeta", ("ocean_time", "eta_rho", "xi_rho"))[0] = zeta_rho
        var("ubar", ("ocean_time", "eta_u", "xi_u"))[0] = ubar
        var("vbar", ("ocean_time", "eta_v", "xi_v"))[0] = vbar
        var("u", ("ocean_time", "s_rho", "eta_u", "xi_u"))[0] = u
        var("v", ("ocean_time", "s_rho", "eta_v", "xi_v"))[0] = v
        temp_var = var("temp", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        temp_var.units = "Celsius"
        temp_var[0] = temp_rho
        salt_var = var("salt", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        salt_var.units = "PSU"
        salt_var[0] = salt_rho
        dye = var("dye_01", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        dye.units = "Bq meter-3"
        dye[0] = 0.0
    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"time_index={time_index}")
    print(f"source_time={selected_time.isoformat()}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
