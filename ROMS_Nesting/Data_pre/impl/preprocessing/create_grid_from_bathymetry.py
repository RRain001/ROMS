#!/usr/bin/env python3
"""Create a ROMS grid from staged bathymetry for the active case domain."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
from scipy.interpolate import RegularGridInterpolator

from case_context import get_case_config_path, get_case_root
from case_naming import bathymetry_subset_path, load_case_naming
from grid_metrics import compute_grid_metrics, METHOD

ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")


def pick_variable(ds: Dataset, candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in ds.variables:
            return name
    lowered = {name.lower(): name for name in ds.variables}
    for name in candidates:
        if name.lower() in lowered:
            return lowered[name.lower()]
    raise KeyError(f"none of {candidates} found in {list(ds.variables)[:30]}")


def meters_per_degree_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def target_grid(domain: dict[str, float], dx_m: float) -> tuple[np.ndarray, np.ndarray, float, float, int, int]:
    lat_mid = 0.5 * (domain["lat_min"] + domain["lat_max"])
    width_m = (domain["lon_max"] - domain["lon_min"]) * meters_per_degree_lon(lat_mid)
    height_m = (domain["lat_max"] - domain["lat_min"]) * 111_320.0
    lm = math.ceil(width_m / dx_m)
    mm = math.ceil(height_m / dx_m)
    xi_rho = lm + 2
    eta_rho = mm + 2
    lon = np.linspace(domain["lon_min"], domain["lon_max"], xi_rho)
    lat = np.linspace(domain["lat_min"], domain["lat_max"], eta_rho)
    lon_rho, lat_rho = np.meshgrid(lon, lat)
    return lon_rho, lat_rho, width_m, height_m, lm, mm


def read_bathymetry(path: Path, lon_name: str | None, lat_name: str | None, z_name: str | None) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    with Dataset(path) as ds:
        lon_var = lon_name or pick_variable(ds, ("lon", "longitude", "x"))
        lat_var = lat_name or pick_variable(ds, ("lat", "latitude", "y"))
        z_var = z_name or pick_variable(ds, ("elevation", "z", "Band1", "bathymetry", "depth"))
        lon = np.asarray(ds.variables[lon_var][:], dtype=float)
        lat = np.asarray(ds.variables[lat_var][:], dtype=float)
        z = np.asarray(ds.variables[z_var][:], dtype=float)
    if lon.ndim != 1 or lat.ndim != 1:
        raise ValueError("Only rectilinear 1D lon/lat bathymetry grids are supported by this script.")
    if z.shape != (lat.size, lon.size):
        if z.shape == (lon.size, lat.size):
            z = z.T
        else:
            raise ValueError(f"bathymetry shape {z.shape} does not match lat/lon ({lat.size}, {lon.size})")
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        z = z[:, ::-1]
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        z = z[::-1, :]
    return lon, lat, z, z_var


def write_grid(
    out: Path,
    lon_rho: np.ndarray,
    lat_rho: np.ndarray,
    h: np.ndarray,
    mask_rho: np.ndarray,
    width_m: float,
    height_m: float,
    lm: int,
    mm: int,
    source_path: Path,
    source_var: str,
    dx_m: float,
) -> None:
    eta_rho, xi_rho = lon_rho.shape
    out.parent.mkdir(parents=True, exist_ok=True)
    metrics = compute_grid_metrics(lon_rho, lat_rho)
    omega = 7.2921159e-5
    coriolis = 2.0 * omega * np.sin(np.deg2rad(lat_rho))

    with Dataset(out, "w", format="NETCDF4") as ds:
        ds.createDimension("xi_rho", xi_rho)
        ds.createDimension("eta_rho", eta_rho)
        ds.createDimension("xi_u", xi_rho - 1)
        ds.createDimension("eta_u", eta_rho)
        ds.createDimension("xi_v", xi_rho)
        ds.createDimension("eta_v", eta_rho - 1)
        ds.createDimension("xi_psi", xi_rho - 1)
        ds.createDimension("eta_psi", eta_rho - 1)
        ds.title = f"{load_case_naming().title} ROMS grid from staged bathymetry"
        ds.bathymetry_source = str(source_path)
        ds.bathymetry_variable = source_var
        ds.resolution_m = dx_m
        ds.grid_metrics_method = METHOD
        ds.grid_auxiliary_coordinates = "x/y and xl/el retain legacy approximate domain extents; use pm/pn for physical spacing"
        ds.land_mask_rule = "mask_rho=1 where interpolated bathymetry is ocean; 0 on land"

        def create(name: str, dims: tuple[str, ...] = (), dtype: str = "f8"):
            return ds.createVariable(name, dtype, dims, zlib=bool(dims), complevel=1)

        xl = create("xl")
        xl.long_name = "domain length in XI-direction"
        xl.units = "meter"
        xl.assignValue(width_m)
        el = create("el")
        el.long_name = "domain length in ETA-direction"
        el.units = "meter"
        el.assignValue(height_m)
        spherical = create("spherical", dtype="i4")
        spherical.long_name = "grid type logical switch"
        spherical.option_T = "spherical"
        spherical.option_F = "Cartesian"
        spherical.assignValue(1)

        x = np.linspace(0.0, width_m, xi_rho)
        y = np.linspace(0.0, height_m, eta_rho)
        x_rho, y_rho = np.meshgrid(x, y)
        create("x_rho", ("eta_rho", "xi_rho"))[:] = x_rho
        create("y_rho", ("eta_rho", "xi_rho"))[:] = y_rho
        create("x_u", ("eta_u", "xi_u"))[:] = 0.5 * (x_rho[:, :-1] + x_rho[:, 1:])
        create("y_u", ("eta_u", "xi_u"))[:] = 0.5 * (y_rho[:, :-1] + y_rho[:, 1:])
        create("x_v", ("eta_v", "xi_v"))[:] = 0.5 * (x_rho[:-1, :] + x_rho[1:, :])
        create("y_v", ("eta_v", "xi_v"))[:] = 0.5 * (y_rho[:-1, :] + y_rho[1:, :])
        create("x_psi", ("eta_psi", "xi_psi"))[:] = 0.25 * (x_rho[:-1, :-1] + x_rho[1:, :-1] + x_rho[:-1, 1:] + x_rho[1:, 1:])
        create("y_psi", ("eta_psi", "xi_psi"))[:] = 0.25 * (y_rho[:-1, :-1] + y_rho[1:, :-1] + y_rho[:-1, 1:] + y_rho[1:, 1:])

        create("lon_rho", ("eta_rho", "xi_rho"))[:] = lon_rho
        create("lat_rho", ("eta_rho", "xi_rho"))[:] = lat_rho
        create("lon_u", ("eta_u", "xi_u"))[:] = 0.5 * (lon_rho[:, :-1] + lon_rho[:, 1:])
        create("lat_u", ("eta_u", "xi_u"))[:] = 0.5 * (lat_rho[:, :-1] + lat_rho[:, 1:])
        create("lon_v", ("eta_v", "xi_v"))[:] = 0.5 * (lon_rho[:-1, :] + lon_rho[1:, :])
        create("lat_v", ("eta_v", "xi_v"))[:] = 0.5 * (lat_rho[:-1, :] + lat_rho[1:, :])
        create("lon_psi", ("eta_psi", "xi_psi"))[:] = 0.25 * (lon_rho[:-1, :-1] + lon_rho[1:, :-1] + lon_rho[:-1, 1:] + lon_rho[1:, 1:])
        create("lat_psi", ("eta_psi", "xi_psi"))[:] = 0.25 * (lat_rho[:-1, :-1] + lat_rho[1:, :-1] + lat_rho[:-1, 1:] + lat_rho[1:, 1:])

        create("h", ("eta_rho", "xi_rho"), "f4")[:] = h.astype("f4")
        create("f", ("eta_rho", "xi_rho"))[:] = coriolis
        for name, values in metrics.items():
            var = create(name, ("eta_rho", "xi_rho"))
            var.units = "meter-1" if name in ("pm", "pn") else "meter"
            var[:] = values
        create("angle", ("eta_rho", "xi_rho"))[:] = np.zeros((eta_rho, xi_rho))

        mask_u = (mask_rho[:, :-1] * mask_rho[:, 1:]).astype("i1")
        mask_v = (mask_rho[:-1, :] * mask_rho[1:, :]).astype("i1")
        mask_psi = (mask_rho[:-1, :-1] * mask_rho[1:, :-1] * mask_rho[:-1, 1:] * mask_rho[1:, 1:]).astype("i1")
        create("mask_rho", ("eta_rho", "xi_rho"), "i1")[:] = mask_rho.astype("i1")
        create("mask_u", ("eta_u", "xi_u"), "i1")[:] = mask_u
        create("mask_v", ("eta_v", "xi_v"), "i1")[:] = mask_v
        create("mask_psi", ("eta_psi", "xi_psi"), "i1")[:] = mask_psi


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bathymetry", default=str(bathymetry_subset_path()))
    parser.add_argument("--resolution-m", type=float, default=None)
    parser.add_argument("--resolution-key", choices=["pilot", "target"], default="pilot")
    parser.add_argument("--output", default=None)
    parser.add_argument("--lon-var", default=None)
    parser.add_argument("--lat-var", default=None)
    parser.add_argument("--z-var", default=None)
    parser.add_argument("--depth-positive-down", action="store_true")
    parser.add_argument("--min-depth-m", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(PARAMS.read_text())
    # The independent Japan Sea nested flow has its own rotated ES3K
    # and genuinely geographic-axis UD1K grid generator.  Never let
    # this copied legacy axis-aligned/angle=0 generator silently
    # manufacture an incorrect ES3K candidate.
    if cfg.get("case", {}).get("name") == "JAPAN_SEA":
        raise SystemExit(
            "JAPAN_SEA cannot use legacy grid_from_bathymetry (angle=0). "
            "Use Data_pre/scripts/nesting/create_bathymetry_grid.py with "
            "an explicit candidate geometry JSON; I3 grid gate remains open."
        )
    domain = cfg["domain"]
    vertical = cfg["vertical"]
    dx_m = args.resolution_m or (
        domain["pilot_resolution_m"] if args.resolution_key == "pilot" else domain["target_resolution_m"]
    )
    min_depth = args.min_depth_m or vertical.get("Hmin_m", 10.0)
    bathy_path = Path(args.bathymetry)
    if not bathy_path.exists():
        raise SystemExit(
            f"bathymetry file not found: {bathy_path}\n"
            "Stage GEBCO/ETOPO-style NetCDF first, or pass --bathymetry /path/to/file.nc"
        )

    lon_rho, lat_rho, width_m, height_m, lm, mm = target_grid(domain, dx_m)
    lon, lat, z, z_var = read_bathymetry(bathy_path, args.lon_var, args.lat_var, args.z_var)
    interp = RegularGridInterpolator((lat, lon), z, bounds_error=False, fill_value=np.nan)
    sampled = interp(np.column_stack([lat_rho.ravel(), lon_rho.ravel()])).reshape(lat_rho.shape)
    if np.isnan(sampled).any():
        raise SystemExit("bathymetry does not fully cover the target domain")

    if args.depth_positive_down:
        water = sampled > 0.0
        h = sampled
    else:
        water = sampled < 0.0
        h = -sampled
    mask_rho = water.astype(np.int8)
    h = np.where(water, np.maximum(h, min_depth), min_depth)

    out = Path(args.output) if args.output else ROOT / "input" / f"roms_grid_bathy_{int(dx_m)}m.nc"
    print(f"bathymetry={bathy_path}")
    print(f"bathymetry_variable={z_var}")
    print(f"resolution_m={dx_m}")
    print(f"Lm={lm} Mm={mm} xi_rho={lon_rho.shape[1]} eta_rho={lon_rho.shape[0]}")
    print(f"water_fraction={mask_rho.mean():.4f}")
    print(f"h_min={float(h.min()):.3f} h_max={float(h.max()):.3f}")
    print(f"output={out}")
    if args.dry_run:
        print("dry-run only; omit --dry-run to write NetCDF")
        return
    write_grid(out, lon_rho, lat_rho, h, mask_rho, width_m, height_m, lm, mm, bathy_path, z_var, dx_m)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
