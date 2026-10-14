#!/usr/bin/env python3
"""Compare fixed-corner bilinear ES3K versus curved-edge conformal pilot.

Both are CANDIDATE diagnostics only. Numeric scientific gate still
requires true GEBCO/GSHHG, nominal angular grid interpretation,
geographic wet boundaries, and ROMS hydrodynamic tests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"Data_pre/nesting"),str(ROOT/"Data_pre/core")]

from es3k_corners import corner_grid
from es3k_conformal import conformal_corner_grid


def produce(out:Path,scale:int)->dict:
    baseline=json.loads((ROOT/"configs/es3k_four_corner_candidate.json").read_text())
    conformal=json.loads((ROOT/"configs/es3k_conformal_candidate.json").read_text())
    b,_,_,bq=corner_grid(baseline,sample_scale=scale)
    c,_,_,cq=conformal_corner_grid(conformal,sample_scale=scale)
    report={
        "status":"GEOMETRY_DIAGNOSTIC_NO_REAL_BATHY_OR_PHYSICS",
        "bilinear_baseline":bq,
        "conformal_cubic":cq,
        "max_orthogonality_improvement_factor":float(
            bq["orthogonality_error_max_deg"]/cq["orthogonality_error_max_deg"]),
        "corner_inputs_match":bq["corner_input_lat_lon"]==cq["corner_input_lat_lon"],
        "scientific_acceptance":"NOT_RUN",
        "actual_1_over_36_angular_mapping":"NOT_IMPLEMENTED",
        "GEBCO_2026_and_GSHHG":"NOT_RUN",
        "ES3K_to_UD1K_hydrodynamics":"NOT_RUN"
    }
    if not report["corner_inputs_match"]:
        raise ValueError("conformal prototype has changed user ES3K corners")
    if cq["orthogonality_gate"]!="PRELIMINARY_PASS_ONLY":
        raise ValueError("WGS84 conformal prototype failed pilot orthogonality gate")
    out.mkdir(parents=True,exist_ok=True)
    (out/"ES3K_conformal_vs_bilinear_quality.json").write_text(
        json.dumps(report,indent=2)+"\n")
    fig,ax=plt.subplots(1,2,figsize=(16,8),layout="constrained")
    for subplot,data,q,title in zip(
        ax,(b,c),(bq,cq),("Bilinear / straight edges",
                         "Conformal polynomial / curved edges")):
        lon,lat=data["lon_rho"],data["lat_rho"]
        stride_x=max(1,lon.shape[1]//22)
        stride_y=max(1,lon.shape[0]//22)
        for i in range(0,lon.shape[1],stride_x):
            subplot.plot(lon[:,i],lat[:,i],lw=.5,c="#5679a6",alpha=.65)
        for j in range(0,lon.shape[0],stride_y):
            subplot.plot(lon[j],lat[j],lw=.5,c="#5679a6",alpha=.65)
        for key,idx in {"W":(0,0),"S":(0,-1),"N":(-1,0),"E":(-1,-1)}.items():
            j,i=idx
            subplot.scatter(lon[j,i],lat[j,i],c="#b44531",s=35,zorder=5)
            subplot.annotate(key,(lon[j,i],lat[j,i]),xytext=(5,6),
                             textcoords="offset points",fontsize=9)
        subplot.set(xlabel="Longitude (E)",ylabel="Latitude (N)",
                    xlim=(120,152),ylim=(30,53))
        subplot.set_title(
            f"{title}\nMax WGS84 orthogonality error = "
            f"{q['orthogonality_error_max_deg']:.3f}°",fontsize=11)
        subplot.grid(alpha=.25)
    fig.suptitle("ES3K | user-specified 4 corners | mesh geometry diagnostics",fontsize=15)
    fig.text(.5,.015,
        "Nominal 1/36° local-metric equivalent only. "
        "Real shoreline/bathymetry, flux nesting and ROMS simulation NOT RUN.",
        ha="center",fontsize=9)
    fig.savefig(out/"ES3K_conformal_vs_bilinear_CANDIDATE.png",dpi=155)
    fig.savefig(out/"ES3K_conformal_vs_bilinear_CANDIDATE.svg")
    plt.close(fig)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--sample-scale",type=int,default=20)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    result=produce(args.output,args.sample_scale)
    print(json.dumps({"status":result["status"],
                      "baseline_max_deg":result["bilinear_baseline"]["orthogonality_error_max_deg"],
                      "conformal_max_deg":result["conformal_cubic"]["orthogonality_error_max_deg"],
                      "factor":result["max_orthogonality_improvement_factor"]},indent=2))
