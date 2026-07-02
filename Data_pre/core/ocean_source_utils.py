#!/usr/bin/env python3
"""Helpers for parallel HYCOM and GLORYS12V1 preprocessing paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from case_naming import roms_input_name, run_infile_name, staged_ocean_name
from case_context import get_case_config_path, get_case_root
from roms_preprocessing_utils import load_project_params

ROOT = get_case_root()

SUPPORTED_OCEAN_SOURCES = ("hycom", "glorys12v1")
DEFAULT_GLORYS_CONFIG = get_case_config_path("glorys12v1_download_config.json")
MJD_UNITS = "days since 1858-11-17 00:00:00"
MJD_CALENDAR = "gregorian"


@dataclass(frozen=True)
class OceanSourcePaths:
    ocean_source: str
    config_path: Path | None
    staged_initial: Path
    staged_boundary: Path
    staged_static: Path | None
    roms_ini: Path
    roms_bdy: Path
    pilot_1day_infile: Path
    pilot_month_infile: Path
    pilot_1day_log: Path
    pilot_month_log: Path
    pilot_1day_run_script: Path | None
    pilot_month_run_script: Path | None


def normalize_ocean_source(name: str | None) -> str:
    source = (name or "hycom").strip().lower()
    if source not in SUPPORTED_OCEAN_SOURCES:
        raise SystemExit(
            f"unsupported ocean source {name!r}; expected one of {', '.join(SUPPORTED_OCEAN_SOURCES)}"
        )
    return source


def load_glorys_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else DEFAULT_GLORYS_CONFIG
    if not config_path.is_absolute():
        config_candidate = get_case_config_path(str(config_path))
        config_path = config_candidate if config_candidate.exists() else (ROOT / config_path)
    return json.loads(config_path.read_text())


def ensure_abs_under_root(path_like: str | Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else ROOT / path


def monthly_or_annual_label(start: datetime, stop: datetime) -> str:
    if (
        start.month == 1
        and start.day == 1
        and stop.year == start.year + 1
        and stop.month == 1
        and stop.day <= 2
    ):
        return f"{start.year:04d}"
    return start.strftime("%Y%m")


def glorys_center_time(config: dict, when: datetime | None = None) -> datetime:
    base = when or datetime.fromisoformat(config["time_start"])
    hh, mm, ss = [int(item) for item in str(config["time_mean_center"]).split(":")]
    return datetime(base.year, base.month, base.day, hh, mm, ss)


def default_project_start_stop() -> tuple[datetime, datetime]:
    params = load_project_params()
    time_cfg = params["time"]
    return datetime.fromisoformat(time_cfg["start"]), datetime.fromisoformat(time_cfg["stop"])


def build_glorys_paths(
    config: dict,
    start: datetime | None = None,
    stop: datetime | None = None,
) -> OceanSourcePaths:
    project_start, project_stop = default_project_start_stop()
    start_dt = start or project_start
    stop_dt = stop or project_stop
    raw_dir = ensure_abs_under_root(config["output_raw_dir"])
    input_dir = ensure_abs_under_root(config["output_input_dir"])
    label = monthly_or_annual_label(start_dt, stop_dt)
    initial_dt = glorys_center_time(config, start_dt)
    source = normalize_ocean_source(config.get("source_name", "glorys12v1"))
    return OceanSourcePaths(
        ocean_source=source,
        config_path=DEFAULT_GLORYS_CONFIG,
        staged_initial=raw_dir / staged_ocean_name(source, "initial"),
        staged_boundary=raw_dir / staged_ocean_name(source, "boundary"),
        staged_static=raw_dir / staged_ocean_name(source, "static"),
        roms_ini=input_dir / roms_input_name("ini", source),
        roms_bdy=input_dir / roms_input_name("bdy", source),
        pilot_1day_infile=ROOT / "run" / run_infile_name("pilot_1day", source),
        pilot_month_infile=ROOT / "run" / run_infile_name("pilot", source),
        pilot_1day_log=ROOT / "output" / f"pilot_1day_{source}_run.log",
        pilot_month_log=ROOT / "output" / f"pilot_{source}_run.log",
        pilot_1day_run_script=ROOT / "run" / f"run_pilot_1day_{source}.sh",
        pilot_month_run_script=ROOT / "run" / f"run_pilot_{source}.sh",
    )


def build_ocean_source_paths(
    ocean_source: str,
    *,
    config: dict | None = None,
    start: datetime | None = None,
    stop: datetime | None = None,
) -> OceanSourcePaths:
    source = normalize_ocean_source(ocean_source)
    if source == "hycom":
        return OceanSourcePaths(
            ocean_source="hycom",
            config_path=get_case_config_path("staged_download_config.json"),
            staged_initial=ROOT / "data" / "raw" / "ocean" / staged_ocean_name("hycom", "initial"),
            staged_boundary=ROOT / "data" / "raw" / "ocean" / staged_ocean_name("hycom", "boundary"),
            staged_static=None,
            roms_ini=ROOT / "input" / roms_input_name("ini"),
            roms_bdy=ROOT / "input" / roms_input_name("bdy"),
            pilot_1day_infile=ROOT / "run" / run_infile_name("pilot_1day"),
            pilot_month_infile=ROOT / "run" / run_infile_name("pilot"),
            pilot_1day_log=ROOT / "output" / "pilot_1day_run.log",
            pilot_month_log=ROOT / "output" / "pilot_run.log",
            pilot_1day_run_script=ROOT / "run" / "run_pilot_1day.sh",
            pilot_month_run_script=ROOT / "run" / "run_pilot.sh",
        )
    return build_glorys_paths(config or load_glorys_config(), start=start, stop=stop)
