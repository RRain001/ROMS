#!/usr/bin/env python3
"""Create ROMS boundary forcing from staged GLORYS12V1 data."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
from scipy.ndimage import distance_transform_edt

from case_naming import load_case_naming
from ocean_source_utils import (
    MJD_CALENDAR,
    MJD_UNITS,
    build_glorys_paths,
    glorys_center_time,
    glorys_time_window,
    load_glorys_config,
)
from roms_preprocessing_utils import (
    create_time_variable,
    depth_average,
    get_rectilinear_lon_lat,
    hz_to_u,
    hz_to_v,
    infer_variable,
    interpolate_rectilinear_2d,
    interpolate_vertical_vectorized,
    load_grid,
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


EDGE_NAMES = ("west", "east", "south", "north")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--src", default=None)
    parser.add_argument("--grid", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--stop", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--profile", default=None)
    return parser.parse_args()


def boundary_window(config: dict, args: argparse.Namespace) -> tuple[datetime, datetime]:
    config_start, config_stop = glorys_time_window(config)
    start = datetime.fromisoformat(args.start) if args.start else glorys_center_time(config, config_start)
    stop = datetime.fromisoformat(args.stop) if args.stop else glorys_center_time(config, config_stop)
    if stop < start:
        raise SystemExit("stop must not be earlier than start")
    return start, stop


def path_window(config: dict, args: argparse.Namespace) -> tuple[datetime, datetime]:
    config_start, config_stop = glorys_time_window(config)
    start = datetime.fromisoformat(args.start) if args.start else config_start
    stop = datetime.fromisoformat(args.stop) if args.stop else config_stop
    return start, stop


def source_depth_to_z(depth: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth, dtype=float)
    return depth if np.nanmax(depth) <= 0.0 else -np.abs(depth)


def interpolate_3d(lon, lat, depth, values, target_lon, target_lat, target_z):
    horizontal = np.empty((len(depth), *target_lon.shape), dtype=float)
    for k in range(len(depth)):
        horizontal[k] = interpolate_2d_filled(lon, lat, values[k], target_lon, target_lat)
    horizontal = fill_nan_profiles_vertical(source_depth_to_z(depth), horizontal)
    return interpolate_vertical_vectorized(source_depth_to_z(depth), horizontal, target_z)


def fill_nan_nearest_2d(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    mask = np.isnan(array)
    if not np.any(mask):
        return array
    if np.all(mask):
        return array
    indices = distance_transform_edt(mask, return_distances=False, return_indices=True)
    return array[tuple(indices)]


def fill_nan_profiles_vertical(source_z: np.ndarray, values: np.ndarray) -> np.ndarray:
    src_z = np.asarray(source_z, dtype=float)
    arr = np.asarray(values, dtype=float).copy()
    if src_z[0] > src_z[-1]:
        src_z = src_z[::-1]
        arr = arr[::-1, ...]
    flat = arr.reshape(arr.shape[0], -1)
    for idx in range(flat.shape[1]):
        profile = flat[:, idx]
        finite = np.isfinite(profile)
        if not np.any(finite):
            continue
        if np.all(finite):
            continue
        flat[:, idx] = np.interp(src_z, src_z[finite], profile[finite], left=profile[finite][0], right=profile[finite][-1])
    filled = flat.reshape(arr.shape)
    if source_z[0] > source_z[-1]:
        filled = filled[::-1, ...]
    return filled


def interpolate_2d_filled(lon, lat, values, target_lon, target_lat):
    filled = fill_nan_nearest_2d(values)
    lon_min = float(np.nanmin(lon))
    lon_max = float(np.nanmax(lon))
    lat_min = float(np.nanmin(lat))
    lat_max = float(np.nanmax(lat))
    clipped_lon = np.clip(target_lon, lon_min, lon_max)
    clipped_lat = np.clip(target_lat, lat_min, lat_max)
    return interpolate_rectilinear_2d(lon, lat, filled, clipped_lon, clipped_lat)


def parse_bbox_attr(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(item) for item in str(value).split(",")]
    return tuple(parts) if len(parts) == 4 else None


def subset_indices(values: np.ndarray, lower: float, upper: float) -> tuple[int, int]:
    start = int(np.searchsorted(values, lower, side="left"))
    stop = int(np.searchsorted(values, upper, side="right"))
    start = max(0, min(start, len(values)))
    stop = max(start, min(stop, len(values)))
    return start, stop


def subset_edge_source(lon, lat, values, bbox: tuple[float, float, float, float] | None):
    if bbox is None:
        return lon, lat, values
    west, east, south, north = bbox
    lat_start, lat_stop = subset_indices(lat, south, north)
    lon_start, lon_stop = subset_indices(lon, west, east)
    if values.ndim == 2:
        subset = values[lat_start:lat_stop, lon_start:lon_stop]
    else:
        subset = values[:, lat_start:lat_stop, lon_start:lon_stop]
    return lon[lon_start:lon_stop], lat[lat_start:lat_stop], subset


def edge_source_with_fallback(lon, lat, values, bbox: tuple[float, float, float, float] | None):
    edge_lon, edge_lat, edge_values = subset_edge_source(lon, lat, values, bbox)
    # A 1-point strip in either horizontal direction is too degenerate for
    # stable 2D interpolation, so fall back to the full staged subset.
    if edge_lon.size < 2 or edge_lat.size < 2:
        return lon, lat, values
    if np.isfinite(edge_values).any():
        return edge_lon, edge_lat, edge_values
    return lon, lat, values


def edge_target_geometry(grid, z_r, hz, edge: str):
    wet_rho = grid.mask_rho == 1
    wet_u = wet_rho[:, :-1] & wet_rho[:, 1:]
    wet_v = wet_rho[:-1, :] & wet_rho[1:, :]
    if edge == "west":
        return {
            "rho_lon": grid.lon_rho[:, :2],
            "rho_lat": grid.lat_rho[:, :2],
            "angle": grid.angle[:, :2],
            "z_r": z_r[:, :, :2],
            "hz": hz[:, :, :2],
            "rho_mask": wet_rho[:, :2],
            "u_mask": wet_u[:, :1],
            "v_mask": wet_v[:, :2],
        }
    if edge == "east":
        return {
            "rho_lon": grid.lon_rho[:, -2:],
            "rho_lat": grid.lat_rho[:, -2:],
            "angle": grid.angle[:, -2:],
            "z_r": z_r[:, :, -2:],
            "hz": hz[:, :, -2:],
            "rho_mask": wet_rho[:, -2:],
            "u_mask": wet_u[:, -1:],
            "v_mask": wet_v[:, -2:],
        }
    if edge == "south":
        return {
            "rho_lon": grid.lon_rho[:2, :],
            "rho_lat": grid.lat_rho[:2, :],
            "angle": grid.angle[:2, :],
            "z_r": z_r[:, :2, :],
            "hz": hz[:, :2, :],
            "rho_mask": wet_rho[:2, :],
            "u_mask": wet_u[:2, :],
            "v_mask": wet_v[:1, :],
        }
    return {
        "rho_lon": grid.lon_rho[-2:, :],
        "rho_lat": grid.lat_rho[-2:, :],
        "angle": grid.angle[-2:, :],
        "z_r": z_r[:, -2:, :],
        "hz": hz[:, -2:, :],
        "rho_mask": wet_rho[-2:, :],
        "u_mask": wet_u[-2:, :],
        "v_mask": wet_v[-1:, :],
    }


def interpolate_edge_state(lon, lat, depth, zeta_src, temp_src, salt_src, u_src, v_src, geometry):
    zeta_rho = interpolate_2d_filled(lon, lat, zeta_src, geometry["rho_lon"], geometry["rho_lat"])
    temp_rho = interpolate_3d(lon, lat, depth, temp_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"])
    salt_rho = interpolate_3d(lon, lat, depth, salt_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"])
    u_rho_east = interpolate_3d(lon, lat, depth, u_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"])
    v_rho_north = interpolate_3d(lon, lat, depth, v_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"])
    u_rho, v_rho = rotate_to_grid(u_rho_east, v_rho_north, geometry["angle"][None, :, :])
    u = rho_to_u(u_rho)
    v = rho_to_v(v_rho)
    u = zero_masked_uv(u, geometry["u_mask"])
    v = zero_masked_uv(v, geometry["v_mask"])
    ubar = depth_average(u, hz_to_u(geometry["hz"]))
    vbar = depth_average(v, hz_to_v(geometry["hz"]))
    zeta_rho = np.where(geometry["rho_mask"], zeta_rho, 0.0)
    temp_rho = zero_masked_uv(temp_rho, geometry["rho_mask"])
    salt_rho = zero_masked_uv(salt_rho, geometry["rho_mask"])
    ubar = zero_masked_uv(ubar, geometry["u_mask"])
    vbar = zero_masked_uv(vbar, geometry["v_mask"])
    return {"zeta_rho": zeta_rho, "temp_rho": temp_rho, "salt_rho": salt_rho, "u": u, "v": v, "ubar": ubar, "vbar": vbar}


def assert_boundary_quality(ds: Dataset) -> None:
    for edge in EDGE_NAMES:
        for name in (f"zeta_{edge}", f"ubar_{edge}", f"vbar_{edge}", f"u_{edge}", f"v_{edge}", f"temp_{edge}", f"salt_{edge}"):
            raw = np.ma.asarray(ds.variables[name][:])
            if raw.size == 0 or np.all(np.ma.getmaskarray(raw)):
                raise SystemExit(f"{name} contains only masked/_FillValue entries")
            values = np.asarray(np.ma.filled(raw, np.nan), dtype=float)
            if np.isnan(values).any():
                raise SystemExit(f"{name} contains NaN values")
            if not np.isfinite(values).any():
                raise SystemExit(f"{name} contains no finite values")
    times = np.asarray(ds.variables["zeta_time"][:], dtype=float)
    if np.any(np.diff(times) <= 0.0):
        raise SystemExit("boundary time axis is not strictly increasing")


def main() -> None:
    args = parse_args()
    config = load_glorys_config(args.config)
    requested_start, requested_stop = boundary_window(config, args)
    name_start, name_stop = path_window(config, args)
    default_paths = build_glorys_paths(config, start=name_start, stop=name_stop, profile=args.profile)
    src_path = Path(args.src) if args.src else default_paths.staged_boundary
    out_path = Path(args.output) if args.output else default_paths.roms_bdy
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)

    if not src_path.exists():
        raise SystemExit(f"source file not found: {src_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    grid = load_grid(grid_path)
    vertical = load_vertical_config()
    z_r, _, hz = sigma_depths(grid.h, vertical)

    with Dataset(src_path) as src:
        lon, lat, lon_name, lat_name = get_rectilinear_lon_lat(src)
        depth_name = infer_variable(src, ("depth", "lev", "level", "z"))
        depth = np.asarray(src.variables[depth_name][:], dtype=float)
        times, _, _ = read_time_values(src, ("time", "ocean_time", "mt"))
        selected = [idx for idx, value in enumerate(times) if requested_start <= value <= requested_stop]
        if not selected:
            raise SystemExit("no source times overlap requested window")

        zeta_name = infer_variable(src, ("zos", "zeta", "ssh", "surf_el"))
        temp_name = infer_variable(src, ("thetao", "temp", "water_temp", "temperature"))
        salt_name = infer_variable(src, ("so", "salt", "salinity"))
        u_name = infer_variable(src, ("uo", "u", "water_u", "u_velocity"))
        v_name = infer_variable(src, ("vo", "v", "water_v", "v_velocity"))
        edge_bboxes = {edge: parse_bbox_attr(getattr(src, f"source_edge_{edge}_bbox", None)) for edge in EDGE_NAMES}

        with Dataset(out_path, "w", format="NETCDF4") as ds:
            size = len(selected)
            for dim in ("zeta_time", "v2d_time", "v3d_time", "temp_time", "salt_time", "dye_time"):
                ds.createDimension(dim, size)
            ds.createDimension("eta_rho", grid.lon_rho.shape[0])
            ds.createDimension("xi_rho", grid.lon_rho.shape[1])
            ds.createDimension("eta_u", grid.lon_u.shape[0])
            ds.createDimension("xi_u", grid.lon_u.shape[1])
            ds.createDimension("eta_v", grid.lon_v.shape[0])
            ds.createDimension("xi_v", grid.lon_v.shape[1])
            ds.createDimension("s_rho", vertical.N)
            ds.title = f"{load_case_naming().title} ROMS boundary forcing from GLORYS12V1 staged data"
            ds.grid_source = str(grid_path)
            ds.source_dataset = str(src_path)
            ds.source = "GLORYS12V1 / GLOBAL_MULTIYEAR_PHY_001_030"
            ds.dataset_id = config["dataset_id_daily"]
            ds.time_reference = f"MJD / {MJD_UNITS}"

            selected_times = [times[index] for index in selected]
            create_time_variable(ds, "zeta_time", selected_times, "boundary free-surface time")
            create_time_variable(ds, "v2d_time", selected_times, "boundary barotropic velocity time")
            create_time_variable(ds, "v3d_time", selected_times, "boundary 3D velocity time")
            create_time_variable(ds, "temp_time", selected_times, "boundary temperature time")
            create_time_variable(ds, "salt_time", selected_times, "boundary salinity time")
            create_time_variable(ds, "dye_time", selected_times, "boundary passive tracer time")
            for name in ("zeta_time", "v2d_time", "v3d_time", "temp_time", "salt_time", "dye_time"):
                ds.variables[name].units = MJD_UNITS
                ds.variables[name].calendar = MJD_CALENDAR

            def var(name: str, dims: tuple[str, ...]):
                return ds.createVariable(name, "f8", dims, zlib=True, complevel=1)

            zeta_vars = {edge: var(f"zeta_{edge}", ("zeta_time", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in EDGE_NAMES}
            ubar_vars = {edge: var(f"ubar_{edge}", ("v2d_time", "eta_u" if edge in {"west", "east"} else "xi_u")) for edge in EDGE_NAMES}
            vbar_vars = {edge: var(f"vbar_{edge}", ("v2d_time", "eta_v" if edge in {"west", "east"} else "xi_v")) for edge in EDGE_NAMES}
            u_vars = {edge: var(f"u_{edge}", ("v3d_time", "s_rho", "eta_u" if edge in {"west", "east"} else "xi_u")) for edge in EDGE_NAMES}
            v_vars = {edge: var(f"v_{edge}", ("v3d_time", "s_rho", "eta_v" if edge in {"west", "east"} else "xi_v")) for edge in EDGE_NAMES}
            temp_vars = {edge: var(f"temp_{edge}", ("temp_time", "s_rho", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in EDGE_NAMES}
            salt_vars = {edge: var(f"salt_{edge}", ("salt_time", "s_rho", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in EDGE_NAMES}
            dye_vars = {edge: var(f"dye_{edge}_01", ("dye_time", "s_rho", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in EDGE_NAMES}

            for out_index, time_index in enumerate(selected):
                zeta_src = read_dimensional_variable(src, zeta_name, lon_name, lat_name, None, time_index)
                temp_src = read_dimensional_variable(src, temp_name, lon_name, lat_name, depth_name, time_index)
                salt_src = read_dimensional_variable(src, salt_name, lon_name, lat_name, depth_name, time_index)
                u_src = read_dimensional_variable(src, u_name, lon_name, lat_name, depth_name, time_index)
                v_src = read_dimensional_variable(src, v_name, lon_name, lat_name, depth_name, time_index)

                for edge in EDGE_NAMES:
                    edge_lon, edge_lat, edge_zeta = edge_source_with_fallback(lon, lat, zeta_src, edge_bboxes[edge])
                    _, _, edge_temp = edge_source_with_fallback(lon, lat, temp_src, edge_bboxes[edge])
                    _, _, edge_salt = edge_source_with_fallback(lon, lat, salt_src, edge_bboxes[edge])
                    _, _, edge_u = edge_source_with_fallback(lon, lat, u_src, edge_bboxes[edge])
                    _, _, edge_v = edge_source_with_fallback(lon, lat, v_src, edge_bboxes[edge])
                    state = interpolate_edge_state(edge_lon, edge_lat, depth, edge_zeta, edge_temp, edge_salt, edge_u, edge_v, edge_target_geometry(grid, z_r, hz, edge))

                    if edge == "west":
                        zeta_vars[edge][out_index, :] = state["zeta_rho"][:, 0]
                        ubar_vars[edge][out_index, :] = state["ubar"][:, 0]
                        vbar_vars[edge][out_index, :] = state["vbar"][:, 0]
                        u_vars[edge][out_index, :, :] = state["u"][:, :, 0]
                        v_vars[edge][out_index, :, :] = state["v"][:, :, 0]
                        temp_vars[edge][out_index, :, :] = state["temp_rho"][:, :, 0]
                        salt_vars[edge][out_index, :, :] = state["salt_rho"][:, :, 0]
                        dye_vars[edge][out_index, :, :] = np.zeros_like(state["temp_rho"][:, :, 0])
                    elif edge == "east":
                        zeta_vars[edge][out_index, :] = state["zeta_rho"][:, -1]
                        ubar_vars[edge][out_index, :] = state["ubar"][:, -1]
                        vbar_vars[edge][out_index, :] = state["vbar"][:, -1]
                        u_vars[edge][out_index, :, :] = state["u"][:, :, -1]
                        v_vars[edge][out_index, :, :] = state["v"][:, :, -1]
                        temp_vars[edge][out_index, :, :] = state["temp_rho"][:, :, -1]
                        salt_vars[edge][out_index, :, :] = state["salt_rho"][:, :, -1]
                        dye_vars[edge][out_index, :, :] = np.zeros_like(state["temp_rho"][:, :, -1])
                    elif edge == "south":
                        zeta_vars[edge][out_index, :] = state["zeta_rho"][0, :]
                        ubar_vars[edge][out_index, :] = state["ubar"][0, :]
                        vbar_vars[edge][out_index, :] = state["vbar"][0, :]
                        u_vars[edge][out_index, :, :] = state["u"][:, 0, :]
                        v_vars[edge][out_index, :, :] = state["v"][:, 0, :]
                        temp_vars[edge][out_index, :, :] = state["temp_rho"][:, 0, :]
                        salt_vars[edge][out_index, :, :] = state["salt_rho"][:, 0, :]
                        dye_vars[edge][out_index, :, :] = np.zeros_like(state["temp_rho"][:, 0, :])
                    else:
                        zeta_vars[edge][out_index, :] = state["zeta_rho"][-1, :]
                        ubar_vars[edge][out_index, :] = state["ubar"][-1, :]
                        vbar_vars[edge][out_index, :] = state["vbar"][-1, :]
                        u_vars[edge][out_index, :, :] = state["u"][:, -1, :]
                        v_vars[edge][out_index, :, :] = state["v"][:, -1, :]
                        temp_vars[edge][out_index, :, :] = state["temp_rho"][:, -1, :]
                        salt_vars[edge][out_index, :, :] = state["salt_rho"][:, -1, :]
                        dye_vars[edge][out_index, :, :] = np.zeros_like(state["temp_rho"][:, -1, :])

        with Dataset(out_path) as check_ds:
            assert_boundary_quality(check_ds)

    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"records={len(selected)}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
