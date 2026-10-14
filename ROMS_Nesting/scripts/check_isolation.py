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
    require(p["domain"]["domain_status"] == "REFERENCE_BBOX_ONLY_ROTATED_ES3K_CORNERS_UNRESOLVED", "rotated ES3K incorrectly finalized")

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
    require(es["source_of_corners"]=="USER_SUPPLIED_2026_10_14",
            "ES3K corners attributed to prior paper pixel estimates")
    require(es["angular_grid_generator_status"]=="NOT_IMPLEMENTED",
            "unsupported ES3K 1/36-degree generator prematurely marked ready")
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
    require(grid["grids"][1]["proposed_modification"]["geometry_approval"]=="APPROVED_BY_USER_2026_10_14",
            "UD1K south boundary must remain user approved")
    require(grid["grids"][1]["proposed_modification"]["physics_approval"]=="PENDING_GEBCO_GSHHG_PARENT_BOUNDARY",
            "UD1K southward expansion incorrectly marked physically accepted")
    print("I0 copied-path isolation/config PASS (not a physical ROMS integration test)")

if __name__ == "__main__":
    main()
