#!/usr/bin/env python3
"""Case-driven naming helpers for multi-region ROMS preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from case_context import get_case_root
from roms_preprocessing_utils import load_project_params


@dataclass(frozen=True)
class CaseNaming:
    case_name: str
    slug: str
    title: str
    cpp_name: str
    description: str
    global_bathymetry: Path
    grid_subset_name: str
    roms_prefix: str
    source_csv_name: str
    source_timeseries_name: str


def _default_cpp_name(slug: str) -> str:
    return slug.upper().replace("-", "_")


def load_case_naming() -> CaseNaming:
    params = load_project_params()
    case_cfg = params.get("case", {})
    project_cfg = params.get("project", {})
    naming_cfg = params.get("naming", {})
    paths_cfg = params.get("paths", {})

    case_name = case_cfg.get("name") or project_cfg.get("name") or get_case_root().name
    slug = case_cfg.get("slug") or naming_cfg.get("roms_prefix") or case_name
    return CaseNaming(
        case_name=case_name,
        slug=slug,
        title=case_cfg.get("title") or project_cfg.get("description") or case_name,
        cpp_name=case_cfg.get("cpp_name") or _default_cpp_name(slug),
        description=case_cfg.get("description") or project_cfg.get("description") or case_name,
        global_bathymetry=Path(paths_cfg.get("global_bathymetry", "/workspace/GEBCO/GEBCO_2026.nc")),
        grid_subset_name=naming_cfg.get("grid_subset_name", f"gebco_{slug}.nc"),
        roms_prefix=naming_cfg.get("roms_prefix", slug),
        source_csv_name=naming_cfg.get("source_csv_name", f"{slug}_source_discharge.csv"),
        source_timeseries_name=naming_cfg.get("source_timeseries_name", f"{slug}_source_hourly.csv"),
    )


def case_time_labels() -> tuple[str, str]:
    params = load_project_params()
    start = datetime.fromisoformat(params["time"]["start"])
    stop = datetime.fromisoformat(params["time"]["stop"])
    start_label = start.strftime("%Y%m%d")
    if (
        start.month == 1
        and start.day == 1
        and stop.year == start.year + 1
        and stop.month == 1
        and stop.day <= 2
    ):
        window_label = f"{start.year:04d}"
    else:
        window_label = start.strftime("%Y%m")
    return start_label, window_label


def bathymetry_subset_path() -> Path:
    naming = load_case_naming()
    return get_case_root() / "data" / "raw" / "bathymetry" / naming.grid_subset_name


def case_start_datetime() -> datetime:
    params = load_project_params()
    return datetime.fromisoformat(params["time"]["start"])


def _profile_suffix(profile: str | None = None) -> str:
    return f"_{profile}" if profile else ""


def run_infile_name(mode: str, ocean_source: str | None = None, profile: str | None = None) -> str:
    naming = load_case_naming()
    suffix = _profile_suffix(profile)
    if ocean_source and ocean_source != "hycom":
        suffix = f"{suffix}_{ocean_source}"
    return f"ocean_{naming.roms_prefix}_{mode}{suffix}.in"


def output_product_name(kind: str, mode: str, ocean_source: str | None = None, profile: str | None = None) -> str:
    naming = load_case_naming()
    suffix = _profile_suffix(profile)
    if ocean_source and ocean_source != "hycom":
        suffix = f"{suffix}_{ocean_source}"
    return f"{kind}_{naming.roms_prefix}_{mode}{suffix}.nc"


def staged_ocean_name(source: str, role: str) -> str:
    naming = load_case_naming()
    start_label, window_label = case_time_labels()
    if role == "initial":
        return f"{source}_initial_{start_label}.nc"
    if role == "boundary":
        return f"{source}_boundary_{window_label}.nc"
    if role == "static":
        return f"{source}_static_{naming.slug}.nc"
    raise ValueError(f"unsupported ocean staged role: {role}")


def staged_atmosphere_name(kind: str) -> str:
    naming = load_case_naming()
    _, window_label = case_time_labels()
    if kind == "atm":
        return f"era5_atm_{naming.roms_prefix}_{window_label}.nc"
    if kind == "rad":
        return f"era5_rad_{naming.roms_prefix}_{window_label}.nc"
    raise ValueError(f"unsupported atmosphere staged kind: {kind}")


def staged_tides_name() -> str:
    naming = load_case_naming()
    _, window_label = case_time_labels()
    return f"tpxo9_{naming.roms_prefix}_{window_label}.nc"


def staged_source_csv_name() -> str:
    return load_case_naming().source_csv_name


def roms_input_name(role: str, ocean_source: str | None = None, profile: str | None = None) -> str:
    naming = load_case_naming()
    start_label, window_label = case_time_labels()
    source_suffix = f"_{ocean_source}" if ocean_source and ocean_source != "hycom" else ""
    profile_suffix = _profile_suffix(profile)
    if role == "ini":
        return f"roms_ini_{naming.roms_prefix}{source_suffix}_{start_label}{profile_suffix}.nc"
    if role == "bdy":
        return f"roms_bdy_{naming.roms_prefix}{source_suffix}_{window_label}{profile_suffix}.nc"
    if role == "atm":
        return f"roms_atm_{naming.roms_prefix}_{window_label}.nc"
    if role == "rad":
        return f"roms_rad_{naming.roms_prefix}_{window_label}.nc"
    if role == "tides":
        return f"roms_tides_{naming.roms_prefix}_{window_label}{profile_suffix}.nc"
    raise ValueError(f"unsupported ROMS input role: {role}")
