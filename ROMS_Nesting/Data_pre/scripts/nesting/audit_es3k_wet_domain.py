#!/usr/bin/env python3
"""Inspect, but do not modify, ES3K wet sea, four straits and open edges."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nesting"))
from es3k_wet_domain_audit import audit_grid, save_report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, required=True,
                   help="Existing ES3K candidate grid.nc")
    p.add_argument("--report-json", type=Path, required=True)
    p.add_argument("--strict-no-yellow-sea-wet", action="store_true",
                   help="Exit code 2 if west-of-Korea probe has wet cells; never changes mask")
    opts = p.parse_args()
    report = audit_grid(opts.grid)
    save_report(report, opts.report_json)
    print(json.dumps({
        "result_status": report["result_status"],
        "wet_rho_points": report["wet_rho_points"],
        "yellow_sea_proxy_wet_rho_points":
            report["region_diagnostics"]["west_of_korea_yellow_sea_proxy"]["wet_rho_points"],
        "review_flags": report["review_flags"],
        "report_json": str(opts.report_json),
        "I3_physics_acceptance": report["I3_physics_acceptance"],
    }, indent=2))
    if (opts.strict_no_yellow_sea_wet and
            report["region_diagnostics"]["west_of_korea_yellow_sea_proxy"]["wet_rho_points"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
