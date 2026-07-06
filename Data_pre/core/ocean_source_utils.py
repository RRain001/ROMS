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


def resolve_glorys_config_path(path: str | Path | None = None) -> Path:
    checked: list[Path] = []
    if path is None:
        checked.append(DEFAULT_GLORYS_CONFIG)
    else:
        candidate = Path(path)
        if candidate.is_absolute():
            checked.append(candidate)
        else:
            checked.extend([get_case_config_path(str(candidate)), ROOT / candidate])

    for candidate in checked:
        if candidate.exists():
            return candidate

    checked_text = "\n".join(f"- {candidate}" for candidate in checked)
    raise SystemExit(f"GLORYS12V1 config not found; checked:\n{checked_text}")


def default_project_start_stop() -> tuple[datetime, datetime]:
    params = load_project_params()
    time_cfg = params["time"]
    return datetime.fromisoformat(time_cfg["start"]), datetime.fromisoformat(time_cfg["stop"])


def load_glorys_config(path: str | Path | None = None) -> dict:
    config_path = resolve_glorys_config_path(path)
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid GLORYS12V1 config JSON: {config_path}: {exc}") from exc

    project_start, project_stop = default_project_start_stop()
    config.setdefault("time_start", project_start.isoformat())
    config.setdefault("time_stop", project_stop.isoformat())
    config.setdefault("time_mean_center", "12:00:00")
    config.setdefault("chunk", "month")
    config.setdefault("source_name", "glorys12v1")
    config.setdefault("output_raw_dir", "data/raw/ocean/glorys12v1")
    config.setdefault("output_input_dir", "input")
    config["_config_path"] = str(config_path)

    required = [
        "product_id",
        "dataset_id_daily",
        "variables_3d",
        "variables_2d",
        "static_variables",
        "longitude_buffer_deg",
        "latitude_buffer_deg",
        "boundary_band_buffer_points",
        "maximum_depth",
    ]
    missing = [key for key in required if key not in config]
    if missing:
        raise SystemExit(f"GLORYS12V1 config {config_path} is missing required keys: {', '.join(missing)}")
    if "dataset_id_static" not in config:
        static_parts = config.get("static_dataset_parts")
        if not static_parts:
            raise SystemExit(
                f"GLORYS12V1 config {config_path} must define dataset_id_static or static_dataset_parts"
            )
    return config


def ensure_abs_under_root(path_like: str | Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else ROOT / path


def glorys_path_override(config: dict, key: str, default: Path) -> Path:
    paths = config.get("paths", {})
    if isinstance(paths, dict) and paths.get(key):
        return ensure_abs_under_root(paths[key])
    return default


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


def glorys_time_window(config: dict) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(config["time_start"]), datetime.fromisoformat(config["time_stop"])


def glorys_center_time(config: dict, when: datetime | None = None) -> datetime:
    start, _ = glorys_time_window(config)
    base = when or start
    hh, mm, ss = [int(item) for item in str(config["time_mean_center"]).split(":")]
    return datetime(base.year, base.month, base.day, hh, mm, ss)


def build_glorys_paths(
    config: dict,
    start: datetime | None = None,
    stop: datetime | None = None,
    profile: str | None = None,
) -> OceanSourcePaths:
    config_start, config_stop = glorys_time_window(config)
    start_dt = start or config_start
    stop_dt = stop or config_stop
    raw_dir = ensure_abs_under_root(config["output_raw_dir"])
    input_dir = ensure_abs_under_root(config["output_input_dir"])
    source = normalize_ocean_source(config.get("source_name", "glorys12v1"))
    staged_initial = raw_dir / staged_ocean_name(source, "initial", start=start_dt, stop=stop_dt)
    staged_boundary = raw_dir / staged_ocean_name(source, "boundary", start=start_dt, stop=stop_dt)
    staged_static = raw_dir / staged_ocean_name(source, "static")
    roms_ini = input_dir / roms_input_name("ini", source, profile=profile, start=start_dt, stop=stop_dt)
    roms_bdy = input_dir / roms_input_name("bdy", source, profile=profile, start=start_dt, stop=stop_dt)
    return OceanSourcePaths(
        ocean_source=source,
        config_path=Path(config["_config_path"]) if config.get("_config_path") else DEFAULT_GLORYS_CONFIG,
        staged_initial=glorys_path_override(config, "staged_initial", staged_initial),
        staged_boundary=glorys_path_override(config, "staged_boundary", staged_boundary),
        staged_static=glorys_path_override(config, "staged_static", staged_static),
        roms_ini=glorys_path_override(config, "roms_ini", roms_ini),
        roms_bdy=glorys_path_override(config, "roms_bdy", roms_bdy),
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
    profile: str | None = None,
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
    return build_glorys_paths(config or load_glorys_config(), start=start, stop=stop, profile=profile)
