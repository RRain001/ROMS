"""WGS84 RHO metrics for spherical ROMS grids.

Adjacent geodesic lengths define each RHO spacing: the mean of the two
incident edges inside, and the sole incident edge at the boundary. ROMS
ana_grid.h differentiates reciprocal metrics per *index*, not per metre.
At file edges we use first order one-sided differences, equivalent to a
linearly extrapolated ghost spacing in that same centered stencil. No
periodicity is assumed. Coordinates, orientation and auxiliary x/y are
not changed here.
"""
from __future__ import annotations

import numpy as np
from pyproj import Geod

METRIC_NAMES = ("pm", "pn", "dndx", "dmde")
METHOD = "WGS84 adjacent-edge means; one-sided edge spacing and index derivatives v1"


def compute_grid_metrics(lon_rho: np.ndarray, lat_rho: np.ndarray) -> dict[str, np.ndarray]:
    lon = np.asarray(np.ma.filled(lon_rho, np.nan), dtype=np.float64)
    lat = np.asarray(np.ma.filled(lat_rho, np.nan), dtype=np.float64)
    if lon.ndim != 2 or lon.shape != lat.shape or min(lon.shape) < 2:
        raise ValueError("lon_rho/lat_rho must be matching 2D arrays with at least two points per axis")
    if not np.isfinite(lon).all() or not np.isfinite(lat).all() or (np.abs(lat) > 90).any():
        raise ValueError("invalid or missing longitude/latitude")
    geod = Geod(ellps="WGS84")
    dx_edge = geod.inv(lon[:, :-1], lat[:, :-1], lon[:, 1:], lat[:, 1:])[2]
    dy_edge = geod.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])[2]
    for edge in (dx_edge, dy_edge):
        if not np.isfinite(edge).all() or (edge <= 0).any():
            raise ValueError("geodesic distances must be finite and positive; duplicate grid points")
    dx = np.empty_like(lon)
    dy = np.empty_like(lat)
    dx[:, 0], dx[:, -1] = dx_edge[:, 0], dx_edge[:, -1]
    dx[:, 1:-1] = 0.5 * (dx_edge[:, :-1] + dx_edge[:, 1:])
    dy[0], dy[-1] = dy_edge[0], dy_edge[-1]
    dy[1:-1] = 0.5 * (dy_edge[:-1] + dy_edge[1:])
    return {"pm": 1.0 / dx, "pn": 1.0 / dy,
            "dndx": np.gradient(dy, axis=1, edge_order=1),
            "dmde": np.gradient(dx, axis=0, edge_order=1)}
