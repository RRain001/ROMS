#!/usr/bin/env python3
"""I0 path/isolation contract test. Run after copying ROMS_Nesting *alone*."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ["ROMS_NESTING_ROOT"] = str(ROOT)
os.environ["ROMS_CASE_NAME"] = "JAPAN_SEA"
os.environ.pop("ROMS_CASE_ROOT", None)
sys.path[0:0] = [str(ROOT / "Data_pre" / "core"), str(ROOT / "ROMS_Build" / "core"), str(ROOT / "ROMS_Run" / "core")]

def within(value: Path, parent: Path) -> bool:
    return value.resolve().is_relative_to(parent.resolve())

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)

def main() -> None:
    # The copied subtree must run without the legacy paths available.
    for name in ("Data_pre", "ROMS_Build", "ROMS_Run", "roms_src/roms"):
        require((ROOT / name).is_dir(), "missing independent copy: " + name)
    cases_root = ROOT / "Data_pre" / "cases"
    cases = {p.name for p in cases_root.iterdir() if p.is_dir()}
    require(cases == {"JAPAN_SEA"}, f"unsafe inherited case configurations: {sorted(cases)}")
    cfg = cases_root / "JAPAN_SEA" / "config"
    for name in ("project_parameters.json", "roms_build_config.json", "roms_run_config.json"):
        require((cfg / name).is_file(), "missing nested-only case config: " + name)
    p = json.loads((cfg / "project_parameters.json").read_text())
    require(p["ocean"]["default_source"] == "glorys12v1", "changed ocean source")
    require(p["vertical"]["N"] == 41, "unexpected sigma levels")
    require(p["domain"]["domain_status"] == "ES3K_USER_SUPPLIED_FOUR_CORNERS_GRID_NOT_GENERATED",
            "ES3K geometric input status inconsistent with user-defined corners")
    require(p["domain"]["lon_min"]==121.9 and p["domain"]["nominal_resolution_deg"]==1/36,
            "ES3K case extent or user-selected angular resolution changed")

    from case_context import resolve_case_context
    from build_context import resolve_build_context
    from run_context import resolve_run_context
    context = resolve_case_context("JAPAN_SEA")
    build = resolve_build_context(case_name="JAPAN_SEA")
    run = resolve_run_context(case_name="JAPAN_SEA", mode="smoke")
    require(context.case_dir == ROOT / "Data_pre" / "cases" / "JAPAN_SEA", "unexpected case config location")
    require(context.case_root == ROOT / "projects" / "JAPAN_SEA", "case writes outside isolated project")
    require(build.roms_src == ROOT / "roms_src" / "roms", "build still targets old ROMS source")
    require(within(build.expected_binary, ROOT / "projects"), "build output outside isolated projects")
    require(within(run.mode.infile, ROOT / "projects"), "run input outside isolated projects")
    require(within(run.mode.log_file, ROOT / "projects"), "run logs outside isolated projects")
    require(within(run.paths.output_dir, ROOT / "projects"), "run output outside isolated projects")
    for module in ("case_context", "build_context", "run_context", "case_naming", "formal_online_workflow"):
        obj = sys.modules.get(module)
        require(obj is not None and within(Path(obj.__file__), ROOT), "legacy Python import: " + module)
    grid = json.loads((ROOT / "configs" / "grid_family.json").read_text())
    require([q["id"] for q in grid["grids"]] == ["ES3K", "UD1K", "L3_300m"], "wrong grid family")
    supplied=json.loads((ROOT/"configs/es3k_user_corners.json").read_text())
    es=grid["grids"][0]
    require(es["corners_deg"] == supplied["user_corners_lat_lon"],
            "user-supplied ES3K corners changed, missing, or in wrong order")
    conformal=json.loads((ROOT/"configs/es3k_conformal_candidate.json").read_text())
    require(conformal["user_corners_lat_lon"]==supplied["user_corners_lat_lon"],
            "ES3K conformal method changed the user's four fixed corners")
    require(conformal["status"]=="PRELIMINARY_ORTHOGONALITY_GATE_ONLY_NOT_PRODUCTION" and
            conformal["exact_angular_resolution"]=="NOT_IMPLEMENTED_LOCAL_METRIC_EQUIVALENT_ONLY",
            "ES3K conformal prototype incorrectly marked physically validated")
    require(es["source_of_corners"]=="USER_SUPPLIED_2026_10_14",
            "ES3K corners attributed to prior paper pixel estimates")
    require(es["angular_grid_generator_status"]=="DIAGNOSTIC_BILINEAR_AND_CONFORMAL_METRIC_EQUIVALENT_NOT_EXACT_1_OVER_36",
            "ES3K diagnostic grid incorrectly claimed exact angular-resolution pass")
    local=grid["grids"][2]["domain"]
    l3_cfg=json.loads((ROOT / "configs" / "l3_coastal_square_candidate.json").read_text())
    require(local is not None and
            local["side_start_A_lat_lon"] == [35.545437,129.407703] and
            local["side_end_B_lat_lon"] == [35.974688,129.522766],
            "user-supplied L3 coastal AB anchors changed or missing")
    require(l3_cfg["side_start_A"] == local["side_start_A_lat_lon"] and
            l3_cfg["side_end_B"] == local["side_end_B_lat_lon"] and
            l3_cfg["offshore_side"]=="right_of_A_to_B" and
            l3_cfg["nominal_resolution_deg"]==1/324,
            "L3 offshore/1-324-degree candidate deviates from user specification")
    ud_cfg=json.loads((ROOT/"configs/ud1k_candidate.json").read_text())
    ud_family=grid["grids"][1]
    require(ud_cfg["geometry_approval"]==
            "USER_UPDATED_NORTH_EAST_ROUNDED_DMS_2026_10_14",
            "UD1K revised E/N DMS bounds are not authoritative")
    require(ud_family["user_defined_bounds_deg"]==[
        ud_cfg["lon_min"],ud_cfg["lon_max"],ud_cfg["lat_min"],ud_cfg["lat_max"]],
        "UD1K family and geometry config disagree about four user bounds")
    require(ud_cfg["angular_boundary_policy"]==
            "ANCHOR_WEST_SOUTH_EXACT_1_OVER_108_ROUNDED_DMS",
            "UD1K grid must fix W/S and match E/N at 0.1 arcsec precision")
    require(ud_cfg["expected_rho_shape_eta_xi"]==[290,438] and
            ud_cfg["expected_xi_intervals"]==437 and
            ud_cfg["expected_eta_intervals"]==289 and
            ud_cfg["actual_lon_step_deg"]==1/108 and
            ud_cfg["actual_lat_step_deg"]==1/108,
            "UD1K must have exact 1/108 degree uniform angular increments")
    require(ud_cfg["requested_bounds_dms"]["east"]=="132°24'42.6\"E" and
            ud_cfg["requested_bounds_dms"]["north"]=="37°38'29.0\"N",
            "UD1K new E/N DMS boundaries changed unexpectedly")
    require(max(abs(ud_cfg["east_offset_from_dms_arcsec"]),
                abs(ud_cfg["north_offset_from_dms_arcsec"]))<0.05,
            "UD1K actual E/N exceed user DMS rounding precision")
    require(ud_family["proposed_modification"]["status"]==
            "SUPERSEDED_BY_NEW_USER_DMS_FOUR_BOUNDARIES",
            "Old 35.35 degree UD1K south limit still treated as authoritative")
    require(ud_family["proposed_modification"]["physical_approval"]==
            "PENDING_GEBCO_GSHHG_PARENT_BOUNDARY",
            "UD1K geometry mistakenly marked physically verified")
    print("I0 copied-path isolation/config PASS (not a physical ROMS integration test)")

if __name__ == "__main__":
    main()
