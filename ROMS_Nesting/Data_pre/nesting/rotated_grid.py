"""Rotated spherical ROMS C-grid geometry (I2 synthetic prototype).

Uses a WGS84 Lambert conformal conic map to create logically rectangular
rotated xi/eta lines. The map is conformal but *not* globally equal-scale.
All published spacings/angles come from independent WGS84 geodesics;
do not treat projected dx/dy as exact physical spacings. Scientific ES3K
geometry cannot be finalized until the Kim (2020) corners are sourced.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
from pyproj import CRS, Geod, Transformer

_CORE = Path(__file__).resolve().parents[1] / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
from grid_metrics import compute_grid_metrics  # copied nested-only implementation

WGS84 = Geod(ellps="WGS84")


@dataclass(frozen=True)
class RotatedGridSpec:
    center_lon: float
    center_lat: float
    width_points: int
    height_points: int
    dx_m: float
    dy_m: float
    angle_deg: float
    std_parallel_south_deg: float | None = None
    std_parallel_north_deg: float | None = None

    def validate(self) -> None:
        if self.width_points < 3 or self.height_points < 3:
            raise ValueError("at least 3 rho points are required in both directions")
        if not (-180 < self.center_lon <= 180) or not (-85 < self.center_lat < 85):
            raise ValueError("center longitude/latitude outside supported range")
        if not np.isfinite([self.dx_m, self.dy_m, self.angle_deg]).all():
            raise ValueError("nonfinite spacing or rotation")
        if self.dx_m <= 0 or self.dy_m <= 0:
            raise ValueError("spacing must be positive")
        lat1, lat2 = self.standard_parallels
        if not (-89 < lat1 < 89 and -89 < lat2 < 89) or abs(lat1 + lat2) < 1e-7:
            raise ValueError("invalid Lambert standard parallels")

    @property
    def standard_parallels(self) -> tuple[float, float]:
        return (
            self.std_parallel_south_deg if self.std_parallel_south_deg is not None else self.center_lat - 4,
            self.std_parallel_north_deg if self.std_parallel_north_deg is not None else self.center_lat + 4,
        )


def east_north_to_grid(east, north, angle):
    """Vector components in earth East/North -> grid xi/eta, at same point."""
    east, north, angle = np.broadcast_arrays(east, north, angle)
    return east * np.cos(angle) + north * np.sin(angle), -east * np.sin(angle) + north * np.cos(angle)


def grid_to_east_north(u_xi, v_eta, angle):
    """Inverse of east_north_to_grid. Staggered ROMS u/v needs preprocessing first."""
    u_xi, v_eta, angle = np.broadcast_arrays(u_xi, v_eta, angle)
    return u_xi * np.cos(angle) - v_eta * np.sin(angle), u_xi * np.sin(angle) + v_eta * np.cos(angle)


def _east_azimuth(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Grid xi tangent angle (radians) relative to geographic East."""
    bearings = np.empty_like(lon)
    bearings[:, 1:-1] = WGS84.inv(lon[:, :-2], lat[:, :-2], lon[:, 2:], lat[:, 2:])[0]
    bearings[:, 0] = WGS84.inv(lon[:, 0], lat[:, 0], lon[:, 1], lat[:, 1])[0]
    bearings[:, -1] = WGS84.inv(lon[:, -2], lat[:, -2], lon[:, -1], lat[:, -1])[0]
    angle = np.deg2rad(90 - bearings)
    return np.arctan2(np.sin(angle), np.cos(angle))


def create_geometry(spec: RotatedGridSpec) -> dict[str, np.ndarray]:
    """Construct rho/u/v/psi C-grid coordinates with independent geodesic metrics."""
    spec.validate()
    lat1, lat2 = spec.standard_parallels
    map_crs = CRS.from_proj4(
        f"+proj=lcc +lat_1={lat1} +lat_2={lat2} +lat_0={spec.center_lat} "
        f"+lon_0={spec.center_lon} +datum=WGS84 +units=m +no_defs"
    )
    project = Transformer.from_crs("EPSG:4326", map_crs, always_xy=True)
    unproject = Transformer.from_crs(map_crs, "EPSG:4326", always_xy=True)
    cx, cy = project.transform(spec.center_lon, spec.center_lat)
    rot = np.deg2rad(spec.angle_deg)
    cc, ss = np.cos(rot), np.sin(rot)
    ny, nx = spec.height_points, spec.width_points
    levels = {
        "rho": (np.arange(nx), np.arange(ny)),
        "u": (np.arange(nx - 1) + 0.5, np.arange(ny)),
        "v": (np.arange(nx), np.arange(ny - 1) + 0.5),
        "psi": (np.arange(nx - 1) + 0.5, np.arange(ny - 1) + 0.5),
    }
    values: dict[str, np.ndarray] = {}
    for label, (ix, iy) in levels.items():
        xi, eta = np.meshgrid((ix - (nx - 1) / 2) * spec.dx_m,
                              (iy - (ny - 1) / 2) * spec.dy_m)
        xx = cx + xi * cc - eta * ss
        yy = cy + xi * ss + eta * cc
        lon, lat = unproject.transform(xx, yy)
        if not np.isfinite(lon).all() or not np.isfinite(lat).all():
            raise ValueError("projection created nonfinite coordinates")
        values["lon_" + label] = np.asarray(lon)
        values["lat_" + label] = np.asarray(lat)
        # ROMS auxiliary coordinates are local xi/eta distances, in metres.
        values["x_" + label] = xi
        values["y_" + label] = eta

    lon, lat = values["lon_rho"], values["lat_rho"]
    values.update(compute_grid_metrics(lon, lat))
    values["angle"] = _east_azimuth(lon, lat)
    values["f"] = 2 * 7.2921159e-5 * np.sin(np.deg2rad(lat))
    values["mask_rho"] = np.ones((ny, nx), dtype=np.int8)
    values["mask_u"] = np.ones((ny, nx - 1), dtype=np.int8)
    values["mask_v"] = np.ones((ny - 1, nx), dtype=np.int8)
    values["mask_psi"] = np.ones((ny - 1, nx - 1), dtype=np.int8)
    values["h"] = np.full((ny, nx), 100.0)
    return values


def geodesic_quality(grid: dict[str, np.ndarray], target_dx_m: float, target_dy_m: float) -> dict[str, float]:
    lon, lat = grid["lon_rho"], grid["lat_rho"]
    ax, _, dx = WGS84.inv(lon[:, :-1], lat[:, :-1], lon[:, 1:], lat[:, 1:])
    ay, _, dy = WGS84.inv(lon[:-1, :], lat[:-1, :], lon[1:, :], lat[1:, :])
    # Angle between distinct xi and eta neighbors, avoiding projection assumptions.
    interior = np.deg2rad(ax[:-1, :] - ay[:, :-1])
    orth_error_deg = np.rad2deg(np.abs(np.arcsin(np.sin(interior + np.pi / 2))))
    # Use cosine for orthogonality; ±90° produce zero. 
    orth_error_deg = np.rad2deg(np.arcsin(np.clip(np.abs(np.cos(interior)), 0, 1)))
    if not (np.isfinite(dx).all() and np.isfinite(dy).all()):
        raise ValueError("nonfinite geodesic edge length")
    return {
        "dx_relerr_max": float(np.max(np.abs(dx / target_dx_m - 1))),
        "dy_relerr_max": float(np.max(np.abs(dy / target_dy_m - 1))),
        "orthogonality_error_max_deg": float(np.max(orth_error_deg)),
        "angle_min_deg": float(np.rad2deg(grid["angle"]).min()),
        "angle_max_deg": float(np.rad2deg(grid["angle"]).max()),
    }


def write_synthetic_grid(path: Path, spec: RotatedGridSpec) -> dict[str, float]:
    """Write all-water, flat-bottom file for interface testing ONLY."""
    from netCDF4 import Dataset
    values = create_geometry(spec)
    ny, nx = values["lon_rho"].shape
    dims = {
        "rho": ("eta_rho", "xi_rho"), "u": ("eta_u", "xi_u"),
        "v": ("eta_v", "xi_v"), "psi": ("eta_psi", "xi_psi"),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(path, "w", format="NETCDF4") as ds:
        for key, n in (("xi_rho", nx), ("eta_rho", ny), ("xi_u", nx-1),
                       ("eta_u", ny), ("xi_v", nx), ("eta_v", ny-1),
                       ("xi_psi", nx-1), ("eta_psi", ny-1)):
            ds.createDimension(key, n)
        ds.synthetic_test_only = "TRUE — DO NOT USE FOR SCIENCE"
        ds.geometry_method = "WGS84 Lambert conformal projection + geodesic angle/metrics"
        ds.rotation_angle_spec_deg = spec.angle_deg
        for name, value in values.items():
            label = next((suffix for suffix in dims if name.endswith("_" + suffix)), "rho")
            dtype = "i1" if name.startswith("mask_") else "f8"
            ds.createVariable(name, dtype, dims[label])[:] = value
        ds.createVariable("spherical", "i4").assignValue(1)
        ds.createVariable("xl", "f8").assignValue((nx - 1) * spec.dx_m)
        ds.createVariable("el", "f8").assignValue((ny - 1) * spec.dy_m)
    return geodesic_quality(values, spec.dx_m, spec.dy_m)
