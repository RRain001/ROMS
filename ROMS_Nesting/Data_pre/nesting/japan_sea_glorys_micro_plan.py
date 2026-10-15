"""Bounded, opt-in REAL GLORYS12V1 small-sample plan for Japan Sea.

Default command performs *NO* API/network calls. It records the exact
small request independently from the full ES3K nested-grid download
workflow, which must NOT be invoked while dates and forcing are pending.

Only --execute with separate Copernicus Marine account credentials already
installed may download. The CDSAPI_KEY Secret used for ERA5 cannot log in
to Copernicus Marine. Never echo/authenticate/print either credential.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil

import numpy as np
from netCDF4 import Dataset, num2date

# Real Copernicus GLORYS MY daily range. This reference is a TEST window,
# NOT an approved 2018 scientific simulation.
SOURCE_PRODUCT="GLOBAL_MULTIYEAR_PHY_001_030"
SOURCE_DATASET="cmems_mod_glo_phy_my_0.083deg_P1D-m"
SOURCE_VARIABLES_3D=("thetao","so","uo","vo")
SOURCE_VARIABLES_2D=("zos",)
TEST_BOUNDS=(129.75,130.25,36.75,37.25)  # west,east,south,north
TEST_TIMES=(datetime(2018,1,1,12),datetime(2018,1,3,12))
TEST_DEPTH_MAX_M=300.
MAX_SAVED_FILE_BYTES=5*1024*1024


def plan()->dict:
    west,east,south,north=TEST_BOUNDS
    begin,end=TEST_TIMES
    return {
        "mode":"SMALL_REAL_MARINE_REQUEST_PLAN_NOT_EXECUTED",
        "source_product":SOURCE_PRODUCT,"source_dataset":SOURCE_DATASET,
        "test_window_not_production":[begin.isoformat(),end.isoformat()],
        "longitude_latitude_bbox":[west,east,south,north],
        "max_depth_m":TEST_DEPTH_MAX_M,
        "all_variables":list(SOURCE_VARIABLES_3D+SOURCE_VARIABLES_2D),
        "requested_days":(end-begin).total_seconds()/86400.,
        "max_accepted_output_file_bytes":MAX_SAVED_FILE_BYTES,
        "auth_service":"COPERNICUS_MARINE_SEPARATE_FROM_ERA5_CDSAPI_KEY",
        "no_full_ES3K_download":True,
        "no_ERA5_download":True,
        "no_roms_integration":True,
        "true_ocean_observations":"NOT_DOWNLOADED",
    }


def validate_small_plan(config:dict)->dict:
    """Lock exact fixture scope; no user-supplied 2024 production bounds."""
    want=plan()
    immutable=("source_product","source_dataset","test_window_not_production",
               "longitude_latitude_bbox","max_depth_m","all_variables",
               "max_accepted_output_file_bytes","requested_days")
    for key in immutable:
        if config.get(key)!=want[key]:
            raise ValueError(f"unsafe GLORYS sample request differs from capped {key}")
    if not config["no_full_ES3K_download"] or not config["no_roms_integration"]:
        raise ValueError("full simulation/download mode not allowed")
    return want


def audit_downloaded_sample(path:Path)->dict:
    """Read bounded true NetCDF from Copernicus; never create synthetic real data."""
    path=Path(path)
    if not path.is_file():
        raise ValueError("GLORYS small NetCDF source not found")
    size=path.stat().st_size
    if size<400 or size>MAX_SAVED_FILE_BYTES:
        raise ValueError("GLORYS subset exceeds 5MiB safety limit or is empty")
    with Dataset(path) as f:
        for name in SOURCE_VARIABLES_3D+SOURCE_VARIABLES_2D:
            if name not in f.variables:
                raise ValueError(f"real GLORYS micro sample missing {name}")
        for axis in ("time","depth","latitude","longitude"):
            if axis not in f.variables or axis not in f.dimensions:
                raise ValueError(f"GLORYS subset missing coordinate {axis}")
        lon=np.asarray(f["longitude"][:],dtype=float)
        lat=np.asarray(f["latitude"][:],dtype=float)
        depth=np.asarray(f["depth"][:],dtype=float)
        if any(x.ndim!=1 or len(x)<2 or not np.isfinite(x).all() for x in (lon,lat,depth)):
            raise ValueError("expected finite rectilinear GLORYS horizontal/vertical grid")
        if not(np.diff(lon)>0).all() or not(np.diff(lat)>0).all() or not(np.diff(depth)>0).all():
            raise ValueError("GLORYS coordinate ordering invalid")
        if lon.min()>130. or lon.max()<130. or lat.min()>37. or lat.max()<37.:
            raise ValueError("GLORYS micro source does not cover central sea sample")
        if lon.min()<TEST_BOUNDS[0]-.09 or lon.max()>TEST_BOUNDS[1]+.09 or lat.min()<TEST_BOUNDS[2]-.09 or lat.max()>TEST_BOUNDS[3]+.09:
            raise ValueError("GLORYS downloaded region unexpectedly exceeds capped box")
        if depth.min()<0 or depth.max()>TEST_DEPTH_MAX_M+50:
            raise ValueError("GLORYS micro depths extend beyond cap")
        t=f["time"]
        if t.dimensions!=("time",) or not isinstance(getattr(t,"units",None),str):
            raise ValueError("GLORYS real time must have CF epoch")
        values=np.asarray(t[:],dtype=float)
        if len(values)<2 or len(values)>5 or not np.isfinite(values).all() or not (np.diff(values)>0).all():
            raise ValueError("GLORYS sample has unexpected temporal coverage")
        dates=num2date(values,t.units,calendar=getattr(t,"calendar","standard"))
        # GLORYS daily mean stored at 12 UTC, len=3 expected; do not
        # constrain to exact day due to minor product calendar differences.
        first,last=dates[0],dates[-1]
        first_iso=str(first);last_iso=str(last)
        if not(first.year==2018 and last.year==2018 and first.month==1 and last.month==1 and first.day<=3 and last.day<=4):
            raise ValueError("GLORYS samples do not represent short Jan 2018 test window")
        source_fields={}
        nearest_lon=int(np.argmin(abs(lon-130.)))
        nearest_lat=int(np.argmin(abs(lat-37.)))
        for name in SOURCE_VARIABLES_3D+SOURCE_VARIABLES_2D:
            var=f[name]
            wanted=(("time","depth","latitude","longitude")
                    if name in SOURCE_VARIABLES_3D else
                    ("time","latitude","longitude"))
            if var.dimensions!=wanted:
                raise ValueError(f"GLORYS {name} variables not in known staged layout")
            if var.shape[0]!=len(values):
                raise ValueError("GLORYS source time length mismatch")
            # Only inspect tiny geographic slabs, not large production fields.
            sample=(var[0,:,nearest_lat,nearest_lon] if name in SOURCE_VARIABLES_3D
                    else var[0,nearest_lat,nearest_lon])
            values_at_site=np.asarray(np.ma.filled(np.ma.asarray(sample,dtype=float),np.nan))
            if not np.isfinite(values_at_site).any():
                raise ValueError(f"GLORYS {name} has no ocean data at central test point")
            if not str(getattr(var,"units","")).strip():
                raise ValueError(f"GLORYS {name} has no physical units")
            source_fields[name]=str(var.units)
        return {
            "status":"REAL_GLORYS_JAPAN_SEA_MINISUBSET_SOURCE_ADMITTED",
            "source_dataset":SOURCE_DATASET,"file_bytes":size,
            "variable_units":source_fields,
            "time_frames":len(values),"first_CF_time":first_iso,"last_CF_time":last_iso,
            "bbox_actual":[float(lon.min()),float(lon.max()),float(lat.min()),float(lat.max())],
            "depth_count":len(depth),"max_source_depth_m":float(depth.max()),
            "physical_parent_ES3K_history":"NOT_RUN",
            "actual_ES3K_or_UD1K_ROMs_integration":"NOT_RUN",
        }


def execute_single_micro_download(out:Path)->dict:
    """Only explicit, bounded external download; uses EXISTING staged downloader.

    Reuses existing Copernicus CLI 3D/2D fallback and CF daily time
    normalization. A machine MUST already have Marine credentials.
    """
    if not(os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and
           os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")):
        raise ValueError("Copernicus Marine account credentials absent; ERA5 CDSAPI_KEY is NOT a Marine login")
    if not shutil.which("copernicusmarine"):
        raise ValueError("copernicusmarine executable absent (opt-in download disabled)")
    out=Path(out)
    if out.exists():
        raise ValueError("refuse to overwrite an existing data file")
    if out.suffix.lower()!=".nc":
        raise ValueError("small real Copernicus output must be .nc")
    # Existing downloaded and normalized staged GLORYS route; never the
    # full domain 'download_glorys12v1_staged.main()'.
    from tempfile import TemporaryDirectory
    from sys import path as module_path
    root=Path(__file__).resolve().parents[1]
    for p in (root/"core",root/"impl"/"preprocessing"):
        if str(p) not in module_path:
            module_path.insert(0,str(p))
    from staged_data_utils import BoundingBox
    from download_glorys12v1_staged import TimeWindow,merged_subset_with_2d3d_fallback,safe_to_netcdf
    west,east,south,north=TEST_BOUNDS
    bbox=BoundingBox(west=west,east=east,south=south,north=north)
    cfg={"dataset_id_daily":SOURCE_DATASET,"variables_3d":list(SOURCE_VARIABLES_3D),
         "variables_2d":list(SOURCE_VARIABLES_2D),"maximum_depth":TEST_DEPTH_MAX_M,
         "time_mean_center":"12:00:00"}
    out.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=str(out.parent)) as tmp:
        merged=merged_subset_with_2d3d_fallback(
            "copernicusmarine",cfg,bbox,TimeWindow(*TEST_TIMES),Path(tmp),"micro_subset.nc")
        merged.attrs.update({
            "source_dataset":SOURCE_DATASET,"source_product":SOURCE_PRODUCT,
            "status":"REAL_COPERNICUS_GLORYS_TEST_ONLY_NOT_PRODUCTION",
            "requested_bounds":str(TEST_BOUNDS),
            "requested_time_window":str(TEST_TIMES),
        })
        staged=Path(tmp)/"REAL_GLORYS_MICRO_staged.nc"
        safe_to_netcdf(merged,staged)
        if staged.stat().st_size>MAX_SAVED_FILE_BYTES:
            raise ValueError("actual GLORYS sample exceeded 5MiB file limit; refusing promotion")
        report=audit_downloaded_sample(staged)
        staged.replace(out)
    return report


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan-json",type=Path,required=True)
    p.add_argument("--execute",action="store_true",
                   help="opt in to small authenticated Marine download; never used in routine CI")
    p.add_argument("--output",type=Path,default=None)
    args=p.parse_args()
    configured=validate_small_plan(plan())
    if args.execute and args.output is None:
        raise SystemExit("explicit --output is required for a real micro download")
    if args.plan_json.exists():
        raise SystemExit("refuse to overwrite existing GLORYS request plan")
    args.plan_json.parent.mkdir(parents=True,exist_ok=True)
    if args.execute:
        result=execute_single_micro_download(args.output)
        configured["download_result"]=result
        configured["mode"]="REAL_SMALL_DOWNLOAD_EXECUTED"
        configured["true_ocean_observations"]="REAL_GLORYS_REANALYSIS_SMALL_SUBSET"
    args.plan_json.write_text(json.dumps(configured,indent=2)+"\n",encoding="utf-8")
    print("JAPAN_SEA_GLORYS_BOUNDED_MICRO",json.dumps({
        "mode":configured["mode"],"variable_count":len(SOURCE_VARIABLES_3D+SOURCE_VARIABLES_2D),
        "max_file_MiB":5,"roms_model":"NOT_RUN"}))


if __name__=="__main__":
    main()
