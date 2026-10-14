#!/usr/bin/env python3
"""Iteratively smooth bathymetry until rx thresholds are met."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from roms_preprocessing_utils import compute_rx0_rx1, load_grid, load_vertical_config, resolve_grid_path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "input" / "roms_grid_bathy_500m_smoothed.nc"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--rx0-target", type=float, default=0.35)
    parser.add_argument("--rx1-target", type=float, default=8.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--blend", type=float, default=0.85)
    return parser.parse_args()


def smooth_once(h: np.ndarray, water: np.ndarray, hmin: float, blend: float) -> np.ndarray:
    neighbor_sum = np.zeros_like(h, dtype=float)
    neighbor_count = np.zeros_like(h, dtype=float)

    wet_north = water[:-1, :]
    wet_south = water[1:, :]
    wet_west = water[:, :-1]
    wet_east = water[:, 1:]

    neighbor_sum[1:, :] += h[:-1, :] * wet_north
    neighbor_count[1:, :] += wet_north
    neighbor_sum[:-1, :] += h[1:, :] * wet_south
    neighbor_count[:-1, :] += wet_south
    neighbor_sum[:, 1:] += h[:, :-1] * wet_west
    neighbor_count[:, 1:] += wet_west
    neighbor_sum[:, :-1] += h[:, 1:] * wet_east
    neighbor_count[:, :-1] += wet_east

    average = h.copy()
    np.divide(neighbor_sum, neighbor_count, out=average, where=neighbor_count > 0.0)
    out = np.where(water, (1.0 - blend) * h + blend * average, h)
    out = np.where(water, np.maximum(out, hmin), h)
    return out


def main() -> None:
    args = parse_args()
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=False)
    out_path = Path(args.output)
    vertical = load_vertical_config()
    grid = load_grid(grid_path)
    h = grid.h.copy()
    water = grid.mask_rho == 1
    history: list[tuple[int, float, float]] = []

    for iteration in range(args.max_iter + 1):
        rx0, rx1 = compute_rx0_rx1(h, grid.mask_rho, vertical)
        history.append((iteration, rx0, rx1))
        if rx0 <= args.rx0_target and rx1 <= args.rx1_target:
            break
        if iteration == args.max_iter:
            break
        h = smooth_once(h, water, vertical.Hmin_m, args.blend)
    else:
        iteration = args.max_iter

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(grid_path) as src, Dataset(out_path, "w", format="NETCDF4") as dst:
        for name, dimension in src.dimensions.items():
            dst.createDimension(name, len(dimension) if not dimension.isunlimited() else None)
        dst.setncatts({attr: src.getncattr(attr) for attr in src.ncattrs()})
        dst.smoothed_from = str(grid_path)
        dst.smoothing_note = "iterative vectorized 5-point water-cell smoothing with fixed mask and Hmin reapplied"
        dst.rx0_target = args.rx0_target
        dst.rx1_target = args.rx1_target
        dst.smoothing_blend = args.blend
        dst.smoothing_iterations = history[-1][0]
        dst.final_rx0 = history[-1][1]
        dst.final_rx1 = history[-1][2]
        for name, variable in src.variables.items():
            dst_var = dst.createVariable(name, variable.datatype, variable.dimensions, zlib=True, complevel=1)
            dst_var.setncatts({attr: variable.getncattr(attr) for attr in variable.ncattrs()})
            if name == "h":
                dst_var[:] = h.astype(variable.dtype)
            else:
                dst_var[:] = variable[:]
    print(f"source_grid={grid_path}")
    print(f"wrote {out_path}")
    for iteration, rx0, rx1 in history[-5:]:
        print(f"iter={iteration} rx0={rx0:.6f} rx1={rx1:.6f}")
    print(f"met_targets={history[-1][1] <= args.rx0_target and history[-1][2] <= args.rx1_target}")


if __name__ == "__main__":
    main()
