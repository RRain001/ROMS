#!/usr/bin/env python3
"""Create separately a minimal-change local-slope ES3K candidate; never replace base."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"nesting"))
from es3k_local_slope_projection import local_slope_candidate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report-json",type=Path,required=True)
    p.add_argument("--vertical-config",type=Path,required=True)
    p.add_argument("--rx1-limit",type=float,default=8.0)
    p.add_argument("--max-p99-change-m",type=float,default=350.)
    args=p.parse_args()
    vertical=json.loads(args.vertical_config.read_text())
    result=local_slope_candidate(args.grid,args.output,args.report_json,
                                 vertical=vertical,rx1_limit=args.rx1_limit,
                                 max_p99_abs_depth_change_m=args.max_p99_change_m)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
