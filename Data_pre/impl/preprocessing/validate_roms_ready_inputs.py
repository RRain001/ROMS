#!/usr/bin/env python3
"""Validate ROMS-ready case input files."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

from case_naming import roms_input_name
from ocean_source_utils import build_glorys_paths, load_glorys_config, normalize_ocean_source
from roms_preprocessing_utils import ROOT, resolve_grid_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--ocean-source", default="hycom")
    parser.add_argument("--config", default=None)
    parser.add_argument("--ini", default=None)
    parser.add_argument("--bry", default=None)
    parser.add_argument("--atm", default=str(ROOT / "input" / roms_input_name("atm")))
    parser.add_argument("--rad", default=str(ROOT / "input" / roms_input_name("rad")))
    parser.add_argument("--tides", default=str(ROOT / "input" / roms_input_name("tides")))
    parser.add_argument("--river", default=str(ROOT / "input" / "roms_rivers_production.nc"))
    return parser.parse_args()


def check_file(path: Path, required: list[str], label: str) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"{label}: missing file {path}"]
    try:
        with Dataset(path) as ds:
            for name in required:
                if name not in ds.variables:
                    issues.append(f"{label}: missing variable {name}")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"{label}: cannot open NetCDF: {type(exc).__name__}: {exc}")
    return issues


def check_required_variables_finite(path: Path, required: list[str], label: str) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return issues
    with Dataset(path) as ds:
        for name in required:
            if name not in ds.variables:
                continue
            values = np.ma.filled(ds.variables[name][:], np.nan).astype(float, copy=False)
            nan_count = int(np.isnan(values).sum())
            if nan_count > 0:
                issues.append(f"{label}: variable {name} contains {nan_count} NaN values")
    return issues


def check_time_range(path: Path, time_name: str) -> list[str]:
    issues: list[str] = []
    with Dataset(path) as ds:
        if time_name not in ds.variables:
            return [f"{path.name}: missing time variable {time_name}"]
        time_var = ds.variables[time_name]
        values = time_var[:]
        if values.size == 0:
            return [f"{path.name}: empty time variable {time_name}"]
        units = getattr(time_var, "units", None)
        if not units:
            return [f"{path.name}: missing units on {time_name}"]
        calendar = getattr(time_var, "calendar", "standard")
        times = num2date(values, units=units, calendar=calendar)
        issues.append(f"{path.name}: {time_name} {times[0].isoformat()} -> {times[-1].isoformat()}")
    return issues


def has_any_variable(ds: Dataset, names: list[str]) -> bool:
    return any(name in ds.variables for name in names)


def check_boundary_content(path: Path) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"bry: missing file {path}"]
    try:
        with Dataset(path) as ds:
            required_edges = ("west", "east", "south", "north")
            for edge in required_edges:
                checks = {
                    f"zeta_{edge}": [f"zeta_{edge}"],
                    f"ubar_{edge}": [f"ubar_{edge}"],
                    f"vbar_{edge}": [f"vbar_{edge}"],
                    f"u_{edge}": [f"u_{edge}"],
                    f"v_{edge}": [f"v_{edge}"],
                    f"temp_{edge}": [f"temp_{edge}"],
                    f"salt_{edge}": [f"salt_{edge}"],
                    f"dye_{edge}": [f"dye_{edge}_01", f"dye_01_{edge}"],
                }
                for label, candidates in checks.items():
                    if not has_any_variable(ds, candidates):
                        issues.append(f"bry: missing variable {label} ({' or '.join(candidates)})")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"bry: cannot open NetCDF: {type(exc).__name__}: {exc}")
    return issues


def main() -> None:
    args = parse_args()
    ocean_source = normalize_ocean_source(args.ocean_source)
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    if ocean_source == "hycom":
        ini_path = Path(args.ini or ROOT / "input" / roms_input_name("ini"))
        bry_path = Path(args.bry or ROOT / "input" / roms_input_name("bdy"))
    else:
        config = load_glorys_config(args.config)
        start = datetime.fromisoformat("2024-01-01T12:00:00")
        stop = datetime.fromisoformat("2024-02-01T12:00:00")
        defaults = build_glorys_paths(config, start=start, stop=stop)
        ini_path = Path(args.ini or defaults.roms_ini)
        bry_path = Path(args.bry or defaults.roms_bdy)
    files = {
        "grid": (Path(grid_path), ["h", "mask_rho", "pm", "pn", "angle", "lon_rho", "lat_rho"]),
        "ini": (ini_path, ["zeta", "u", "v", "ubar", "vbar", "temp", "salt", "dye_01"]),
        "atm": (Path(args.atm), ["Uwind", "Vwind", "Pair", "Tair", "Qair", "rain", "EminusP"]),
        "rad": (Path(args.rad), ["swrad", "lwrad", "lwrad_down"]),
        "tides": (Path(args.tides), ["tide_period", "tide_Eamp", "tide_Ephase"]),
        "river": (Path(args.river), ["river_transport", "river_dye_01", "river_temp", "river_salt"]),
    }
    issues: list[str] = []
    for label, (path, required) in files.items():
        issues.extend(check_file(path, required, label))
        if label in {"ini", "atm", "rad", "river"}:
            issues.extend(check_required_variables_finite(path, required, label))
    issues.extend(check_boundary_content(bry_path))

    if not issues:
        issues.extend(check_time_range(ini_path, "ocean_time"))
        issues.extend(check_time_range(bry_path, "zeta_time"))
        issues.extend(check_time_range(Path(args.atm), "wind_time"))
        issues.extend(check_time_range(Path(args.rad), "srf_time"))
        issues.extend(check_time_range(Path(args.river), "river_time"))
        with Dataset(args.river) as ds:
            units = getattr(ds.variables["river_dye_01"], "units", "")
            if units != "Bq meter-3":
                issues.append(f"river: expected river_dye_01 units Bq meter-3, got {units!r}")

    for message in issues:
        print(message)
    fatal = [message for message in issues if "missing" in message or "cannot open" in message or "expected" in message]
    if fatal:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
