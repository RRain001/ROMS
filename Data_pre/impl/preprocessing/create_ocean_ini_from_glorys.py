#!/usr/bin/env python3
"""Create ROMS initial conditions from staged GLORYS12V1 data."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_naming import load_case_naming
from ocean_source_utils import MJD_CALENDAR, MJD_UNITS, build_glorys_paths, load_glorys_config
from roms_preprocessing_utils import (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--src", default=None)
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--time", default=None)
    return parser.parse_args()


def target_ini_time(config: dict, args: argparse.Namespace) -> datetime:
    if args.time:
        return datetime.fromisoformat(args.time)
    base = datetime.fromisoformat(config["time_start"])
    hh, mm, ss = [int(item) for item in str(config["time_mean_center"]).split(":")]
    return datetime(base.year, base.month, base.day, hh, mm, ss)


def source_depth_to_z(depth: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth, dtype=float)
    return depth if np.nanmax(depth) <= 0.0 else -np.abs(depth)


def interpolate_3d(lon, lat, depth, values, target_lon, target_lat, target_z):
    horizontal = np.empty((len(depth), *target_lon.shape), dtype=float)
    for k in range(len(depth)):
        horizontal[k] = interpolate_rectilinear_2d(lon, lat, values[k], target_lon, target_lat)
    return interpolate_vertical_vectorized(source_depth_to_z(depth), horizontal, target_z)


def main() -> None:
    args = parse_args()
    config = load_glorys_config(args.config)
    default_paths = build_glorys_paths(config, profile=args.profile)
    src_path = Path(args.src) if args.src else default_paths.staged_initial
    out_path = Path(args.output) if args.output else default_paths.roms_ini
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)

    if not src_path.exists():
        raise SystemExit(f"source file not found: {src_path}")

    grid = load_grid(grid_path)
    vertical = load_vertical_config()
    params = load_project_params()
    requested_start = datetime.fromisoformat(params["time"]["start"])
    desired_time = target_ini_time(config, args)
    z_r, _, hz = sigma_depths(grid.h, vertical)
    wet_rho = grid.mask_rho == 1
    wet_u = wet_rho[:, :-1] & wet_rho[:, 1:]
    wet_v = wet_rho[:-1, :] & wet_rho[1:, :]

    with Dataset(src_path) as src:
        lon, lat, lon_name, lat_name = get_rectilinear_lon_lat(src)
        depth_name = infer_variable(src, ("depth", "lev", "level", "z"))
        depth = np.asarray(src.variables[depth_name][:], dtype=float)
        time_values, _, _ = read_time_values(src, ("time", "ocean_time", "mt"))
        deltas = np.asarray([abs((time_value - desired_time).total_seconds()) for time_value in time_values], dtype=float)
        time_index = int(np.argmin(deltas))
        selected_time = time_values[time_index]

        zeta_name = infer_variable(src, ("zos", "zeta", "ssh", "surf_el"))
        temp_name = infer_variable(src, ("thetao", "temp", "water_temp", "temperature"))
        salt_name = infer_variable(src, ("so", "salt", "salinity"))
        u_name = infer_variable(src, ("uo", "u", "water_u", "u_velocity"))
        v_name = infer_variable(src, ("vo", "v", "water_v", "v_velocity"))

        zeta_src = read_dimensional_variable(src, zeta_name, lon_name, lat_name, None, time_index)
        temp_src = read_dimensional_variable(src, temp_name, lon_name, lat_name, depth_name, time_index)
        salt_src = read_dimensional_variable(src, salt_name, lon_name, lat_name, depth_name, time_index)
        u_src = read_dimensional_variable(src, u_name, lon_name, lat_name, depth_name, time_index)
        v_src = read_dimensional_variable(src, v_name, lon_name, lat_name, depth_name, time_index)
        temp_units = getattr(src.variables[temp_name], "units", "")
        salt_units = getattr(src.variables[salt_name], "units", "")

    zeta_rho = interpolate_rectilinear_2d(lon, lat, zeta_src, grid.lon_rho, grid.lat_rho)
    temp_rho = interpolate_3d(lon, lat, depth, temp_src, grid.lon_rho, grid.lat_rho, z_r)
    salt_rho = interpolate_3d(lon, lat, depth, salt_src, grid.lon_rho, grid.lat_rho, z_r)
    u_rho_east = interpolate_3d(lon, lat, depth, u_src, grid.lon_rho, grid.lat_rho, z_r)
    v_rho_north = interpolate_3d(lon, lat, depth, v_src, grid.lon_rho, grid.lat_rho, z_r)

    zeta_rho = fill_rho_field_2d(zeta_rho, wet_rho)
    temp_rho = fill_rho_field_3d(temp_rho, wet_rho)
    salt_rho = fill_rho_field_3d(salt_rho, wet_rho)
    u_rho_east = fill_rho_field_3d(u_rho_east, wet_rho)
    v_rho_north = fill_rho_field_3d(v_rho_north, wet_rho)
    zeta_rho = np.where(wet_rho, zeta_rho, 0.0)
    temp_rho = zero_masked_uv(temp_rho, wet_rho)
    salt_rho = zero_masked_uv(salt_rho, wet_rho)

    u_rho, v_rho = rotate_to_grid(u_rho_east, v_rho_north, grid.angle[None, :, :])
    u = rho_to_u(u_rho)
    v = rho_to_v(v_rho)
    u = zero_masked_uv(u, wet_u)
    v = zero_masked_uv(v, wet_v)
    ubar = depth_average(u, hz_to_u(hz))
    vbar = depth_average(v, hz_to_v(hz))

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
        ds.title = f"{load_case_naming().title} ROMS initial conditions from GLORYS12V1 staged data"
        ds.grid_source = str(grid_path)
        ds.source_dataset = str(src_path)
        ds.source = "GLORYS12V1 / GLOBAL_MULTIYEAR_PHY_001_030"
        ds.dataset_id = config["dataset_id_daily"]
        ds.source_time_index = str(time_index)
        ds.source_time = selected_time.isoformat()
        ds.time_reference = f"MJD / {MJD_UNITS}"
        ds.requested_model_start = requested_start.isoformat()

        create_time_variable(ds, "ocean_time", [selected_time], "time since reference date")
        ocean_time = ds.variables["ocean_time"]
        ocean_time.units = MJD_UNITS
        ocean_time.calendar = MJD_CALENDAR

        def var(name: str, dims: tuple[str, ...]):
            return ds.createVariable(name, "f8", dims, zlib=True, complevel=1)

        var("zeta", ("ocean_time", "eta_rho", "xi_rho"))[0] = zeta_rho
        var("ubar", ("ocean_time", "eta_u", "xi_u"))[0] = ubar
        var("vbar", ("ocean_time", "eta_v", "xi_v"))[0] = vbar
        var("u", ("ocean_time", "s_rho", "eta_u", "xi_u"))[0] = u
        var("v", ("ocean_time", "s_rho", "eta_v", "xi_v"))[0] = v
        temp_var = var("temp", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        temp_var.units = temp_units
        temp_var[0] = temp_rho
        salt_var = var("salt", ("ocean_time", "s_rho", "eta_rho", "xi_rho"))
        salt_var.units = salt_units
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
