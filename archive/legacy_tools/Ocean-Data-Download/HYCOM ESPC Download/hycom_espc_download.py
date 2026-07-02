#!/usr/bin/env python3
"""Compatibility wrapper for unified HYCOM ESPC 3D downloading."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from hycom_3d_download_core import (  # noqa: E402
    DEFAULT_DEPTH_RANGE,
    IndexRange,
    VAR_ATTRS,
    build_dataset,
    build_output_path,
    bounding_indices,
    fetch_coord_vector,
    fetch_variable_3d,
    hours_to_datetime,
    resolve_source_segment,
    split_index_range,
    time_indices,
)


BASE_URLS = {
    "ssh": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/ssh",
    "sal": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/s3z",
    "temp": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/t3z",
    "u": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/u3z",
    "v": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/v3z",
}


def fetch_3d_cube(
    short_name: str,
    time_sel: IndexRange,
    depth_sel: IndexRange,
    lat_sel: IndexRange,
    lon_sel: IndexRange,
):
    return fetch_variable_3d(BASE_URLS[short_name], short_name, time_sel, depth_sel, lat_sel, lon_sel)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download HYCOM ESPC-D-V02 subsets as NetCDF.")
    parser.add_argument("--lat-min", type=float, default=36.0)
    parser.add_argument("--lat-max", type=float, default=38.0)
    parser.add_argument("--lon-min", type=float, default=140.0)
    parser.add_argument("--lon-max", type=float, default=142.0)
    parser.add_argument("--start", type=str, default="20250101")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--depth-min", type=float, default=DEFAULT_DEPTH_RANGE[0])
    parser.add_argument("--depth-max", type=float, default=DEFAULT_DEPTH_RANGE[1])
    parser.add_argument("--output-dir", type=Path, default=Path("HYCOM ESPC Download/python_output"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y%m%d")
    segment = resolve_source_segment("espc", start)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ds = build_dataset(
        source="espc",
        start=start,
        days=args.days,
        lat_bounds=(args.lat_min, args.lat_max),
        lon_bounds=(args.lon_min, args.lon_max),
        depth_bounds=(args.depth_min, args.depth_max),
    )
    out_path = build_output_path(args.output_dir, "espc", segment, start, args.days)
    ds.to_netcdf(out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
