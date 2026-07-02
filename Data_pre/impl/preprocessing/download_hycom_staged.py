#!/usr/bin/env python3
"""Download staged HYCOM raw files through the unified HYCOM 3D core."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import xarray as xr

from case_naming import load_case_naming
from staged_data_utils import config_path_to_abs, get_bbox, get_time_window, load_download_config


CORE_PATH = Path("/home/lhy/ROMS/Data_pre/core")
if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))

from hycom_3d_download_core import (  # noqa: E402
    COMMON_STEP_HOURS,
    SOURCE_AUTO,
    download_partitioned_windows,
    normalize_requested_stop,
    resolve_download_target,
    safe_to_netcdf,
)


DEFAULT_CONFIG = str(Path("/home/lhy/ROMS/Data_pre/core").parents[0] / "cases" / "default_case.txt")
DATA_PRE_RENAMES = {
    "ssh": "zeta",
    "sal": "salt",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--initial-output", default=None)
    parser.add_argument("--boundary-output", default=None)
    parser.add_argument("--chunk-days", type=int, default=1)
    parser.add_argument("--mode", choices=["boundary-only", "merge-only"], default="boundary-only")
    parser.add_argument("--edge-buffer-points", type=int, default=3)
    parser.add_argument("--tmp-dir", default=None)
    parser.add_argument("--fallback-order", default=None)
    parser.add_argument("--groups", default="ssh,ts3z,uv3z")
    parser.add_argument("--edges", default="west,east,south,north")
    parser.add_argument("--start", default=None)
    parser.add_argument("--stop", default=None)
    parser.add_argument("--skip-initial-product", action="store_true")
    parser.add_argument("--force-redownload-boundary", action="store_true")
    parser.add_argument("--ignore-existing-boundary-cache", action="store_true", dest="force_redownload_boundary")
    parser.add_argument("--source", choices=[SOURCE_AUTO, "espc", "gofs31_standard"], default=None)
    parser.add_argument("--source-key", default=None)
    return parser.parse_args()


def choose_source(config: dict, args: argparse.Namespace) -> tuple[str, str | None]:
    hycom_cfg = config.get("hycom", {})
    source = args.source or hycom_cfg.get("source") or SOURCE_AUTO
    if args.source_key is not None:
        source_key = args.source_key
    elif source == SOURCE_AUTO:
        source_key = None
    else:
        source_key = hycom_cfg.get("source_key")
    return source, source_key


def harmonize_variable_names(ds: xr.Dataset) -> xr.Dataset:
    rename_map = {src: dst for src, dst in DATA_PRE_RENAMES.items() if src in ds.variables and dst not in ds.variables}
    return ds.rename(rename_map) if rename_map else ds


def select_initial_snapshot(boundary: xr.Dataset, requested_start: datetime) -> xr.Dataset:
    target = requested_start.toordinal()  # dummy to keep scalar comparable path simple
    del target
    time_values = [datetime.fromisoformat(str(value).replace("Z", "")) for value in boundary.time.values.astype("datetime64[s]").astype(str)]
    best_index = min(range(len(time_values)), key=lambda idx: abs((time_values[idx] - requested_start).total_seconds()))
    return boundary.isel(time=[best_index]).copy()


def enrich_boundary_attrs(ds: xr.Dataset, source: str, source_key: str | None, requested_start: datetime, requested_stop: datetime, bbox) -> xr.Dataset:
    ds = ds.copy()
    ds.attrs["title"] = f"{load_case_naming().title} staged HYCOM boundary subset"
    ds.attrs["download_strategy"] = "unified_hycom_3d_core"
    ds.attrs["source_name"] = source
    if source_key:
        ds.attrs["source_key_requested"] = source_key
    ds.attrs["source_time_start_requested"] = requested_start.isoformat()
    ds.attrs["source_time_end_requested"] = requested_stop.isoformat()
    ds.attrs["requested_source_bbox"] = f"{bbox.west},{bbox.east},{bbox.south},{bbox.north}"
    return ds


def enrich_initial_attrs(ds: xr.Dataset, source: str, source_key: str | None, requested_start: datetime, requested_stop: datetime, bbox) -> xr.Dataset:
    ds = ds.copy()
    ds.attrs["title"] = f"{load_case_naming().title} staged HYCOM initial subset"
    ds.attrs["download_strategy"] = "unified_hycom_3d_core"
    ds.attrs["source_name"] = source
    if source_key:
        ds.attrs["source_key_requested"] = source_key
    ds.attrs["source_time_start_requested"] = requested_start.isoformat()
    ds.attrs["source_time_end_requested"] = requested_stop.isoformat()
    ds.attrs["requested_source_bbox"] = f"{bbox.west},{bbox.east},{bbox.south},{bbox.north}"
    if "time" in ds.coords and ds.sizes.get("time", 0) > 0:
        ds.attrs["source_time"] = str(ds.time.values[0]).replace("Z", "")
    return ds


def main() -> None:
    args = parse_args()
    config = load_download_config(args.config)
    bbox = get_bbox(config, source="hycom")
    window = get_time_window(config)
    requested_start = datetime.fromisoformat(args.start) if args.start else window.start
    requested_stop = datetime.fromisoformat(args.stop) if args.stop else window.stop
    if requested_start > requested_stop:
        raise SystemExit("start must not be later than stop")

    source, source_key = choose_source(config, args)
    boundary_out = Path(args.boundary_output) if args.boundary_output else config_path_to_abs(config, "ocean_boundary")
    initial_out = Path(args.initial_output) if args.initial_output else config_path_to_abs(config, "ocean_initial")
    boundary_out.parent.mkdir(parents=True, exist_ok=True)
    initial_out.parent.mkdir(parents=True, exist_ok=True)

    normalized_stop = normalize_requested_stop(requested_stop, COMMON_STEP_HOURS)
    boundary_tmp = boundary_out.with_name(f"{boundary_out.stem}_merged_raw{boundary_out.suffix}")
    part_output_dir = boundary_out.parent / f"{boundary_out.stem}_parts"
    result = download_partitioned_windows(
        start=requested_start,
        stop=requested_stop,
        source=source,
        source_key=source_key,
        lat_bounds=(bbox.south, bbox.north),
        lon_bounds=(bbox.west, bbox.east),
        depth_bounds=(0.0, 5000.0),
        part_output_dir=part_output_dir,
        merge_output=boundary_tmp,
        keep_parts=True,
        max_retries_per_part=3,
    )
    if not result["success"]:
        raise SystemExit(f"HYCOM partitioned download incomplete; see manifest: {result['manifest_path']}")

    with xr.open_dataset(boundary_tmp, engine="netcdf4") as merged_raw:
        boundary = harmonize_variable_names(merged_raw.load())
    resolved_source = str(boundary.attrs.get("source", source))
    resolved_segment = str(boundary.attrs.get("source_key", source_key or ""))
    boundary = enrich_boundary_attrs(boundary, resolved_source, resolved_segment, requested_start, normalized_stop, bbox)
    safe_to_netcdf(boundary, boundary_out)
    boundary_tmp.unlink(missing_ok=True)
    print(f"wrote boundary source: {boundary_out}")

    if not args.skip_initial_product:
        initial = select_initial_snapshot(boundary, requested_start)
        initial = enrich_initial_attrs(initial, resolved_source, resolved_segment, requested_start, normalized_stop, bbox)
        safe_to_netcdf(initial, initial_out)
        print(f"wrote initial source: {initial_out}")


if __name__ == "__main__":
    main()
