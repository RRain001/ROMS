#!/usr/bin/env python3
"""Download and merge staged GLORYS12V1 subsets for the active case."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from netCDF4 import Dataset
import xarray as xr

from case_naming import load_case_naming
from ocean_source_utils import build_glorys_paths, glorys_time_window, load_glorys_config
from roms_preprocessing_utils import load_grid, resolve_grid_path
from staged_data_utils import BoundingBox, ensure_parent


EDGE_NAMES = ("south", "north", "west", "east")
CLI = "copernicusmarine"


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    stop: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--grid", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--stop", default=None)
    parser.add_argument("--mode", choices=["initial", "boundary", "both"], default="both")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--command", default=CLI)
    return parser.parse_args()


def config_window(config: dict, args: argparse.Namespace) -> TimeWindow:
    start = datetime.fromisoformat(args.start) if args.start else datetime.fromisoformat(config["time_start"])
    stop = datetime.fromisoformat(args.stop) if args.stop else datetime.fromisoformat(config["time_stop"])
    if stop < start:
        raise SystemExit("stop must not be earlier than start")
    return TimeWindow(start=start, stop=stop)


def center_time(config: dict, window: TimeWindow) -> datetime:
    hh, mm, ss = [int(item) for item in str(config["time_mean_center"]).split(":")]
    return datetime(window.start.year, window.start.month, window.start.day, hh, mm, ss)


def active_grid_bbox(grid, lon_buffer_deg: float, lat_buffer_deg: float) -> BoundingBox:
    return BoundingBox(
        west=float(np.nanmin(grid.lon_rho) - lon_buffer_deg),
        east=float(np.nanmax(grid.lon_rho) + lon_buffer_deg),
        south=float(np.nanmin(grid.lat_rho) - lat_buffer_deg),
        north=float(np.nanmax(grid.lat_rho) + lat_buffer_deg),
    )


def edge_bbox(grid, edge_name: str, buffer_points: int) -> BoundingBox:
    lon = np.asarray(grid.lon_rho, dtype=float)
    lat = np.asarray(grid.lat_rho, dtype=float)
    if lon.shape[1] > 1:
        lon_step = float(np.nanmedian(np.abs(np.diff(lon, axis=1))))
    else:
        lon_step = 0.083333
    if lat.shape[0] > 1:
        lat_step = float(np.nanmedian(np.abs(np.diff(lat, axis=0))))
    else:
        lat_step = 0.083333
    lon_pad = max(buffer_points, 1) * lon_step
    lat_pad = max(buffer_points, 1) * lat_step
    if edge_name == "west":
        return BoundingBox(
            west=float(np.nanmin(lon[:, :2]) - lon_pad),
            east=float(np.nanmax(lon[:, :2]) + lon_pad),
            south=float(np.nanmin(lat[:, :2]) - lat_pad),
            north=float(np.nanmax(lat[:, :2]) + lat_pad),
        )
    if edge_name == "east":
        return BoundingBox(
            west=float(np.nanmin(lon[:, -2:]) - lon_pad),
            east=float(np.nanmax(lon[:, -2:]) + lon_pad),
            south=float(np.nanmin(lat[:, -2:]) - lat_pad),
            north=float(np.nanmax(lat[:, -2:]) + lat_pad),
        )
    if edge_name == "south":
        return BoundingBox(
            west=float(np.nanmin(lon[:2, :]) - lon_pad),
            east=float(np.nanmax(lon[:2, :]) + lon_pad),
            south=float(np.nanmin(lat[:2, :]) - lat_pad),
            north=float(np.nanmax(lat[:2, :]) + lat_pad),
        )
    return BoundingBox(
        west=float(np.nanmin(lon[-2:, :]) - lon_pad),
        east=float(np.nanmax(lon[-2:, :]) + lon_pad),
        south=float(np.nanmin(lat[-2:, :]) - lat_pad),
        north=float(np.nanmax(lat[-2:, :]) + lat_pad),
    )


def start_of_next_month(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1)
    return datetime(value.year, value.month + 1, 1)


def split_monthly(window: TimeWindow) -> list[TimeWindow]:
    chunks: list[TimeWindow] = []
    cursor = window.start
    while cursor <= window.stop:
        boundary = start_of_next_month(cursor)
        stop = min(window.stop, boundary - timedelta(seconds=1))
        chunks.append(TimeWindow(cursor, stop))
        cursor = stop + timedelta(seconds=1)
    return chunks


def split_fixed_days(window: TimeWindow, days: int) -> list[TimeWindow]:
    chunks: list[TimeWindow] = []
    cursor = window.start
    delta = timedelta(days=days) - timedelta(seconds=1)
    while cursor <= window.stop:
        stop = min(window.stop, cursor + delta)
        chunks.append(TimeWindow(cursor, stop))
        cursor = stop + timedelta(seconds=1)
    return chunks


def xarray_sorted(ds: xr.Dataset) -> xr.Dataset:
    out = ds
    for coord in ("longitude", "latitude", "depth", "time"):
        if coord in out.coords:
            out = out.sortby(coord)
    return out


def normalize_center_time(ds: xr.Dataset, config: dict) -> xr.Dataset:
    if "time" not in ds.coords:
        return ds
    hh, mm, ss = [int(item) for item in str(config["time_mean_center"]).split(":")]
    centered = []
    for value in ds["time"].values.astype("datetime64[s]"):
        stamp = value.astype(object)
        centered.append(np.datetime64(datetime(stamp.year, stamp.month, stamp.day, hh, mm, ss)))
    return ds.assign_coords(time=("time", np.asarray(centered, dtype="datetime64[s]")))


def dedupe_times(ds: xr.Dataset) -> xr.Dataset:
    if "time" not in ds.coords:
        return xarray_sorted(ds)
    values = ds["time"].values.astype("datetime64[s]")
    _, idx = np.unique(values, return_index=True)
    return xarray_sorted(ds.isel(time=np.sort(idx)))


def subset_time_string(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def chunk_path(raw_dir: Path, area: str, window: TimeWindow) -> Path:
    key = f"{window.start:%Y%m%dT%H%M%S}__{window.stop:%Y%m%dT%H%M%S}.nc"
    return raw_dir / "chunks" / area / key


def chunk_dir(raw_dir: Path, area: str) -> Path:
    return raw_dir / "chunks" / area


def existing_chunk_paths(raw_dir: Path, area: str) -> list[Path]:
    return sorted(chunk_dir(raw_dir, area).glob("*.nc"))


def valid_netcdf(path: Path, required_vars: list[str]) -> bool:
    if not path.exists():
        return False
    try:
        with Dataset(path) as ds:
            for name in required_vars:
                if name not in ds.variables:
                    return False
            return True
    except Exception:  # noqa: BLE001
        return False


def safe_to_netcdf(ds: xr.Dataset, path: Path) -> None:
    ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    ds.to_netcdf(tmp, engine="netcdf4")
    tmp.replace(path)


def run_subset_command(
    command: str,
    dataset_id: str,
    variables: list[str],
    bbox: BoundingBox,
    window: TimeWindow,
    out_dir: Path,
    out_name: str,
    max_depth: float | None,
    with_time: bool = True,
    dataset_part: str | None = None,
) -> Path:
    ensure_parent(out_dir / out_name)
    cmd = [
        command,
        "subset",
        "--dataset-id",
        dataset_id,
        "--disable-progress-bar",
        "--log-level",
        "WARN",
    ]
    if dataset_part:
        cmd.extend(["--dataset-part", dataset_part])
    for variable in variables:
        cmd.extend(["--variable", variable])
    cmd.extend(
        [
            "--minimum-longitude",
            f"{bbox.west:.8f}",
            "--maximum-longitude",
            f"{bbox.east:.8f}",
            "--minimum-latitude",
            f"{bbox.south:.8f}",
            "--maximum-latitude",
            f"{bbox.north:.8f}",
        ]
    )
    if max_depth is not None:
        cmd.extend(["--minimum-depth", "0", "--maximum-depth", f"{max_depth:.3f}"])
    if with_time:
        cmd.extend(
            [
                "--start-datetime",
                subset_time_string(window.start),
                "--end-datetime",
                subset_time_string(window.stop),
            ]
        )
    cmd.extend(
        [
            "--coordinates-selection-method",
            "outside",
            "--output-directory",
            str(out_dir),
            "--output-filename",
            out_name,
            "--file-format",
            "netcdf",
            "--overwrite",
        ]
    )
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown copernicusmarine failure"
        raise RuntimeError(message)
    return out_dir / out_name


def merged_subset_with_2d3d_fallback(
    command: str,
    config: dict,
    bbox: BoundingBox,
    window: TimeWindow,
    out_dir: Path,
    out_name: str,
) -> xr.Dataset:
    dataset_id = config["dataset_id_daily"]
    variables_3d = list(config["variables_3d"])
    variables_2d = list(config["variables_2d"])
    maximum_depth = float(config["maximum_depth"])
    try:
        path = run_subset_command(
            command,
            dataset_id,
            variables_3d + variables_2d,
            bbox,
            window,
            out_dir,
            out_name,
            maximum_depth,
        )
        with xr.open_dataset(path, engine="netcdf4") as ds:
            return xarray_sorted(normalize_center_time(ds.load(), config))
    except Exception:
        with TemporaryDirectory(dir=str(out_dir)) as tmp:
            tmp_dir = Path(tmp)
            path_3d = run_subset_command(
                command,
                dataset_id,
                variables_3d,
                bbox,
                window,
                tmp_dir,
                "subset_3d.nc",
                maximum_depth,
            )
            path_2d = run_subset_command(
                command,
                dataset_id,
                variables_2d,
                bbox,
                window,
                tmp_dir,
                "subset_2d.nc",
                None,
            )
            with xr.open_dataset(path_3d, engine="netcdf4") as ds_3d, xr.open_dataset(
                path_2d, engine="netcdf4"
            ) as ds_2d:
                merged = xr.merge([ds_3d.load(), ds_2d.load()], compat="override")
        return xarray_sorted(normalize_center_time(merged, config))


def write_chunk_dataset(
    command: str,
    config: dict,
    bbox: BoundingBox,
    window: TimeWindow,
    out_path: Path,
) -> None:
    ensure_parent(out_path)
    with TemporaryDirectory(dir=str(out_path.parent)) as tmp:
        tmp_dir = Path(tmp)
        ds = merged_subset_with_2d3d_fallback(command, config, bbox, window, tmp_dir, out_path.name)
    ds.attrs["source_name"] = "glorys12v1"
    ds.attrs["product_id"] = config["product_id"]
    ds.attrs["dataset_id"] = config["dataset_id_daily"]
    ds.attrs["requested_start"] = window.start.isoformat()
    ds.attrs["requested_stop"] = window.stop.isoformat()
    ds.attrs["requested_bbox"] = f"{bbox.west},{bbox.east},{bbox.south},{bbox.north}"
    safe_to_netcdf(ds, out_path)


def ensure_window_downloaded(
    command: str,
    config: dict,
    bbox: BoundingBox,
    raw_dir: Path,
    area: str,
    window: TimeWindow,
    resume: bool,
    overwrite: bool,
    tier: int = 0,
) -> list[Path]:
    out_path = chunk_path(raw_dir, area, window)
    required = list(config["variables_3d"]) + list(config["variables_2d"])
    if resume and valid_netcdf(out_path, required):
        return [out_path]
    if overwrite and out_path.exists():
        out_path.unlink()
    try:
        write_chunk_dataset(command, config, bbox, window, out_path)
        return [out_path]
    except Exception as exc:
        if tier == 0:
            fallback_windows = split_fixed_days(window, 7)
        elif tier == 1:
            fallback_windows = split_fixed_days(window, 1)
        else:
            raise RuntimeError(
                f"failed chunk {window.start.isoformat()} -> {window.stop.isoformat()}: {type(exc).__name__}: {exc}"
            ) from exc
        paths: list[Path] = []
        for child in fallback_windows:
            paths.extend(
                ensure_window_downloaded(
                    command,
                    config,
                    bbox,
                    raw_dir,
                    area,
                    child,
                    resume=resume,
                    overwrite=overwrite,
                    tier=tier + 1,
                )
            )
        return paths


def load_chunk_datasets(paths: list[Path], config: dict | None = None) -> xr.Dataset:
    datasets: list[xr.Dataset] = []
    for path in sorted(paths):
        with xr.open_dataset(path, engine="netcdf4") as ds:
            loaded = ds.load()
            if config is not None:
                loaded = normalize_center_time(loaded, config)
            datasets.append(loaded)
    if not datasets:
        raise SystemExit("no chunk datasets found to merge")
    return dedupe_times(xr.concat(datasets, dim="time").sortby("time"))


def merge_boundary_edges(edge_datasets: dict[str, xr.Dataset]) -> xr.Dataset:
    ordered = [edge_datasets[name] for name in EDGE_NAMES if name in edge_datasets]
    merged = ordered[0]
    for dataset in ordered[1:]:
        merged = merged.combine_first(dataset)
    return xarray_sorted(merged)


def write_initial_product(ds: xr.Dataset, out_path: Path, config: dict, requested_window: TimeWindow, bbox: BoundingBox) -> None:
    target = np.datetime64(center_time(config, requested_window).strftime("%Y-%m-%dT%H:%M:%S"))
    values = ds["time"].values.astype("datetime64[s]")
    time_index = int(np.argmin(np.abs(values - target)))
    initial = ds.isel(time=slice(time_index, time_index + 1)).copy()
    initial.attrs["title"] = f"{load_case_naming().title} staged GLORYS12V1 initial subset"
    initial.attrs["source"] = "GLORYS12V1 / GLOBAL_MULTIYEAR_PHY_001_030"
    initial.attrs["dataset_id"] = config["dataset_id_daily"]
    initial.attrs["source_time"] = np.datetime_as_string(values[time_index], unit="s")
    initial.attrs["source_time_index"] = str(time_index)
    initial.attrs["requested_bbox"] = f"{bbox.west},{bbox.east},{bbox.south},{bbox.north}"
    safe_to_netcdf(initial, out_path)


def write_boundary_product(
    ds: xr.Dataset,
    out_path: Path,
    config: dict,
    requested_window: TimeWindow,
    bbox: BoundingBox | None = None,
    edge_boxes: dict[str, BoundingBox] | None = None,
) -> None:
    boundary = dedupe_times(ds)
    boundary.attrs["title"] = f"{load_case_naming().title} staged GLORYS12V1 boundary subset"
    boundary.attrs["source"] = "GLORYS12V1 / GLOBAL_MULTIYEAR_PHY_001_030"
    boundary.attrs["dataset_id"] = config["dataset_id_daily"]
    boundary.attrs["boundary_download_strategy"] = config["boundary_download_strategy"]
    boundary.attrs["source_time_start_requested"] = requested_window.start.isoformat()
    boundary.attrs["source_time_end_requested"] = requested_window.stop.isoformat()
    if bbox is not None:
        boundary.attrs["requested_bbox"] = f"{bbox.west},{bbox.east},{bbox.south},{bbox.north}"
    if edge_boxes is not None:
        for edge_name, edge_bbox_value in edge_boxes.items():
            boundary.attrs[f"source_edge_{edge_name}_bbox"] = (
                f"{edge_bbox_value.west},{edge_bbox_value.east},"
                f"{edge_bbox_value.south},{edge_bbox_value.north}"
            )
    safe_to_netcdf(boundary, out_path)


def static_download_requests(config: dict) -> list[dict]:
    configured = config.get("static_dataset_parts")
    if isinstance(configured, list):
        requests = configured
    elif isinstance(configured, dict):
        requests = []
        for name, item in configured.items():
            if not isinstance(item, dict):
                continue
            request = dict(item)
            request.setdefault("name", name)
            requests.append(request)
    else:
        static_variables = list(config["static_variables"])
        default_variables = [name for name in static_variables if name != "mdt"]
        requests = []
        if default_variables:
            requests.append(
                {
                    "name": "default",
                    "dataset_id": config["dataset_id_static"],
                    "variables": default_variables,
                    "output_name": "static_default.nc",
                }
            )
        if "mdt" in static_variables:
            requests.append(
                {
                    "name": "mdt",
                    "dataset_id": config["dataset_id_static"],
                    "dataset_part": "mdt",
                    "variables": ["mdt"],
                    "output_name": "static_mdt.nc",
                }
            )

    normalized: list[dict] = []
    for index, request in enumerate(requests):
        variables = list(request.get("variables", []))
        if not variables:
            raise SystemExit("GLORYS static dataset part is missing variables")
        name = str(request.get("name") or f"part{index + 1}")
        normalized.append(
            {
                "name": name,
                "dataset_id": request.get("dataset_id", config.get("dataset_id_static")),
                "dataset_part": request.get("dataset_part"),
                "variables": variables,
                "output_name": request.get("output_name", f"static_{name}.nc"),
            }
        )
    return normalized


def write_static_product(command: str, config: dict, bbox: BoundingBox, out_path: Path, overwrite: bool) -> None:
    if out_path.exists() and not overwrite:
        return
    ensure_parent(out_path)
    start, stop = glorys_time_window(config)
    window = TimeWindow(start, stop)
    requests = static_download_requests(config)
    with TemporaryDirectory(dir=str(out_path.parent)) as tmp:
        tmp_dir = Path(tmp)
        datasets: list[xr.Dataset] = []
        for request in requests:
            if not request["dataset_id"]:
                raise SystemExit(f"GLORYS static dataset part {request['name']!r} is missing dataset_id")
            path = run_subset_command(
                command,
                str(request["dataset_id"]),
                request["variables"],
                bbox,
                window,
                tmp_dir,
                str(request["output_name"]),
                None,
                with_time=False,
                dataset_part=request["dataset_part"],
            )
            with xr.open_dataset(path, engine="netcdf4") as ds:
                datasets.append(ds.load())
        if not datasets:
            raise SystemExit("no GLORYS static dataset parts configured")
        merged = xr.merge(datasets, compat="override")
    merged.attrs["source"] = "GLORYS12V1 / GLOBAL_MULTIYEAR_PHY_001_030"
    merged.attrs["dataset_id"] = ",".join(str(request["dataset_id"]) for request in requests)
    safe_to_netcdf(xarray_sorted(merged), out_path)


def main() -> None:
    args = parse_args()
    config = load_glorys_config(args.config)
    window = config_window(config, args)
    paths = build_glorys_paths(config, start=window.start, stop=window.stop)
    grid = load_grid(resolve_grid_path(args.grid, prefer_smoothed=True))
    bbox = active_grid_bbox(grid, float(config["longitude_buffer_deg"]), float(config["latitude_buffer_deg"]))
    boundary_strategy = config["boundary_download_strategy"]
    boundary_boxes = {}
    if boundary_strategy == "edge_bands":
        boundary_boxes = {
            edge: edge_bbox(grid, edge, int(config["boundary_band_buffer_points"])) for edge in EDGE_NAMES
        }
    raw_dir = Path(paths.staged_boundary).parent
    required = list(config["variables_3d"]) + list(config["variables_2d"])

    if not args.merge_only and args.mode in {"initial", "both"} and paths.staged_static is not None:
        write_static_product(args.command, config, bbox, paths.staged_static, overwrite=args.overwrite)

    base_windows = split_monthly(window) if str(config["chunk"]).lower() == "month" else [window]

    initial_merged: xr.Dataset | None = None
    if args.mode in {"initial", "both"}:
        area = "initial"
        chunk_paths = existing_chunk_paths(raw_dir, area)
        if not args.merge_only:
            chunk_paths = []
            for item in base_windows:
                chunk_paths.extend(
                    ensure_window_downloaded(
                        args.command,
                        config,
                        bbox,
                        raw_dir,
                        area,
                        item,
                        resume=args.resume,
                        overwrite=args.overwrite,
                    )
                )
        else:
            if not chunk_paths:
                raise SystemExit(f"no existing chunks found for merge-only area {area}")
            for path in chunk_paths:
                if not valid_netcdf(path, required):
                    raise SystemExit(f"missing or invalid chunk for merge-only: {path}")
        initial_merged = load_chunk_datasets(chunk_paths, config)
        write_initial_product(initial_merged, paths.staged_initial, config, window, bbox)
        print(f"wrote {paths.staged_initial}")

    if args.mode in {"boundary", "both"}:
        if boundary_strategy == "domain":
            if initial_merged is not None:
                boundary = initial_merged
            else:
                area = "boundary/domain"
                chunk_paths = existing_chunk_paths(raw_dir, area)
                if not args.merge_only:
                    chunk_paths = []
                    for item in base_windows:
                        chunk_paths.extend(
                            ensure_window_downloaded(
                                args.command,
                                config,
                                bbox,
                                raw_dir,
                                area,
                                item,
                                resume=args.resume,
                                overwrite=args.overwrite,
                            )
                        )
                else:
                    if not chunk_paths:
                        raise SystemExit(f"no existing chunks found for merge-only area {area}")
                    for path in chunk_paths:
                        if not valid_netcdf(path, required):
                            raise SystemExit(f"missing or invalid chunk for merge-only: {path}")
                boundary = load_chunk_datasets(chunk_paths, config)
            write_boundary_product(boundary, paths.staged_boundary, config, window, bbox=bbox)
            print(f"wrote {paths.staged_boundary}")
        else:
            edge_datasets: dict[str, xr.Dataset] = {}
            for edge_name in EDGE_NAMES:
                area = f"boundary/{edge_name}"
                chunk_paths = existing_chunk_paths(raw_dir, area)
                if not args.merge_only:
                    chunk_paths = []
                    for item in base_windows:
                        chunk_paths.extend(
                            ensure_window_downloaded(
                                args.command,
                                config,
                                boundary_boxes[edge_name],
                                raw_dir,
                                area,
                                item,
                                resume=args.resume,
                                overwrite=args.overwrite,
                            )
                        )
                else:
                    if not chunk_paths:
                        raise SystemExit(f"no existing chunks found for merge-only area {area}")
                    for path in chunk_paths:
                        if not valid_netcdf(path, required):
                            raise SystemExit(f"missing or invalid chunk for merge-only: {path}")
                edge_ds = load_chunk_datasets(chunk_paths, config)
                edge_ds.attrs["source_edge"] = edge_name
                edge_datasets[edge_name] = edge_ds
            boundary = merge_boundary_edges(edge_datasets)
            write_boundary_product(boundary, paths.staged_boundary, config, window, edge_boxes=boundary_boxes)
            print(f"wrote {paths.staged_boundary}")

    if paths.staged_static is not None and paths.staged_static.exists():
        print(f"static={paths.staged_static}")


if __name__ == "__main__":
    main()
