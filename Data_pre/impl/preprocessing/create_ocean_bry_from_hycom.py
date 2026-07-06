#!/usr/bin/env python3
"""Create ROMS boundary forcing from staged HYCOM-like data."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
from scipy.ndimage import distance_transform_edt
from scipy.interpolate import RegularGridInterpolator

from case_naming import load_case_naming, roms_input_name, staged_ocean_name
from radioactive_decay import radioactive_decay_attrs
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
    normalize_longitudes,
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
    ensure_ascending,
    sigma_depths,
    summarize_numeric,
    zero_masked_uv,
)


DEFAULT_SRC = ROOT / "data" / "raw" / "ocean" / staged_ocean_name("hycom", "boundary")
DEFAULT_OUT = ROOT / "input" / roms_input_name("bdy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--stop", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--profile", default=None)
    return parser.parse_args()


def source_depth_to_z(depth: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth, dtype=float)
    return depth if np.nanmax(depth) <= 0.0 else -np.abs(depth)


def interpolate_rectilinear_2d_nearest(
    lon: np.ndarray,
    lat: np.ndarray,
    values: np.ndarray,
    target_lon: np.ndarray,
    target_lat: np.ndarray,
) -> np.ndarray:
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    values = np.asarray(values, dtype=float)
    lon, values = ensure_ascending(lon, values, axis=-1)
    lat, values = ensure_ascending(lat, values, axis=-2)
    src_lon, tgt_lon = normalize_longitudes(lon, target_lon)
    interp = RegularGridInterpolator(
        (lat, src_lon),
        values,
        method="nearest",
        bounds_error=False,
        fill_value=np.nan,
    )
    return interp(np.column_stack([target_lat.ravel(), tgt_lon.ravel()])).reshape(target_lon.shape)


def interpolate_3d(lon, lat, depth, values, target_lon, target_lat, target_z, wet_mask: np.ndarray | None = None):
    horizontal = np.empty((len(depth), *target_lon.shape), dtype=float)
    for k in range(len(depth)):
        field = interpolate_rectilinear_2d(lon, lat, values[k], target_lon, target_lat)
        if wet_mask is not None and not np.isfinite(field[np.asarray(wet_mask, dtype=bool)]).any():
            field = interpolate_rectilinear_2d_nearest(lon, lat, values[k], target_lon, target_lat)
        horizontal[k] = field
    return interpolate_vertical_vectorized(source_depth_to_z(depth), horizontal, target_z)


def convert_temperature(values: np.ndarray, units: str | None) -> np.ndarray:
    if units and "kelvin" in units.lower():
        return values - 273.15
    if np.nanmean(values) > 100.0:
        return values - 273.15
    return values


def parse_bbox_attr(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(item) for item in str(value).split(",")]
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


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


def ensure_finite(name: str, values: np.ndarray, mask: np.ndarray | None = None) -> None:
    array = np.asarray(values, dtype=float)
    if mask is not None:
        wet = np.asarray(mask, dtype=bool)
        if array.ndim != wet.ndim:
            wet = np.broadcast_to(wet, array.shape)
        array = array[wet]
    if array.size == 0:
        return
    if np.isnan(array).any():
        raise SystemExit(f"{name} still contains NaN after fill")


def print_summary(name: str, values: np.ndarray) -> None:
    summary = summarize_numeric(values)
    print(
        f"{name}: min={summary['min']} max={summary['max']} "
        f"mean={summary['mean']} finite={summary['finite_count']} nan={summary['nan_count']}"
    )


def ensure_reasonable_temp_salt(temp: np.ndarray, salt: np.ndarray, context: str) -> None:
    temp_values = np.asarray(temp, dtype=float)
    salt_values = np.asarray(salt, dtype=float)
    temp_finite = temp_values[np.isfinite(temp_values)]
    salt_finite = salt_values[np.isfinite(salt_values)]
    if salt_finite.size == 0:
        raise SystemExit(f"{context}: salt has no finite values")
    if abs(float(np.mean(temp_finite)) - float(np.mean(salt_finite))) < 3.0:
        raise SystemExit(f"{context}: salt mean is suspiciously close to temp mean")
    if float(np.mean(salt_finite < 25.0)) > 0.01:
        raise SystemExit(f"{context}: too many salt values below 25 psu")


def fill_any_field_2d(field: np.ndarray) -> np.ndarray:
    values = np.asarray(field, dtype=float)
    finite = np.isfinite(values)
    if not np.any(finite):
        raise SystemExit("cannot fill source 2D field: no finite points available")
    _, nearest = distance_transform_edt(~finite, return_indices=True)
    return np.asarray(values[nearest[0], nearest[1]], dtype=float)


def fill_any_field_3d(field: np.ndarray) -> np.ndarray:
    values = np.asarray(field, dtype=float)
    if values.ndim != 3:
        raise SystemExit("fill_any_field_3d expects a 3D array")
    out = np.empty_like(values, dtype=float)
    valid_levels = [k for k in range(values.shape[0]) if np.isfinite(values[k]).any()]
    if not valid_levels:
        raise SystemExit("cannot fill source 3D field: no finite points available in any layer")
    for k in range(values.shape[0]):
        source_k = min(valid_levels, key=lambda idx: abs(idx - k))
        out[k] = fill_any_field_2d(values[source_k])
    return out


def edge_target_geometry(grid, z_r, hz, edge: str):
    if edge == "west":
        mask_rho = grid.mask_rho[:, :2] == 1
        return {
            "rho_lon": grid.lon_rho[:, :2],
            "rho_lat": grid.lat_rho[:, :2],
            "angle": grid.angle[:, :2],
            "z_r": z_r[:, :, :2],
            "hz": hz[:, :, :2],
            "mask_rho": mask_rho,
            "mask_u": mask_rho[:, :-1] & mask_rho[:, 1:],
            "mask_v": mask_rho[:-1, :] & mask_rho[1:, :],
        }
    if edge == "east":
        mask_rho = grid.mask_rho[:, -2:] == 1
        return {
            "rho_lon": grid.lon_rho[:, -2:],
            "rho_lat": grid.lat_rho[:, -2:],
            "angle": grid.angle[:, -2:],
            "z_r": z_r[:, :, -2:],
            "hz": hz[:, :, -2:],
            "mask_rho": mask_rho,
            "mask_u": mask_rho[:, :-1] & mask_rho[:, 1:],
            "mask_v": mask_rho[:-1, :] & mask_rho[1:, :],
        }
    if edge == "south":
        mask_rho = grid.mask_rho[:2, :] == 1
        return {
            "rho_lon": grid.lon_rho[:2, :],
            "rho_lat": grid.lat_rho[:2, :],
            "angle": grid.angle[:2, :],
            "z_r": z_r[:, :2, :],
            "hz": hz[:, :2, :],
            "mask_rho": mask_rho,
            "mask_u": mask_rho[:, :-1] & mask_rho[:, 1:],
            "mask_v": mask_rho[:-1, :] & mask_rho[1:, :],
        }
    mask_rho = grid.mask_rho[-2:, :] == 1
    return {
        "rho_lon": grid.lon_rho[-2:, :],
        "rho_lat": grid.lat_rho[-2:, :],
        "angle": grid.angle[-2:, :],
        "z_r": z_r[:, -2:, :],
        "hz": hz[:, -2:, :],
        "mask_rho": mask_rho,
        "mask_u": mask_rho[:, :-1] & mask_rho[:, 1:],
        "mask_v": mask_rho[:-1, :] & mask_rho[1:, :],
    }


def write_zero_edge(
    edge: str,
    out_index: int,
    zeta_vars: dict,
    ubar_vars: dict,
    vbar_vars: dict,
    u_vars: dict,
    v_vars: dict,
    temp_vars: dict,
    salt_vars: dict,
    dye_vars: dict,
) -> None:
    zeta_vars[edge][out_index, :] = 0.0
    ubar_vars[edge][out_index, :] = 0.0
    vbar_vars[edge][out_index, :] = 0.0
    u_vars[edge][out_index, :, :] = 0.0
    v_vars[edge][out_index, :, :] = 0.0
    temp_vars[edge][out_index, :, :] = 0.0
    salt_vars[edge][out_index, :, :] = 0.0
    dye_vars[edge][out_index, :, :] = 0.0


def interpolate_edge_state(lon, lat, depth, zeta_src, temp_src, salt_src, u_src, v_src, geometry):
    zeta_src = fill_any_field_2d(zeta_src)
    temp_src = fill_any_field_3d(temp_src)
    salt_src = fill_any_field_3d(salt_src)
    u_src = fill_any_field_3d(u_src)
    v_src = fill_any_field_3d(v_src)
    zeta_rho = interpolate_rectilinear_2d(lon, lat, zeta_src, geometry["rho_lon"], geometry["rho_lat"])
    if not np.isfinite(zeta_rho[geometry["mask_rho"]]).any():
        zeta_rho = interpolate_rectilinear_2d_nearest(lon, lat, zeta_src, geometry["rho_lon"], geometry["rho_lat"])
    temp_rho = interpolate_3d(
        lon, lat, depth, temp_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"], geometry["mask_rho"]
    )
    salt_rho = interpolate_3d(
        lon, lat, depth, salt_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"], geometry["mask_rho"]
    )
    u_rho_east = interpolate_3d(
        lon, lat, depth, u_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"], geometry["mask_rho"]
    )
    v_rho_north = interpolate_3d(
        lon, lat, depth, v_src, geometry["rho_lon"], geometry["rho_lat"], geometry["z_r"], geometry["mask_rho"]
    )
    if np.any(geometry["mask_rho"]):
        zeta_rho = fill_rho_field_2d(zeta_rho, geometry["mask_rho"])
        temp_rho = fill_rho_field_3d(temp_rho, geometry["mask_rho"])
        salt_rho = fill_rho_field_3d(salt_rho, geometry["mask_rho"])
        u_rho_east = fill_rho_field_3d(u_rho_east, geometry["mask_rho"])
        v_rho_north = fill_rho_field_3d(v_rho_north, geometry["mask_rho"])
    u_rho, v_rho = rotate_to_grid(u_rho_east, v_rho_north, geometry["angle"][None, :, :])
    u = rho_to_u(u_rho)
    v = rho_to_v(v_rho)
    ubar = depth_average(u, hz_to_u(geometry["hz"]))
    vbar = depth_average(v, hz_to_v(geometry["hz"]))
    u = zero_masked_uv(u, geometry["mask_u"])
    v = zero_masked_uv(v, geometry["mask_v"])
    ubar = zero_masked_uv(ubar, geometry["mask_u"])
    vbar = zero_masked_uv(vbar, geometry["mask_v"])
    ensure_finite("edge zeta", zeta_rho, geometry["mask_rho"])
    ensure_finite("edge temp", temp_rho, geometry["mask_rho"])
    ensure_finite("edge salt", salt_rho, geometry["mask_rho"])
    ensure_finite("edge u", u, geometry["mask_u"])
    ensure_finite("edge v", v, geometry["mask_v"])
    ensure_finite("edge ubar", ubar, geometry["mask_u"])
    ensure_finite("edge vbar", vbar, geometry["mask_v"])
    return {
        "zeta_rho": zeta_rho,
        "temp_rho": temp_rho,
        "salt_rho": salt_rho,
        "u": u,
        "v": v,
        "ubar": ubar,
        "vbar": vbar,
    }


def main() -> None:
    args = parse_args()
    src_path = Path(args.src)
    if not src_path.exists():
        raise SystemExit(f"source file not found: {src_path}")
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    out_path = Path(args.output)
    if args.profile and args.output == str(DEFAULT_OUT):
        out_path = ROOT / "input" / roms_input_name("bdy", profile=args.profile)
    grid = load_grid(grid_path)
    vertical = load_vertical_config()
    z_r, _, hz = sigma_depths(grid.h, vertical)
    params = load_project_params()
    start = datetime.fromisoformat(args.start or params["time"]["start"])
    stop = datetime.fromisoformat(args.stop or params["time"]["stop"])

    with Dataset(src_path) as src:
        lon, lat, lon_name, lat_name = get_rectilinear_lon_lat(src)
        depth_name = infer_variable(src, ("depth", "lev", "level", "z"))
        depth = np.asarray(src.variables[depth_name][:], dtype=float)
        times, _, _ = read_time_values(src, ("time", "ocean_time", "mt"))
        selected = [index for index, time in enumerate(times) if start <= time <= stop]
        if not selected:
            raise SystemExit("no source times overlap requested window")

        zeta_name = infer_variable(src, ("zeta", "ssh", "surf_el"))
        temp_name = infer_variable(src, ("temp", "water_temp", "temperature"))
        salt_name = infer_variable(src, ("salt", "salinity"))
        u_name = infer_variable(src, ("u", "water_u", "u_velocity"))
        v_name = infer_variable(src, ("v", "water_v", "v_velocity"))
        edge_bboxes = {
            edge: parse_bbox_attr(getattr(src, f"source_edge_{edge}_bbox", None))
            for edge in ("west", "east", "south", "north")
        }

        with Dataset(out_path, "w", format="NETCDF4") as ds:
            ds.createDimension("zeta_time", len(selected))
            ds.createDimension("v2d_time", len(selected))
            ds.createDimension("v3d_time", len(selected))
            ds.createDimension("temp_time", len(selected))
            ds.createDimension("salt_time", len(selected))
            ds.createDimension("dye_time", len(selected))
            ds.createDimension("eta_rho", grid.lon_rho.shape[0])
            ds.createDimension("xi_rho", grid.lon_rho.shape[1])
            ds.createDimension("eta_u", grid.lon_u.shape[0])
            ds.createDimension("xi_u", grid.lon_u.shape[1])
            ds.createDimension("eta_v", grid.lon_v.shape[0])
            ds.createDimension("xi_v", grid.lon_v.shape[1])
            ds.createDimension("s_rho", vertical.N)
            ds.title = f"{load_case_naming().title} ROMS boundary forcing from HYCOM-like staged data"
            ds.grid_source = str(grid_path)
            ds.source_dataset = str(src_path)
            ds.preprocessing_version = PREPROCESSING_VERSION
            for name, value in radioactive_decay_attrs(params, args.profile).items():
                setattr(ds, name, value)

            selected_times = [times[index] for index in selected]
            create_time_variable(ds, "zeta_time", selected_times, "boundary free-surface time")
            create_time_variable(ds, "v2d_time", selected_times, "boundary barotropic velocity time")
            create_time_variable(ds, "v3d_time", selected_times, "boundary 3D velocity time")
            create_time_variable(ds, "temp_time", selected_times, "boundary temperature time")
            create_time_variable(ds, "salt_time", selected_times, "boundary salinity time")
            create_time_variable(ds, "dye_time", selected_times, "boundary passive tracer time")

            def var(name: str, dims: tuple[str, ...]):
                return ds.createVariable(name, "f8", dims, zlib=True, complevel=1)

            zeta_vars = {edge: var(f"zeta_{edge}", ("zeta_time", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in ("west", "east", "south", "north")}
            ubar_vars = {edge: var(f"ubar_{edge}", ("v2d_time", "eta_u" if edge in {"west", "east"} else "xi_u")) for edge in ("west", "east", "south", "north")}
            vbar_vars = {edge: var(f"vbar_{edge}", ("v2d_time", "eta_v" if edge in {"west", "east"} else "xi_v")) for edge in ("west", "east", "south", "north")}
            u_vars = {edge: var(f"u_{edge}", ("v3d_time", "s_rho", "eta_u" if edge in {"west", "east"} else "xi_u")) for edge in ("west", "east", "south", "north")}
            v_vars = {edge: var(f"v_{edge}", ("v3d_time", "s_rho", "eta_v" if edge in {"west", "east"} else "xi_v")) for edge in ("west", "east", "south", "north")}
            temp_vars = {edge: var(f"temp_{edge}", ("temp_time", "s_rho", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in ("west", "east", "south", "north")}
            salt_vars = {edge: var(f"salt_{edge}", ("salt_time", "s_rho", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in ("west", "east", "south", "north")}
            dye_vars = {edge: var(f"dye_{edge}_01", ("dye_time", "s_rho", "eta_rho" if edge in {"west", "east"} else "xi_rho")) for edge in ("west", "east", "south", "north")}

            for out_index, time_index in enumerate(selected):
                zeta_src = read_dimensional_variable(src, zeta_name, lon_name, lat_name, None, time_index)
                temp_src = read_dimensional_variable(src, temp_name, lon_name, lat_name, depth_name, time_index)
                salt_src = read_dimensional_variable(src, salt_name, lon_name, lat_name, depth_name, time_index)
                u_src = read_dimensional_variable(src, u_name, lon_name, lat_name, depth_name, time_index)
                v_src = read_dimensional_variable(src, v_name, lon_name, lat_name, depth_name, time_index)
                temp_src = convert_temperature(temp_src, getattr(src.variables[temp_name], "units", ""))
                for edge in ("west", "east", "south", "north"):
                    edge_lon, edge_lat, edge_zeta = subset_edge_source(lon, lat, zeta_src, edge_bboxes[edge])
                    if not np.isfinite(edge_zeta).any():
                        edge_lon, edge_lat, edge_zeta = lon, lat, zeta_src
                    _, _, edge_temp = subset_edge_source(lon, lat, temp_src, edge_bboxes[edge])
                    _, _, edge_salt = subset_edge_source(lon, lat, salt_src, edge_bboxes[edge])
                    _, _, edge_u = subset_edge_source(lon, lat, u_src, edge_bboxes[edge])
                    _, _, edge_v = subset_edge_source(lon, lat, v_src, edge_bboxes[edge])
                    if not np.isfinite(edge_temp).any() or not np.isfinite(edge_salt).any():
                        edge_temp = temp_src
                        edge_salt = salt_src
                    if not np.isfinite(edge_u).any() or not np.isfinite(edge_v).any():
                        edge_u = u_src
                        edge_v = v_src
                    geometry = edge_target_geometry(grid, z_r, hz, edge)
                    if not np.any(geometry["mask_rho"]):
                        write_zero_edge(
                            edge,
                            out_index,
                            zeta_vars,
                            ubar_vars,
                            vbar_vars,
                            u_vars,
                            v_vars,
                            temp_vars,
                            salt_vars,
                            dye_vars,
                        )
                        continue
                    state = interpolate_edge_state(
                        edge_lon,
                        edge_lat,
                        depth,
                        edge_zeta,
                        edge_temp,
                        edge_salt,
                        edge_u,
                        edge_v,
                        geometry,
                    )
                    if edge == "west":
                        temp_edge = state["temp_rho"][:, :, 0]
                        salt_edge = state["salt_rho"][:, :, 0]
                    elif edge == "east":
                        temp_edge = state["temp_rho"][:, :, -1]
                        salt_edge = state["salt_rho"][:, :, -1]
                    elif edge == "south":
                        temp_edge = state["temp_rho"][:, 0, :]
                        salt_edge = state["salt_rho"][:, 0, :]
                    else:
                        temp_edge = state["temp_rho"][:, -1, :]
                        salt_edge = state["salt_rho"][:, -1, :]
                    ensure_reasonable_temp_salt(temp_edge, salt_edge, f"{edge} {times[time_index].isoformat()}")
                    print_summary(f"{edge} temp {times[time_index].isoformat()}", temp_edge)
                    print_summary(f"{edge} salt {times[time_index].isoformat()}", salt_edge)
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

            for name, variables in (
                ("zeta", zeta_vars),
                ("ubar", ubar_vars),
                ("vbar", vbar_vars),
                ("u", u_vars),
                ("v", v_vars),
                ("temp", temp_vars),
                ("salt", salt_vars),
            ):
                mask_u_full = (grid.mask_rho[:, :-1] == 1) & (grid.mask_rho[:, 1:] == 1)
                mask_v_full = (grid.mask_rho[:-1, :] == 1) & (grid.mask_rho[1:, :] == 1)
                for edge, variable in variables.items():
                    if edge in {"west", "east"}:
                        rho_mask = grid.mask_rho[:, 0] == 1 if edge == "west" else grid.mask_rho[:, -1] == 1
                        u_mask = mask_u_full[:, 0] if edge == "west" else mask_u_full[:, -1]
                        v_mask = mask_v_full[:, 0] if edge == "west" else mask_v_full[:, -1]
                    else:
                        rho_mask = grid.mask_rho[0, :] == 1 if edge == "south" else grid.mask_rho[-1, :] == 1
                        u_mask = mask_u_full[0, :] if edge == "south" else mask_u_full[-1, :]
                        v_mask = mask_v_full[0, :] if edge == "south" else mask_v_full[-1, :]
                    mask = rho_mask if name in {"zeta", "temp", "salt"} else (u_mask if name in {"u", "ubar"} else v_mask)
                    ensure_finite(f"{name}_{edge}", np.ma.filled(variable[:], np.nan), mask)
    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"records={len(selected)}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
