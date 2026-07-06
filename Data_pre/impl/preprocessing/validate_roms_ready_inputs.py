#!/usr/bin/env python3
"""Validate ROMS-ready case input files."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re

import numpy as np
from netCDF4 import Dataset, num2date

from case_naming import roms_input_name
from ocean_source_utils import build_glorys_paths, load_glorys_config, normalize_ocean_source
from roms_preprocessing_utils import ROOT, load_vertical_config, resolve_grid_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--ocean-source", default="hycom")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--require-uv-tides", action="store_true")
    parser.add_argument("--ini", default=None)
    parser.add_argument("--bry", default=None)
    parser.add_argument("--atm", default=str(ROOT / "input" / roms_input_name("atm")))
    parser.add_argument("--rad", default=str(ROOT / "input" / roms_input_name("rad")))
    parser.add_argument("--tides", default=None)
    parser.add_argument("--river", default=None)
    parser.add_argument("--infile", default=None, help="Optional ROMS .in file for Lm/Mm/N consistency checks")
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


def check_zero_variable(path: Path, names: tuple[str, ...], label: str) -> list[str]:
    if not path.exists():
        return []
    with Dataset(path) as ds:
        for name in names:
            if name not in ds.variables:
                continue
            values = np.ma.filled(ds.variables[name][:], np.nan).astype(float, copy=False)
            finite = values[np.isfinite(values)]
            if finite.size and not np.allclose(finite, 0.0):
                return [f"{label}: {name} is not all zero"]
            return []
    return [f"{label}: missing {' or '.join(names)}"]


def check_uv_tide_content(path: Path, require_uv: bool) -> list[str]:
    if not require_uv or not path.exists():
        return []
    issues: list[str] = []
    with Dataset(path) as ds:
        for name in ("tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase"):
            if name not in ds.variables:
                issues.append(f"tides: missing UV tide variable {name}")
    return issues


def check_river_vshape(path: Path) -> list[str]:
    if not path.exists():
        return []
    with Dataset(path) as ds:
        if "river_Vshape" not in ds.variables:
            return ["river: missing river_Vshape"]
        values = np.asarray(ds.variables["river_Vshape"][:], dtype=float)
        if not np.allclose(values.sum(axis=0), 1.0):
            return ["river: river_Vshape column sums are not 1"]
    return []


def _dim(ds: Dataset, name: str) -> int | None:
    return len(ds.dimensions[name]) if name in ds.dimensions else None


def check_dimension_consistency(grid_path: Path, ini_path: Path, bry_path: Path, river_path: Path) -> list[str]:
    issues: list[str] = []
    if not grid_path.exists():
        return issues
    vertical = load_vertical_config()
    with Dataset(grid_path) as grid:
        grid_dims = {
            "xi_rho": _dim(grid, "xi_rho"),
            "eta_rho": _dim(grid, "eta_rho"),
            "xi_u": _dim(grid, "xi_u"),
            "eta_u": _dim(grid, "eta_u"),
            "xi_v": _dim(grid, "xi_v"),
            "eta_v": _dim(grid, "eta_v"),
        }

    for label, path in (("ini", ini_path), ("bry", bry_path)):
        if not path.exists():
            continue
        with Dataset(path) as ds:
            if _dim(ds, "s_rho") != vertical.N:
                issues.append(f"{label}: s_rho={_dim(ds, 's_rho')} does not match configured vertical.N={vertical.N}")
            for dim_name, expected in grid_dims.items():
                actual = _dim(ds, dim_name)
                if actual is not None and expected is not None and actual != expected:
                    issues.append(f"{label}: {dim_name}={actual} does not match grid {dim_name}={expected}")

    if river_path.exists():
        with Dataset(river_path) as ds:
            if _dim(ds, "s_rho") != vertical.N:
                issues.append(f"river: s_rho={_dim(ds, 's_rho')} does not match configured vertical.N={vertical.N}")
    return issues


def _parse_infile_int(text: str, key: str) -> int | None:
    match = re.search(rf"^\s*{re.escape(key)}\s*=+\s*([0-9]+)", text, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def check_infile_dimensions(infile_path: Path, grid_path: Path) -> list[str]:
    issues: list[str] = []
    if not infile_path.exists():
        return [f"infile: missing file {infile_path}"]
    vertical = load_vertical_config()
    text = infile_path.read_text(errors="ignore")
    n = _parse_infile_int(text, "N")
    lm = _parse_infile_int(text, "Lm")
    mm = _parse_infile_int(text, "Mm")
    if n != vertical.N:
        issues.append(f"infile: N={n} does not match configured vertical.N={vertical.N}")
    if grid_path.exists():
        with Dataset(grid_path) as grid:
            expected_lm = _dim(grid, "xi_rho") - 2 if _dim(grid, "xi_rho") is not None else None
            expected_mm = _dim(grid, "eta_rho") - 2 if _dim(grid, "eta_rho") is not None else None
        if lm != expected_lm:
            issues.append(f"infile: Lm={lm} does not match grid xi_rho-2={expected_lm}")
        if mm != expected_mm:
            issues.append(f"infile: Mm={mm} does not match grid eta_rho-2={expected_mm}")
    return issues


def main() -> None:
    args = parse_args()
    ocean_source = normalize_ocean_source(args.ocean_source)
    profile = args.profile
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    if ocean_source == "hycom":
        ini_path = Path(args.ini or ROOT / "input" / roms_input_name("ini", profile=profile))
        bry_path = Path(args.bry or ROOT / "input" / roms_input_name("bdy", profile=profile))
    else:
        config = load_glorys_config(args.config)
        start = datetime.fromisoformat("2024-01-01T12:00:00")
        stop = datetime.fromisoformat("2024-02-01T12:00:00")
        defaults = build_glorys_paths(config, start=start, stop=stop)
        ini_path = Path(args.ini or defaults.roms_ini)
        bry_path = Path(args.bry or defaults.roms_bdy)
    river_path = Path(args.river) if args.river else ROOT / "input" / (f"roms_rivers_production_{profile}.nc" if profile else "roms_rivers_production.nc")
    tide_path = Path(args.tides) if args.tides else ROOT / "input" / roms_input_name("tides", profile=profile)
    files = {
        "grid": (Path(grid_path), ["h", "mask_rho", "pm", "pn", "angle", "lon_rho", "lat_rho"]),
        "ini": (ini_path, ["zeta", "u", "v", "ubar", "vbar", "temp", "salt", "dye_01"]),
        "atm": (Path(args.atm), ["Uwind", "Vwind", "Pair", "Tair", "Qair", "rain", "EminusP"]),
        "rad": (Path(args.rad), ["swrad", "lwrad", "lwrad_down"]),
        "tides": (tide_path, ["tide_period", "tide_Eamp", "tide_Ephase"]),
        "river": (river_path, ["river_transport", "river_dye_01", "river_temp", "river_salt"]),
    }
    issues: list[str] = []
    for label, (path, required) in files.items():
        issues.extend(check_file(path, required, label))
        if label in {"ini", "atm", "rad", "river"}:
            issues.extend(check_required_variables_finite(path, required, label))
    issues.extend(check_boundary_content(bry_path))
    issues.extend(check_zero_variable(ini_path, ("dye_01",), "ini"))
    for edge in ("west", "east", "south", "north"):
        issues.extend(check_zero_variable(bry_path, (f"dye_{edge}_01", f"dye_01_{edge}"), f"bry {edge}"))
    issues.extend(check_uv_tide_content(files["tides"][0], args.require_uv_tides))
    issues.extend(check_river_vshape(river_path))
    issues.extend(check_dimension_consistency(Path(grid_path), ini_path, bry_path, river_path))
    if args.infile:
        issues.extend(check_infile_dimensions(Path(args.infile), Path(grid_path)))

    if not issues:
        issues.extend(check_time_range(ini_path, "ocean_time"))
        issues.extend(check_time_range(bry_path, "zeta_time"))
        issues.extend(check_time_range(Path(args.atm), "wind_time"))
        issues.extend(check_time_range(Path(args.rad), "srf_time"))
        issues.extend(check_time_range(river_path, "river_time"))
        with Dataset(river_path) as ds:
            units = getattr(ds.variables["river_dye_01"], "units", "")
            if units != "Bq meter-3":
                issues.append(f"river: expected river_dye_01 units Bq meter-3, got {units!r}")

    for message in issues:
        print(message)
    fatal = [
        message
        for message in issues
        if "missing" in message or "cannot open" in message or "expected" in message or "does not match" in message
    ]
    if fatal:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
