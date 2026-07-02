#!/usr/bin/env python3
"""Unified HYCOM 3D downloader for ESPC and GOFS 3.1 standard products."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen

import numpy as np
import xarray as xr


TIME_ORIGIN = datetime(2000, 1, 1, 0, 0, 0)
DEFAULT_DEPTH_RANGE = (0.0, 5000.0)
COMMON_STEP_HOURS = 3
PART_RETRY_SLEEP_SECONDS = 5

VAR_ATTRS = {
    "ssh": {"remote_name": "surf_el", "units": "m", "scale_factor": 0.001, "add_offset": 0.0, "_FillValue": -30000},
    "temp": {"remote_name": "water_temp", "units": "degC", "scale_factor": 0.001, "add_offset": 20.0, "_FillValue": -30000},
    "sal": {"remote_name": "salinity", "units": "psu", "scale_factor": 0.001, "add_offset": 20.0, "_FillValue": -30000},
    "u": {"remote_name": "water_u", "units": "m/s", "scale_factor": 0.001, "add_offset": 0.0, "_FillValue": -30000},
    "v": {"remote_name": "water_v", "units": "m/s", "scale_factor": 0.001, "add_offset": 0.0, "_FillValue": -30000},
}

ESPC_SOURCE = {
    "key": "espc",
    "label": "HYCOM ESPC-D-V02",
    "segment_key": "espc_d_v02",
    "start": datetime(2024, 8, 10, 0, 0, 0),
    "end": None,
    "coord_url": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/s3z",
    "var_urls": {
        "ssh": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/ssh",
        "temp": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/t3z",
        "sal": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/s3z",
        "u": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/u3z",
        "v": "https://tds.hycom.org/thredds/dodsC/ESPC-D-V02/v3z",
    },
    "step_hours": 3,
    "chunk_size": 8,
    "default_prefix": "hycom_espc_3d",
}


def build_gofs31_reanalysis_year_segment(year: int) -> dict:
    base_url = f"https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_53.X/data/{year}"
    return {
        "key": f"reanalysis_{year}",
        "label": f"HYCOM GOFS 3.1 standard reanalysis {year}",
        "segment_key": f"reanalysis_{year}",
        "start": datetime(year, 1, 1, 0, 0, 0),
        "end": datetime(year, 12, 31, 21, 0, 0),
        "coord_url": base_url,
        "var_urls": {name: base_url for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    }


GOFS31_STANDARD_SEGMENTS = [
    *[build_gofs31_reanalysis_year_segment(year) for year in range(1994, 2014)],
    {
        **build_gofs31_reanalysis_year_segment(2014),
        "end": datetime(2014, 7, 1, 21, 0, 0),
    },
    {
        "key": "analysis_56_3",
        "label": "HYCOM GOFS 3.1 standard analysis expt_56.3",
        "segment_key": "analysis_56_3",
        "start": datetime(2014, 7, 2, 0, 0, 0),
        "end": datetime(2016, 8, 31, 21, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_56.3",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_56.3" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
    {
        "key": "analysis_57_2",
        "label": "HYCOM GOFS 3.1 standard analysis expt_57.2",
        "segment_key": "analysis_57_2",
        "start": datetime(2016, 9, 1, 0, 0, 0),
        "end": datetime(2017, 2, 1, 9, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_57.2",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_57.2" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
    {
        "key": "analysis_92_8",
        "label": "HYCOM GOFS 3.1 standard analysis expt_92.8",
        "segment_key": "analysis_92_8",
        "start": datetime(2017, 2, 1, 12, 0, 0),
        "end": datetime(2017, 6, 1, 9, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_92.8",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_92.8" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
    {
        "key": "analysis_57_7",
        "label": "HYCOM GOFS 3.1 standard analysis expt_57.7",
        "segment_key": "analysis_57_7",
        "start": datetime(2017, 6, 1, 12, 0, 0),
        "end": datetime(2017, 10, 1, 9, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_57.7",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_57.7" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
    {
        "key": "analysis_92_9",
        "label": "HYCOM GOFS 3.1 standard analysis expt_92.9",
        "segment_key": "analysis_92_9",
        "start": datetime(2017, 10, 1, 12, 0, 0),
        "end": datetime(2018, 2, 28, 21, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_92.9",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_92.9" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
    {
        "key": "analysis_93_0_glbv",
        "label": "HYCOM GOFS 3.1 standard analysis GLBv0.08 expt_93.0",
        "segment_key": "analysis_93_0_glbv",
        "start": datetime(2018, 3, 1, 0, 0, 0),
        "end": datetime(2018, 12, 31, 21, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_93.0",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_93.0" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
    {
        "key": "analysis_93_0_glby",
        "label": "HYCOM GOFS 3.1 standard analysis GLBy0.08 expt_93.0",
        "segment_key": "analysis_93_0_glby",
        "start": datetime(2019, 1, 1, 0, 0, 0),
        "end": datetime(2024, 9, 4, 21, 0, 0),
        "coord_url": "https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0",
        "var_urls": {name: "https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0" for name in VAR_ATTRS},
        "step_hours": 3,
        "chunk_size": 8,
        "default_prefix": "hycom_gofs31_standard",
    },
]

SOURCES = {
    "espc": {"segments": [ESPC_SOURCE]},
    "gofs31_standard": {"segments": GOFS31_STANDARD_SEGMENTS},
}
SOURCE_AUTO = "auto"
SOURCE_PRIORITY = ("espc", "gofs31_standard")


@dataclass(frozen=True)
class IndexRange:
    start: int
    stop: int
    step: int = 1

    def dap(self) -> str:
        return f"[{self.start}:{self.step}:{self.stop}]"

    def count(self) -> int:
        return ((self.stop - self.start) // self.step) + 1


@dataclass(frozen=True)
class DownloadWindow:
    start: datetime
    stop: datetime
    resolved_source: str
    segment_key: str
    coord_url: str
    output_label: str
    part_id: str
    step_hours: int

    @property
    def part_filename(self) -> str:
        return f"hycom_{self.resolved_source}_{self.segment_key}_{self.start:%Y%m%dT%H%M%S}_{self.stop:%Y%m%dT%H%M%S}.nc"


def fetch_text(url: str, retries: int = 8, sleep_seconds: int = 10) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(url, timeout=180) as response:
                return response.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Request failed ({attempt}/{retries}): {exc}")
            if attempt < retries:
                time.sleep(sleep_seconds)
    raise RuntimeError(f"Failed to fetch {url}") from last_error


def segment_covers_time(segment: dict, when: datetime) -> bool:
    segment_end = segment["end"] or datetime.max
    return segment["start"] <= when <= segment_end


def segment_covers_window(segment: dict, start: datetime, stop: datetime) -> bool:
    segment_end = segment["end"] or datetime.max
    return segment["start"] <= start and stop <= segment_end


def requested_last_time(start: datetime, days: int, step_hours: int) -> datetime:
    return start + timedelta(hours=step_hours * ((days * (24 // step_hours)) - 1))


def floor_datetime_to_step(when: datetime, step_hours: int = COMMON_STEP_HOURS) -> datetime:
    aligned = when.replace(minute=0, second=0, microsecond=0)
    return aligned - timedelta(hours=aligned.hour % step_hours)


def ensure_step_aligned(when: datetime, step_hours: int = COMMON_STEP_HOURS) -> datetime:
    aligned = floor_datetime_to_step(when, step_hours)
    if aligned != when:
        raise ValueError(f"time must align to a {step_hours}-hour HYCOM step: {when.isoformat()}")
    return when


def normalize_requested_stop(when: datetime, step_hours: int = COMMON_STEP_HOURS) -> datetime:
    return floor_datetime_to_step(when, step_hours)


def build_requested_times(start: datetime, *, days: int | None = None, stop: datetime | None = None, step_hours: int = COMMON_STEP_HOURS) -> list[datetime]:
    ensure_step_aligned(start, step_hours)
    if stop is not None:
        stop = normalize_requested_stop(stop, step_hours)
        if stop < start:
            raise ValueError("stop must not be earlier than start after step alignment")
        count = int((stop - start).total_seconds() // (step_hours * 3600)) + 1
        return [start + timedelta(hours=step_hours * idx) for idx in range(count)]
    if days is None or days <= 0:
        raise ValueError("days must be positive when stop is not provided")
    return [start + timedelta(hours=step_hours * idx) for idx in range(days * (24 // step_hours))]


def month_end_step(start: datetime, step_hours: int = COMMON_STEP_HOURS) -> datetime:
    ensure_step_aligned(start, step_hours)
    next_month = datetime(start.year + (1 if start.month == 12 else 0), 1 if start.month == 12 else start.month + 1, 1)
    return next_month - timedelta(hours=step_hours)


def next_step(when: datetime, step_hours: int = COMMON_STEP_HOURS) -> datetime:
    return when + timedelta(hours=step_hours)


def iter_selection_boundaries(after: datetime) -> list[datetime]:
    boundaries: set[datetime] = set()
    for source_name in SOURCE_PRIORITY:
        for segment in SOURCES[source_name]["segments"]:
            if segment["start"] > after:
                boundaries.add(segment["start"])
    return sorted(boundaries)


def resolve_download_target(
    *,
    start: datetime,
    days: int | None = None,
    stop: datetime | None = None,
    source: str | None = None,
    source_key: str | None = None,
) -> tuple[str, dict]:
    requested_source = source or SOURCE_AUTO
    requested_times = build_requested_times(start, days=days, stop=stop)
    effective_stop = requested_times[-1]
    if requested_source != SOURCE_AUTO:
        segment = resolve_source_segment(requested_source, start, source_key=source_key)
        if not segment_covers_window(segment, start, effective_stop):
            raise ValueError(
                f"Requested window {start.isoformat()} to {effective_stop.isoformat()} exceeds "
                f"{requested_source}:{segment['segment_key']} coverage"
            )
        return requested_source, segment

    if source_key is not None:
        matches: list[tuple[str, dict]] = []
        for candidate_source in SOURCE_PRIORITY:
            try:
                segment = resolve_source_segment(candidate_source, start, source_key=source_key)
            except ValueError:
                continue
            if segment_covers_window(segment, start, effective_stop):
                matches.append((candidate_source, segment))
        if not matches:
            raise ValueError(f"Unknown or incompatible source_key {source_key} for automatic source selection")
        return matches[0]

    for candidate_source in SOURCE_PRIORITY:
        try:
            segment = resolve_source_segment(candidate_source, start)
        except ValueError:
            continue
        if segment_covers_window(segment, start, effective_stop):
            return candidate_source, segment
    raise ValueError(f"No HYCOM source covers requested window starting at {start.isoformat()} ending at {effective_stop.isoformat()}")


def parse_ascii_vector(payload: str, name: str) -> np.ndarray:
    marker = f"{name}["
    lines = payload.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith(marker):
            start = idx + 1
            break
    if start is None:
        raise ValueError(f"Could not find vector block for {name}")
    values: list[float] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            break
        values.extend(float(item.strip()) for item in stripped.split(",") if item.strip())
    return np.asarray(values, dtype=np.float64)


def parse_ascii_array(payload: str, remote_name: str, shape: tuple[int, ...]) -> np.ndarray:
    marker = f"{remote_name}.{remote_name}["
    lines = payload.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith(marker):
            start = idx + 1
            break
    if start is None:
        raise ValueError(f"Could not find array block for {remote_name}")
    result = np.empty(shape, dtype=np.float32)
    row_re = re.compile(r"^((?:\[\d+\])+),\s*(.*)$")
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            break
        match = row_re.match(stripped)
        if not match:
            continue
        prefix, values_text = match.groups()
        indices = tuple(int(item) for item in re.findall(r"\[(\d+)\]", prefix))
        values = np.asarray([float(item.strip()) for item in values_text.split(",") if item.strip()], dtype=np.float32)
        result[indices] = values
    return result


def decode_data(short_name: str, values: np.ndarray) -> np.ndarray:
    attrs = VAR_ATTRS[short_name]
    decoded = values.astype(np.float32)
    decoded[decoded == attrs["_FillValue"]] = np.nan
    decoded = decoded * attrs["scale_factor"] + attrs["add_offset"]
    return decoded


def hours_to_datetime(hours: Iterable[float]) -> list[datetime]:
    return [TIME_ORIGIN + timedelta(hours=float(item)) for item in hours]


def nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(values - target)))


def bounding_indices(values: np.ndarray, lower: float, upper: float) -> IndexRange:
    start = nearest_index(values, lower)
    stop = nearest_index(values, upper)
    if start > stop:
        start, stop = stop, start
    return IndexRange(start, stop)


def time_indices(values: np.ndarray, targets: list[datetime]) -> IndexRange:
    target_hours = [(target - TIME_ORIGIN).total_seconds() / 3600.0 for target in targets]
    indices = [nearest_index(values, target_hour) for target_hour in target_hours]
    unique_sorted = sorted(set(indices))
    if len(unique_sorted) == 1:
        return IndexRange(unique_sorted[0], unique_sorted[0])
    step = unique_sorted[1] - unique_sorted[0]
    for left, right in zip(unique_sorted, unique_sorted[1:]):
        if right - left != step:
            raise ValueError("Requested times do not map to a uniform HYCOM step")
    return IndexRange(unique_sorted[0], unique_sorted[-1], step)


def split_index_range(index_range: IndexRange, chunk_size: int) -> list[IndexRange]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    indices = list(range(index_range.start, index_range.stop + 1, index_range.step))
    return [IndexRange(group[0], group[-1], index_range.step) for group in (indices[i : i + chunk_size] for i in range(0, len(indices), chunk_size))]


def build_ascii_url(base_url: str, selections: list[str]) -> str:
    return f"{base_url}.ascii?{','.join(selections)}"


def fetch_coord_vector(base_url: str, coord_name: str) -> np.ndarray:
    return parse_ascii_vector(fetch_text(build_ascii_url(base_url, [coord_name])), coord_name)


def fetch_variable_2d(base_url: str, short_name: str, time_sel: IndexRange, lat_sel: IndexRange, lon_sel: IndexRange) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    remote_name = VAR_ATTRS[short_name]["remote_name"]
    payload = fetch_text(
        build_ascii_url(
            base_url,
            [
                f"time{time_sel.dap()}",
                f"lat{lat_sel.dap()}",
                f"lon{lon_sel.dap()}",
                f"{remote_name}{time_sel.dap()}{lat_sel.dap()}{lon_sel.dap()}",
            ],
        )
    )
    times = parse_ascii_vector(payload, "time")
    lats = parse_ascii_vector(payload, "lat")
    lons = parse_ascii_vector(payload, "lon")
    raw = parse_ascii_array(payload, remote_name, (time_sel.count(), lat_sel.count(), lon_sel.count()))
    return times, lats, lons, decode_data(short_name, raw)


def fetch_variable_3d(base_url: str, short_name: str, time_sel: IndexRange, depth_sel: IndexRange, lat_sel: IndexRange, lon_sel: IndexRange) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    remote_name = VAR_ATTRS[short_name]["remote_name"]
    payload = fetch_text(
        build_ascii_url(
            base_url,
            [
                f"time{time_sel.dap()}",
                f"depth{depth_sel.dap()}",
                f"lat{lat_sel.dap()}",
                f"lon{lon_sel.dap()}",
                f"{remote_name}{time_sel.dap()}{depth_sel.dap()}{lat_sel.dap()}{lon_sel.dap()}",
            ],
        )
    )
    times = parse_ascii_vector(payload, "time")
    depths = parse_ascii_vector(payload, "depth")
    lats = parse_ascii_vector(payload, "lat")
    lons = parse_ascii_vector(payload, "lon")
    raw = parse_ascii_array(payload, remote_name, (time_sel.count(), depth_sel.count(), lat_sel.count(), lon_sel.count()))
    return times, depths, lats, lons, decode_data(short_name, raw)


def resolve_source_segment(source: str, start: datetime, source_key: str | None = None) -> dict:
    if source not in SOURCES:
        raise ValueError(f"Unsupported source: {source}")
    segments = SOURCES[source]["segments"]
    if source_key is not None:
        for segment in segments:
            if segment["key"] == source_key:
                return segment
        raise ValueError(f"Unknown source_key {source_key} for source {source}")
    for segment in segments:
        segment_end = segment["end"] or datetime.max
        if segment["start"] <= start <= segment_end:
            return segment
    raise ValueError(f"No segment found for source {source} at {start}")


def build_dataset(
    *,
    source: str | None,
    start: datetime,
    days: int | None = None,
    stop: datetime | None = None,
    lat_bounds: tuple[float, float],
    lon_bounds: tuple[float, float],
    depth_bounds: tuple[float, float],
    source_key: str | None = None,
    variables: list[str] | None = None,
) -> xr.Dataset:
    variables = variables or ["ssh", "temp", "sal", "u", "v"]
    resolved_source, segment = resolve_download_target(
        start=start,
        days=days,
        stop=stop,
        source=source,
        source_key=source_key,
    )
    step_hours = segment["step_hours"]
    times_requested = build_requested_times(start, days=days, stop=stop, step_hours=step_hours)
    coord_url = segment["coord_url"]
    all_times = fetch_coord_vector(coord_url, "time")
    all_depths = fetch_coord_vector(coord_url, "depth")
    all_lats = fetch_coord_vector(coord_url, "lat")
    all_lons = fetch_coord_vector(coord_url, "lon")
    t_sel = time_indices(all_times, times_requested)
    d_sel = bounding_indices(all_depths, *depth_bounds)
    lat_sel = bounding_indices(all_lats, *lat_bounds)
    lon_sel = bounding_indices(all_lons, *lon_bounds)
    chunk_ranges = split_index_range(t_sel, chunk_size=segment["chunk_size"])
    time_parts: list[np.ndarray] = []
    data_parts: dict[str, list[np.ndarray]] = {name: [] for name in variables}
    depths = lats = lons = None
    for chunk_no, chunk in enumerate(chunk_ranges, start=1):
        print(f"[{resolved_source}:{segment['segment_key']}] Downloading chunk {chunk_no}/{len(chunk_ranges)}: time indices {chunk.start}-{chunk.stop}")
        chunk_times = None
        for name in variables:
            base_url = segment["var_urls"][name]
            if name == "ssh":
                times, chunk_lats, chunk_lons, values = fetch_variable_2d(base_url, name, chunk, lat_sel, lon_sel)
                lats = chunk_lats
                lons = chunk_lons
            else:
                times, chunk_depths, chunk_lats, chunk_lons, values = fetch_variable_3d(base_url, name, chunk, d_sel, lat_sel, lon_sel)
                depths = chunk_depths
                lats = chunk_lats
                lons = chunk_lons
            data_parts[name].append(values)
            chunk_times = times
        if chunk_times is not None:
            time_parts.append(chunk_times)
    if depths is None or lats is None or lons is None or not time_parts:
        raise RuntimeError("No data downloaded")
    coords = {
        "time": np.array(hours_to_datetime(np.concatenate(time_parts, axis=0)), dtype="datetime64[ns]"),
        "depth": depths.astype(np.float32),
        "lat": lats.astype(np.float32),
        "lon": lons.astype(np.float32),
    }
    data_vars = {}
    for name in variables:
        if name == "ssh":
            data_vars[name] = (("time", "lat", "lon"), np.concatenate(data_parts[name], axis=0))
        else:
            data_vars[name] = (("time", "depth", "lat", "lon"), np.concatenate(data_parts[name], axis=0))
    ds = xr.Dataset(
        data_vars=data_vars,
        coords=coords,
        attrs={
            "source": resolved_source,
            "source_requested": source or SOURCE_AUTO,
            "source_key": segment["segment_key"],
            "source_label": segment["label"],
            "coord_url": segment["coord_url"],
            "time_start_requested": times_requested[0].isoformat(),
            "time_stop_requested": times_requested[-1].isoformat(),
        },
    )
    for name in variables:
        long_name = {
            "ssh": "Water Surface Elevation",
            "temp": "Water Temperature",
            "sal": "Salinity",
            "u": "Eastward Water Velocity",
            "v": "Northward Water Velocity",
        }[name]
        ds[name].attrs.update({"long_name": long_name, "units": VAR_ATTRS[name]["units"]})
    return ds


def build_output_path(output_dir: Path, source: str, segment: dict, start: datetime, days: int | None = None, stop: datetime | None = None) -> Path:
    if stop is not None:
        end_time = stop
    elif days is not None:
        end_time = requested_last_time(start, days, segment["step_hours"])
    else:
        raise ValueError("days or stop must be provided")
    return output_dir / f"hycom_{source}_{segment['segment_key']}_{start:%Y%m%d}_{end_time:%Y%m%d%H}.nc"


def build_merged_output_path(output_dir: Path, requested_source: str, start: datetime, stop: datetime) -> Path:
    return output_dir / f"hycom_{requested_source}_{start:%Y%m%dT%H%M%S}_{stop:%Y%m%dT%H%M%S}.nc"


def build_manifest_path(target_path: Path) -> Path:
    return target_path.with_suffix(target_path.suffix + ".manifest.json")


def safe_to_netcdf(ds: xr.Dataset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    ds.to_netcdf(tmp, engine="netcdf4")
    tmp.replace(path)


def dedupe_times(ds: xr.Dataset) -> xr.Dataset:
    if "time" not in ds.coords:
        return ds
    values = ds.time.values
    _, first_indices = np.unique(values, return_index=True)
    return ds.isel(time=np.sort(first_indices))


def next_selection_boundary(current: datetime, source: str | None, source_key: str | None, active_source: str, active_segment_key: str) -> datetime | None:
    for candidate_start in iter_selection_boundaries(current):
        try:
            candidate_source, candidate_segment = resolve_download_target(
                start=candidate_start,
                days=1,
                source=source,
                source_key=source_key,
            )
        except ValueError:
            continue
        if candidate_source != active_source or candidate_segment["segment_key"] != active_segment_key:
            return candidate_start
    return None


def plan_download_windows(start_dt: datetime, stop_dt: datetime, source: str | None = None, source_key: str | None = None) -> list[DownloadWindow]:
    start = ensure_step_aligned(start_dt, COMMON_STEP_HOURS)
    stop = normalize_requested_stop(stop_dt, COMMON_STEP_HOURS)
    if stop < start:
        raise ValueError("stop must not be earlier than start after step alignment")
    windows: list[DownloadWindow] = []
    current = start
    while current <= stop:
        resolved_source, segment = resolve_download_target(
            start=current,
            days=1,
            source=source,
            source_key=source_key,
        )
        step_hours = segment["step_hours"]
        segment_end = segment["end"] or datetime.max
        part_end = min(stop, month_end_step(current, step_hours), segment_end)
        boundary = next_selection_boundary(current, source, source_key, resolved_source, segment["segment_key"])
        if boundary is not None:
            part_end = min(part_end, boundary - timedelta(hours=step_hours))
        part_index = len(windows) + 1
        windows.append(
            DownloadWindow(
                start=current,
                stop=part_end,
                resolved_source=resolved_source,
                segment_key=segment["segment_key"],
                coord_url=segment["coord_url"],
                output_label=f"{current:%Y%m}",
                part_id=f"part_{part_index:03d}",
                step_hours=step_hours,
            )
        )
        current = next_step(part_end, step_hours)
    return windows


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def download_window_part(
    window: DownloadWindow,
    *,
    lat_bounds: tuple[float, float],
    lon_bounds: tuple[float, float],
    depth_bounds: tuple[float, float],
    output_dir: Path,
    max_retries_per_part: int = 1,
    variables: list[str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / window.part_filename
    attempt = 0
    last_error: Exception | None = None
    while attempt < max(1, max_retries_per_part):
        attempt += 1
        try:
            ds = build_dataset(
                source=window.resolved_source,
                start=window.start,
                stop=window.stop,
                lat_bounds=lat_bounds,
                lon_bounds=lon_bounds,
                depth_bounds=depth_bounds,
                variables=variables,
            )
            safe_to_netcdf(ds, out_path)
            return out_path
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[{window.part_id}] failed attempt {attempt}/{max(1, max_retries_per_part)}: {exc}")
            if attempt < max(1, max_retries_per_part):
                time.sleep(PART_RETRY_SLEEP_SECONDS)
    raise RuntimeError(f"failed to download {window.part_id}") from last_error


def merge_window_parts(
    paths: list[Path],
    out_path: Path,
    *,
    requested_source: str,
    requested_start: datetime,
    requested_stop: datetime,
    windows: list[DownloadWindow],
) -> Path:
    datasets: list[xr.Dataset] = []
    for path in sorted(paths):
        with xr.open_dataset(path, engine="netcdf4") as ds:
            datasets.append(ds.load())
    if not datasets:
        raise RuntimeError("no successful part datasets to merge")
    merged = dedupe_times(xr.concat(datasets, dim="time").sortby("time"))
    merged.attrs["source_requested"] = requested_source
    merged.attrs["download_mode"] = "partitioned_long_window"
    merged.attrs["part_count"] = len(windows)
    merged.attrs["successful_part_count"] = len(paths)
    merged.attrs["failed_part_count"] = 0
    merged.attrs["time_start_requested"] = requested_start.isoformat()
    merged.attrs["time_stop_requested"] = requested_stop.isoformat()
    merged.attrs["resolved_sources_used"] = ",".join(dict.fromkeys(window.resolved_source for window in windows))
    merged.attrs["resolved_segment_keys_used"] = ",".join(dict.fromkeys(window.segment_key for window in windows))
    safe_to_netcdf(merged, out_path)
    return out_path


def download_partitioned_windows(
    *,
    start: datetime,
    stop: datetime,
    source: str | None,
    source_key: str | None,
    lat_bounds: tuple[float, float],
    lon_bounds: tuple[float, float],
    depth_bounds: tuple[float, float],
    part_output_dir: Path,
    merge_output: Path,
    keep_parts: bool = True,
    max_retries_per_part: int = 1,
    variables: list[str] | None = None,
) -> dict:
    windows = plan_download_windows(start, stop, source=source, source_key=source_key)
    part_output_dir.mkdir(parents=True, exist_ok=True)
    successful_parts: list[Path] = []
    failures: list[dict] = []
    for window in windows:
        try:
            part_path = download_window_part(
                window,
                lat_bounds=lat_bounds,
                lon_bounds=lon_bounds,
                depth_bounds=depth_bounds,
                output_dir=part_output_dir,
                max_retries_per_part=max_retries_per_part,
                variables=variables,
            )
            successful_parts.append(part_path)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    **asdict(window),
                    "start": window.start.isoformat(),
                    "stop": window.stop.isoformat(),
                    "output_path": str(part_output_dir / window.part_filename),
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    manifest = {
        "requested_source": source or SOURCE_AUTO,
        "requested_start": start.isoformat(),
        "requested_stop": stop.isoformat(),
        "part_count": len(windows),
        "successful_part_count": len(successful_parts),
        "failed_part_count": len(failures),
        "parts": [
            {
                **asdict(window),
                "start": window.start.isoformat(),
                "stop": window.stop.isoformat(),
                "output_path": str(part_output_dir / window.part_filename),
                "status": "success" if (part_output_dir / window.part_filename) in successful_parts else "failed",
            }
            for window in windows
        ],
        "failures": failures,
        "merge_output": str(merge_output),
    }
    if failures:
        manifest_path = build_manifest_path(merge_output)
        write_manifest(manifest_path, manifest)
        return {
            "success": False,
            "windows": windows,
            "successful_parts": successful_parts,
            "failures": failures,
            "manifest_path": manifest_path,
            "merge_output": merge_output,
        }
    merged_path = merge_window_parts(
        successful_parts,
        merge_output,
        requested_source=source or SOURCE_AUTO,
        requested_start=start,
        requested_stop=normalize_requested_stop(stop, COMMON_STEP_HOURS),
        windows=windows,
    )
    manifest["merged"] = True
    manifest_path = build_manifest_path(merged_path)
    write_manifest(manifest_path, manifest)
    if not keep_parts:
        for path in successful_parts:
            path.unlink(missing_ok=True)
    return {
        "success": True,
        "windows": windows,
        "successful_parts": successful_parts,
        "failures": failures,
        "manifest_path": manifest_path,
        "merge_output": merged_path,
    }


def parse_datetime_arg(value: str) -> datetime:
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"unsupported datetime format: {value}")


def parse_stop_arg(value: str) -> datetime:
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").replace(hour=23, minute=59, second=59)
    return parse_datetime_arg(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified HYCOM 3D downloader for ESPC and GOFS 3.1 standard.")
    parser.add_argument("--source", choices=[SOURCE_AUTO, *sorted(SOURCES)], default=SOURCE_AUTO)
    parser.add_argument("--source-key", help="Optional explicit source segment key, mainly for gofs31_standard.")
    parser.add_argument("--lat-min", type=float, required=True)
    parser.add_argument("--lat-max", type=float, required=True)
    parser.add_argument("--lon-min", type=float, required=True)
    parser.add_argument("--lon-max", type=float, required=True)
    parser.add_argument("--start", type=parse_datetime_arg, required=True, help="YYYYMMDD or YYYYMMDDTHHMMSS")
    parser.add_argument("--stop", type=parse_stop_arg, default=None, help="YYYYMMDD or YYYYMMDDTHHMMSS")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--depth-min", type=float, default=DEFAULT_DEPTH_RANGE[0])
    parser.add_argument("--depth-max", type=float, default=DEFAULT_DEPTH_RANGE[1])
    parser.add_argument("--output-dir", type=Path, default=Path("python_output_unified"))
    parser.add_argument("--part-output-dir", type=Path, default=None)
    parser.add_argument("--merge-output", type=Path, default=None)
    parser.add_argument("--max-retries-per-part", type=int, default=1)
    parser.add_argument("--keep-parts", action="store_true", default=True)
    parser.add_argument("--no-keep-parts", action="store_false", dest="keep_parts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.stop is None:
        resolved_source, segment = resolve_download_target(
            start=args.start,
            days=args.days,
            source=args.source,
            source_key=args.source_key,
        )
        ds = build_dataset(
            source=args.source,
            source_key=args.source_key,
            start=args.start,
            days=args.days,
            lat_bounds=(args.lat_min, args.lat_max),
            lon_bounds=(args.lon_min, args.lon_max),
            depth_bounds=(args.depth_min, args.depth_max),
        )
        out_path = args.merge_output or build_output_path(args.output_dir, resolved_source, segment, args.start, days=args.days)
        safe_to_netcdf(ds, out_path)
        print(f"Saved {out_path}")
        return
    merge_output = args.merge_output or build_merged_output_path(
        args.output_dir,
        args.source,
        ensure_step_aligned(args.start, COMMON_STEP_HOURS),
        normalize_requested_stop(args.stop, COMMON_STEP_HOURS),
    )
    part_output_dir = args.part_output_dir or (args.output_dir / f"{merge_output.stem}_parts")
    result = download_partitioned_windows(
        start=args.start,
        stop=args.stop,
        source=args.source,
        source_key=args.source_key,
        lat_bounds=(args.lat_min, args.lat_max),
        lon_bounds=(args.lon_min, args.lon_max),
        depth_bounds=(args.depth_min, args.depth_max),
        part_output_dir=part_output_dir,
        merge_output=merge_output,
        keep_parts=args.keep_parts,
        max_retries_per_part=args.max_retries_per_part,
    )
    if result["success"]:
        print(f"Saved {result['merge_output']}")
        print(f"Manifest {result['manifest_path']}")
        return
    raise SystemExit(f"partitioned download incomplete; see manifest: {result['manifest_path']}")


if __name__ == "__main__":
    main()
