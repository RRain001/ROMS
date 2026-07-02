#!/usr/bin/env python3
"""Download only boundary 3D fields from HYCOM ESPC-D-V02.

This second-generation script targets south/north/west/east boundaries of a
requested lat/lon box and stores only 3D u/v/temp/salt data on those edges.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

from hycom_espc_download import (
    DEFAULT_DEPTH_RANGE,
    VAR_ATTRS,
    bounding_indices,
    fetch_3d_cube,
    fetch_coord_vector,
    hours_to_datetime,
    split_index_range,
    time_indices,
)


def build_boundary_dataset(
    start: datetime,
    days: int,
    lat_bounds: tuple[float, float],
    lon_bounds: tuple[float, float],
    depth_bounds: tuple[float, float],
) -> xr.Dataset:
    if days <= 0:
        raise ValueError("days must be positive")

    base_url = "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/s3z"
    all_times = fetch_coord_vector(base_url, "time")
    all_depths = fetch_coord_vector(base_url, "depth")
    all_lats = fetch_coord_vector(base_url, "lat")
    all_lons = fetch_coord_vector(base_url, "lon")

    times_requested = [start + timedelta(hours=3 * step) for step in range(days * 8)]
    t_sel = time_indices(all_times, times_requested)
    d_sel = bounding_indices(all_depths, *depth_bounds)
    lat_sel = bounding_indices(all_lats, *lat_bounds)
    lon_sel = bounding_indices(all_lons, *lon_bounds)
    chunk_ranges = split_index_range(t_sel, chunk_size=8)

    time_parts: list[np.ndarray] = []
    south_parts: dict[str, list[np.ndarray]] = {name: [] for name in ("salt", "temp", "u", "v")}
    north_parts: dict[str, list[np.ndarray]] = {name: [] for name in ("salt", "temp", "u", "v")}
    west_parts: dict[str, list[np.ndarray]] = {name: [] for name in ("salt", "temp", "u", "v")}
    east_parts: dict[str, list[np.ndarray]] = {name: [] for name in ("salt", "temp", "u", "v")}

    depths = south_lon = north_lon = west_lat = east_lat = None
    south_lat = north_lat = west_lon = east_lon = None

    short_names = ("sal", "temp", "u", "v")
    output_names = {"sal": "salt", "temp": "temp", "u": "u", "v": "v"}

    for chunk_no, chunk in enumerate(chunk_ranges, start=1):
        print(f"Downloading boundary chunk {chunk_no}/{len(chunk_ranges)}: time indices {chunk.start}-{chunk.stop}")
        times = None
        for short_name in short_names:
            south_time, chunk_depths, _, chunk_south_lon, south = fetch_3d_cube(
                short_name, chunk, d_sel, lat_sel=type(lat_sel)(lat_sel.start, lat_sel.start, lat_sel.step), lon_sel=lon_sel
            )
            north_time, _, _, chunk_north_lon, north = fetch_3d_cube(
                short_name, chunk, d_sel, lat_sel=type(lat_sel)(lat_sel.stop, lat_sel.stop, lat_sel.step), lon_sel=lon_sel
            )
            west_time, _, chunk_west_lat, _, west = fetch_3d_cube(
                short_name, chunk, d_sel, lat_sel=lat_sel, lon_sel=type(lon_sel)(lon_sel.start, lon_sel.start, lon_sel.step)
            )
            east_time, _, chunk_east_lat, _, east = fetch_3d_cube(
                short_name, chunk, d_sel, lat_sel=lat_sel, lon_sel=type(lon_sel)(lon_sel.stop, lon_sel.stop, lon_sel.step)
            )

            out_name = output_names[short_name]
            south_parts[out_name].append(np.squeeze(south, axis=2))
            north_parts[out_name].append(np.squeeze(north, axis=2))
            west_parts[out_name].append(np.squeeze(west, axis=3))
            east_parts[out_name].append(np.squeeze(east, axis=3))

            times = south_time
            depths = chunk_depths
            south_lon = chunk_south_lon
            north_lon = chunk_north_lon
            west_lat = chunk_west_lat
            east_lat = chunk_east_lat

            south_lat = all_lats[lat_sel.start]
            north_lat = all_lats[lat_sel.stop]
            west_lon = all_lons[lon_sel.start]
            east_lon = all_lons[lon_sel.stop]

        if times is not None:
            time_parts.append(times)

    if any(value is None for value in (depths, south_lon, north_lon, west_lat, east_lat)):
        raise RuntimeError("Boundary download did not return coordinates")

    datetimes = np.array(hours_to_datetime(np.concatenate(time_parts, axis=0)), dtype="datetime64[ns]")
    ds = xr.Dataset(
        coords={
            "time": datetimes,
            "depth": depths.astype(np.float32),
            "south_lon": south_lon.astype(np.float32),
            "north_lon": north_lon.astype(np.float32),
            "west_lat": west_lat.astype(np.float32),
            "east_lat": east_lat.astype(np.float32),
        },
        attrs={
            "source": "HYCOM ESPC-D-V02 boundary-only 3D fields",
            "requested_lat_bounds": f"{lat_bounds[0]},{lat_bounds[1]}",
            "requested_lon_bounds": f"{lon_bounds[0]},{lon_bounds[1]}",
            "south_lat": float(south_lat),
            "north_lat": float(north_lat),
            "west_lon": float(west_lon),
            "east_lon": float(east_lon),
        },
    )

    for name in ("salt", "temp", "u", "v"):
        ds[f"south_{name}"] = (("time", "depth", "south_lon"), np.concatenate(south_parts[name], axis=0))
        ds[f"north_{name}"] = (("time", "depth", "north_lon"), np.concatenate(north_parts[name], axis=0))
        ds[f"west_{name}"] = (("time", "depth", "west_lat"), np.concatenate(west_parts[name], axis=0))
        ds[f"east_{name}"] = (("time", "depth", "east_lat"), np.concatenate(east_parts[name], axis=0))

    ds["south_lat"] = xr.DataArray(np.float32(south_lat))
    ds["north_lat"] = xr.DataArray(np.float32(north_lat))
    ds["west_lon"] = xr.DataArray(np.float32(west_lon))
    ds["east_lon"] = xr.DataArray(np.float32(east_lon))

    ds["south_salt"].attrs.update({"long_name": "South boundary salinity", "units": VAR_ATTRS["sal"]["units"]})
    ds["north_salt"].attrs.update({"long_name": "North boundary salinity", "units": VAR_ATTRS["sal"]["units"]})
    ds["west_salt"].attrs.update({"long_name": "West boundary salinity", "units": VAR_ATTRS["sal"]["units"]})
    ds["east_salt"].attrs.update({"long_name": "East boundary salinity", "units": VAR_ATTRS["sal"]["units"]})
    ds["south_temp"].attrs.update({"long_name": "South boundary temperature", "units": VAR_ATTRS["temp"]["units"]})
    ds["north_temp"].attrs.update({"long_name": "North boundary temperature", "units": VAR_ATTRS["temp"]["units"]})
    ds["west_temp"].attrs.update({"long_name": "West boundary temperature", "units": VAR_ATTRS["temp"]["units"]})
    ds["east_temp"].attrs.update({"long_name": "East boundary temperature", "units": VAR_ATTRS["temp"]["units"]})
    ds["south_u"].attrs.update({"long_name": "South boundary eastward velocity", "units": VAR_ATTRS["u"]["units"]})
    ds["north_u"].attrs.update({"long_name": "North boundary eastward velocity", "units": VAR_ATTRS["u"]["units"]})
    ds["west_u"].attrs.update({"long_name": "West boundary eastward velocity", "units": VAR_ATTRS["u"]["units"]})
    ds["east_u"].attrs.update({"long_name": "East boundary eastward velocity", "units": VAR_ATTRS["u"]["units"]})
    ds["south_v"].attrs.update({"long_name": "South boundary northward velocity", "units": VAR_ATTRS["v"]["units"]})
    ds["north_v"].attrs.update({"long_name": "North boundary northward velocity", "units": VAR_ATTRS["v"]["units"]})
    ds["west_v"].attrs.update({"long_name": "West boundary northward velocity", "units": VAR_ATTRS["v"]["units"]})
    ds["east_v"].attrs.update({"long_name": "East boundary northward velocity", "units": VAR_ATTRS["v"]["units"]})
    return ds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download HYCOM ESPC boundary-only 3D fields.")
    parser.add_argument("--lat-min", type=float, required=True)
    parser.add_argument("--lat-max", type=float, required=True)
    parser.add_argument("--lon-min", type=float, required=True)
    parser.add_argument("--lon-max", type=float, required=True)
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--depth-min", type=float, default=DEFAULT_DEPTH_RANGE[0])
    parser.add_argument("--depth-max", type=float, default=DEFAULT_DEPTH_RANGE[1])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("HYCOM ESPC Download/python_output_v2"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    start = datetime.strptime(args.start, "%Y%m%d")
    ds = build_boundary_dataset(
        start=start,
        days=args.days,
        lat_bounds=(args.lat_min, args.lat_max),
        lon_bounds=(args.lon_min, args.lon_max),
        depth_bounds=(args.depth_min, args.depth_max),
    )
    end_time = start + timedelta(days=args.days) - timedelta(hours=3)
    out_path = output_dir / f"hycom_espc_boundary_tsuv_{start:%Y%m%d}_{end_time:%Y%m%d%H}.nc"
    ds.to_netcdf(out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
