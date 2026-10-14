#!/usr/bin/env python3
"""Render a four-corner constrained ES3K *geometry diagnostic*.

This is NOT a production ROMS grid; inspect orthogonality and edge
refinement before running with bathymetry and actual ocean forcing.
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
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"Data_pre/nesting"))
sys.path.insert(0,str(ROOT/"Data_pre/core"))
from es3k_corners import corner_grid


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--geometry-json",type=Path,
                   default=ROOT/"configs/es3k_four_corner_candidate.json")
    p.add_argument("--sample-scale",type=int,default=20)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    spec=json.loads(args.geometry_json.read_text())
    values,dx,dy,report=corner_grid(spec,sample_scale=args.sample_scale)
    args.output.mkdir(parents=True,exist_ok=True)
    report["warning"]="DIAGNOSTIC_ONLY; orthogonality and true rotated 1/36-degree grid NOT YET PASSED"
    (args.output/"ES3K_four_corner_quality.json").write_text(json.dumps(report,indent=2)+"\n")
    lon=values["lon_rho"];lat=values["lat_rho"]
    fig,ax=plt.subplots(figsize=(11,8),layout="constrained")
    ax.set_title("ES3K: user W=121.9°E | four-corner candidate grid (NOT ACCEPTED)",fontsize=13)
    for i in range(0,lon.shape[1],max(1,lon.shape[1]//24)):
        ax.plot(lon[:,i],lat[:,i],lw=.45,color="#536c90",alpha=.6)
    for j in range(0,lon.shape[0],max(1,lon.shape[0]//24)):
        ax.plot(lon[j],lat[j],lw=.45,color="#536c90",alpha=.6)
    for k,(row,col) in {"W":(0,0),"N":(-1,0),"E":(-1,-1),"S":(0,-1)}.items():
        ax.scatter([lon[row,col]],[lat[row,col]],s=25,color="maroon",zorder=5)
        ax.annotate(k,(lon[row,col],lat[row,col]),xytext=(5,5),textcoords="offset points")
    ax.set_xlim(120,152);ax.set_ylim(29,53)
    ax.set_xlabel("Longitude (degrees E)")
    ax.set_ylabel("Latitude (degrees N)")
    ax.grid(alpha=.2)
    ax.text(.02,.02,f"AEQD transfinite pilot; max orthogonality error {report['orthogonality_error_max_deg']:.2f}°\n"
            "True 1/36° rotated system, GEBCO, GSHHG and ROMS physics NOT RUN.",
            transform=ax.transAxes,fontsize=9,va="bottom",
            bbox={"boxstyle":"round","facecolor":"white","alpha":.85})
    fig.savefig(args.output/"ES3K_four_corner_CANDIDATE.png",dpi=155)
    fig.savefig(args.output/"ES3K_four_corner_CANDIDATE.svg")
    plt.close(fig)
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
