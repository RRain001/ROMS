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
    cfg = ROOT / "Data_pre" / "cases" / "JAPAN_SEA" / "config"
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
    require(grid["grids"][0]["corners_deg"] is None and grid["grids"][2]["domain"] is None,
            "invented ES3K corner or local 300m domain")
    print("I0 copied-path isolation/config PASS (not a physical ROMS integration test)")

if __name__ == "__main__":
    main()
