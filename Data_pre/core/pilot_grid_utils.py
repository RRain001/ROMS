#!/usr/bin/env python3
"""Shared helpers for the active pilot grid and source placement."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import get_case_root

ROOT = get_case_root()
DEFAULT_RAW_GRID = ROOT / "input" / "roms_grid_bathy_500m.nc"
DEFAULT_MASKCLEAN_GRID = ROOT / "input" / "roms_grid_bathy_500m_maskclean.nc"
DEFAULT_SMOOTHED_GRID = ROOT / "input" / "roms_grid_bathy_500m_smoothed.nc"


@dataclass(frozen=True)
class SourcePlacement:
    configured_lon: float
    configured_lat: float
    nearest_xi: int
    nearest_eta: int
    nearest_lon: float
    nearest_lat: float
    nearest_is_water: bool
    snapped_xi: int
    snapped_eta: int
    snapped_lon: float
    snapped_lat: float
    snapped_distance_m: float
    snapped_depth_m: float
    placement_rule: str


def resolve_active_pilot_grid(grid_arg: str | None = None) -> Path:
    """Resolve the grid path used by the real 500 m pilot workflow."""
    if grid_arg:
        grid_path = Path(grid_arg).expanduser().resolve()
        if not grid_path.exists():
            raise SystemExit(f"grid file not found: {grid_path}")
        return grid_path

    if DEFAULT_SMOOTHED_GRID.exists():
        return DEFAULT_SMOOTHED_GRID
    if DEFAULT_MASKCLEAN_GRID.exists():
        return DEFAULT_MASKCLEAN_GRID
    if DEFAULT_RAW_GRID.exists():
        return DEFAULT_RAW_GRID

    raise SystemExit(
        "default active pilot grid not found.\n"
        f"expected one of: {DEFAULT_SMOOTHED_GRID}, {DEFAULT_MASKCLEAN_GRID}, or {DEFAULT_RAW_GRID}\n"
        "Generate it first with preprocessing/create_grid_from_bathymetry.py "
        "--resolution-key pilot, or pass --grid /path/to/grid.nc"
    )


def _distance_m(lon: np.ndarray, lat: np.ndarray, lon0: float, lat0: float) -> np.ndarray:
    meters_per_degree_lon = 111_320.0 * math.cos(math.radians(lat0))
    meters_per_degree_lat = 111_320.0
    dx = (lon - lon0) * meters_per_degree_lon
    dy = (lat - lat0) * meters_per_degree_lat
    return np.hypot(dx, dy)


def locate_source_on_grid(grid_path: Path, source_lon: float, source_lat: float) -> SourcePlacement:
    """Locate the configured source and snap it to the nearest water rho cell."""
    with Dataset(grid_path) as grid:
        lon = np.asarray(grid.variables["lon_rho"][:, :], dtype=float)
        lat = np.asarray(grid.variables["lat_rho"][:, :], dtype=float)
        mask = np.asarray(grid.variables["mask_rho"][:, :], dtype=int)
        depth = np.asarray(grid.variables["h"][:, :], dtype=float)

    dist = _distance_m(lon, lat, source_lon, source_lat)
    nearest_eta, nearest_xi = np.unravel_index(np.argmin(dist), dist.shape)
    nearest_is_water = bool(mask[nearest_eta, nearest_xi] == 1)

    if nearest_is_water:
        snapped_eta, snapped_xi = nearest_eta, nearest_xi
        placement_rule = "configured source already on water rho cell"
    else:
        water = mask == 1
        if not np.any(water):
            raise SystemExit(f"grid has no water rho cells: {grid_path}")
        water_dist = np.where(water, dist, np.inf)
        snapped_eta, snapped_xi = np.unravel_index(np.argmin(water_dist), water_dist.shape)
        placement_rule = "configured source on land; snapped to nearest mask_rho=1 rho cell"

    return SourcePlacement(
        configured_lon=source_lon,
        configured_lat=source_lat,
        nearest_xi=int(nearest_xi),
        nearest_eta=int(nearest_eta),
        nearest_lon=float(lon[nearest_eta, nearest_xi]),
        nearest_lat=float(lat[nearest_eta, nearest_xi]),
        nearest_is_water=nearest_is_water,
        snapped_xi=int(snapped_xi),
        snapped_eta=int(snapped_eta),
        snapped_lon=float(lon[snapped_eta, snapped_xi]),
        snapped_lat=float(lat[snapped_eta, snapped_xi]),
        snapped_distance_m=float(dist[snapped_eta, snapped_xi]),
        snapped_depth_m=float(depth[snapped_eta, snapped_xi]),
        placement_rule=placement_rule,
    )
