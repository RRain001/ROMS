#!/usr/bin/env python3
"""Shared utilities for case-driven ROMS preprocessing workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
from netCDF4 import Dataset, date2num, num2date
from scipy.ndimage import distance_transform_edt
from scipy.interpolate import RegularGridInterpolator

from case_context import get_case_config_path, get_case_root

ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")
DEFAULT_RAW_GRID = ROOT / "input" / "roms_grid_bathy_500m.nc"
DEFAULT_MASKCLEAN_GRID = ROOT / "input" / "roms_grid_bathy_500m_maskclean.nc"
DEFAULT_MASKCLEAN_SMOOTHED_GRID = ROOT / "input" / "roms_grid_bathy_500m_maskclean_smoothed.nc"
DEFAULT_SMOOTHED_GRID = ROOT / "input" / "roms_grid_bathy_500m_smoothed.nc"
PREPROCESSING_VERSION = "20260628_boundary_audit_v1"


@dataclass(frozen=True)
class VerticalConfig:
    N: int
    theta_s: float
    theta_b: float
    Tcline: float
    Hmin_m: float
    Vtransform: int
    Vstretching: int

    @property
    def hc(self) -> float:
        return min(self.Hmin_m, self.Tcline) if self.Vtransform == 1 else self.Tcline


@dataclass(frozen=True)
class GridData:
    path: Path
    lon_rho: np.ndarray
    lat_rho: np.ndarray
    lon_u: np.ndarray
    lat_u: np.ndarray
    lon_v: np.ndarray
    lat_v: np.ndarray
    h: np.ndarray
    mask_rho: np.ndarray
    angle: np.ndarray
    pm: np.ndarray
    pn: np.ndarray


def load_project_params() -> dict:
    params = json.loads(PARAMS.read_text())
    if "case" not in params:
        project_cfg = params.get("project", {})
        default_name = project_cfg.get("name", ROOT.name)
        params["case"] = {
            "name": default_name,
            "slug": default_name,
            "title": project_cfg.get("description", default_name),
            "cpp_name": default_name.upper().replace("-", "_"),
            "description": project_cfg.get("description", default_name),
        }
    if "naming" not in params:
        slug = params["case"].get("slug", ROOT.name)
        params["naming"] = {
            "grid_subset_name": f"gebco_{slug}.nc",
            "roms_prefix": slug,
            "source_csv_name": f"{slug}_source_discharge.csv",
            "source_timeseries_name": f"{slug}_source_hourly.csv",
        }
    params.setdefault("ocean", {})
    params["ocean"].setdefault("default_source", "hycom")
    params.setdefault("vertical", {})
    params["vertical"].setdefault("N", 30)
    params["vertical"].setdefault("theta_s", 5.0)
    params["vertical"].setdefault("theta_b", 0.8)
    params["vertical"].setdefault("Tcline_m", 50.0)
    params["vertical"].setdefault("Hmin_m", 10.0)
    params["vertical"].setdefault("Vtransform", 2)
    params["vertical"].setdefault("Vstretching", 4)
    return params


def to_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def summarize_numeric(values: np.ndarray, mask: np.ndarray | None = None) -> dict[str, object]:
    data = np.asarray(values, dtype=float)
    if mask is not None:
        wet = np.asarray(mask, dtype=bool)
        if data.ndim != wet.ndim:
            wet = np.broadcast_to(wet, data.shape)
        subset = data[wet]
    else:
        subset = data.reshape(-1)
    finite = subset[np.isfinite(subset)]
    out: dict[str, object] = {
        "count": int(subset.size),
        "finite_count": int(np.isfinite(subset).sum()),
        "nan_count": int(np.isnan(subset).sum()),
        "min": None,
        "max": None,
        "mean": None,
    }
    if finite.size:
        out["min"] = float(np.min(finite))
        out["max"] = float(np.max(finite))
        out["mean"] = float(np.mean(finite))
    return out


def load_vertical_config() -> VerticalConfig:
    vertical = load_project_params()["vertical"]
    return VerticalConfig(
        N=int(vertical["N"]),
        theta_s=float(vertical["theta_s"]),
        theta_b=float(vertical["theta_b"]),
        Tcline=float(vertical["Tcline_m"]),
        Hmin_m=float(vertical["Hmin_m"]),
        Vtransform=int(vertical["Vtransform"]),
        Vstretching=int(vertical["Vstretching"]),
    )


def derive_staggered_masks(mask_rho: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = np.asarray(mask_rho, dtype=np.int8)
    wet = mask == 1
    mask_u = (wet[:, :-1] & wet[:, 1:]).astype(np.int8)
    mask_v = (wet[:-1, :] & wet[1:, :]).astype(np.int8)
    mask_psi = (wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]).astype(np.int8)
    return mask_u, mask_v, mask_psi


def resolve_grid_path(
    grid_arg: str | None = None,
    prefer_smoothed: bool = True,
    prefer_maskclean: bool = True,
) -> Path:
    if grid_arg:
        grid_path = Path(grid_arg).expanduser().resolve()
        if not grid_path.exists():
            raise SystemExit(f"grid file not found: {grid_path}")
        return grid_path
    if prefer_smoothed and DEFAULT_MASKCLEAN_SMOOTHED_GRID.exists():
        return DEFAULT_MASKCLEAN_SMOOTHED_GRID
    if prefer_smoothed and DEFAULT_SMOOTHED_GRID.exists():
        return DEFAULT_SMOOTHED_GRID
    if prefer_maskclean and DEFAULT_MASKCLEAN_GRID.exists():
        return DEFAULT_MASKCLEAN_GRID
    if DEFAULT_RAW_GRID.exists():
        return DEFAULT_RAW_GRID
    raise SystemExit(
        f"no active grid found under {ROOT / 'input'}\n"
        "expected one of: "
        f"{DEFAULT_MASKCLEAN_SMOOTHED_GRID}, {DEFAULT_SMOOTHED_GRID}, "
        f"{DEFAULT_MASKCLEAN_GRID}, or {DEFAULT_RAW_GRID}"
    )


def load_grid(grid_path: Path) -> GridData:
    with Dataset(grid_path) as ds:
        lon_rho = np.asarray(ds.variables["lon_rho"][:, :], dtype=float)
        lat_rho = np.asarray(ds.variables["lat_rho"][:, :], dtype=float)
        h = np.asarray(ds.variables["h"][:, :], dtype=float)
        mask_rho = np.asarray(ds.variables["mask_rho"][:, :], dtype=np.int8)
        angle = np.asarray(ds.variables["angle"][:, :], dtype=float)
        pm = np.asarray(ds.variables["pm"][:, :], dtype=float)
        pn = np.asarray(ds.variables["pn"][:, :], dtype=float)
        lon_u = np.asarray(ds.variables["lon_u"][:, :], dtype=float)
        lat_u = np.asarray(ds.variables["lat_u"][:, :], dtype=float)
        lon_v = np.asarray(ds.variables["lon_v"][:, :], dtype=float)
        lat_v = np.asarray(ds.variables["lat_v"][:, :], dtype=float)
    return GridData(
        path=grid_path,
        lon_rho=lon_rho,
        lat_rho=lat_rho,
        lon_u=lon_u,
        lat_u=lat_u,
        lon_v=lon_v,
        lat_v=lat_v,
        h=h,
        mask_rho=mask_rho,
        angle=angle,
        pm=pm,
        pn=pn,
    )


def sigma_stretching(vertical: VerticalConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = vertical.N
    ds = 1.0 / float(n)
    sc_w = np.empty(n + 1, dtype=float)
    Cs_w = np.empty(n + 1, dtype=float)
    sc_r = np.empty(n, dtype=float)
    Cs_r = np.empty(n, dtype=float)

    sc_w[n] = 0.0
    Cs_w[n] = 0.0
    sc_w[0] = -1.0
    Cs_w[0] = -1.0

    if vertical.Vstretching == 4:
        for k in range(n - 1, 0, -1):
            s = ds * (k - n)
            sc_w[k] = s
            c_sur = (1.0 - math.cosh(vertical.theta_s * s)) / (math.cosh(vertical.theta_s) - 1.0) if vertical.theta_s > 0 else -(s**2)
            if vertical.theta_b > 0:
                c_bot = (math.exp(vertical.theta_b * c_sur) - 1.0) / (1.0 - math.exp(-vertical.theta_b))
                Cs_w[k] = c_bot
            else:
                Cs_w[k] = c_sur
        for k in range(1, n + 1):
            s = ds * ((k - n) - 0.5)
            sc_r[k - 1] = s
            c_sur = (1.0 - math.cosh(vertical.theta_s * s)) / (math.cosh(vertical.theta_s) - 1.0) if vertical.theta_s > 0 else -(s**2)
            if vertical.theta_b > 0:
                c_bot = (math.exp(vertical.theta_b * c_sur) - 1.0) / (1.0 - math.exp(-vertical.theta_b))
                Cs_r[k - 1] = c_bot
            else:
                Cs_r[k - 1] = c_sur
    elif vertical.Vstretching == 2:
        aweight = 1.0
        bweight = 1.0
        for k in range(n - 1, 0, -1):
            s = ds * (k - n)
            sc_w[k] = s
            if vertical.theta_s > 0:
                c_sur = (1.0 - math.cosh(vertical.theta_s * s)) / (math.cosh(vertical.theta_s) - 1.0)
                if vertical.theta_b > 0:
                    c_bot = math.sinh(vertical.theta_b * (s + 1.0)) / math.sinh(vertical.theta_b) - 1.0
                    c_weight = (s + 1.0) ** aweight * (1.0 + (aweight / bweight) * (1.0 - (s + 1.0) ** bweight))
                    Cs_w[k] = c_weight * c_sur + (1.0 - c_weight) * c_bot
                else:
                    Cs_w[k] = c_sur
            else:
                Cs_w[k] = s
        for k in range(1, n + 1):
            s = ds * ((k - n) - 0.5)
            sc_r[k - 1] = s
            if vertical.theta_s > 0:
                c_sur = (1.0 - math.cosh(vertical.theta_s * s)) / (math.cosh(vertical.theta_s) - 1.0)
                if vertical.theta_b > 0:
                    c_bot = math.sinh(vertical.theta_b * (s + 1.0)) / math.sinh(vertical.theta_b) - 1.0
                    c_weight = (s + 1.0) ** aweight * (1.0 + (aweight / bweight) * (1.0 - (s + 1.0) ** bweight))
                    Cs_r[k - 1] = c_weight * c_sur + (1.0 - c_weight) * c_bot
                else:
                    Cs_r[k - 1] = c_sur
            else:
                Cs_r[k - 1] = s
    else:
        raise SystemExit(f"unsupported Vstretching={vertical.Vstretching} for preprocessing utilities")

    return sc_r, Cs_r, sc_w, Cs_w


def sigma_depths(h: np.ndarray, vertical: VerticalConfig, zeta: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if zeta is None:
        zeta = np.zeros_like(h, dtype=float)
    sc_r, Cs_r, sc_w, Cs_w = sigma_stretching(vertical)
    hc = vertical.hc
    hwater = np.asarray(h, dtype=float)
    z_r = np.empty((vertical.N, *hwater.shape), dtype=float)
    z_w = np.empty((vertical.N + 1, *hwater.shape), dtype=float)
    hz = np.empty((vertical.N, *hwater.shape), dtype=float)
    z_w[0, :, :] = -hwater
    if vertical.Vtransform != 2:
        raise SystemExit(f"unsupported Vtransform={vertical.Vtransform} for preprocessing utilities")
    hinv = 1.0 / (hc + hwater)
    for k in range(1, vertical.N + 1):
        cff_r = hc * sc_r[k - 1]
        cff_w = hc * sc_w[k]
        cff2_r = (cff_r + Cs_r[k - 1] * hwater) * hinv
        cff2_w = (cff_w + Cs_w[k] * hwater) * hinv
        z_r[k - 1, :, :] = zeta + (zeta + hwater) * cff2_r
        z_w[k, :, :] = zeta + (zeta + hwater) * cff2_w
        hz[k - 1, :, :] = z_w[k, :, :] - z_w[k - 1, :, :]
    return z_r, z_w, hz


def compute_rx0_rx1(h: np.ndarray, mask_rho: np.ndarray, vertical: VerticalConfig) -> tuple[float, float]:
    _, z_w, _ = sigma_depths(h, vertical)
    rx0 = 0.0
    rx1 = 0.0
    water = mask_rho == 1

    def pairwise_stats(a: tuple[slice, slice], b: tuple[slice, slice]) -> tuple[float, float]:
        nonlocal rx0, rx1
        wet = water[a] & water[b]
        if not np.any(wet):
            return rx0, rx1
        z0a = z_w[0][a][wet]
        z0b = z_w[0][b][wet]
        denom0 = z0a + z0b
        valid0 = np.abs(denom0) > 0
        if np.any(valid0):
            rx0 = max(rx0, float(np.max(np.abs((z0a[valid0] - z0b[valid0]) / denom0[valid0]))))
        for k in range(1, vertical.N + 1):
            zk_a = z_w[k][a][wet]
            zk_b = z_w[k][b][wet]
            zkm1_a = z_w[k - 1][a][wet]
            zkm1_b = z_w[k - 1][b][wet]
            numerator = zk_a - zk_b + zkm1_a - zkm1_b
            denominator = zk_a + zk_b - zkm1_a - zkm1_b
            valid = np.abs(denominator) > 0
            if np.any(valid):
                rx1 = max(rx1, float(np.max(np.abs(numerator[valid] / denominator[valid]))))
        return rx0, rx1

    pairwise_stats((slice(None), slice(1, None)), (slice(None), slice(None, -1)))
    pairwise_stats((slice(1, None), slice(None)), (slice(None, -1), slice(None)))
    return rx0, rx1


def local_rx0(h: np.ndarray, mask_rho: np.ndarray) -> np.ndarray:
    water = mask_rho == 1
    west = np.full(h.shape, np.nan, dtype=float)
    south = np.full(h.shape, np.nan, dtype=float)
    wet_west = water[:, 1:] & water[:, :-1]
    wet_south = water[1:, :] & water[:-1, :]
    west[:, 1:][wet_west] = np.abs((h[:, 1:][wet_west] - h[:, :-1][wet_west]) / (h[:, 1:][wet_west] + h[:, :-1][wet_west]))
    south[1:, :][wet_south] = np.abs((h[1:, :][wet_south] - h[:-1, :][wet_south]) / (h[1:, :][wet_south] + h[:-1, :][wet_south]))
    west = np.where(np.isfinite(west), west, -np.inf)
    south = np.where(np.isfinite(south), south, -np.inf)
    out = np.maximum(west, south)
    out[~np.isfinite(out)] = np.nan
    return out


def infer_variable(ds: Dataset, candidates: Iterable[str]) -> str:
    lowered = {name.lower(): name for name in ds.variables}
    for candidate in candidates:
        if candidate in ds.variables:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    raise KeyError(f"none of {tuple(candidates)} found in {list(ds.variables)[:30]}")


def infer_dimension_role(name: str) -> str | None:
    lowered = name.lower()
    if lowered in {"lon", "longitude", "x"} or "lon" in lowered:
        return "lon"
    if lowered in {"lat", "latitude", "y"} or "lat" in lowered:
        return "lat"
    if lowered in {"depth", "lev", "level", "z"} or "depth" in lowered or lowered.startswith("lev"):
        return "depth"
    if lowered == "time" or lowered.endswith("_time") or "time" in lowered:
        return "time"
    return None


def read_dimensional_variable(
    ds: Dataset,
    variable_name: str,
    lon_name: str,
    lat_name: str,
    depth_name: str | None = None,
    time_index: int | None = None,
) -> np.ndarray:
    var = ds.variables[variable_name]
    raw = var[:]
    if np.ma.isMaskedArray(raw):
        data = np.ma.filled(raw, np.nan).astype(float, copy=False)
    else:
        data = np.asarray(raw, dtype=float)
    dims = list(var.dimensions)
    axes = {infer_dimension_role(dim): index for index, dim in enumerate(dims) if infer_dimension_role(dim)}

    if "time" in axes:
        if time_index is None:
            raise SystemExit(f"{variable_name} contains a time dimension but no time index was provided")
        data = np.take(data, time_index, axis=axes["time"])
        dims.pop(axes["time"])
        axes = {infer_dimension_role(dim): index for index, dim in enumerate(dims) if infer_dimension_role(dim)}

    if depth_name is None:
        expected = ["lat", "lon"]
    else:
        expected = ["depth", "lat", "lon"]
    try:
        transpose_order = [axes[key] for key in expected]
    except KeyError as exc:
        raise SystemExit(f"{variable_name} is missing expected dimension role {exc.args[0]!r}") from exc
    return np.transpose(data, axes=transpose_order)


def normalize_longitudes(source_lon: np.ndarray, target_lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    src = np.asarray(source_lon, dtype=float).copy()
    tgt = np.asarray(target_lon, dtype=float).copy()
    if np.nanmax(src) > 180.0 and np.nanmin(tgt) < 0.0:
        tgt = (tgt + 360.0) % 360.0
    elif np.nanmax(src) <= 180.0 and np.nanmax(tgt) > 180.0:
        src = ((src + 180.0) % 360.0) - 180.0
    return src, tgt


def get_rectilinear_lon_lat(ds: Dataset) -> tuple[np.ndarray, np.ndarray, str, str]:
    lon_name = infer_variable(ds, ("lon", "longitude", "x"))
    lat_name = infer_variable(ds, ("lat", "latitude", "y"))
    lon = np.asarray(ds.variables[lon_name][:], dtype=float)
    lat = np.asarray(ds.variables[lat_name][:], dtype=float)
    if lon.ndim != 1 or lat.ndim != 1:
        raise SystemExit("only rectilinear 1D lon/lat source grids are supported")
    return lon, lat, lon_name, lat_name


def ensure_ascending(coord: np.ndarray, data: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    if coord[0] <= coord[-1]:
        return coord, data
    coord_rev = coord[::-1]
    data_rev = np.flip(data, axis=axis)
    return coord_rev, data_rev


def interpolate_rectilinear_2d(
    lon: np.ndarray,
    lat: np.ndarray,
    values: np.ndarray,
    target_lon: np.ndarray,
    target_lat: np.ndarray,
) -> np.ndarray:
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    values = np.asarray(values, dtype=float)
    lon, values = ensure_ascending(lon, values, axis=-1)
    lat, values = ensure_ascending(lat, values, axis=-2)
    src_lon, tgt_lon = normalize_longitudes(lon, target_lon)
    interp = RegularGridInterpolator((lat, src_lon), values, bounds_error=False, fill_value=np.nan)
    result = interp(np.column_stack([target_lat.ravel(), tgt_lon.ravel()])).reshape(target_lon.shape)
    return result


def interpolate_vertical_vectorized(source_z: np.ndarray, values: np.ndarray, target_z: np.ndarray) -> np.ndarray:
    src_z = np.asarray(source_z, dtype=float)
    vals = np.asarray(values, dtype=float)
    target = np.asarray(target_z, dtype=float)
    if src_z.ndim != 1:
        raise SystemExit("source vertical coordinate must be 1D")
    if src_z[0] > src_z[-1]:
        src_z = src_z[::-1]
        vals = vals[::-1, ...]

    nz = src_z.size
    flat_vals = vals.reshape(nz, -1)
    flat_target = target.reshape(target.shape[0], -1)
    idx = np.searchsorted(src_z, flat_target, side="left")
    idx = np.clip(idx, 1, nz - 1)
    idx0 = idx - 1
    idx1 = idx

    z0 = src_z[idx0]
    z1 = src_z[idx1]
    v0 = np.take_along_axis(flat_vals, idx0, axis=0)
    v1 = np.take_along_axis(flat_vals, idx1, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        weight = np.where(np.abs(z1 - z0) > 0, (flat_target - z0) / (z1 - z0), 0.0)
    out = v0 + weight * (v1 - v0)

    below = flat_target <= src_z[0]
    above = flat_target >= src_z[-1]
    if np.any(below):
        out[below] = flat_vals[0][np.where(below)[1]]
    if np.any(above):
        out[above] = flat_vals[-1][np.where(above)[1]]
    return out.reshape(target.shape)


def fill_rho_field_2d(field: np.ndarray, wet_mask: np.ndarray) -> np.ndarray:
    values = np.asarray(field, dtype=float).copy()
    wet = np.asarray(wet_mask, dtype=bool)
    finite_wet = wet & np.isfinite(values)
    if not np.any(finite_wet):
        raise SystemExit("cannot fill rho 2D field: no finite wet points available")
    _, nearest = distance_transform_edt(~finite_wet, return_indices=True)
    filled = values[nearest[0], nearest[1]]
    return np.asarray(filled, dtype=float)


def fill_rho_field_3d(field: np.ndarray, wet_mask: np.ndarray) -> np.ndarray:
    values = np.asarray(field, dtype=float)
    wet = np.asarray(wet_mask, dtype=bool)
    if values.ndim != 3:
        raise SystemExit("fill_rho_field_3d expects a 3D array")
    out = np.empty_like(values, dtype=float)
    for k in range(values.shape[0]):
        out[k] = fill_rho_field_2d(values[k], wet)
    return out


def zero_masked_uv(field: np.ndarray, wet_mask: np.ndarray) -> np.ndarray:
    values = np.asarray(field, dtype=float).copy()
    wet = np.asarray(wet_mask, dtype=bool)
    if values.ndim == wet.ndim:
        values[~wet] = 0.0
        return values
    expanded = np.broadcast_to(wet, values.shape)
    values[~expanded] = 0.0
    return values


def read_time_values(ds: Dataset, candidates: Iterable[str]) -> tuple[np.ndarray, str, str]:
    time_name = infer_variable(ds, candidates)
    time_var = ds.variables[time_name]
    values = np.asarray(time_var[:], dtype=float)
    units = getattr(time_var, "units", None)
    if not units:
        raise SystemExit(f"time variable {time_name} is missing units")
    calendar = getattr(time_var, "calendar", "standard")
    datetimes = np.asarray(num2date(values, units=units, calendar=calendar), dtype=object)
    return datetimes, units, time_name


def nearest_time_index(times: np.ndarray, target: datetime) -> int:
    deltas = np.array([abs((t - target).total_seconds()) for t in times], dtype=float)
    return int(np.argmin(deltas))


def to_mjd(datetimes: Iterable[datetime]) -> np.ndarray:
    return np.asarray(date2num(list(datetimes), units="days since 1858-11-17 00:00:00", calendar="gregorian"), dtype=float)


def rotate_to_grid(u_east: np.ndarray, v_north: np.ndarray, angle: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u_grid = u_east * np.cos(angle) + v_north * np.sin(angle)
    v_grid = v_north * np.cos(angle) - u_east * np.sin(angle)
    return u_grid, v_grid


def rho_to_u(field: np.ndarray) -> np.ndarray:
    return 0.5 * (field[..., :, :-1] + field[..., :, 1:])


def rho_to_v(field: np.ndarray) -> np.ndarray:
    return 0.5 * (field[..., :-1, :] + field[..., 1:, :])


def hz_to_u(hz: np.ndarray) -> np.ndarray:
    return 0.5 * (hz[..., :, :-1] + hz[..., :, 1:])


def hz_to_v(hz: np.ndarray) -> np.ndarray:
    return 0.5 * (hz[..., :-1, :] + hz[..., 1:, :])


def depth_average(velocity: np.ndarray, hz: np.ndarray) -> np.ndarray:
    numerator = np.sum(velocity * hz, axis=0)
    denominator = np.sum(hz, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(denominator) > 0, numerator / denominator, 0.0)
    return out


def create_time_variable(ds: Dataset, name: str, datetimes: list[datetime], long_name: str) -> None:
    var = ds.createVariable(name, "f8", (name,), zlib=True, complevel=1)
    var.long_name = long_name
    var.units = "days since 1858-11-17 00:00:00"
    var.calendar = "gregorian"
    var[:] = to_mjd(datetimes)
