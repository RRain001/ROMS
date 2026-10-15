#!/usr/bin/env python3
"""Stage publicly hosted GEBCO_2026 COG + GSHHG 2.3.7 ES3K subset.

No global 7-GB bathymetry download and no dependency on /workspace.
READ-ONLY public sources; all outputs are explicitly cached in the target directory.
A cropped, pixel-centred NetCDF elevation raster feeds the nesting-only
bathymetry_grid.build_grid entrypoint. This is NOT a physics pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

GEBCO_COG_URL = "https://data.source.coop/ausantarctic/gebco/GEBCO_2026.tif"
GSHHG_ZIP_URL = ("https://github.com/GenericMappingTools/gshhg-gmt/"
                 "releases/download/2.3.7/gshhg-shp-2.3.7.zip")
# Extend beyond the fixed four-corner bounding box by 0.5° for interpolation.
ES3K_BOUNDS = (121.4, 30.3, 150.9, 52.5)  # west south east north


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for b in iter(lambda: src.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def bathymetry(output: Path, *, resolution_arcsec: int = 30) -> dict:
    """GDAL HTTP byte-range reads against native 15 arcsecond COG.

    30" staging uses averaged oversampled source as an explicit *pilot*;
    15" reads native cells and is the desired scientific candidate.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds, transform as window_transform
    from netCDF4 import Dataset

    if resolution_arcsec not in (15, 30):
        raise ValueError("GEBCO 2026 online subset supports 15 or 30 arcseconds")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="5",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        with rasterio.open("/vsicurl/" + GEBCO_COG_URL) as src:
            if src.count != 1 or not src.crs or src.crs.to_epsg() != 4326:
                raise ValueError("unexpected GEBCO 2026 global COG dimensions/CRS")
            win = from_bounds(*ES3K_BOUNDS, transform=src.transform)
            win = win.round_offsets().round_lengths()
            if win.col_off < 0 or win.row_off < 0 or win.col_off + win.width > src.width or win.row_off + win.height > src.height:
                raise ValueError("GEBCO COG window extends outside global source")
            stride = resolution_arcsec // 15
            ny = int(win.height) // stride
            nx = int(win.width) // stride
            if not (300 <= ny < 6000 and 500 <= nx < 9000):
                raise ValueError("invalid crop/stride dimensions")
            data = src.read(1, window=win, out_shape=(ny, nx),
                            resampling=Resampling.average)
            # Pixel-centred coordinates from actual cropped/resampled window;
            # keep descending source rows until writing lat-ascending NetCDF.
            full_transform = window_transform(win, src.transform)
            t = full_transform * rasterio.Affine.scale(win.width/nx, win.height/ny)
            x = t.c + t.a * (np.arange(nx) + 0.5)
            y = t.f + t.e * (np.arange(ny) + 0.5)
            if not (np.all(np.diff(x) > 0) and np.all(np.diff(y) < 0)):
                raise ValueError("unexpected COG grid orientation")
            if not np.isfinite(data).all():
                raise ValueError("nonfinite GEBCO bathymetry subset")
    output.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(output, "w", format="NETCDF4") as nc:
        nc.createDimension("lat", ny)
        nc.createDimension("lon", nx)
        nc.createVariable("lon", "f8", ("lon",))[:] = x
        nc.createVariable("lat", "f8", ("lat",))[:] = y[::-1]
        v = nc.createVariable("elevation", "f4", ("lat", "lon"),
                              zlib=True, complevel=3)
        v[:] = data[::-1].astype("f4")
        v.units = "m"
        v.positive = "up"
        nc.title = "ES3K bounded public GEBCO_2026 elevation subset"
        nc.reference = GEBCO_COG_URL
        nc.geographic_bounds_wsen = json.dumps(ES3K_BOUNDS)
        nc.source_native_resolution_arcsec = 15
        nc.staging_resolution_arcsec = resolution_arcsec
        nc.staging_method = ("NATIVE" if stride == 1 else "COG_AVERAGE_DOWNSAMPLE_PILOT")
    return {
        "source": GEBCO_COG_URL,
        "file": str(output),
        "size_bytes": output.stat().st_size,
        "sha256": sha256(output),
        "shape_lat_lon": [ny, nx],
        "staging_resolution_arcsec": resolution_arcsec,
        "source_resolution_arcsec": 15,
        "data_min_m": float(data.min()),
        "data_max_m": float(data.max()),
        "subset_bounds_wsen": list(ES3K_BOUNDS),
        "data_class": "REAL_PUBLIC_GEBCO_2026_ELEVATION",
    }


def coastline(base: Path, *, resolution: str = "h") -> dict:
    """Download official GMT 2.3.7 release and extract only L1 polygon layer."""
    import requests

    if resolution not in ("i", "h", "f"):
        raise ValueError("shoreline resolution must be i, h, or f")
    dest = base / resolution
    dest.mkdir(parents=True, exist_ok=True)
    stems = [f"GSHHS_{resolution}_L1.{ext}" for ext in ("shp", "shx", "dbf")]
    existing = [dest / s for s in stems]
    if not all(x.exists() and x.stat().st_size > 0 for x in existing):
        archive = base.parent / "gshhg-shp-2.3.7.zip"
        if not archive.exists():
            with requests.get(GSHHG_ZIP_URL, stream=True, timeout=(25, 120)) as rsp:
                rsp.raise_for_status()
                tmp = archive.with_suffix(".partial")
                with tmp.open("wb") as target:
                    for chunk in rsp.iter_content(2 * 1024 * 1024):
                        if chunk:
                            target.write(chunk)
                tmp.rename(archive)
        if not zipfile.is_zipfile(archive):
            raise ValueError("GSHHG download is not a valid ZIP archive")
        with zipfile.ZipFile(archive) as z:
            for stem in stems:
                matches = [n for n in z.namelist()
                           if n.replace("\\", "/").endswith("/" + resolution + "/" + stem)]
                if len(matches) != 1:
                    raise ValueError(f"GSHHG 2.3.7 missing/ambiguous {stem}")
                # Extract the chosen archive member to a fixed basename;
                # arbitrary ZIP path is never used as output destination.
                with z.open(matches[0]) as src, (dest / stem).open("wb") as dst:
                    import shutil
                    shutil.copyfileobj(src, dst)
    return {
        "source": GSHHG_ZIP_URL,
        "GSHHG_version": "2.3.7",
        "resolution": resolution,
        "level": 1,
        "base_dir": str(base),
        "files": [{"path": str(p), "size_bytes": p.stat().st_size,
                   "sha256": sha256(p)} for p in existing],
        "data_class": "REAL_PUBLIC_GSHHG_2_3_7_L1_SHAPEFILE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution-arcsec", type=int, choices=(15, 30), default=30)
    parser.add_argument("--coast-resolution", choices=("i", "h", "f"), default="h")
    args = parser.parse_args()
    root = args.output_dir.resolve()
    source = root / f"GEBCO_2026_ES3K_{args.resolution_arcsec}sec.nc"
    source_meta = bathymetry(source, resolution_arcsec=args.resolution_arcsec)
    coast_meta = coastline(root / "GSHHS_shp", resolution=args.coast_resolution)
    report = {"GEBCO": source_meta, "GSHHG": coast_meta,
              "scope": "REAL_PUBLIC_GRID_PREPROCESSING_NO_PHYSICS"}
    dest = root / "online_source_manifest.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
