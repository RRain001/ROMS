#!/usr/bin/env python3
"""Wrapper for unified HYCOM GOFS 3.1 standard 3D downloading."""

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
    build_dataset,
    build_output_path,
    resolve_source_segment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download HYCOM GOFS 3.1 standard fields as NetCDF.")
    parser.add_argument("--source-key", help="Optional explicit source segment key such as analysis_93_0_glby.")
    parser.add_argument("--lat-min", type=float, default=37.0)
    parser.add_argument("--lat-max", type=float, default=37.84)
    parser.add_argument("--lon-min", type=float, default=140.88)
    parser.add_argument("--lon-max", type=float, default=142.0)
    parser.add_argument("--start", type=str, required=True, help="YYYYMMDD")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--depth-min", type=float, default=DEFAULT_DEPTH_RANGE[0])
    parser.add_argument("--depth-max", type=float, default=DEFAULT_DEPTH_RANGE[1])
    parser.add_argument("--output-dir", type=Path, default=Path("HYCOM GOFS 3.1 Download/python_output"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y%m%d")
    segment = resolve_source_segment("gofs31_standard", start, source_key=args.source_key)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ds = build_dataset(
        source="gofs31_standard",
        source_key=args.source_key,
        start=start,
        days=args.days,
        lat_bounds=(args.lat_min, args.lat_max),
        lon_bounds=(args.lon_min, args.lon_max),
        depth_bounds=(args.depth_min, args.depth_max),
    )
    out_path = build_output_path(args.output_dir, "gofs31_standard", segment, start, args.days)
    ds.to_netcdf(out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
