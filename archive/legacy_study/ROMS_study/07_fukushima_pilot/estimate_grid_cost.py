#!/usr/bin/env python3
"""Estimate ROMS grid and output sizes for the Fukushima pilot domain."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def meters_per_degree_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def estimate(lon_min: float, lon_max: float, lat_min: float, lat_max: float, dx_m: float, nlev: int) -> dict[str, float]:
    lat_mid = 0.5 * (lat_min + lat_max)
    width_m = abs(lon_max - lon_min) * meters_per_degree_lon(lat_mid)
    height_m = abs(lat_max - lat_min) * 111_320.0
    xi = math.ceil(width_m / dx_m)
    eta = math.ceil(height_m / dx_m)
    horizontal = xi * eta
    sigma_cells = horizontal * nlev
    one_3d_var_gb = sigma_cells * 4 / 1024**3
    core_3d_record_gb = one_3d_var_gb * 5  # u, v, temp, salt, dye_01; order-of-magnitude only.
    return {
        "dx_m": dx_m,
        "xi_rho_approx": xi,
        "eta_rho_approx": eta,
        "horizontal_cells": horizontal,
        "sigma_cells": sigma_cells,
        "one_float32_3d_var_gb_per_record": one_3d_var_gb,
        "five_core_3d_vars_gb_per_record": core_3d_record_gb,
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(project_root / "config" / "project_parameters.json"),
        help="Path to project_parameters.json",
    )
    parser.add_argument("--resolutions", nargs="*", type=float, default=[50.0, 250.0, 500.0])
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    domain = cfg["domain"]
    nlev = int(cfg.get("vertical", {}).get("N", 21))

    print("Fukushima ROMS grid cost estimate")
    print(f"domain: {domain['lon_min']}E-{domain['lon_max']}E, {domain['lat_min']}N-{domain['lat_max']}N")
    print(f"vertical levels: N={nlev}")
    print()
    for dx in args.resolutions:
        row = estimate(domain["lon_min"], domain["lon_max"], domain["lat_min"], domain["lat_max"], dx, nlev)
        print(f"dx={dx:g} m")
        print(f"  xi_rho x eta_rho approx: {row['xi_rho_approx']} x {row['eta_rho_approx']}")
        print(f"  horizontal cells: {row['horizontal_cells']:,}")
        print(f"  sigma cells: {row['sigma_cells']:,}")
        print(f"  one float32 3D variable per output record: {row['one_float32_3d_var_gb_per_record']:.2f} GiB")
        print(f"  five core 3D variables per output record: {row['five_core_3d_vars_gb_per_record']:.2f} GiB")
        print()

    print("Interpretation:")
    print("- 500 m is appropriate for workflow and first full-domain forcing tests.")
    print("- 250 m may be a reasonable first production candidate if forcing and bathymetry are ready.")
    print("- 50 m should be reserved for a later nested coastal domain unless high-resolution forcing and validation data are available.")


if __name__ == "__main__":
    main()
