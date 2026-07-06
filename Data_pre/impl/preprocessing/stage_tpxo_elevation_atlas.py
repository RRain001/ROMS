#!/usr/bin/env python3
"""Convert local TPXO atlas elevation binaries into a staged NetCDF subset."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
from scipy.ndimage import distance_transform_edt

from case_naming import load_case_naming, staged_tides_name
from roms_preprocessing_utils import ROOT, load_grid, resolve_grid_path


DEFAULT_ATLAS_DIR = Path("/workspace/tpxo9_atlas_v5")
DEFAULT_OUTPUT = ROOT / "data" / "raw" / "tides" / staged_tides_name()
CONSTITUENT_PERIOD_HOURS = {
    "mm": 661.3106,
    "mf": 327.8599,
    "q1": 26.8684,
    "o1": 25.8193,
    "p1": 24.0659,
    "k1": 23.9345,
    "s1": 24.0,
    "n2": 12.6583,
    "m2": 12.4206,
    "s2": 12.0,
    "k2": 11.9672,
    "2n2": 12.9054,
    "mn4": 6.2692,
    "m4": 6.2103,
    "ms4": 6.1033,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas-dir", default=str(DEFAULT_ATLAS_DIR))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--constituents", default=",".join(CONSTITUENT_PERIOD_HOURS))
    parser.add_argument("--include-uv", action="store_true", help="Stage TPXO current ellipse variables for UV_TIDES")
    parser.add_argument("--profile", default=None, help="Optional profile suffix for the staged output name")
    parser.add_argument("--velocity-depth-min", type=float, default=10.0, help="Minimum TPXO depth used when converting transports to velocity")
    return parser.parse_args()


def read_grid_header(path: Path) -> tuple[int, int, float]:
    with path.open("rb") as handle:
        record_len = struct.unpack(">i", handle.read(4))[0]
        if record_len != 32:
            raise SystemExit(f"unexpected TPXO grid header length {record_len} in {path}")
        raw = handle.read(record_len)
    nlon, nlat, _, _, half_step, _, _, _ = struct.unpack(">2i6f", raw)
    return nlon, nlat, float(half_step)


def atlas_coordinates(nlon: int, nlat: int, half_step: float) -> tuple[np.ndarray, np.ndarray]:
    step = 2.0 * half_step
    lon = np.arange(nlon, dtype=float) * step
    lat = -90.0 + np.arange(nlat, dtype=float) * step
    return lon, lat


def subset_bounds(lon: np.ndarray, lat: np.ndarray, grid_path: Path) -> tuple[slice, slice]:
    grid = load_grid(grid_path)
    west = float(np.nanmin(grid.lon_rho))
    east = float(np.nanmax(grid.lon_rho))
    south = float(np.nanmin(grid.lat_rho))
    north = float(np.nanmax(grid.lat_rho))
    lon_step = float(np.nanmedian(np.diff(lon))) if lon.size > 1 else 0.0
    lat_step = float(np.nanmedian(np.diff(lat))) if lat.size > 1 else 0.0
    lon_start = max(0, int(np.searchsorted(lon, west - lon_step, side="left")))
    lon_stop = min(len(lon), int(np.searchsorted(lon, east + lon_step, side="right")))
    lat_start = max(0, int(np.searchsorted(lat, south - lat_step, side="left")))
    lat_stop = min(len(lat), int(np.searchsorted(lat, north + lat_step, side="right")))
    return slice(lat_start, lat_stop), slice(lon_start, lon_stop)


def read_grid_subset(path: Path, lat_slice: slice, lon_slice: slice, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    nlat, nlon = shape
    count = nlat * nlon
    depth_offset = 56
    mask_offset = 52 + 4 + count * 4 + 4 + 4
    depth = np.memmap(path, dtype=">f4", mode="r", offset=depth_offset, shape=(nlat, nlon))
    mask = np.memmap(path, dtype=">i4", mode="r", offset=mask_offset, shape=(nlat, nlon))
    return np.asarray(depth[lat_slice, lon_slice], dtype=np.float32), np.asarray(mask[lat_slice, lon_slice], dtype=np.int8)


def read_constituent_subset(path: Path, lat_slice: slice, lon_slice: slice, shape: tuple[int, int]) -> np.ndarray:
    nlat, nlon = shape
    data = np.memmap(path, dtype=">f4", mode="r", offset=44, shape=(2, nlat, nlon))
    real = np.asarray(data[0, lat_slice, lon_slice], dtype=np.float32)
    imag = np.asarray(data[1, lat_slice, lon_slice], dtype=np.float32)
    return (real + 1j * imag).astype(np.complex64)


def read_transport_subset(path: Path, lat_slice: slice, lon_slice: slice, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    nlat, nlon = shape
    data = np.memmap(path, dtype=">f4", mode="r", offset=44, shape=(4, nlat, nlon))
    u = np.asarray(data[0, lat_slice, lon_slice], dtype=np.float32) + 1j * np.asarray(data[1, lat_slice, lon_slice], dtype=np.float32)
    v = np.asarray(data[2, lat_slice, lon_slice], dtype=np.float32) + 1j * np.asarray(data[3, lat_slice, lon_slice], dtype=np.float32)
    return u.astype(np.complex64), v.astype(np.complex64)


def fill_nearest(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=np.float32)
    valid = np.isfinite(data)
    if np.all(valid):
        return data
    if not np.any(valid):
        return np.zeros_like(data, dtype=np.float32)
    _, indices = distance_transform_edt(~valid, return_indices=True)
    return data[tuple(indices)].astype(np.float32)


def transport_to_velocity(transport: np.ndarray, depth: np.ndarray, mask: np.ndarray, depth_min: float) -> np.ndarray:
    wet = (np.asarray(mask) == 1) & np.isfinite(depth) & (depth > 0.0)
    divisor = np.maximum(np.asarray(depth, dtype=np.float32), np.float32(depth_min))
    real = np.where(wet, np.real(transport) / divisor, np.nan)
    imag = np.where(wet, np.imag(transport) / divisor, np.nan)
    return fill_nearest(real) + 1j * fill_nearest(imag)


def current_ellipse(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    wp = 0.5 * (u + 1j * v)
    wm = 0.5 * np.conj(u - 1j * v)
    sema = np.abs(wp) + np.abs(wm)
    semi = np.abs(wp) - np.abs(wm)
    angle = 0.5 * (np.angle(wp) + np.angle(wm))
    phase = 0.5 * (np.angle(wm) - np.angle(wp))
    cangle = np.mod(np.degrees(angle), 180.0)
    cphase = np.mod(np.degrees(phase), 360.0)
    return sema.astype(np.float32), semi.astype(np.float32), cangle.astype(np.float32), cphase.astype(np.float32)


def main() -> None:
    args = parse_args()
    atlas_dir = Path(args.atlas_dir)
    grid_file = atlas_dir / "grid_tpxo9_atlas_30_v5"
    if not grid_file.exists():
        raise SystemExit(f"TPXO atlas grid file not found: {grid_file}")
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    out_path = Path(args.output)
    if args.profile and args.output == str(DEFAULT_OUTPUT):
        out_path = DEFAULT_OUTPUT.with_name(f"{DEFAULT_OUTPUT.stem}_{args.profile}{DEFAULT_OUTPUT.suffix}")

    nlon, nlat, half_step = read_grid_header(grid_file)
    lon, lat = atlas_coordinates(nlon, nlat, half_step)
    lat_slice, lon_slice = subset_bounds(lon, lat, grid_path)
    depth, mask = read_grid_subset(grid_file, lat_slice, lon_slice, (nlat, nlon))
    subset_lon = lon[lon_slice]
    subset_lat = lat[lat_slice]

    constituents = [item.strip().lower() for item in args.constituents.split(",") if item.strip()]
    unknown = [name for name in constituents if name not in CONSTITUENT_PERIOD_HOURS]
    if unknown:
        raise SystemExit(f"unknown TPXO constituent(s): {', '.join(unknown)}")

    eamp = np.empty((len(constituents), len(subset_lat), len(subset_lon)), dtype=np.float32)
    ephase = np.empty_like(eamp)
    cmax = np.empty_like(eamp) if args.include_uv else None
    cmin = np.empty_like(eamp) if args.include_uv else None
    cangle = np.empty_like(eamp) if args.include_uv else None
    cphase = np.empty_like(eamp) if args.include_uv else None
    for index, constituent in enumerate(constituents):
        path = atlas_dir / f"h_{constituent}_tpxo9_atlas_30_v5"
        if not path.exists():
            raise SystemExit(f"TPXO constituent file not found: {path}")
        values = read_constituent_subset(path, lat_slice, lon_slice, (nlat, nlon))
        eamp[index] = np.abs(values)
        ephase[index] = np.mod(np.degrees(np.angle(values)), 360.0)
        if args.include_uv:
            uv_path = atlas_dir / f"u_{constituent}_tpxo9_atlas_30_v5"
            if not uv_path.exists():
                raise SystemExit(f"TPXO current constituent file not found: {uv_path}")
            u_transport, v_transport = read_transport_subset(uv_path, lat_slice, lon_slice, (nlat, nlon))
            u_velocity = transport_to_velocity(u_transport, depth, mask, args.velocity_depth_min)
            v_velocity = transport_to_velocity(v_transport, depth, mask, args.velocity_depth_min)
            assert cmax is not None and cmin is not None and cangle is not None and cphase is not None
            cmax[index], cmin[index], cangle[index], cphase[index] = current_ellipse(u_velocity, v_velocity)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("tide_period", len(constituents))
        ds.createDimension("lat", len(subset_lat))
        ds.createDimension("lon", len(subset_lon))
        ds.title = f"{load_case_naming().title} staged TPXO tidal elevation subset"
        ds.source_dataset = str(atlas_dir)
        ds.grid_source = str(grid_path)
        ds.constituents = ",".join(constituents)
        ds.tide_mode = "ssh_uv" if args.include_uv else "elevation_only"
        ds.uv_tides_included = "true" if args.include_uv else "false"
        if args.include_uv:
            ds.current_source = "TPXO atlas u_* files, four float planes [Ure,Uim,Vre,Vim]"
            ds.current_conversion = "transport divided by TPXO atlas depth, then converted to tidal ellipse"
            ds.velocity_depth_min_m = float(args.velocity_depth_min)

        tide_period = ds.createVariable("tide_period", "f8", ("tide_period",), zlib=True, complevel=1)
        tide_period.units = "hours"
        tide_period[:] = [CONSTITUENT_PERIOD_HOURS[name] for name in constituents]

        lon_var = ds.createVariable("lon", "f8", ("lon",), zlib=True, complevel=1)
        lon_var.units = "degrees_east"
        lon_var[:] = subset_lon
        lat_var = ds.createVariable("lat", "f8", ("lat",), zlib=True, complevel=1)
        lat_var.units = "degrees_north"
        lat_var[:] = subset_lat

        depth_var = ds.createVariable("depth", "f4", ("lat", "lon"), zlib=True, complevel=1)
        depth_var.units = "m"
        depth_var.long_name = "TPXO atlas bathymetry"
        depth_var[:, :] = depth

        mask_var = ds.createVariable("mask", "i1", ("lat", "lon"), zlib=True, complevel=1)
        mask_var.long_name = "TPXO water mask"
        mask_var.flag_values = np.array([0, 1], dtype=np.int8)
        mask_var.flag_meanings = "land water"
        mask_var[:, :] = mask

        amp_var = ds.createVariable("tide_Eamp", "f4", ("tide_period", "lat", "lon"), zlib=True, complevel=1)
        amp_var.units = "m"
        amp_var[:, :, :] = eamp

        phase_var = ds.createVariable("tide_Ephase", "f4", ("tide_period", "lat", "lon"), zlib=True, complevel=1)
        phase_var.units = "degrees"
        phase_var[:, :, :] = ephase

        if args.include_uv:
            assert cmax is not None and cmin is not None and cangle is not None and cphase is not None
            cmax_var = ds.createVariable("tide_Cmax", "f4", ("tide_period", "lat", "lon"), zlib=True, complevel=1)
            cmax_var.units = "meter second-1"
            cmax_var[:, :, :] = cmax
            cmin_var = ds.createVariable("tide_Cmin", "f4", ("tide_period", "lat", "lon"), zlib=True, complevel=1)
            cmin_var.units = "meter second-1"
            cmin_var[:, :, :] = cmin
            cangle_var = ds.createVariable("tide_Cangle", "f4", ("tide_period", "lat", "lon"), zlib=True, complevel=1)
            cangle_var.units = "degrees"
            cangle_var[:, :, :] = cangle
            cphase_var = ds.createVariable("tide_Cphase", "f4", ("tide_period", "lat", "lon"), zlib=True, complevel=1)
            cphase_var.units = "degrees"
            cphase_var[:, :, :] = cphase

    print(f"atlas_dir={atlas_dir}")
    print(f"grid={grid_path}")
    print(f"constituents={','.join(constituents)}")
    print(f"include_uv={args.include_uv}")
    print(f"output={out_path}")


if __name__ == "__main__":
    main()
