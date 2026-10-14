#!/usr/bin/env python3
"""Helpers shared by staged raw data download and validation scripts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from case_context import get_case_config_path, get_case_root, resolve_case_config_path
ROOT = get_case_root()
DEFAULT_CONFIG = get_case_config_path("staged_download_config.json")
DEFAULT_BBOX_BUFFER_BY_SOURCE = {
    "hycom": 0.08,
    "era5": 0.25,
    "default": 0.08,
}


@dataclass(frozen=True)
class BoundingBox:
    west: float
    east: float
    south: float
    north: float


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    stop: datetime


def load_download_config(path: str | None = None) -> dict:
    config_path = resolve_case_config_path(path, "staged_download_config.json")
    return json.loads(config_path.read_text())


def load_project_parameters() -> dict:
    return json.loads(get_case_config_path("project_parameters.json").read_text())


def config_path_to_abs(config: dict, key: str) -> Path:
    rel = Path(config["paths"][key])
    return rel if rel.is_absolute() else ROOT / rel


def _bbox_from_mapping(bbox: dict) -> BoundingBox:
    return BoundingBox(
        west=float(bbox["west"]),
        east=float(bbox["east"]),
        south=float(bbox["south"]),
        north=float(bbox["north"]),
    )


def _domain_bbox_with_buffer(domain: dict, buffer_deg: float) -> BoundingBox:
    return BoundingBox(
        west=float(domain["lon_min"]) - buffer_deg,
        east=float(domain["lon_max"]) + buffer_deg,
        south=float(domain["lat_min"]) - buffer_deg,
        north=float(domain["lat_max"]) + buffer_deg,
    )


def _resolve_bbox_buffer_deg(config: dict, source: str | None) -> float:
    if source:
        source_key = f"{source}_bbox_buffer_deg"
        if source_key in config:
            return float(config[source_key])
    if "bbox_buffer_deg" in config:
        return float(config["bbox_buffer_deg"])
    if source and source in DEFAULT_BBOX_BUFFER_BY_SOURCE:
        return float(DEFAULT_BBOX_BUFFER_BY_SOURCE[source])
    return float(DEFAULT_BBOX_BUFFER_BY_SOURCE["default"])


def get_bbox(config: dict, source: str | None = None) -> BoundingBox:
    bbox = config.get("bbox")
    if bbox is not None:
        return _bbox_from_mapping(bbox)

    project = load_project_parameters()
    domain = project.get("domain")
    if domain is None:
        raise SystemExit(
            "download bbox is not configured: provide staged_download_config.json:bbox "
            "or define domain.lon_min/lon_max/lat_min/lat_max in project_parameters.json"
        )

    buffer_deg = _resolve_bbox_buffer_deg(config, source)
    return _domain_bbox_with_buffer(domain, buffer_deg)


def get_time_window(config: dict) -> TimeWindow:
    time_cfg = config["time"]
    return TimeWindow(
        start=datetime.fromisoformat(time_cfg["start"]),
        stop=datetime.fromisoformat(time_cfg["stop"]),
    )


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_first(items: Iterable[str], candidates: Iterable[str]) -> str:
    lowered = {name.lower(): name for name in items}
    for candidate in candidates:
        if candidate in lowered.values():
            return candidate
        found = lowered.get(candidate.lower())
        if found:
            return found
    raise KeyError(f"none of {tuple(candidates)} found in {list(items)}")


def normalize_longitudes(lon: np.ndarray) -> np.ndarray:
    values = np.asarray(lon, dtype=float)
    if np.nanmax(values) > 180.0:
        values = ((values + 180.0) % 360.0) - 180.0
    return values


def sort_lat_lon_depth_time(ds, lon_name: str, lat_name: str, depth_name: str | None, time_name: str | None):
    out = ds
    for name in [lon_name, lat_name, depth_name, time_name]:
        if name and name in out.coords:
            out = out.sortby(name)
    return out


def parse_era5_credentials(path: str | Path) -> tuple[str, str]:
    credentials_path = Path(path)
    if not credentials_path.exists():
        raise SystemExit(f"ERA5 credential file not found: {credentials_path}")
    values: dict[str, str] = {}
    for line in credentials_path.read_text().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip()
    url = values.get("url")
    token = values.get("key")
    if not url or not token:
        raise SystemExit(f"ERA5 credential file must contain url and key: {credentials_path}")
    return url, token


def infer_time_step_seconds(times: np.ndarray) -> np.ndarray:
    if len(times) == 0:
        return np.zeros(0, dtype=float)
    if len(times) == 1:
        return np.array([3600.0], dtype=float)
    diffs = np.diff(times).astype("timedelta64[s]").astype(float)
    out = np.empty(len(times), dtype=float)
    out[1:] = diffs
    out[0] = diffs[0]
    out[out <= 0.0] = np.nanmedian(diffs[diffs > 0.0]) if np.any(diffs > 0.0) else 3600.0
    return out


def accumulated_to_step_amount(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data, dtype=float)
    if data.shape[0] <= 1:
        return np.maximum(data, 0.0)
    sample = np.nanmean(data.reshape(data.shape[0], -1), axis=1)
    deltas = np.diff(sample)
    monotonic_fraction = float(np.mean(deltas >= -1e-12)) if deltas.size else 1.0
    if monotonic_fraction < 0.8:
        return data
    out = np.empty_like(data)
    out[0] = np.maximum(data[0], 0.0)
    for idx in range(1, data.shape[0]):
        delta = data[idx] - data[idx - 1]
        out[idx] = np.where(delta >= -1e-12, delta, data[idx])
    return np.maximum(out, 0.0)


def step_amount_to_rate(data: np.ndarray, times: np.ndarray) -> np.ndarray:
    seconds = infer_time_step_seconds(times)
    reshape = (len(seconds),) + (1,) * (data.ndim - 1)
    safe_seconds = np.where(seconds > 0.0, seconds, 3600.0).reshape(reshape)
    return data / safe_seconds


def dewpoint_to_relative_humidity_percent(tair_c: np.ndarray, dewpoint_c: np.ndarray) -> np.ndarray:
    exponent_t = (17.625 * tair_c) / (243.04 + tair_c)
    exponent_td = (17.625 * dewpoint_c) / (243.04 + dewpoint_c)
    rh = 100.0 * np.exp(exponent_td - exponent_t)
    return np.clip(rh, 0.0, 100.0)
