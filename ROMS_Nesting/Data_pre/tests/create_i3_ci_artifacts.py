#!/usr/bin/env python3
"""Generate archived I3 synthetic proof files; never production ES3K/UD1K."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[0]))
from test_bathymetry_grid import ES,UD,make_fixture

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from bathymetry_grid import build_grid


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    args=p.parse_args()
    root=Path(args.output)
    root.mkdir(parents=True,exist_ok=True)
    bathy=root/"synthetic_gebco_fixture.nc"
    make_fixture(bathy)
    reports=[]
    for spec in (ES,UD):
        out=root/(spec["grid_id"]+"_SYNTHETIC_CANDIDATE.nc")
        report=build_grid(spec,bathy,out,allow_gebco_only_mask=True,synthetic_fixture=True)
        assert report["status"]=="CANDIDATE_NOT_VALIDATED_FOR_ROMS"
        assert report["quality"]["orthogonality_error_max_deg"]<0.1
        reports.append(report)
    (root/"I3_Synthetic_Report.json").write_text(json.dumps({
        "scientific_gate":"NOT_RUN",
        "real_geography":"NOT_USED",
        "real_GSHHG":"NOT_USED",
        "ES3K_Kim_2020_exact_geometry":"UNKNOWN",
        "real_parent_to_child_forcing":"NOT_RUN",
        "artifacts":reports,
    },indent=2)+"\n")
    print(json.dumps(reports,indent=2))


if __name__=="__main__":
    main()
