#!/usr/bin/env python3
"""Validate case-driven spin-up input products and write readiness reports."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset, num2date

from case_naming import load_case_naming, roms_input_name, staged_atmosphere_name, staged_ocean_name, staged_tides_name
from formal_online_workflow import load_formal_online_workflow, spinup_zero_source_name
from ocean_source_utils import build_glorys_paths, load_glorys_config, normalize_ocean_source
from roms_preprocessing_utils import ROOT, load_project_params, load_vertical_config, resolve_grid_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--ocean-source", default=None)
    parser.add_argument("--raw-ini", default=None)
    parser.add_argument("--raw-bdy", default=None)
    parser.add_argument("--raw-atm", default=None)
    parser.add_argument("--raw-rad", default=None)
    parser.add_argument("--raw-tides", default=None)
    parser.add_argument("--ini", default=None)
    parser.add_argument("--bdy", default=None)
    parser.add_argument("--atm", default=None)
    parser.add_argument("--rad", default=None)
    parser.add_argument("--tides", default=None)
    parser.add_argument("--river", default=None)
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--report-md", default=None)
    return parser.parse_args()


def _to_builtin(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime(
        int(value.year),
        int(value.month),
        int(value.day),
        int(getattr(value, "hour", 0)),
        int(getattr(value, "minute", 0)),
        int(getattr(value, "second", 0)),
    )


def _format_label(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"


def _expected_paths(start: datetime, end: datetime, profile: str, ocean_source: str) -> dict[str, Path]:
    naming = load_case_naming()
    workflow = load_formal_online_workflow(load_project_params())
    if ocean_source == "glorys12v1":
        ocean_paths = build_glorys_paths(load_glorys_config(), start=start, stop=end, profile=profile)
        raw_ini = ocean_paths.staged_initial
        raw_bdy = ocean_paths.staged_boundary
    else:
        raw_ini = ROOT / "data" / "raw" / "ocean" / staged_ocean_name(ocean_source, "initial", start=start, stop=end)
        raw_bdy = ROOT / "data" / "raw" / "ocean" / staged_ocean_name(ocean_source, "boundary", start=start, stop=end)
    return {
        "raw_ini": raw_ini,
        "raw_bdy": raw_bdy,
        "raw_atm": ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("atm", start=start, stop=end),
        "raw_rad": ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("rad", start=start, stop=end),
        "raw_tides": ROOT / "data" / "raw" / "tides" / staged_tides_name(start=start, stop=end),
        "ini": ROOT / "input" / roms_input_name("ini", profile=profile, start=start, stop=end),
        "bdy": ROOT / "input" / roms_input_name("bdy", profile=profile, start=start, stop=end),
        "atm": ROOT / "input" / roms_input_name("atm", start=start, stop=end),
        "rad": ROOT / "input" / roms_input_name("rad", start=start, stop=end),
        "tides": ROOT / "input" / roms_input_name("tides", profile=profile, start=start, stop=end),
        "river": ROOT / "input" / spinup_zero_source_name(naming.roms_prefix, workflow),
    }


def _raw_ocean_requirements(ocean_source: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if ocean_source == "glorys12v1":
        return ("time",), ("zos", "uo", "vo", "thetao", "so")
    return ("time",), ("zeta", "u", "v", "temp", "salt")


def _decode_times(ds: Dataset, variable_name: str) -> list[datetime]:
    var = ds.variables[variable_name]
    values = np.asarray(var[:])
    units = getattr(var, "units", None)
    if units is None:
        raise ValueError(f"{variable_name} missing units")
    calendar = getattr(var, "calendar", "standard")
    decoded = num2date(values, units=units, calendar=calendar)
    return [_as_datetime(item) for item in decoded]


def _file_summary(path: Path, time_vars: tuple[str, ...], required_vars: tuple[str, ...]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "dimensions": {},
        "time_ranges": {},
        "missing_variables": [],
        "nan_checks": {},
    }
    if not path.exists():
        summary["missing_variables"] = list(required_vars)
        return summary
    with Dataset(path) as ds:
        summary["dimensions"] = {name: len(dim) for name, dim in ds.dimensions.items()}
        for time_name in time_vars:
            if time_name not in ds.variables:
                continue
            times = _decode_times(ds, time_name)
            if times:
                summary["time_ranges"][time_name] = {
                    "start": _iso(times[0]),
                    "end": _iso(times[-1]),
                    "count": len(times),
                }
        for name in required_vars:
            if name not in ds.variables:
                summary["missing_variables"].append(name)
                continue
            values = np.ma.filled(ds.variables[name][:], np.nan).astype(float, copy=False)
            summary["nan_checks"][name] = {
                "nan_count": int(np.isnan(values).sum()),
                "finite_count": int(np.isfinite(values).sum()),
            }
    return summary


def _coverage_ok(file_summary: dict[str, Any], time_name: str, start: datetime, end: datetime, exact_start: bool) -> list[str]:
    issues: list[str] = []
    time_ranges = file_summary.get("time_ranges", {})
    if time_name not in time_ranges:
        return [f"{Path(file_summary['path']).name}: missing time variable {time_name}"]
    actual_start = datetime.fromisoformat(time_ranges[time_name]["start"])
    actual_end = datetime.fromisoformat(time_ranges[time_name]["end"])
    if exact_start and actual_start != start:
        issues.append(f"{Path(file_summary['path']).name}: expected start {start.isoformat()} but found {actual_start.isoformat()}")
    if actual_start > start:
        issues.append(f"{Path(file_summary['path']).name}: starts too late at {actual_start.isoformat()}")
    if actual_end < end:
        issues.append(f"{Path(file_summary['path']).name}: ends too early at {actual_end.isoformat()}")
    return issues


def _grid_and_vertical_checks(grid_path: Path, ini_path: Path, bdy_path: Path, tide_path: Path, river_path: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    details: dict[str, Any] = {"grid_path": str(grid_path), "grid_dimensions": {}, "vertical_N": None}
    vertical = load_vertical_config()
    details["vertical_N"] = vertical.N
    with Dataset(grid_path) as grid:
        grid_dims = {name: len(dim) for name, dim in grid.dimensions.items()}
        details["grid_dimensions"] = grid_dims
        expected = {
            "eta_rho": grid_dims["eta_rho"],
            "xi_rho": grid_dims["xi_rho"],
            "eta_u": grid_dims["eta_u"],
            "xi_u": grid_dims["xi_u"],
            "eta_v": grid_dims["eta_v"],
            "xi_v": grid_dims["xi_v"],
        }
    for label, path in (("ini", ini_path), ("bdy", bdy_path), ("tides", tide_path), ("river", river_path)):
        if not path.exists():
            issues.append(f"{label}: missing file {path}")
            continue
        with Dataset(path) as ds:
            if label in {"ini", "bdy", "river"}:
                s_rho = len(ds.dimensions["s_rho"]) if "s_rho" in ds.dimensions else None
                if s_rho != vertical.N:
                    issues.append(f"{label}: s_rho={s_rho} does not match configured vertical.N={vertical.N}")
            for dim_name, expected_size in expected.items():
                if dim_name in ds.dimensions and len(ds.dimensions[dim_name]) != expected_size:
                    issues.append(f"{label}: {dim_name}={len(ds.dimensions[dim_name])} does not match grid {dim_name}={expected_size}")
    return issues, details


def _river_zero_checks(path: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    details: dict[str, Any] = {"source_is_zero": False}
    if not path.exists():
        return [f"river: missing file {path}"], details
    with Dataset(path) as ds:
        if "river_dye_01" not in ds.variables:
            return ["river: missing river_dye_01"], details
        dye = np.asarray(ds.variables["river_dye_01"][:], dtype=float)
        transport = np.asarray(ds.variables["river_transport"][:], dtype=float) if "river_transport" in ds.variables else None
        vshape = np.asarray(ds.variables["river_Vshape"][:], dtype=float) if "river_Vshape" in ds.variables else None
        details["dye_nan_count"] = int(np.isnan(dye).sum())
        details["dye_min"] = float(np.nanmin(dye))
        details["dye_max"] = float(np.nanmax(dye))
        details["release_Bq_s"] = float(getattr(ds, "release_Bq_s", np.nan))
        details["source_mode"] = getattr(ds, "source_mode", None)
        details["transport_min"] = float(np.nanmin(transport)) if transport is not None else None
        details["transport_max"] = float(np.nanmax(transport)) if transport is not None else None
        if not np.allclose(np.nan_to_num(dye), 0.0):
            issues.append("river: river_dye_01 is not identically zero")
        if details["release_Bq_s"] != 0.0:
            issues.append(f"river: expected release_Bq_s=0 but found {details['release_Bq_s']}")
        if vshape is None:
            issues.append("river: missing river_Vshape")
        else:
            column_sums = np.sum(vshape, axis=0)
            details["vshape_column_sums"] = [float(value) for value in column_sums]
            details["surface_only"] = bool(np.count_nonzero(vshape[:-1, :]) == 0 and np.allclose(vshape[-1, :], 1.0))
            if not np.allclose(column_sums, 1.0):
                issues.append("river: river_Vshape column sums are not 1")
        details["source_is_zero"] = not issues
    return issues, details


def _tide_checks(path: Path, expected_zero_phase_date: float) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    details: dict[str, Any] = {"uv_complete": False}
    if not path.exists():
        return [f"tides: missing file {path}"], details
    with Dataset(path) as ds:
        required = ("tide_Eamp", "tide_Ephase", "tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase")
        missing = [name for name in required if name not in ds.variables]
        details["missing_variables"] = missing
        if missing:
            issues.extend([f"tides: missing variable {name}" for name in missing])
        zero_phase_value = float(ds.variables["zero_phase_date"].getValue()) if "zero_phase_date" in ds.variables else None
        details["zero_phase_date"] = zero_phase_value
        if zero_phase_value != expected_zero_phase_date:
            issues.append(
                f"tides: expected zero_phase_date {expected_zero_phase_date:.0f} but found "
                f"{zero_phase_value if zero_phase_value is not None else 'missing'}"
            )
        details["uv_complete"] = not missing
    return issues, details


def _overwrite_checks(paths: dict[str, Path]) -> tuple[list[str], dict[str, Any]]:
    naming = load_case_naming()
    params = load_project_params()
    workflow = load_formal_online_workflow(params)
    preserved = {
        "ini": ROOT / "input" / roms_input_name("ini", profile=workflow.profile, start=workflow.production_start, stop=workflow.production_end),
        "bdy": ROOT / "input" / roms_input_name("bdy", profile=workflow.profile, start=workflow.production_start, stop=workflow.production_end),
        "tides": ROOT / "input" / roms_input_name("tides", profile=workflow.profile, start=workflow.production_start, stop=workflow.production_end),
        "river": ROOT / "input" / f"roms_rivers_production_{workflow.profile}.nc",
        "atm": ROOT / "input" / roms_input_name("atm", start=workflow.production_start, stop=workflow.production_end),
        "rad": ROOT / "input" / roms_input_name("rad", start=workflow.production_start, stop=workflow.production_end),
    }
    issues: list[str] = []
    details = {
        "preserved_paths": {key: str(value) for key, value in preserved.items()},
        "preserved_exist": {key: value.exists() for key, value in preserved.items()},
        "collisions": {},
    }
    mapping = {"ini": "ini", "bdy": "bdy", "tides": "tides", "river": "river", "atm": "atm", "rad": "rad"}
    for key, preserved_key in mapping.items():
        collision = paths[key].resolve() == preserved[preserved_key].resolve()
        details["collisions"][key] = collision
        if collision:
            issues.append(f"{key}: spin-up output path collides with production input file")
    return issues, details


def _missing_variable_issues(file_summaries: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for label, summary in file_summaries.items():
        for variable in summary.get("missing_variables", []):
            issues.append(f"{label}: missing variable {variable}")
    return issues


def _nan_issues(file_summaries: dict[str, dict[str, Any]], *, labels: tuple[str, ...] | None = None) -> list[str]:
    issues: list[str] = []
    selected = labels or tuple(file_summaries.keys())
    for label in selected:
        summary = file_summaries[label]
        for variable, checks in summary.get("nan_checks", {}).items():
            if checks["nan_count"] > 0:
                issues.append(f"{label}: variable {variable} contains {checks['nan_count']} NaN values")
    return issues


def _write_reports(payload: dict[str, Any], md_path: Path, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_to_builtin) + "\n", encoding="utf-8")

    lines = [
        f"# {payload['case_name']} Spin-up Data Ready Report",
        "",
        f"- case: `{payload['case_name']}`",
        f"- profile: `{payload['profile']}`",
        f"- window: `{payload['window']['start']}` -> `{payload['window']['end']}`",
        f"- status: `{payload['status']}`",
        f"- can_generate_spinup_run_mode: `{payload['can_generate_run_mode']}`",
        "",
        "## Inputs",
        "",
    ]
    for key, info in payload["file_summaries"].items():
        lines.append(f"- {key}: `{info['path']}`")
        if info["time_ranges"]:
            for time_name, time_info in info["time_ranges"].items():
                lines.append(
                    f"  {time_name}: `{time_info['start']}` -> `{time_info['end']}` "
                    f"({time_info['count']} records)"
                )
        if info["dimensions"]:
            dims = ", ".join(f"{name}={size}" for name, size in info["dimensions"].items())
            lines.append(f"  dims: `{dims}`")
        if info["missing_variables"]:
            lines.append(f"  missing_variables: `{', '.join(info['missing_variables'])}`")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            f"- tide_uv_complete: `{payload['tide_checks']['uv_complete']}`",
            f"- source_is_zero: `{payload['river_checks']['source_is_zero']}`",
            f"- overwrite_safe: `{not payload['overwrite_checks']['collisions']['ini'] and not payload['overwrite_checks']['collisions']['bdy'] and not payload['overwrite_checks']['collisions']['tides'] and not payload['overwrite_checks']['collisions']['river'] and not payload['overwrite_checks']['collisions']['atm'] and not payload['overwrite_checks']['collisions']['rad']}`",
            "",
            "## Blocking Issues",
            "",
        ]
    )
    if payload["blocking_issues"]:
        lines.extend([f"- {item}" for item in payload["blocking_issues"]])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            f"- {payload['next_step']}",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    params = load_project_params()
    workflow = load_formal_online_workflow(params)
    start = datetime.fromisoformat(args.start) if args.start else workflow.spinup_start
    end = datetime.fromisoformat(args.end) if args.end else workflow.spinup_end
    profile = args.profile or workflow.profile
    if start >= end:
        raise SystemExit("start must be earlier than end")

    label = _format_label(start, end)
    reports_dir = ROOT / "reports"
    ocean_source = normalize_ocean_source(args.ocean_source)
    expected = _expected_paths(start, end, profile, ocean_source)
    paths = {
        "raw_ini": Path(args.raw_ini) if args.raw_ini else expected["raw_ini"],
        "raw_bdy": Path(args.raw_bdy) if args.raw_bdy else expected["raw_bdy"],
        "raw_atm": Path(args.raw_atm) if args.raw_atm else expected["raw_atm"],
        "raw_rad": Path(args.raw_rad) if args.raw_rad else expected["raw_rad"],
        "raw_tides": Path(args.raw_tides) if args.raw_tides else expected["raw_tides"],
        "ini": Path(args.ini) if args.ini else expected["ini"],
        "bdy": Path(args.bdy) if args.bdy else expected["bdy"],
        "atm": Path(args.atm) if args.atm else expected["atm"],
        "rad": Path(args.rad) if args.rad else expected["rad"],
        "tides": Path(args.tides) if args.tides else expected["tides"],
        "river": Path(args.river) if args.river else expected["river"],
    }
    report_json = Path(args.report_json) if args.report_json else reports_dir / f"{load_case_naming().roms_prefix}_spinup_{label}_data_ready.json"
    report_md = Path(args.report_md) if args.report_md else reports_dir / f"{load_case_naming().roms_prefix}_spinup_{label}_data_ready.md"

    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    raw_ocean_time_vars, raw_ocean_vars = _raw_ocean_requirements(ocean_source)
    file_summaries = {
        "raw_ini": _file_summary(paths["raw_ini"], raw_ocean_time_vars, raw_ocean_vars),
        "raw_bdy": _file_summary(paths["raw_bdy"], raw_ocean_time_vars, raw_ocean_vars),
        "raw_atm": _file_summary(paths["raw_atm"], ("time",), ("Uwind", "Vwind", "Pair", "Tair", "Qair", "rain", "EminusP")),
        "raw_rad": _file_summary(paths["raw_rad"], ("time",), ("swrad", "lwrad", "lwrad_down")),
        "raw_tides": _file_summary(paths["raw_tides"], tuple(), ("tide_Eamp", "tide_Ephase", "tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase")),
        "ini": _file_summary(paths["ini"], ("ocean_time",), ("zeta", "u", "v", "ubar", "vbar", "temp", "salt", "dye_01")),
        "bdy": _file_summary(
            paths["bdy"],
            ("zeta_time", "v2d_time", "v3d_time", "temp_time", "salt_time", "dye_time"),
            (
                "zeta_west", "zeta_east", "zeta_south", "zeta_north",
                "ubar_west", "ubar_east", "ubar_south", "ubar_north",
                "vbar_west", "vbar_east", "vbar_south", "vbar_north",
                "u_west", "u_east", "u_south", "u_north",
                "v_west", "v_east", "v_south", "v_north",
                "temp_west", "temp_east", "temp_south", "temp_north",
                "salt_west", "salt_east", "salt_south", "salt_north",
                "dye_west_01", "dye_east_01", "dye_south_01", "dye_north_01",
            ),
        ),
        "atm": _file_summary(paths["atm"], ("wind_time", "pair_time", "tair_time", "qair_time", "rain_time", "swf_time"), ("Uwind", "Vwind", "Pair", "Tair", "Qair", "rain", "EminusP", "swflux")),
        "rad": _file_summary(paths["rad"], ("srf_time", "lrf_time"), ("swrad", "lwrad", "lwrad_down")),
        "tides": _file_summary(paths["tides"], tuple(), ("tide_Eamp", "tide_Ephase", "tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase")),
        "river": _file_summary(paths["river"], ("river_time",), ("river_transport", "river_dye_01", "river_temp", "river_salt", "river_Vshape")),
    }

    issues: list[str] = []
    issues.extend(_missing_variable_issues(file_summaries))
    issues.extend(_nan_issues(file_summaries, labels=("ini", "bdy", "atm", "rad", "tides", "river")))
    issues.extend(_coverage_ok(file_summaries["ini"], "ocean_time", start, start, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["raw_ini"], "time", start, start, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["bdy"], "zeta_time", start, end, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["raw_bdy"], "time", start, end, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["atm"], "wind_time", start, end, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["raw_atm"], "time", start, end, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["rad"], "srf_time", start, end, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["raw_rad"], "time", start, end, exact_start=True))
    issues.extend(_coverage_ok(file_summaries["river"], "river_time", start, end, exact_start=True))

    grid_issues, grid_details = _grid_and_vertical_checks(grid_path, paths["ini"], paths["bdy"], paths["tides"], paths["river"])
    river_issues, river_details = _river_zero_checks(paths["river"])
    tide_issues, tide_details = _tide_checks(paths["tides"], float(start.strftime("%Y%m%d")))
    overwrite_issues, overwrite_details = _overwrite_checks(paths)
    issues.extend(grid_issues)
    issues.extend(river_issues)
    issues.extend(tide_issues)
    issues.extend(overwrite_issues)

    can_generate_run_mode = not issues
    payload = {
        "case_name": load_case_naming().case_name,
        "profile": profile,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "status": "ready" if can_generate_run_mode else "blocked",
        "file_summaries": file_summaries,
        "grid_checks": grid_details,
        "river_checks": river_details,
        "tide_checks": tide_details,
        "overwrite_checks": overwrite_details,
        "blocking_issues": issues,
        "can_generate_run_mode": can_generate_run_mode,
        "next_step": (
            f"Generate and validate {workflow.spinup_mode} run mode wiring."
            if can_generate_run_mode
            else f"Resolve the blocking issues above before creating {workflow.spinup_mode}."
        ),
    }
    _write_reports(payload, report_md, report_json)
    print(f"report_md={report_md}")
    print(f"report_json={report_json}")
    for issue in issues:
        print(issue)
    if issues:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
