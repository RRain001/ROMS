#!/usr/bin/env python3
"""Reproducible 3-level Japan Sea ROMS research-domain SCHEMATIC.

Inputs: source-of-truth user AB, approved UD1K south limit, and a
NON-SCIENTIFIC paper-Fig1 ES3K polygon. Generates PNG, SVG and a
machine-readable geometry preflight; does NOT certify wet GSHHG masks,
production ROMS grids, physics, or offline HTO conservation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from numpy import cos, deg2rad
from pyproj import Geod, Transformer
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[3]
CONF=ROOT/"configs"
WGS84=Geod(ellps="WGS84")


def produce(destination: Path) -> dict:
    from sys import path as syspath
    syspath.insert(0,str(ROOT/"Data_pre/nesting"))
    from l3_square import square_corners

    family=json.loads((CONF/"grid_family.json").read_text())
    es=json.loads((CONF/"es3k_user_corners.json").read_text())
    ud=json.loads((CONF/"ud1k_candidate.json").read_text())
    l3=json.loads((CONF/"l3_coastal_square_candidate.json").read_text())
    if ud["parent_expansion"]!="APPROVED_BY_USER_2026_10_14_GEOMETRY_ONLY":
        raise ValueError("unapproved UD1K southern boundary")
    if l3["side_start_A"]!=[35.545437,129.407703] or l3["side_end_B"]!=[35.974688,129.522766]:
        raise ValueError("user-given L3 fixed AB changed")

    corners=square_corners(l3)["corners_lat_lon"]
    points=es["user_corners_lat_lon"]
    family_es=next(q for q in family["grids"] if q["id"]=="ES3K")
    if family_es["corners_deg"] != points:
        raise ValueError("ES3K user corner config drift")
    outer=[[points[k][1],points[k][0]] for k in ("W","N","E","S")]
    # North-anchored exact integer 1/108 degree geographic lattice.
    step=1/108
    south=ud["lat_max"]-round((ud["lat_max"]-ud["lat_min"])/step)*step
    middle=[[ud["lon_min"],south],[ud["lon_max"],south],
            [ud["lon_max"],ud["lat_max"]],[ud["lon_min"],ud["lat_max"]]]
    inner=[[corners[k][1],corners[k][0]] for k in ("A","B","C","D")]
    if not Polygon(middle).contains(Polygon(inner)):
        raise AssertionError("L3 not inside approved UD1K geographic extent")
    if not Polygon(outer).is_valid or not Polygon(outer).contains(Polygon(middle)):
        raise AssertionError("user ES3K four-corner perimeter invalid or fails to contain UD1K")
    if Polygon([[ud["lon_min"],35.5],[ud["lon_max"],35.5],
                [ud["lon_max"],39.0],[ud["lon_min"],39.0]]).contains(Polygon(inner)):
        raise AssertionError("paper original UD1K south incorrectly contains L3")
    _,_,margin=WGS84.inv(corners["D"][1],corners["D"][0],
                         corners["D"][1],south)
    if margin<=10000:
        raise AssertionError("L3 south buffer under 10 km")
    report={
        "purpose":"SCHEMATIC_ONLY_NOT_A_SCIENTIFIC_ROMS_GRID",
        "ES3K":{"nominal_deg":1/36,"status":es["status"],
                "boundary_authority":"USER_SUPPLIED_2026_10_14",
                "outline_lon_lat":outer,
                "exact_corner_and_rotation_validation":"CORNERS_FIXED_GRID_NOT_GENERATED"},
        "UD1K":{"nominal_deg":1/108,"geometry_approval":"USER_APPROVED",
                "lon_min":ud["lon_min"],"lon_max":ud["lon_max"],
                "lat_north":ud["lat_max"],"lat_south_requested":ud["lat_min"],
                "lat_south_grid":south,
                "GSHHG_wet_mask":"NOT_RUN"},
        "L3":{"nominal_deg":1/324,"AB":"USER_FIXED",
              "C_D":"GEODESICALLY_DERIVED_CANDIDATES",
              "corners_lat_lon":corners,
              "inside_UD1K_geometric_extent":True,
              "south_boundary_gap_km":margin/1000,
              "GSHHG_wet_mask":"NOT_RUN",
              "exact_angular_spacing":"NOT_IMPLEMENTED_LOCAL_METRIC_EQUIVALENT"},
        "parent_child_Bq_flux_conservation":"NOT_RUN",
        "ROMS_hydrodynamics":"NOT_RUN"
    }

    fig,ax=plt.subplots(1,3,figsize=(17,8),layout="constrained")
    fig.suptitle("Japan Sea ROMS: ES3K / UD1K / user-anchored L3 (schematic only)",
                 weight="bold",fontsize=17)
    domains=(("1  ES3K | 1/36 deg | USER CORNERS",(120,152),(30,53),42),
             ("2  UD1K | 1/108 deg | south extended",(126.8,134.8),(35.0,39.4),37),
             ("3  L3 | 1/324 deg | A-B offshore",(129.12,130.28),(35.25,36.18),36))
    colors={"ES3K":"#3d526e","UD1K":"#09819f","L3":"#db673e"}
    for i,(title,xlim,ylim,latitude) in enumerate(domains):
        a=ax[i]
        a.set_xlim(*xlim);a.set_ylim(*ylim)
        a.set_aspect(1/cos(deg2rad(latitude)),adjustable="box")
        a.set_facecolor("#e9f3f8");a.grid(alpha=.3)
        a.set_title(title,fontsize=10)
        a.set_xlabel("Longitude (deg E)")
        a.set_ylabel("Latitude (deg N)")
        for key,coords in (("ES3K",outer),("UD1K",middle),("L3",inner)):
            if i==1 and key=="ES3K" or i==2 and key!="L3":
                continue
            color=colors[key]
            patch=MplPolygon(coords,closed=True,fill=True,fc=color,
                             ec=color,alpha=.12 if key!="L3" else .22)
            a.add_patch(patch)
            seq=coords+[coords[0]]
            a.plot([v[0] for v in seq],[v[1] for v in seq],c=color,
                   ls="--" if key=="ES3K" else "-",lw=2.2)
        if i==1:
            a.axhline(35.5,c="#727c86",ls="--",lw=1,label="Kim UD1K south")
            a.axhline(south,c=colors["UD1K"],ls="-.",lw=1.4)
        if i==2:
            for key,(lat,lon) in corners.items():
                a.plot(lon,lat,marker="o",markersize=5,c=colors["L3"])
                a.annotate(key,(lon,lat),xytext=(4,4),textcoords="offset points",fontsize=9)
            a.axhline(south,c=colors["UD1K"],ls="-.",lw=1)
            a.axhline(35.5,c="#727c86",ls="--",lw=1)
    fig.text(.5,.025,
             f"UD1K south {south:.6f} N; L3 south 35.450754 N (buffer {margin/1000:.1f} km). "
             "Coast/bathymetry NOT assessed. ES3K corners user-supplied; grid not yet built.",
             ha="center",fontsize=9,color="#85504a")
    destination.mkdir(parents=True,exist_ok=True)
    fig.savefig(destination/"Japan_Sea_Three_Grids_CANDIDATE.png",dpi=160)
    fig.savefig(destination/"Japan_Sea_Three_Grids_CANDIDATE.svg")
    plt.close(fig)
    (destination/"three_grid_geometry_preflight.json").write_text(
        json.dumps(report,indent=2)+"\n")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(produce(args.output),indent=2))
