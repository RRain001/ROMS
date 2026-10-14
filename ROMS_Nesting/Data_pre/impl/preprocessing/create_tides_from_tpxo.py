#!/usr/bin/env python3
"""Create ROMS tide forcing from staged TPXO-like data."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_naming import case_start_datetime, load_case_naming, roms_input_name, staged_tides_name
from roms_preprocessing_utils import ROOT, get_rectilinear_lon_lat, infer_variable, interpolate_rectilinear_2d, load_grid, load_project_params, resolve_grid_path


DEFAULT_SRC = ROOT / "data" / "raw" / "tides" / staged_tides_name()
DEFAULT_OUT = ROOT / "input" / roms_input_name("tides")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--start", default=None, help="Optional window start used only for default output naming")
    parser.add_argument("--stop", default=None, help="Optional window stop used for default naming")
    parser.add_argument("--zero-phase-date", default=None, help="Optional YYYYMMDD or ISO date/datetime override")
    parser.add_argument("--require-uv", action="store_true", help="Require tide_Cmax/Cmin/Cangle/Cphase for UV_TIDES")
    parser.add_argument("--profile", default=None, help="Optional profile label used in blocked reports")
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    return parser.parse_args()


def parse_zero_phase_date(value: str | None) -> float:
    if value is None:
        configured = load_project_params().get("tides", {}).get("zero_phase_date")
        if configured:
            value = str(configured)
        else:
            raise ValueError("tides.zero_phase_date must be configured or supplied explicitly")
    cleaned = value.strip()
    if len(cleaned) == 8 and cleaned.isdigit():
        return float(cleaned)
    parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    return float(parsed.strftime("%Y%m%d"))


def current_ellipse(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """ROMS set_tides.F ellipse reconstruction from complex U/V constants."""
    wp = 0.5 * (u + 1j * v)
    wm = 0.5 * np.conj(u - 1j * v)
    sema = np.abs(wp) + np.abs(wm)
    semi = np.abs(wp) - np.abs(wm)
    angle = 0.5 * (np.angle(wp) + np.angle(wm))
    phase = 0.5 * (np.angle(wm) - np.angle(wp))
    return (
        sema.astype(np.float64),
        semi.astype(np.float64),
        np.mod(np.degrees(angle), 180.0).astype(np.float64),
        np.mod(np.degrees(phase), 360.0).astype(np.float64),
    )


def fill_nearest(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    valid = np.isfinite(data)
    if np.all(valid):
        return data
    if not np.any(valid):
        return np.zeros_like(data)
    from scipy.ndimage import distance_transform_edt

    _, indices = distance_transform_edt(~valid, return_indices=True)
    return data[tuple(indices)]


def _source_slice(var, tide_dim_name: str | None, tide_index: int | None) -> np.ndarray:
    data = np.asarray(var[:], dtype=float)
    if tide_index is not None and tide_dim_name and tide_dim_name in var.dimensions:
        axis = list(var.dimensions).index(tide_dim_name)
        data = np.take(data, tide_index, axis=axis)
    return data


def write_blocked_report(report_dir: Path, profile: str | None, src_path: Path, missing: list[str]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    label = profile or "tides"
    payload = {
        "status": "blocked",
        "profile": profile,
        "source_dataset": str(src_path),
        "missing_variables": missing,
        "message": "UV_TIDES requires TPXO current ellipse variables; variables were not fabricated.",
    }
    json_path = report_dir / f"{label}_uv_tides_blocked.json"
    md_path = report_dir / f"{label}_uv_tides_blocked.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md_path.write_text(
        "# UV_TIDES blocked\n\n"
        f"- Source: `{src_path}`\n"
        f"- Missing variables: {', '.join(missing)}\n"
        "- Action: stage TPXO u/v current ellipse data and rerun tide generation.\n"
        "- Note: no `tide_C*` variables were fabricated.\n"
    )


def main() -> None:
    args = parse_args()
    src_path = Path(args.src)
    if not src_path.exists():
        raise SystemExit(f"source file not found: {src_path}")
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    out_path = Path(args.output)
    if args.profile and args.output == str(DEFAULT_OUT):
        out_path = ROOT / "input" / roms_input_name(
            "tides",
            profile=args.profile,
            start=datetime.fromisoformat(args.start) if args.start else None,
            stop=datetime.fromisoformat(args.stop) if args.stop else None,
        )
    grid = load_grid(grid_path)
    zero_phase_date = parse_zero_phase_date(args.zero_phase_date)
    tide_cfg = load_project_params().get("tides", {})

    with Dataset(src_path) as src:
        lon, lat, lon_name, lat_name = get_rectilinear_lon_lat(src)
        tide_dim_name = None
        for name in src.dimensions:
            lowered = name.lower()
            if "tide" in lowered or "const" in lowered:
                tide_dim_name = name
                break
        if tide_dim_name is None:
            tide_period = np.asarray([12.42], dtype=float)
            tide_axis = [None]
        else:
            tide_period_name = infer_variable(src, ("tide_period", tide_dim_name))
            tide_period = np.asarray(src.variables[tide_period_name][:], dtype=float)
            tide_axis = list(range(len(tide_period)))

        raw_elevation_names = {}
        for out_name, candidates in {
            "tide_ERe": ("tide_ERe", "ERe"),
            "tide_EIm": ("tide_EIm", "EIm"),
        }.items():
            try:
                raw_elevation_names[out_name] = infer_variable(src, candidates)
            except KeyError:
                pass
        raw_elevation = len(raw_elevation_names) == 2
        if not raw_elevation:
            required_var_names = {
                "tide_Eamp": infer_variable(src, ("tide_Eamp", "Eamp")),
                "tide_Ephase": infer_variable(src, ("tide_Ephase", "Ephase")),
            }
        else:
            required_var_names = {}

        optional_var_names = {}
        missing_uv: list[str] = []
        for out_name, candidates in {
            "tide_Cmax": ("tide_Cmax", "Cmax"),
            "tide_Cmin": ("tide_Cmin", "Cmin"),
            "tide_Cangle": ("tide_Cangle", "Cangle"),
            "tide_Cphase": ("tide_Cphase", "Cphase"),
        }.items():
            try:
                optional_var_names[out_name] = infer_variable(src, candidates)
            except KeyError:
                missing_uv.append(out_name)
        if args.require_uv and missing_uv:
            write_blocked_report(Path(args.report_dir), args.profile, src_path, missing_uv)
            raise SystemExit(
                "UV_TIDES requested but source tide file is missing: " + ", ".join(missing_uv)
            )
        raw_current_names = {}
        for out_name, candidates in {
            "tide_URe": ("tide_URe", "URe"),
            "tide_UIm": ("tide_UIm", "UIm"),
            "tide_VRe": ("tide_VRe", "VRe"),
            "tide_VIm": ("tide_VIm", "VIm"),
        }.items():
            try:
                raw_current_names[out_name] = infer_variable(src, candidates)
            except KeyError:
                pass
        raw_current_components = len(raw_current_names) == 4
        raw_current = raw_current_components and all(name in src.variables for name in ("depth", "mask"))
        if args.require_uv and raw_current_components and not raw_current:
            raise SystemExit("raw TPXO UV components require staged depth and mask variables")
        var_names = required_var_names if raw_current else required_var_names | optional_var_names

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with Dataset(out_path, "w", format="NETCDF4") as ds:
            ds.createDimension("tide_period", len(tide_axis))
            ds.createDimension("eta_rho", grid.lon_rho.shape[0])
            ds.createDimension("xi_rho", grid.lon_rho.shape[1])
            ds.title = f"{load_case_naming().title} ROMS tide forcing from TPXO-like staged data"
            ds.grid_source = str(grid_path)
            ds.source_dataset = str(src_path)
            ds.phase_convention = str(tide_cfg.get("phase_convention", "OTPS"))
            ds.source_phase_reference = str(tide_cfg.get("source_reference", "TPXO9-atlas_v5 OTPS complex harmonic constants"))
            ds.source_reference_date = str(tide_cfg.get("source_reference_date", "OTPS model convention; calendar epoch is not encoded in atlas binary"))
            ds.v0_handling = str(tide_cfg.get("v0_handling", "source-model convention not re-applied"))
            ds.nodal_correction = str(tide_cfg.get("nodal_correction", "not applied to external TPXO coefficients"))
            ds.phase_reconstruction = "interpolate complex real/imaginary components before deriving Ephase and ROMS current ellipse"
            ds.zero_phase_date_policy = "fixed configured tidal reference date; never inferred from simulation start"
            ds.tide_source_representation = "raw complex TPXO components" if raw_elevation else "derived TPXO amplitude/phase compatibility input"
            tide_period_var = ds.createVariable("tide_period", "f8", ("tide_period",), zlib=True, complevel=1)
            tide_period_var.units = "hours"
            tide_period_var[:] = tide_period
            zero_phase = ds.createVariable("zero_phase_date", "f8")
            zero_phase.long_name = "tidal reference date for zero phase"
            zero_phase.units = "days as %Y%m%d.%f"
            zero_phase.C_format = "%13.4f"
            zero_phase.FORTRAN_format = "(f13.4)"
            zero_phase.assignValue(zero_phase_date)

            outputs = {
                name: ds.createVariable(name, "f8", ("tide_period", "eta_rho", "xi_rho"), zlib=True, complevel=1)
                for name in var_names
            }
            if raw_elevation:
                outputs["tide_Eamp"] = ds.createVariable("tide_Eamp", "f8", ("tide_period", "eta_rho", "xi_rho"), zlib=True, complevel=1)
                outputs["tide_Ephase"] = ds.createVariable("tide_Ephase", "f8", ("tide_period", "eta_rho", "xi_rho"), zlib=True, complevel=1)
            raw_depth = _source_slice(src.variables["depth"], None, None) if raw_current and "depth" in src.variables else None
            raw_mask = _source_slice(src.variables["mask"], None, None) if raw_current and "mask" in src.variables else None
            depth_on_grid = interpolate_rectilinear_2d(lon, lat, raw_depth, grid.lon_rho, grid.lat_rho) if raw_depth is not None else None
            mask_on_grid = interpolate_rectilinear_2d(lon, lat, raw_mask, grid.lon_rho, grid.lat_rho) if raw_mask is not None else None
            if raw_current:
                for name in ("tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase"):
                    outputs[name] = ds.createVariable(name, "f8", ("tide_period", "eta_rho", "xi_rho"), zlib=True, complevel=1)
            for out_index, tide_index in enumerate(tide_axis):
                if raw_elevation:
                    e_re = interpolate_rectilinear_2d(
                        lon, lat, _source_slice(src.variables[raw_elevation_names["tide_ERe"]], tide_dim_name, tide_index), grid.lon_rho, grid.lat_rho
                    )
                    e_im = interpolate_rectilinear_2d(
                        lon, lat, _source_slice(src.variables[raw_elevation_names["tide_EIm"]], tide_dim_name, tide_index), grid.lon_rho, grid.lat_rho
                    )
                    e_complex = e_re + 1j * e_im
                    outputs["tide_Eamp"][out_index] = np.abs(e_complex)
                    outputs["tide_Ephase"][out_index] = np.mod(-np.degrees(np.angle(e_complex)), 360.0)
                for out_name, src_name in var_names.items():
                    data = _source_slice(src.variables[src_name], tide_dim_name, tide_index)
                    outputs[out_name][out_index] = interpolate_rectilinear_2d(lon, lat, data, grid.lon_rho, grid.lat_rho)
                if raw_current:
                    u_re = interpolate_rectilinear_2d(lon, lat, _source_slice(src.variables[raw_current_names["tide_URe"]], tide_dim_name, tide_index), grid.lon_rho, grid.lat_rho)
                    u_im = interpolate_rectilinear_2d(lon, lat, _source_slice(src.variables[raw_current_names["tide_UIm"]], tide_dim_name, tide_index), grid.lon_rho, grid.lat_rho)
                    v_re = interpolate_rectilinear_2d(lon, lat, _source_slice(src.variables[raw_current_names["tide_VRe"]], tide_dim_name, tide_index), grid.lon_rho, grid.lat_rho)
                    v_im = interpolate_rectilinear_2d(lon, lat, _source_slice(src.variables[raw_current_names["tide_VIm"]], tide_dim_name, tide_index), grid.lon_rho, grid.lat_rho)
                    if depth_on_grid is None or mask_on_grid is None:
                        raise SystemExit("cannot reconstruct ROMS current ellipse without staged depth and mask")
                    wet = (mask_on_grid > 0.5) & np.isfinite(depth_on_grid) & (depth_on_grid > 0.0)
                    divisor = np.maximum(depth_on_grid, float(getattr(src, "velocity_depth_min_m", 10.0)))
                    u = fill_nearest(np.where(wet, u_re / divisor, np.nan)) + 1j * fill_nearest(np.where(wet, u_im / divisor, np.nan))
                    v = fill_nearest(np.where(wet, v_re / divisor, np.nan)) + 1j * fill_nearest(np.where(wet, v_im / divisor, np.nan))
                    cmax, cmin, cangle, cphase = current_ellipse(u, v)
                    outputs["tide_Cmax"][out_index] = cmax
                    outputs["tide_Cmin"][out_index] = cmin
                    outputs["tide_Cangle"][out_index] = cangle
                    outputs["tide_Cphase"][out_index] = cphase
    print(f"grid={grid_path}")
    print(f"source={src_path}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
