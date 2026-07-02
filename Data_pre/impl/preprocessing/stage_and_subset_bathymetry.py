#!/usr/bin/env python3
"""Stage and subset offline GEBCO bathymetry for a ROMS case.

The default workflow uses offline GEBCO 2026 data stored under
`/workspace/GEBCO/`. If `/workspace/GEBCO/GEBCO_2026.nc` already exists, it is
used directly. Otherwise the script extracts it from
`/workspace/GEBCO/GEBCO_2026.zip`, subsets the active case region, and writes a
compact GEBCO-style file with variables expected by the ROMS grid generation
script:

  lon, lat, elevation
"""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from netCDF4 import Dataset

from case_naming import bathymetry_subset_path, load_case_naming
from roms_preprocessing_utils import load_project_params


DEFAULT_GEBCO_ZIP = Path("/workspace/GEBCO/GEBCO_2026.zip")
DEFAULT_GEBCO_MEMBER = "GEBCO_2026.nc"
DEFAULT_GEBCO_GLOBAL_NC = Path("/workspace/GEBCO/GEBCO_2026.nc")


def stage_global_file(global_nc: Path, zip_path: Path | None, zip_member: str) -> Path:
    if global_nc.exists() and global_nc.stat().st_size > 0:
        print(f"using existing global file: {global_nc}")
        return global_nc
    if zip_path is None:
        raise SystemExit(f"global bathymetry file not found: {global_nc}")
    if not zip_path.exists():
        raise SystemExit(f"offline GEBCO archive not found: {zip_path}")
    global_nc.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        try:
            member = archive.getinfo(zip_member)
        except KeyError as exc:
            raise SystemExit(f"archive member not found in {zip_path}: {zip_member}") from exc
        print(f"extracting {zip_member} from {zip_path} -> {global_nc}")
        with archive.open(member) as src, global_nc.open("wb") as dst:
            dst.write(src.read())
    return global_nc


def pick_var(ds: Dataset, candidates: tuple[str, ...]) -> str:
    names = set(ds.variables)
    for name in candidates:
        if name in names:
            return name
    lower = {name.lower(): name for name in ds.variables}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    raise KeyError(f"none of {candidates} found; available={list(ds.variables)[:40]}")


def subset(global_nc: Path, out_nc: Path, west: float, east: float, south: float, north: float, margin: float) -> None:
    with Dataset(global_nc) as src:
        lon_name = pick_var(src, ("lon", "longitude", "x"))
        lat_name = pick_var(src, ("lat", "latitude", "y"))
        z_name = pick_var(src, ("z", "elevation", "Band1"))
        lon = np.asarray(src.variables[lon_name][:], dtype=float)
        lat = np.asarray(src.variables[lat_name][:], dtype=float)
        zvar = src.variables[z_name]

        lon_mask = (lon >= west - margin) & (lon <= east + margin)
        lat_mask = (lat >= south - margin) & (lat <= north + margin)
        if not lon_mask.any() or not lat_mask.any():
            raise SystemExit("requested subset is outside source bathymetry extent")
        lon_idx = np.where(lon_mask)[0]
        lat_idx = np.where(lat_mask)[0]
        z = np.asarray(zvar[lat_idx.min() : lat_idx.max() + 1, lon_idx.min() : lon_idx.max() + 1])
        lon_sub = lon[lon_idx.min() : lon_idx.max() + 1]
        lat_sub = lat[lat_idx.min() : lat_idx.max() + 1]

    out_nc.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out_nc, "w", format="NETCDF4") as dst:
        dst.createDimension("lon", lon_sub.size)
        dst.createDimension("lat", lat_sub.size)
        lon_out = dst.createVariable("lon", "f8", ("lon",))
        lat_out = dst.createVariable("lat", "f8", ("lat",))
        elev = dst.createVariable("elevation", "f4", ("lat", "lon"), zlib=True, complevel=3)
        lon_out.units = "degrees_east"
        lat_out.units = "degrees_north"
        elev.units = "m"
        elev.long_name = "bedrock elevation relative to sea level"
        elev.positive = "up"
        dst.source = str(global_nc)
        dst.subset_bounds = f"west={west}, east={east}, south={south}, north={north}, margin={margin}"
        dst.note = "Positive elevation is land; negative elevation is ocean depth."
        lon_out[:] = lon_sub
        lat_out[:] = lat_sub
        elev[:, :] = z.astype("f4")
    print(f"wrote {out_nc}")
    print(f"lon={lon_sub.size}, lat={lat_sub.size}, elevation min={float(np.nanmin(z)):.3f}, max={float(np.nanmax(z)):.3f}")


def main() -> None:
    params = load_project_params()
    naming = load_case_naming()
    domain = params["domain"]
    default_out = bathymetry_subset_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default=str(default_out.parent))
    parser.add_argument("--global-file", default=str(naming.global_bathymetry))
    parser.add_argument("--zip-file", default=str(DEFAULT_GEBCO_ZIP))
    parser.add_argument("--zip-member", default=DEFAULT_GEBCO_MEMBER)
    parser.add_argument("--output", default=default_out.name)
    parser.add_argument("--west", type=float, default=domain["lon_min"])
    parser.add_argument("--east", type=float, default=domain["lon_max"])
    parser.add_argument("--south", type=float, default=domain["lat_min"])
    parser.add_argument("--north", type=float, default=domain["lat_max"])
    parser.add_argument("--margin", type=float, default=0.25)
    args = parser.parse_args()

    work = Path(args.work_dir)
    global_nc_arg = Path(args.global_file)
    global_nc = global_nc_arg if global_nc_arg.is_absolute() else work / global_nc_arg
    zip_path = None if str(args.zip_file).strip().lower() in {"", "none"} else Path(args.zip_file)
    out_nc = work / args.output
    stage_global_file(global_nc, zip_path, args.zip_member)
    subset(global_nc, out_nc, args.west, args.east, args.south, args.north, args.margin)


if __name__ == "__main__":
    main()
