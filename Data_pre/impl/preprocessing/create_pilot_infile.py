#!/usr/bin/env python3
"""Create case-driven ROMS input files for smoke, 1-day, and pilot modes."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

from case_naming import load_case_naming, output_product_name, roms_input_name, run_infile_name
from ocean_source_utils import build_ocean_source_paths, glorys_center_time, load_glorys_config, normalize_ocean_source
from radioactive_decay import radioactive_decay_config
from roms_preprocessing_utils import ROOT, load_project_params, resolve_grid_path


RUN_DIR = ROOT / "run"
PILOT_MONTH_OUT = RUN_DIR / run_infile_name("pilot")
PILOT_1DAY_OUT = RUN_DIR / run_infile_name("pilot_1day")
SMOKE_OUT = RUN_DIR / run_infile_name("smoke")
AUDIT_JSON_CANDIDATES = [
    ROOT / "output" / "bathymetry_stability_audit.json",
    ROOT / "output" / "smoothed_grid_stability_audit.json",
    ROOT / "output" / "raw_grid_stability_audit.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--ocean-source", default="hycom")
    parser.add_argument("--profile", default=None, help="Optional profile suffix such as online_my25_uvtide")
    parser.add_argument("--config", default=None)
    parser.add_argument("--pilot", choices=["1day", "month", "month_or_year"], default=None)
    parser.add_argument(
        "--mode",
        choices=[
            "smoke",
            "pilot_1day",
            "pilot_month",
            "online_6h",
            "online_3d",
            "online_7d",
            "online_month",
            "online_spinup_3mo",
            "both",
            "pilot",
        ],
        default="both",
    )
    parser.add_argument("--forcing-mode", choices=["analytical", "external"], default="analytical")
    parser.add_argument("--ini-path", default=None)
    parser.add_argument("--bry-path", default=None)
    parser.add_argument("--clm-path", default=None)
    parser.add_argument("--river-path", default=None)
    parser.add_argument("--tides-path", default=None)
    parser.add_argument("--atm-path", default=None)
    parser.add_argument("--rad-path", default=None)
    parser.add_argument("--dt-seconds", type=float, default=None)
    parser.add_argument("--template", default=None, help="Override ROMS .in template path")
    parser.add_argument("--dry-run", "--dry-equivalent", action="store_true", help="Resolve and print planned output without writing files")
    return parser.parse_args()


def grid_metrics(grid_path: Path) -> tuple[int, int]:
    with Dataset(grid_path) as grid:
        xi_rho = len(grid.dimensions["xi_rho"])
        eta_rho = len(grid.dimensions["eta_rho"])
    return xi_rho - 2, eta_rho - 2


def open_boundary_flags(grid_path: Path | None) -> dict[str, bool] | None:
    if not grid_path or not grid_path.exists():
        return None
    with Dataset(grid_path) as grid:
        mask = np.asarray(grid.variables["mask_rho"][:, :], dtype=int)
    return {
        "west": bool(mask[:, 0].any()),
        "south": bool(mask[0, :].any()),
        "east": bool(mask[:, -1].any()),
        "north": bool(mask[-1, :].any()),
    }


def boundary_values(open_edges: dict[str, bool] | None, open_value: str) -> str:
    if open_edges is None:
        return f"{open_value:<7} {open_value:<7} {open_value:<7} {open_value:<7}"
    return " ".join(("Clo" if not open_edges[edge] else open_value).ljust(7) for edge in ("west", "south", "east", "north"))


def relative_to_run(path: Path, run_dir: Path = RUN_DIR) -> str:
    return os.path.relpath(path, run_dir).replace(os.sep, "/")


def run_visible_path(path: Path) -> str:
    path = path.expanduser()
    if not path.is_absolute():
        return str(path).replace(os.sep, "/")
    try:
        return relative_to_run(path)
    except ValueError:
        return str(path)


def varinfo_path(params: dict) -> str:
    candidates: list[Path] = []
    configured = params.get("paths", {}).get("varinfo_yaml")
    if configured:
        candidates.append(Path(str(configured)).expanduser())
    candidates.append(RUN_DIR / "varinfo.yaml")
    roms_src = params.get("paths", {}).get("roms_src")
    if roms_src:
        candidates.append(Path(str(roms_src)).expanduser() / "ROMS" / "External" / "varinfo.yaml")

    for candidate in candidates:
        path = candidate if candidate.is_absolute() else ROOT / candidate
        if path.exists():
            return run_visible_path(path.resolve())
    return "varinfo.yaml"


def tile_layout(params: dict) -> tuple[int, int]:
    run_cfg = params.get("run", {})
    tiles_cfg = run_cfg.get("tiles", {}) if isinstance(run_cfg.get("tiles"), dict) else {}
    ntile_i = run_cfg.get("ntile_i", tiles_cfg.get("ntile_i", 2))
    ntile_j = run_cfg.get("ntile_j", tiles_cfg.get("ntile_j", 2))

    try:
        ntile_i = int(ntile_i)
        ntile_j = int(ntile_j)
    except (TypeError, ValueError) as exc:
        raise SystemExit("run.ntile_i and run.ntile_j must be positive integers") from exc
    if ntile_i <= 0 or ntile_j <= 0:
        raise SystemExit("run.ntile_i and run.ntile_j must be positive integers")
    return ntile_i, ntile_j


def all_tracer_flags(params: dict, value: str) -> str:
    tracer_count = int(params.get("source", {}).get("tracer_count", 0))
    return " ".join([value] * (2 + max(0, tracer_count)))


def source_tracer_flags(params: dict) -> str:
    tracer_count = int(params.get("source", {}).get("tracer_count", 0))
    return " ".join(["F", "F", *(["T"] * max(0, tracer_count))])


def fortran_float(value: float, *, precision: int = 1) -> str:
    mantissa, exponent = f"{float(value):.{precision}e}".split("e")
    return f"{mantissa}d{int(exponent):+03d}"


def replace_line(text: str, key: str, value: str) -> str:
    return re.sub(rf"^(\s*{re.escape(key)}\s*(?:==|=)).*$", rf"\1 {value}", text, flags=re.MULTILINE)


def replace_block(text: str, start_key: str, replacement: str, next_marker: str) -> str:
    pattern = rf"(^\s*{re.escape(start_key)}\s*==.*?)(?=^\s*{re.escape(next_marker)}\s*==)"
    return re.sub(pattern, replacement.rstrip() + "\n\n", text, flags=re.MULTILINE | re.DOTALL)


def replace_nffiles_block(text: str, nfiles: int, file_lines: list[str]) -> str:
    text = replace_line(text, "NFFILES", str(nfiles))
    pattern = r"(^\s*FRCNAME\s*==.*?)(?=^\s*DAINAME\s*==)"
    replacement = "\n".join(file_lines).rstrip() + "\n\n"
    return re.sub(pattern, replacement, text, flags=re.MULTILINE | re.DOTALL)


def pick_stable_dt(default_dt: float) -> float:
    for audit_json in AUDIT_JSON_CANDIDATES:
        if not audit_json.exists():
            continue
        try:
            report = json.loads(audit_json.read_text())
            if report.get("largest_successful_dt_seconds"):
                return float(report["largest_successful_dt_seconds"])
        except Exception:  # noqa: BLE001
            continue
    return default_dt


def active_profile(args: argparse.Namespace, mode: str | None = None) -> str | None:
    if args.profile:
        return args.profile
    if mode and mode.startswith("online_"):
        return "online_my25_uvtide"
    return None


def forcing_paths(args: argparse.Namespace, forcing_mode: str, mode: str | None = None) -> dict[str, str]:
    profile = active_profile(args, mode)
    if forcing_mode == "analytical":
        return {
            "ini": "../input/roms_ini_pilot.nc",
            "bry": "../input/roms_bdy_pilot.nc",
            "clm": "../input/roms_clm_pilot.nc",
            "nud": "none",
            "river": "../input/roms_rivers_pilot.nc",
            "tides": "../input/roms_tides_pilot.nc",
            "frc_files": ["     FRCNAME == ../input/roms_frc_pilot.nc"],
            "nffiles": 1,
            "nclmfiles": 1,
        }
    ocean_source = normalize_ocean_source(args.ocean_source)
    if ocean_source == "glorys12v1":
        source_paths = build_ocean_source_paths(
            ocean_source,
            config=load_glorys_config(args.config),
            profile=profile,
        )
    else:
        source_paths = build_ocean_source_paths(ocean_source)
    atm_default = f"../input/{roms_input_name('atm')}"
    rad_default = f"../input/{roms_input_name('rad')}"
    river_default = "../input/roms_rivers_production.nc"
    if profile:
        river_default = f"../input/roms_rivers_production_{profile}.nc"
    ini_default = f"../input/{roms_input_name('ini', ocean_source=ocean_source, profile=profile)}"
    bry_default = f"../input/{roms_input_name('bdy', ocean_source=ocean_source, profile=profile)}"
    if ocean_source == "glorys12v1":
        ini_default = relative_to_run(source_paths.roms_ini)
        bry_default = relative_to_run(source_paths.roms_bdy)
    return {
        "ini": args.ini_path or ini_default,
        "bry": args.bry_path or bry_default,
        "clm": args.clm_path or args.ini_path or relative_to_run(source_paths.roms_ini),
        "nud": "none",
        "river": args.river_path or river_default,
        "tides": args.tides_path or f"../input/{roms_input_name('tides', profile=profile)}",
        "frc_files": [
            f"     FRCNAME == {args.atm_path or atm_default} \\",
            f"                {args.rad_path or rad_default}",
        ],
        "nffiles": 2,
        "nclmfiles": 1,
    }


def external_model_start(params: dict, forcing_mode: str, forcing_ini: str | None) -> datetime:
    configured = datetime.fromisoformat(params["time"]["start"])
    if forcing_mode != "external" or not forcing_ini:
        return configured
    ini_path = (RUN_DIR / forcing_ini).resolve()
    if not ini_path.exists():
        return configured
    try:
        with Dataset(ini_path) as ds:
            if "ocean_time" not in ds.variables:
                return configured
            time_var = ds.variables["ocean_time"]
            units = getattr(time_var, "units", None)
            if not units:
                return configured
            calendar = getattr(time_var, "calendar", "standard")
            values = time_var[:]
            if values.size == 0:
                return configured
            parsed = num2date(values, units=units, calendar=calendar)
            value = parsed[0]
            return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)
    except Exception:  # noqa: BLE001
        return configured


def external_model_start_value(forcing_mode: str, forcing_ini: str | None) -> float | None:
    if forcing_mode != "external" or not forcing_ini:
        return None
    ini_path = (RUN_DIR / forcing_ini).resolve()
    if not ini_path.exists():
        return None
    try:
        with Dataset(ini_path) as ds:
            if "ocean_time" not in ds.variables:
                return None
            values = ds.variables["ocean_time"][:]
            if values.size == 0:
                return None
            return float(values[0])
    except Exception:  # noqa: BLE001
        return None


def external_model_stop(params: dict, forcing_mode: str, forcing_bry: str | None) -> datetime:
    configured = datetime.fromisoformat(params["time"]["stop"])
    if forcing_mode != "external" or not forcing_bry:
        return configured
    bry_path = (RUN_DIR / forcing_bry).resolve()
    if not bry_path.exists():
        return configured
    try:
        with Dataset(bry_path) as ds:
            if "zeta_time" not in ds.variables:
                return configured
            time_var = ds.variables["zeta_time"]
            units = getattr(time_var, "units", None)
            if not units:
                return configured
            calendar = getattr(time_var, "calendar", "standard")
            values = time_var[:]
            if values.size == 0:
                return configured
            parsed = num2date(values, units=units, calendar=calendar)
            value = parsed[-1]
            actual = datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)
            return min(configured, actual)
    except Exception:  # noqa: BLE001
        return configured


def common_year_offset_days(start: datetime) -> float:
    year_start = datetime(start.year, 1, 1)
    return (start - year_start).total_seconds() / 86400.0


def set_lbc(text: str, forcing_mode: str, open_edges: dict[str, bool] | None = None) -> str:
    if forcing_mode == "analytical":
        lbc = (
            "   LBC(isFsur) ==   Per     Clo     Per     Clo         ! free-surface\n"
            "   LBC(isUbar) ==   Per     Clo     Per     Clo         ! 2D U-momentum\n"
            "   LBC(isVbar) ==   Per     Clo     Per     Clo         ! 2D V-momentum\n"
            "   LBC(isUvel) ==   Per     Clo     Per     Clo         ! 3D U-momentum\n"
            "   LBC(isVvel) ==   Per     Clo     Per     Clo         ! 3D V-momentum\n"
            "   LBC(isMtke) ==   Per     Clo     Per     Clo         ! mixing TKE\n\n"
            "   LBC(isTvar) ==   Per     Clo     Per     Clo \\       ! temperature\n"
            "                    Per     Clo     Per     Clo \\       ! salinity\n"
            "                    Per     Clo     Per     Clo         ! dye_01"
        )
        ad_lbc = (
            "ad_LBC(isFsur) ==   Per     Clo     Per     Clo         ! free-surface\n"
            "ad_LBC(isUbar) ==   Per     Clo     Per     Clo         ! 2D U-momentum\n"
            "ad_LBC(isVbar) ==   Per     Clo     Per     Clo         ! 2D V-momentum\n"
            "ad_LBC(isUvel) ==   Per     Clo     Per     Clo         ! 3D U-momentum\n"
            "ad_LBC(isVvel) ==   Per     Clo     Per     Clo         ! 3D V-momentum\n"
            "ad_LBC(isMtke) ==   Per     Clo     Per     Clo         ! mixing TKE\n\n"
            "ad_LBC(isTvar) ==   Per     Clo     Per     Clo \\       ! temperature\n"
            "                    Per     Clo     Per     Clo \\       ! salinity\n"
            "                    Per     Clo     Per     Clo         ! dye_01"
        )
        text = replace_block(text, "LBC(isFsur)", lbc, "LBC(isU2Sd)")
        text = replace_block(text, "ad_LBC(isFsur)", ad_lbc, "VolCons(west)")
        text = replace_line(text, "VolCons(west)", "F")
        text = replace_line(text, "VolCons(east)", "F")
        text = replace_line(text, "VolCons(south)", "F")
        text = replace_line(text, "VolCons(north)", "F")
        text = replace_line(text, "ad_VolCons(west)", "F")
        text = replace_line(text, "ad_VolCons(east)", "F")
        text = replace_line(text, "ad_VolCons(south)", "F")
        text = replace_line(text, "ad_VolCons(north)", "F")
        return text

    fsur_lbc = boundary_values(open_edges, "Cha")
    m2_lbc = boundary_values(open_edges, "Fla")
    m3_lbc = boundary_values(open_edges, "RadNud")
    lbc = (
        f"   LBC(isFsur) ==   {fsur_lbc}        ! free-surface\n"
        f"   LBC(isUbar) ==   {m2_lbc}        ! 2D U-momentum\n"
        f"   LBC(isVbar) ==   {m2_lbc}        ! 2D V-momentum\n"
        f"   LBC(isUvel) ==   {m3_lbc}     ! 3D U-momentum\n"
        f"   LBC(isVvel) ==   {m3_lbc}     ! 3D V-momentum\n"
        "   LBC(isMtke) ==   Clo     Clo     Clo     Clo         ! mixing TKE\n\n"
        f"   LBC(isTvar) ==   {m3_lbc} \\    ! temperature\n"
        f"                    {m3_lbc} \\    ! salinity\n"
        f"                    {m3_lbc}      ! dye_01"
    )
    ad_lbc = (
        f"ad_LBC(isFsur) ==   {fsur_lbc}        ! free-surface\n"
        f"ad_LBC(isUbar) ==   {m2_lbc}        ! 2D U-momentum\n"
        f"ad_LBC(isVbar) ==   {m2_lbc}        ! 2D V-momentum\n"
        f"ad_LBC(isUvel) ==   {m3_lbc}     ! 3D U-momentum\n"
        f"ad_LBC(isVvel) ==   {m3_lbc}     ! 3D V-momentum\n"
        "ad_LBC(isMtke) ==   Clo     Clo     Clo     Clo         ! mixing TKE\n\n"
        f"ad_LBC(isTvar) ==   {m3_lbc} \\    ! temperature\n"
        f"                    {m3_lbc} \\    ! salinity\n"
        f"                    {m3_lbc}      ! dye_01"
    )
    text = replace_block(text, "LBC(isFsur)", lbc, "LBC(isU2Sd)")
    text = replace_block(text, "ad_LBC(isFsur)", ad_lbc, "VolCons(west)")
    text = replace_line(text, "VolCons(west)", "F")
    text = replace_line(text, "VolCons(east)", "F")
    text = replace_line(text, "VolCons(south)", "F")
    text = replace_line(text, "VolCons(north)", "F")
    text = replace_line(text, "ad_VolCons(west)", "F")
    text = replace_line(text, "ad_VolCons(east)", "F")
    text = replace_line(text, "ad_VolCons(south)", "F")
    text = replace_line(text, "ad_VolCons(north)", "F")
    return text


def glorys_source_paths_for_args(args: argparse.Namespace):
    if normalize_ocean_source(args.ocean_source) != "glorys12v1":
        return None
    return build_ocean_source_paths(
        "glorys12v1",
        config=load_glorys_config(args.config),
    )


def base_text(
    args: argparse.Namespace,
    params: dict,
    template_path: Path,
    grid_name: str,
    lm: int | None,
    mm: int | None,
    dt_seconds: float,
    mode: str,
    forcing_mode: str,
    open_edges: dict[str, bool] | None,
) -> str:
    vertical = params["vertical"]
    time_cfg = params["time"]
    physics_cfg = params.get("physics", {})
    output_cfg = params.get("output", {})
    source_cfg = params.get("source", {})
    naming = load_case_naming()
    ocean_source = normalize_ocean_source(args.ocean_source)
    glorys_paths = glorys_source_paths_for_args(args)
    profile = active_profile(args, mode)
    forcing = forcing_paths(args, forcing_mode, mode)
    ntile_i, ntile_j = tile_layout(params)
    start = external_model_start(params, forcing_mode, forcing["ini"])
    if forcing_mode == "external" and ocean_source == "glorys12v1":
        ini_path = (RUN_DIR / forcing["ini"]).resolve()
        if not ini_path.exists():
            start = glorys_center_time(load_glorys_config(args.config), start)
    boundary_stop = external_model_stop(params, forcing_mode, forcing["bry"])
    source_label = f" ({ocean_source})" if forcing_mode == "external" and ocean_source != "hycom" else ""
    if mode == "pilot_1day":
        stop = min(start + timedelta(days=1), boundary_stop)
        title = f"{naming.title} 1-day pilot{source_label}"
        out_prefix = "pilot_1day"
    elif mode == "online_6h":
        stop = min(start + timedelta(hours=6), boundary_stop)
        title = f"{naming.title} online MY25/UV tide 6-hour check{source_label}"
        out_prefix = "online_6h"
    elif mode == "online_3d":
        stop = min(start + timedelta(days=3), boundary_stop)
        title = f"{naming.title} online MY25/UV tide 3-day check{source_label}"
        out_prefix = "online_3d"
    elif mode == "online_7d":
        stop = min(start + timedelta(days=7), boundary_stop)
        title = f"{naming.title} online MY25/UV tide 7-day check{source_label}"
        out_prefix = "online_7d"
    elif mode == "online_month":
        stop = boundary_stop
        title = f"{naming.title} online MY25/UV tide month{source_label}"
        out_prefix = "online_month"
    elif mode == "online_spinup_3mo":
        stop = boundary_stop
        title = f"{naming.title} online MY25/UV tide 3-month spin-up{source_label}"
        out_prefix = "online_spinup_3mo"
    elif mode == "pilot_month":
        stop = boundary_stop
        title = f"{naming.title} pilot{source_label}"
        out_prefix = "pilot"
    else:
        stop = start + timedelta(seconds=dt_seconds * 5)
        title = f"{naming.title} smoke run"
        out_prefix = "smoke"

    seconds = int((stop - start).total_seconds())
    ntimes = max(1, int(round(seconds / dt_seconds)))
    if mode.startswith("online_"):
        nhis = max(1, int(round(float(output_cfg.get("history_interval_hours", 1)) * 3600 / dt_seconds)))
        navg = max(1, int(round(float(output_cfg.get("average_interval_hours", 1)) * 3600 / dt_seconds)))
        ndia = max(1, int(round(float(output_cfg.get("diagnostic_interval_hours", 1)) * 3600 / dt_seconds)))
    else:
        nhis = max(1, int(round(time_cfg["output_interval_hours"] * 3600 / dt_seconds))) if mode != "smoke" else 5
        navg = 0 if mode in {"smoke", "pilot_1day"} else nhis
        ndia = 0 if mode in {"smoke", "pilot_1day"} else nhis
    nrst = nhis if mode == "smoke" else max(1, int(round(24 * 3600 / dt_seconds)))
    text = template_path.read_text()
    profile_note = f" {profile}" if profile else ""
    text = f"! Draft {naming.slug} {mode}{profile_note} input derived from roms_upwelling.in.\n" + text
    text = replace_line(text, "TITLE", title)
    app_cpp = f"{naming.cpp_name}_{profile.upper()}" if profile else naming.cpp_name
    text = replace_line(text, "MyAppCPP", app_cpp)
    decay_cfg = radioactive_decay_config(params, profile)
    decay_note = (
        f"! passive_tracer.name = {decay_cfg['tracer_name']}\n"
        f"! passive_tracer.unit = {decay_cfg['tracer_unit']}\n"
        f"! passive_tracer.species = {decay_cfg['species']}\n"
        f"! radioactive_decay_enabled = {str(bool(decay_cfg['enabled'])).lower()}\n"
        f"! radioactive_decay_half_life_years = {float(decay_cfg['half_life_years']):.12g}\n"
        f"! radioactive_decay_lambda_s = {float(decay_cfg['lambda_s']):.15e}\n"
        f"! radioactive_decay_lambda_source = {decay_cfg['lambda_source']}\n"
        f"! radioactive_decay_target = {decay_cfg['target_tracer']}\n"
        f"! radioactive_decay_apply_to_temp_salt = {str(bool(decay_cfg['apply_to_temp_salt'])).lower()}\n"
        f"! radioactive_decay_year_days = {float(decay_cfg['days_per_year']):.6g}\n"
    )
    text = text.replace("! Input variable information file name.", decay_note + "\n! Input variable information file name.", 1)
    lm_value = str(lm) if lm is not None else "UNRESOLVED"
    mm_value = str(mm) if mm is not None else "UNRESOLVED"
    text = replace_line(text, "Lm", f"{lm_value}            ! pilot interior XI points")
    text = replace_line(text, "Mm", f"{mm_value}            ! pilot interior ETA points")
    text = replace_line(text, "N", f"{int(vertical['N'])}             ! vertical levels")
    tracer_count = int(source_cfg.get("tracer_count", source_cfg.get("roms_NPT", 1)))
    text = replace_line(text, "NPT", f"{tracer_count}             ! inert passive tracer count")
    text = replace_line(text, "Vtransform", str(int(vertical["Vtransform"])))
    text = replace_line(text, "Vstretching", str(int(vertical["Vstretching"])))
    text = replace_line(text, "THETA_S", f"{float(vertical['theta_s']):.1f}d0")
    text = replace_line(text, "THETA_B", f"{float(vertical['theta_b']):.1f}d0")
    text = replace_line(text, "TCLINE", f"{float(vertical['Tcline_m']):.1f}d0")
    text = replace_line(text, "NTIMES", str(ntimes))
    text = replace_line(text, "DT", f"{dt_seconds:.1f}d0")
    text = replace_line(text, "NDTFAST", str(int(time_cfg["pilot_ndtfast"])))
    if forcing_mode == "external":
        dstart_value = external_model_start_value(forcing_mode, forcing["ini"])
        text = replace_line(
            text,
            "DSTART",
            f"{dstart_value:.10f}d0" if dstart_value is not None else f"{common_year_offset_days(start):.10f}d0",
        )
        text = replace_line(text, "TIME_REF", "18581117.0d0")
    else:
        text = replace_line(text, "DSTART", f"{common_year_offset_days(start):.10f}d0")
        text = replace_line(text, "TIME_REF", "0.0d0")
    text = replace_line(text, "NTIMES_ANA", str(ntimes))
    text = replace_line(text, "NTIMES_FCT", str(ntimes))
    text = replace_line(text, "NRST", str(nrst))
    text = replace_line(text, "NINFO", "1" if mode == "smoke" else str(nhis))
    text = replace_line(text, "NHIS", str(nhis))
    text = replace_line(text, "NXTR", "0" if mode in {"smoke", "pilot_1day"} else str(nhis))
    text = replace_line(text, "NAVG", str(navg))
    text = replace_line(text, "NDIA", str(ndia))
    text = replace_line(text, "NTLM", str(nhis if mode != "smoke" else 5))
    text = replace_line(text, "NADJ", str(nhis if mode != "smoke" else 5))
    text = replace_line(text, "NSFF", str(nhis if mode != "smoke" else 5))
    text = replace_line(text, "NOBC", str(nhis if mode != "smoke" else 5))
    text = replace_line(text, "NtileI", str(ntile_i))
    text = replace_line(text, "NtileJ", str(ntile_j))

    text = replace_block(
        text,
        "Hadvection",
        "   Hadvection == U3       \\                     ! temperature\n"
        "                 HSIMT    \\                     ! salinity\n"
        "                 HSIMT                          ! dye_01 inert tracer",
        "Vadvection",
    )
    text = replace_block(
        text,
        "Vadvection",
        "   Vadvection == C4       \\                     ! temperature\n"
        "                 HSIMT    \\                     ! salinity\n"
        "                 HSIMT                          ! dye_01 inert tracer",
        "ad_Hadvection",
    )
    text = replace_block(
        text,
        "ad_Hadvection",
        "ad_Hadvection == U3       \\                     ! temperature\n"
        "                 U3       \\                     ! salinity\n"
        "                 U3                             ! dye_01 inert tracer",
        "ad_Vadvection",
    )
    text = replace_block(
        text,
        "ad_Vadvection",
        "ad_Vadvection == C4       \\                     ! temperature\n"
        "                 C4       \\                     ! salinity\n"
        "                 C4                             ! dye_01 inert tracer",
        "LBC(isFsur)",
    )
    tracer_slots = 2 + max(0, tracer_count)
    tracer_values = " ".join([f"{float(physics_cfg.get('tnu2_m2_s', 10.0)):.1f}d0"] * tracer_slots)
    zero_tracer_values = " ".join(["0.0d0"] * tracer_slots)
    akt_bak = " ".join([fortran_float(float(physics_cfg.get("akt_bak_m2_s", 1.0e-6)))] * tracer_slots)
    text = replace_line(text, "TNU2", f"{tracer_values}              ! temp, salt, dye m2/s")
    text = replace_line(text, "TNU4", f"{zero_tracer_values}              ! temp, salt, dye m4/s")
    text = replace_line(text, "ad_TNU2", f"{tracer_values}              ! temp, salt, dye m2/s")
    text = replace_line(text, "ad_TNU4", f"{zero_tracer_values}              ! temp, salt, dye m4/s")
    text = replace_line(text, "VISC2", f"{float(physics_cfg.get('visc2_m2_s', 10.0)):.1f}d0                          ! m2/s")
    text = replace_line(text, "AKT_BAK", f"{akt_bak}                   ! m2/s")
    text = replace_line(text, "AKV_BAK", f"{fortran_float(float(physics_cfg.get('akv_bak_m2_s', 1.0e-5)))}                          ! m2/s")
    avg_tracer_flags = all_tracer_flags(params, "F")
    text = replace_line(text, "Aout(idTTav)", f"{avg_tracer_flags}     ! disable quadratic tracer averages")
    text = replace_line(text, "Aout(idUTav)", f"{avg_tracer_flags}     ! disable quadratic u-tracer averages")
    text = replace_line(text, "Aout(idVTav)", f"{avg_tracer_flags}     ! disable quadratic v-tracer averages")
    text = replace_line(text, "Aout(iHUTav)", f"{avg_tracer_flags}     ! disable tracer u-volume flux averages")
    text = replace_line(text, "Aout(iHVTav)", f"{avg_tracer_flags}     ! disable tracer v-volume flux averages")
    text = replace_line(text, "LuvSrc", "F                            ! no horizontal momentum source in pilot")
    text = replace_line(text, "LwSrc", "T                             ! enable vertical point/source transport")
    text = replace_line(text, "LtracerSrc", f"{source_tracer_flags(params)}                        ! active tracers and inert dyes")
    text = replace_line(text, "LtracerCLM", f"{all_tracer_flags(params, 'F')}                        ! active tracers and inert dyes")
    text = replace_line(text, "LnudgeTCLM", f"{all_tracer_flags(params, 'F')}                        ! active tracers and inert dyes")
    for key in ("Hout(idVvis)", "Hout(idTdif)", "Hout(idSdif)", "Aout(idVvis)", "Aout(idTdif)", "Aout(idSdif)"):
        text = replace_line(text, key, "T")
    text = replace_line(text, "VARNAME", varinfo_path(params))
    text = replace_line(text, "GRDNAME", grid_name)

    text = replace_line(text, "ININAME", forcing["ini"])
    text = replace_line(text, "BRYNAME", forcing["bry"])
    text = replace_line(text, "CLMNAME", forcing["clm"])
    text = replace_line(text, "NUDNAME", forcing["nud"])
    text = replace_line(text, "SSFNAME", forcing["river"])
    text = replace_line(text, "TIDENAME", forcing["tides"])
    text = replace_line(text, "NBCFILES", "1")
    text = replace_line(text, "NCLMFILES", str(forcing["nclmfiles"]))
    text = replace_nffiles_block(text, forcing["nffiles"], forcing["frc_files"])
    text = set_lbc(text, forcing_mode, open_edges)

    if forcing_mode == "external":
        text = replace_line(text, "LsshCLM", "F                          ! sea-surface height")
        text = replace_line(text, "Lm2CLM", "F                          ! 2D momentum")
        text = replace_line(text, "Lm3CLM", "F                          ! 3D momentum")
        text = replace_line(text, "TNUDG", "1.0d0 1.0d0 1.0d0          ! days")
        text = replace_line(text, "ZNUDG", "0.5d0                      ! days")
        text = replace_line(text, "M2NUDG", "0.5d0                      ! days")
        text = replace_line(text, "M3NUDG", "1.0d0                      ! days")
        text = replace_line(text, "OBCFAC", "10.0d0                     ! stronger inflow nudging")
    else:
        text = replace_line(text, "TNUDG", "3*0.0d0                    ! days")
        text = replace_line(text, "ZNUDG", "0.0d0                      ! days")
        text = replace_line(text, "M2NUDG", "0.0d0                      ! days")
        text = replace_line(text, "M3NUDG", "0.0d0                      ! days")
        text = replace_line(text, "OBCFAC", "0.0d0                      ! nondimensional")

    source_for_name = None if out_prefix == "smoke" else ocean_source
    text = replace_line(text, "RSTNAME", f"../output/{output_product_name('rst', out_prefix, source_for_name, profile)}")
    text = replace_line(text, "HISNAME", f"../output/{output_product_name('his', out_prefix, source_for_name, profile)}")
    text = replace_line(text, "AVGNAME", f"../output/{output_product_name('avg', out_prefix, source_for_name, profile)}")
    text = replace_line(text, "DIANAME", f"../output/{output_product_name('dia', out_prefix, source_for_name, profile)}")
    text = replace_line(text, "XTRNAME", f"../output/{output_product_name('xtr', 'pilot', source_for_name, profile)}")
    text = replace_line(text, "QCKNAME", f"../output/{output_product_name('qck', 'pilot', source_for_name, profile)}")
    return text


def output_path_for_mode(mode: str, ocean_source: str, args: argparse.Namespace) -> Path:
    profile = active_profile(args, mode)
    if mode.startswith("online_"):
        return RUN_DIR / run_infile_name(mode, None if ocean_source == "hycom" else ocean_source, profile)
    if mode == "smoke":
        return SMOKE_OUT
    if ocean_source == "glorys12v1":
        source_paths = build_ocean_source_paths(ocean_source, config=load_glorys_config(args.config))
        if mode == "pilot_1day":
            return source_paths.pilot_1day_infile
        return source_paths.pilot_month_infile
    if mode == "pilot_1day":
        return PILOT_1DAY_OUT
    return PILOT_MONTH_OUT


def write_mode(path: Path, text: str) -> None:
    path.write_text(text)
    print(f"wrote {path}")


def print_mode_plan(path: Path, text: str, grid_note: str | None = None) -> None:
    print(f"would write {path}")
    if grid_note:
        print(f"  grid_status: unresolved ({grid_note.splitlines()[0]})")
    for key in ("TITLE", "MyAppCPP", "Lm", "Mm", "N", "NtileI", "NtileJ", "NTIMES", "DT", "VARNAME", "GRDNAME", "ININAME", "BRYNAME", "TIDENAME", "SSFNAME"):
        match = re.search(rf"^\s*{re.escape(key)}\s*(?:==|=)\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if match:
            print(f"  {key}: {match.group(1).strip()}")


def resolve_template_path(args: argparse.Namespace, params: dict) -> Path:
    candidates: list[Path] = []
    if args.template:
        candidates.append(Path(args.template).expanduser())
    configured = params.get("paths", {}).get("roms_in_template")
    if configured:
        candidates.append(Path(str(configured)).expanduser())
    roms_src = params.get("paths", {}).get("roms_src")
    if roms_src:
        candidates.append(Path(str(roms_src)).expanduser() / "ROMS" / "External" / "roms_upwelling.in")
    candidates.append(ROOT / "run" / "roms_upwelling.in")

    for candidate in candidates:
        path = candidate if candidate.is_absolute() else ROOT / candidate
        if path.exists():
            return path.resolve()
    formatted = "\n".join(f"- {candidate}" for candidate in candidates)
    raise SystemExit(f"ROMS .in template not found; checked:\n{formatted}")


def main() -> None:
    args = parse_args()
    ocean_source = normalize_ocean_source(args.ocean_source)
    params = load_project_params()
    template_path = resolve_template_path(args, params)
    grid_note = None
    try:
        grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    except SystemExit as exc:
        if not args.dry_run:
            raise
        grid_note = str(exc)
        grid_path = Path(args.grid).expanduser().resolve() if args.grid else ROOT / "input" / "roms_grid_bathy_500m_smoothed.nc"
    grid_name = relative_to_run(grid_path)
    if grid_path.exists():
        lm, mm = grid_metrics(grid_path)
        open_edges = open_boundary_flags(grid_path)
    else:
        lm = None
        mm = None
        open_edges = None
    default_dt = float(params["time"]["pilot_dt_seconds"])
    if args.mode == "smoke":
        dt_seconds = args.dt_seconds or 10.0
    elif args.forcing_mode == "external":
        dt_seconds = args.dt_seconds or pick_stable_dt(10.0)
    else:
        dt_seconds = args.dt_seconds or default_dt

    mode = args.mode
    if args.pilot == "1day":
        mode = "pilot_1day"
    elif args.pilot in {"month", "month_or_year"}:
        mode = "pilot_month"

    if mode == "both":
        modes = ["pilot_month", "pilot_1day"] if args.forcing_mode == "external" else ["pilot_month", "smoke"]
    elif mode == "pilot":
        modes = ["pilot_month"]
    else:
        modes = [mode]

    for mode in modes:
        local_forcing_mode = "analytical" if mode == "smoke" and args.forcing_mode == "external" else args.forcing_mode
        text = base_text(args, params, template_path, grid_name, lm, mm, dt_seconds, mode, local_forcing_mode, open_edges)
        path = output_path_for_mode(mode, ocean_source, args)
        if args.dry_run:
            print_mode_plan(path, text, grid_note)
        else:
            write_mode(path, text)


if __name__ == "__main__":
    main()
