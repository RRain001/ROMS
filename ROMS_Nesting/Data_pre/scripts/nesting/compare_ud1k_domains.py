#!/usr/bin/env python3
"""Compare two separate UD1K domain candidates on the same real ES3K grid.

This report is a read-only *geometry and wet-stencil preflight*. It does not
modify either grid, generate a ROMS bry file, or claim physical validation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

NESTING = Path(__file__).resolve().parents[2] / "nesting"
sys.path.insert(0, str(NESTING))
from validate_nesting_geometries import check_pair


def case_summary(spec_path: Path, grid_path: Path, report: dict) -> dict:
    spec = json.loads(spec_path.read_text())
    with Dataset(grid_path) as f:
        lon = np.asarray(f["lon_rho"][:], dtype=float)
        lat = np.asarray(f["lat_rho"][:], dtype=float)
        wet = np.asarray(f["mask_rho"][:], dtype=bool)
    expected = spec.get("expected_rho_shape_eta_xi")
    if expected and list(lon.shape) != expected:
        raise ValueError(f"wrong RHO shape for {grid_path.name}: {lon.shape}, expected {expected}")
    bounds = {
        "west": float(lon.min()), "east": float(lon.max()),
        "south": float(lat.min()), "north": float(lat.max())
    }
    for key, value in zip(("west","east","south","north"),
                          ("lon_min","lon_max","lat_min","lat_max")):
        # User DMS labels have a known 0.0333 arcsec rounding difference.
        if abs(bounds[key] - float(spec[value])) * 3600 > 0.051:
            raise ValueError(f"{grid_path.name}: {key} differs from frozen spec")
    d = report.get("full_wet_parent_quad_stencil", {})
    return {
        "spec_path": str(spec_path),
        "grid_path": str(grid_path),
        "actual_bounds_wsen": bounds,
        "rho_shape_eta_xi": list(lon.shape),
        "rho_wet_cells": int(wet.sum()),
        "rho_land_cells": int((~wet).sum()),
        "rho_wet_fraction": float(wet.mean()),
        "preflight_status": report["status"],
        "full_wet_quad_stencils": d,
        "nearest_wet_max_distance_m": report.get("farthest_nearest_parent_wet_m"),
        "buffered_parent_boundary_gap_min_m": report.get("buffered_parent_boundary_gap_min_m"),
        "physical_nesting_status": "NOT_RUN"
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid", "current-grid", "paper-grid",
                 "current-config", "paper-config",
                 "current-preflight", "output-json"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    current_result = json.loads(args.current_preflight.read_text())
    # The exact same function and one ES3K parent are used for both cases.
    paper_result = check_pair(args.parent_grid, args.paper_grid,
                              margin_parent_rho_cells=2)
    cases = {
        "CURRENT_USER_20261014": case_summary(args.current_config,
                                              args.current_grid, current_result),
        "KIM2020_TABLE1": case_summary(args.paper_config,
                                      args.paper_grid, paper_result)
    }
    a = cases["CURRENT_USER_20261014"]["full_wet_quad_stencils"]
    b = cases["KIM2020_TABLE1"]["full_wet_quad_stencils"]
    same_preflight = (a["without_full_wet_parent_rho_quad"]
                      == b["without_full_wet_parent_rho_quad"])
    record = {
        "comparison": "CURRENT_UD1K_VS_KIM2020_TABLE1_DOMAIN_SAME_ES3K_SOURCE",
        "parent_grid_path": str(args.parent_grid),
        "same_parent_bathymetry_and_coastline": True,
        "child_bathymetry_and_coastline_source": "SAME_GEBCO2026_AND_GSHHG237_NATIVE15S",
        "source_of_paper_bounds": (
            "Kim et al. 2020, Journal of Korean Society of Coastal and "
            "Ocean Engineers 32(6):587-601, Table 1, "
            "DOI 10.9765/KSCOE.2020.32.6.587"),
        "scope": "RHO_WET_OPEN_BOUNDARY_GEOMETRIC_PREFLIGHT_ONLY",
        "cases": cases,
        "comparison_summary": {
            "current_uncovered": int(a["without_full_wet_parent_rho_quad"]),
            "paper_uncovered": int(b["without_full_wet_parent_rho_quad"]),
            "current_wet_boundary": int(a["child_wet_boundary_rho_points"]),
            "paper_wet_boundary": int(b["child_wet_boundary_rho_points"]),
            "current_full_quad_fraction": float(a["fraction_with_full_wet_quad"]),
            "paper_full_quad_fraction": float(b["fraction_with_full_wet_quad"]),
            "same_number_of_uncovered": bool(same_preflight),
            "paper_uncovered_by_side": b["uncovered_by_logical_side_corner_counts_overlap"],
            "paper_static_footprint_preflight": paper_result["status"]
        },
        "original_config_mutated": False,
        "physical_validation": "NOT_RUN"
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    # No expected outcome is imposed: a scientific comparison must capture
    # both a pass and a legitimate failure, without cherry-picking a range.


if __name__ == "__main__":
    main()
