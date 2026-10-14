#!/usr/bin/env python3
"""Preflight ES3K/UD1K geometric containment and wet open boundaries."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"nesting"))
from validate_nesting_geometries import check_pair

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent-grid",required=True)
    p.add_argument("--child-grid",required=True)
    p.add_argument("--parent-margin-cells",type=int,default=2)
    p.add_argument("--wet-search-cells",type=float,default=2.0)
    p.add_argument("--output-json")
    x=p.parse_args()
    report=check_pair(Path(x.parent_grid),Path(x.child_grid),
                      margin_parent_rho_cells=x.parent_margin_cells,
                      wet_parent_search_cells=x.wet_search_cells)
    if x.output_json:
        target=Path(x.output_json)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    if report["status"]!="PASS_PRELIMINARY_ONLY":
        raise SystemExit(2)

if __name__=="__main__":
    main()
