#!/usr/bin/env python3
"""Perform deeper validation of staged raw data needed by the active case."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import get_case_config_path
from ocean_source_utils import build_glorys_paths, glorys_center_time, load_glorys_config, normalize_ocean_source
from roms_preprocessing_utils import load_grid, resolve_grid_path
from staged_data_utils import ROOT, candidate_first, get_bbox, get_time_window, load_download_config

DEFAULT_CONFIG = get_case_config_path("staged_download_config.json")
DEFAULT_MANIFEST = get_case_config_path("staged_data_manifest.csv")


@dataclass(frozen=True)
class Requirement:
    category: str
    required: bool
    path: Path
    variables: list[str]


def parse_iso_like_datetime(value: str) -> datetime:
    text = str(value).strip().replace("Z", "")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        dt64 = np.datetime64(text)
        unix_seconds = dt64.astype("datetime64[s]").astype(int)
        return datetime.utcfromtimestamp(int(unix_seconds))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"unsupported datetime string: {value!r}") from exc


def inferred_coord_tolerance(values: np.ndarray) -> float:
    coords = np.asarray(values, dtype=float)
    if coords.size <= 1:
        return 1e-6
    diffs = np.diff(np.sort(coords))
    positive = np.abs(diffs[np.abs(diffs) > 0.0])
    if positive.size == 0:
        return 1e-6
    return float(np.nanmedian(positive)) + 1e-6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--skip-categories", default="")
    parser.add_argument("--ocean-source", default="hycom")
    return parser.parse_args()


def read_manifest(path: Path) -> list[Requirement]:
    rows: list[Requirement] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                Requirement(
                    category=row["category"],
                    required=row["required"].strip().lower() in {"1", "true", "yes", "required"},
                    path=ROOT / row["path"],
                    variables=[item for item in row["variables"].split() if item],
                )
            )
    return rows


def validate_rectilinear_netcdf(
    path: Path,
    variables: list[str],
    require_depth: bool,
    require_time: bool,
    coverage_bbox,
    window,
    expect_source_time_match: bool = False,
) -> list[str]:
    problems: list[str] = []
    if not path.exists():
        return [f"missing file: {path}"]
    with Dataset(path) as ds:
        for variable in variables:
            if variable not in ds.variables:
                problems.append(f"missing variable: {variable}")
        try:
            lon_name = candidate_first(ds.variables, ("lon", "longitude", "x"))
            lat_name = candidate_first(ds.variables, ("lat", "latitude", "y"))
        except KeyError as exc:
            return [str(exc)]

        lon = np.asarray(ds.variables[lon_name][:], dtype=float)
        lat = np.asarray(ds.variables[lat_name][:], dtype=float)
        if lon.ndim != 1 or lat.ndim != 1:
            problems.append("lon/lat must be 1D rectilinear coordinates")
        lon_tol = inferred_coord_tolerance(lon)
        lat_tol = inferred_coord_tolerance(lat)
        if np.nanmin(lon) > coverage_bbox.west + lon_tol or np.nanmax(lon) < coverage_bbox.east - lon_tol:
            problems.append("longitude coverage does not span the active grid domain")
        if np.nanmin(lat) > coverage_bbox.south + lat_tol or np.nanmax(lat) < coverage_bbox.north - lat_tol:
            problems.append("latitude coverage does not span the active grid domain")

        if require_depth:
            try:
                depth_name = candidate_first(ds.variables, ("depth", "Depth", "lev", "level"))
            except KeyError as exc:
                problems.append(str(exc))
            else:
                depth = np.asarray(ds.variables[depth_name][:], dtype=float)
                if depth.ndim != 1 or depth.size < 2:
                    problems.append("depth must be a 1D coordinate with at least 2 levels")

        if require_time:
            try:
                time_name = candidate_first(ds.variables, ("time", "valid_time", "mt"))
            except KeyError as exc:
                problems.append(str(exc))
            else:
                time_var = ds.variables[time_name]
                if not getattr(time_var, "units", None):
                    problems.append("time variable is missing units")
                else:
                    from netCDF4 import num2date

                    values = np.asarray(time_var[:], dtype=float)
                    times = np.asarray(
                        num2date(values, units=time_var.units, calendar=getattr(time_var, "calendar", "standard")),
                        dtype=object,
                    )
                    if times.size == 0:
                        problems.append("time coordinate has no records")
                    else:
                        if window is not None and (times[0] > window.start or times[-1] < window.stop):
                            problems.append(
                                f"time coverage {times[0].isoformat()} to {times[-1].isoformat()} "
                                f"does not cover {window.start.isoformat()} to {window.stop.isoformat()}"
                            )
                        if expect_source_time_match and hasattr(ds, "source_time"):
                            source_time = str(getattr(ds, "source_time"))
                            try:
                                declared = parse_iso_like_datetime(source_time)
                            except ValueError:
                                problems.append(f"global source_time is not ISO-8601 parseable: {source_time!r}")
                            else:
                                if declared != times[0]:
                                    problems.append(
                                        f"global source_time {declared.isoformat()} does not match first time record "
                                        f"{times[0].isoformat()}"
                                    )
    return problems


def validate_source_csv(path: Path, window) -> list[str]:
    problems: list[str] = []
    if not path.exists():
        return [f"missing file: {path}"]
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if "time" not in reader.fieldnames or "discharge_m3_s" not in reader.fieldnames:
            return ["source discharge CSV must contain time and discharge_m3_s columns"]
        rows = list(reader)
    if not rows:
        return ["source discharge CSV has no records"]
    times = [datetime.fromisoformat(row["time"]) for row in rows]
    discharge = [float(row["discharge_m3_s"]) for row in rows]
    if any(value <= 0.0 for value in discharge):
        problems.append("source discharge contains non-positive values")
    if times[0] > window.start or times[-1] < window.stop:
        problems.append(
            f"source discharge coverage {times[0].isoformat()} to {times[-1].isoformat()} "
            f"does not cover {window.start.isoformat()} to {window.stop.isoformat()}"
        )
    return problems


def read_time_coverage(path: Path) -> tuple[datetime, datetime] | None:
    if not path.exists():
        return None
    with Dataset(path) as ds:
        try:
            time_name = candidate_first(ds.variables, ("time", "ocean_time", "zeta_time", "valid_time", "mt"))
        except KeyError:
            return None
        time_var = ds.variables[time_name]
        units = getattr(time_var, "units", None)
        if not units:
            return None
        from netCDF4 import num2date

        values = np.asarray(time_var[:], dtype=float)
        if values.size == 0:
            return None
        parsed = np.asarray(
            num2date(values, units=units, calendar=getattr(time_var, "calendar", "standard")),
            dtype=object,
        )
        start = parsed[0]
        stop = parsed[-1]
        return (
            datetime(start.year, start.month, start.day, start.hour, start.minute, start.second),
            datetime(stop.year, stop.month, stop.day, stop.hour, stop.minute, stop.second),
        )


def get_active_grid_bbox():
    try:
        grid_path = resolve_grid_path(None, prefer_smoothed=True)
    except SystemExit:
        return None
    grid = load_grid(grid_path)
    return type("CoverageBox", (), {
        "west": float(np.nanmin(grid.lon_rho)),
        "east": float(np.nanmax(grid.lon_rho)),
        "south": float(np.nanmin(grid.lat_rho)),
        "north": float(np.nanmax(grid.lat_rho)),
    })()


def effective_window(config: dict):
    window = get_time_window(config)
    initial_path = ROOT / config["paths"]["ocean_initial"]
    boundary_path = ROOT / config["paths"]["ocean_boundary"]
    initial_coverage = read_time_coverage(initial_path)
    boundary_coverage = read_time_coverage(boundary_path)
    start = max(window.start, initial_coverage[0]) if initial_coverage else window.start
    stop = min(window.stop, boundary_coverage[1]) if boundary_coverage else window.stop
    return type(window)(start=start, stop=stop)


def glorys_validation_window(config: dict):
    paths = build_glorys_paths(config)
    boundary_coverage = read_time_coverage(paths.staged_boundary)
    if boundary_coverage is not None:
        return type("Window", (), {"start": boundary_coverage[0], "stop": boundary_coverage[1]})()
    start_base = datetime.fromisoformat(config["time_start"])
    stop_base = datetime.fromisoformat(config["time_stop"])
    start = glorys_center_time(config, start_base)
    stop = glorys_center_time(config, stop_base)
    return type("Window", (), {"start": start, "stop": stop})()


def main() -> None:
    args = parse_args()
    ocean_source = normalize_ocean_source(args.ocean_source)
    if ocean_source == "hycom":
        config = load_download_config(args.config or str(DEFAULT_CONFIG))
        bbox = get_active_grid_bbox() or get_bbox(config)
        window = effective_window(config)
        requirements = read_manifest(Path(args.manifest))
    else:
        config = load_glorys_config(args.config)
        bbox = get_active_grid_bbox()
        if bbox is None:
            raise SystemExit("active ROMS grid is required for GLORYS validation")
        window = glorys_validation_window(config)
        paths = build_glorys_paths(config)
        requirements = [
            Requirement("ocean_static", True, paths.staged_static, list(config["static_variables"])),
            Requirement("ocean_initial", True, paths.staged_initial, list(config["variables_3d"]) + list(config["variables_2d"])),
            Requirement("ocean_boundary", True, paths.staged_boundary, list(config["variables_3d"]) + list(config["variables_2d"])),
        ]
    skip = {item.strip() for item in args.skip_categories.split(",") if item.strip()}

    failures = 0
    for item in requirements:
        if item.category in skip:
            print(f"[SKIP] {item.category}: {item.path.relative_to(ROOT)}")
            continue

        if item.category == "source_discharge":
            problems = validate_source_csv(item.path, window)
        elif item.category == "bathymetry":
            problems = validate_rectilinear_netcdf(item.path, item.variables, False, False, bbox, window)
        elif item.category in {"ocean_initial", "ocean_boundary"}:
            target_window = window if item.category == "ocean_boundary" else None
            problems = validate_rectilinear_netcdf(
                item.path,
                item.variables,
                item.category != "ocean_static",
                True,
                bbox,
                target_window,
                expect_source_time_match=item.category == "ocean_initial",
            )
        elif item.category == "ocean_static":
            problems = validate_rectilinear_netcdf(item.path, item.variables, False, False, bbox, None)
        elif item.category in {"atmosphere", "radiation"}:
            problems = validate_rectilinear_netcdf(item.path, item.variables, False, True, bbox, window)
        else:
            problems = validate_rectilinear_netcdf(item.path, item.variables, False, False, bbox, window)

        status = "OK" if not problems else "FAIL"
        print(f"[{status}] {item.category}: {item.path.relative_to(ROOT)}")
        for problem in problems:
            print(f"  - {problem}")
        if problems and item.required:
            failures += 1

    print(f"summary: required_failures={failures}")
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
