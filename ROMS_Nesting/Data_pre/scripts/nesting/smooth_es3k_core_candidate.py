#!/usr/bin/env python3
"""Write separate slope-smoothed I3 ES3K core candidate (never overwrite source)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nesting"))
from es3k_core_bathymetry_smoothing import smooth_core_candidate

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report-json", type=Path, required=True)
    p.add_argument("--rx0-target", type=float, default=.35)
    p.add_argument("--rx1-target", type=float, default=8.)
    p.add_argument("--max-iter", type=int, default=120)
    p.add_argument("--max-volume-fraction", type=float, default=.02)
    p.add_argument("--vertical-config", type=Path, required=True,
                   help="JSON with explicit N=41, theta_s/b, Tcline/Hmin and Vtransform/stretching")
    a = p.parse_args()
    spec = json.loads(a.vertical_config.read_text())
    result = smooth_core_candidate(
        a.grid, a.output, a.report_json, vertical=spec,
        rx0_target=a.rx0_target, rx1_target=a.rx1_target,
        max_iterations=a.max_iter,
        max_volume_change_fraction=a.max_volume_fraction)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
