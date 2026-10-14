#!/usr/bin/env python3
"""Create an idealized all-water ROMS grid for plumbing checks."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import get_case_config_path, get_case_root
from case_naming import load_case_naming

ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")


def compute(resolution_key: str):
    p = json.loads(PARAMS.read_text())
    d = p["domain"]
    res = d["pilot_resolution_m"] if resolution_key == "pilot" else d["target_resolution_m"]
    lat_mid = 0.5 * (d["lat_min"] + d["lat_max"])
    width = (d["lon_max"] - d["lon_min"]) * 111_320.0 * math.cos(math.radians(lat_mid))
    height = (d["lat_max"] - d["lat_min"]) * 111_320.0
    lm = math.ceil(width / res)
    mm = math.ceil(height / res)
    xi_rho = lm + 2
    eta_rho = mm + 2
    lon = np.linspace(d["lon_min"], d["lon_max"], xi_rho)
    lat = np.linspace(d["lat_min"], d["lat_max"], eta_rho)
    lon_rho, lat_rho = np.meshgrid(lon, lat)
    return p, res, lm, mm, width, height, lon_rho, lat_rho


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", choices=["pilot", "target"], default="pilot")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    p, res, lm, mm, width, height, lon_rho, lat_rho = compute(args.resolution)
    eta_rho, xi_rho = lon_rho.shape
    out = ROOT / "input" / f"roms_grid_idealized_{int(res)}m.nc"
    print(f"resolution_m={res}")
    print(f"Lm={lm} Mm={mm} xi_rho={xi_rho} eta_rho={eta_rho} rho_points={xi_rho * eta_rho}")
    print(f"target={out}")
    if not args.write:
        print("dry-run only; add --write to create NetCDF")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(out, "w", format="NETCDF4") as ds:
        ds.createDimension("xi_rho", xi_rho)
        ds.createDimension("eta_rho", eta_rho)
        ds.createDimension("xi_u", xi_rho - 1)
        ds.createDimension("eta_u", eta_rho)
        ds.createDimension("xi_v", xi_rho)
        ds.createDimension("eta_v", eta_rho - 1)
        ds.createDimension("xi_psi", xi_rho - 1)
        ds.createDimension("eta_psi", eta_rho - 1)
        ds.title = f"Idealized {load_case_naming().title} ROMS grid; replace before scientific run"
        ds.warning = "Constant-depth all-water grid, for file plumbing only"
        ds.resolution_m = res

        def create(name, dims, dtype="f8"):
            return ds.createVariable(name, dtype, dims, zlib=True, complevel=1)

        xl = ds.createVariable("xl", "f8")
        xl.long_name = "domain length in XI-direction"
        xl.units = "meter"
        xl.assignValue(width)

        el = ds.createVariable("el", "f8")
        el.long_name = "domain length in ETA-direction"
        el.units = "meter"
        el.assignValue(height)

        spherical = ds.createVariable("spherical", "i4")
        spherical.long_name = "grid type logical switch"
        spherical.option_T = "spherical"
        spherical.option_F = "Cartesian"
        spherical.assignValue(1)

        dx = width / lm
        dy = height / mm
        omega = 7.2921159e-5
        coriolis = 2.0 * omega * np.sin(np.deg2rad(lat_rho))

        x = np.linspace(0.0, width, xi_rho)
        y = np.linspace(0.0, height, eta_rho)
        x_rho, y_rho = np.meshgrid(x, y)
        x_u = 0.5 * (x_rho[:, :-1] + x_rho[:, 1:])
        y_u = 0.5 * (y_rho[:, :-1] + y_rho[:, 1:])
        x_v = 0.5 * (x_rho[:-1, :] + x_rho[1:, :])
        y_v = 0.5 * (y_rho[:-1, :] + y_rho[1:, :])
        x_psi = 0.25 * (x_rho[:-1, :-1] + x_rho[1:, :-1] + x_rho[:-1, 1:] + x_rho[1:, 1:])
        y_psi = 0.25 * (y_rho[:-1, :-1] + y_rho[1:, :-1] + y_rho[:-1, 1:] + y_rho[1:, 1:])

        create("x_rho", ("eta_rho", "xi_rho"))[:] = x_rho
        create("y_rho", ("eta_rho", "xi_rho"))[:] = y_rho
        create("x_u", ("eta_u", "xi_u"))[:] = x_u
        create("y_u", ("eta_u", "xi_u"))[:] = y_u
        create("x_v", ("eta_v", "xi_v"))[:] = x_v
        create("y_v", ("eta_v", "xi_v"))[:] = y_v
        create("x_psi", ("eta_psi", "xi_psi"))[:] = x_psi
        create("y_psi", ("eta_psi", "xi_psi"))[:] = y_psi

        create("lon_rho", ("eta_rho", "xi_rho"))[:] = lon_rho
        create("lat_rho", ("eta_rho", "xi_rho"))[:] = lat_rho
        create("lon_u", ("eta_u", "xi_u"))[:] = 0.5 * (lon_rho[:, :-1] + lon_rho[:, 1:])
        create("lat_u", ("eta_u", "xi_u"))[:] = 0.5 * (lat_rho[:, :-1] + lat_rho[:, 1:])
        create("lon_v", ("eta_v", "xi_v"))[:] = 0.5 * (lon_rho[:-1, :] + lon_rho[1:, :])
        create("lat_v", ("eta_v", "xi_v"))[:] = 0.5 * (lat_rho[:-1, :] + lat_rho[1:, :])
        create("lon_psi", ("eta_psi", "xi_psi"))[:] = 0.25 * (lon_rho[:-1, :-1] + lon_rho[1:, :-1] + lon_rho[:-1, 1:] + lon_rho[1:, 1:])
        create("lat_psi", ("eta_psi", "xi_psi"))[:] = 0.25 * (lat_rho[:-1, :-1] + lat_rho[1:, :-1] + lat_rho[:-1, 1:] + lat_rho[1:, 1:])

        create("h", ("eta_rho", "xi_rho"), "f4")[:] = np.full((eta_rho, xi_rho), 100.0, dtype=np.float32)
        create("f", ("eta_rho", "xi_rho"))[:] = coriolis
        create("pm", ("eta_rho", "xi_rho"))[:] = np.full((eta_rho, xi_rho), 1.0 / dx)
        create("pn", ("eta_rho", "xi_rho"))[:] = np.full((eta_rho, xi_rho), 1.0 / dy)
        create("dndx", ("eta_rho", "xi_rho"))[:] = np.zeros((eta_rho, xi_rho))
        create("dmde", ("eta_rho", "xi_rho"))[:] = np.zeros((eta_rho, xi_rho))
        create("angle", ("eta_rho", "xi_rho"))[:] = np.zeros((eta_rho, xi_rho))

        create("mask_rho", ("eta_rho", "xi_rho"), "i1")[:] = np.ones((eta_rho, xi_rho), dtype=np.int8)
        create("mask_u", ("eta_u", "xi_u"), "i1")[:] = np.ones((eta_rho, xi_rho - 1), dtype=np.int8)
        create("mask_v", ("eta_v", "xi_v"), "i1")[:] = np.ones((eta_rho - 1, xi_rho), dtype=np.int8)
        create("mask_psi", ("eta_psi", "xi_psi"), "i1")[:] = np.ones((eta_rho - 1, xi_rho - 1), dtype=np.int8)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
