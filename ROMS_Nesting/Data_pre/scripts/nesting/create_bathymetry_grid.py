#!/usr/bin/env python3
"""Generate *candidate only* ES3K/UD1K from a real GEBCO subset."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"nesting"))
from bathymetry_grid import build_grid


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry-json",required=True)
    parser.add_argument("--bathymetry",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--min-depth-m",type=float,default=10.0)
    parser.add_argument("--max-source-cells",type=int,default=50_000_000,
                        help="Hard upper limit for cropped source raster, NEVER global GEBCO read")
    parser.add_argument("--gshhg-base",default=None)
    parser.add_argument("--gshhg-resolution",choices=["l","i","h","f","c"],default="h")
    parser.add_argument("--allow-gebco-only-mask",action="store_true",
                        help="Candidate / synthetic only; not a production shoreline approval")
    parser.add_argument("--synthetic-test-only",action="store_true")
    parser.add_argument("--report-json",default=None)
    args=parser.parse_args()
    spec=json.loads(Path(args.geometry_json).read_text())
    report=build_grid(spec,Path(args.bathymetry),Path(args.output),
                      min_depth_m=args.min_depth_m,
                      gshhg_base=Path(args.gshhg_base) if args.gshhg_base else None,
                      gshhg_resolution=args.gshhg_resolution,
                      allow_gebco_only_mask=args.allow_gebco_only_mask,
                      synthetic_fixture=args.synthetic_test_only,
                      max_source_cells=args.max_source_cells)
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True,exist_ok=True)
        Path(args.report_json).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
