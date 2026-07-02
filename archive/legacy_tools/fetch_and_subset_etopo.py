#!/usr/bin/env python3
"""Fetch and subset NOAA ETOPO bathymetry for the Fukushima ROMS project.

This is an offline-ready helper for the next remote execution step. It downloads
an official NOAA ETOPO global NetCDF file if needed, subsets 140E-142E and
36N-38N, and writes a compact GEBCO/ETOPO-style file with variables expected by
the remote ROMS preprocessing script:

  lon, lat, elevation

The script is intentionally separate from the ROMS project tree so it can be
reviewed before being copied to the remote host.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


NOAA_ETOPO_60S_URLS = [
    "https://www.ngdc.noaa.gov/thredds/fileServer/global/ETOPO2022/60s/60s_bed_elev_netcdf/ETOPO_2022_v1_60s_N90W180_bed.nc",
    "https://www.ncei.noaa.gov/thredds/fileServer/global/ETOPO2022/60s/60s_bed_elev_netcdf/ETOPO_2022_v1_60s_N90W180_bed.nc",
]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def download(urls: list[str], out: Path) -> None:
    if out.exists() and out.stat().st_size > 0:
        print(f"using existing global file: {out}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    downloader = shutil.which("curl") or shutil.which("wget")
    if downloader is None:
        raise SystemExit("curl or wget is required for download")
    last_error: Exception | None = None
    for url in urls:
        try:
            if Path(downloader).name == "curl":
                run([downloader, "-L", "--fail", "--retry", "3", "--connect-timeout", "20", "-o", str(tmp), url])
            else:
                run([downloader, "-O", str(tmp), url])
            tmp.replace(out)
            return
        except Exception as exc:  # noqa: BLE001 - try next official mirror.
            last_error = exc
            if tmp.exists():
                tmp.unlink()
            print(f"download failed for {url}: {exc}")
    raise SystemExit(f"all NOAA ETOPO download URLs failed; last error: {last_error}")


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default="data/raw/bathymetry")
    parser.add_argument("--global-file", default="ETOPO_2022_v1_60s_N90W180_bed.nc")
    parser.add_argument("--output", default="gebco_fukushima.nc")
    parser.add_argument("--west", type=float, default=140.0)
    parser.add_argument("--east", type=float, default=142.0)
    parser.add_argument("--south", type=float, default=36.0)
    parser.add_argument("--north", type=float, default=38.0)
    parser.add_argument("--margin", type=float, default=0.25)
    args = parser.parse_args()

    work = Path(args.work_dir)
    global_nc = work / args.global_file
    out_nc = work / args.output
    download(NOAA_ETOPO_60S_URLS, global_nc)
    subset(global_nc, out_nc, args.west, args.east, args.south, args.north, args.margin)


if __name__ == "__main__":
    main()
