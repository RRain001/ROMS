#!/usr/bin/env python3
"""Run reproducible current UD1K 27-point coastal triangle audit (read-only)."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"nesting"))
from ud1k_wet_triangle_review import review_current


def main():
    a=argparse.ArgumentParser(description=__doc__)
    for field in ("parent-grid","child-grid","preflight-json","gshhg-base","output-json"):
        a.add_argument("--"+field, type=Path, required=True)
    a.add_argument("--gshhg-resolution",choices=("h","f"),default="h")
    o=a.parse_args()
    report=review_current(o.parent_grid,o.child_grid,o.preflight_json,
                          o.gshhg_base,resolution=o.gshhg_resolution)
    o.output_json.parent.mkdir(parents=True,exist_ok=True)
    o.output_json.write_text(json.dumps(report,indent=2)+"\n")
    print("CURRENT_UD1K_27_TRIANGLE_AUDIT: "+
          json.dumps(report["status_counts"],sort_keys=True))
    print("GEOMETRY_AND_GSHHG_COASTLINE_PREFLIGHT_ONLY; ROMS physics NOT_RUN")


if __name__=="__main__":
    main()
