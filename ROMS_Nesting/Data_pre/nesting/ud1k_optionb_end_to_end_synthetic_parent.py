"""Actual archived Option B C-grid/mapping -> synthetic parent history -> 28-field bry smoke.

Uses *REAL* GEBCO/GSHHG child Option B grid and original independently
certified RHO/U/V donor records, with an explicitly **ARTIFICIAL ALL-WET
ES3K SOURCE GRID** and tiny synthetic 2-frame history. Real ES3K geography,
coastal wetness, dynamic transport and physical nesting are NOT verified.

The goal is to detect real-manifest schema mismatch, source-donor indexing,
C-grid face target rotation, CF MJD/seconds alignment, and 28 boundary
field/normal-flux arithmetic without large ocean/atmosphere downloads.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime,timedelta
from pathlib import Path

import numpy as np
from netCDF4 import Dataset,date2num

try:
    from ud1k_parent_history_contract import validate_parent_history
    from ud1k_real_optionb_manifest_contract import validate_real_candidate_b,PARENT_RHO_SHAPE,EXPECTED_COUNTS,EXPECTED_NORMAL
    from ud1k_boundary_remap_preview import prepare_boundary_preview
    from ud1k_bry_schema_contract import write_synthetic_schema_fixture
    from ud1k_vertical_flux_primitives import stretching4
except ImportError:
    from .ud1k_parent_history_contract import validate_parent_history
    from .ud1k_real_optionb_manifest_contract import validate_real_candidate_b,PARENT_RHO_SHAPE,EXPECTED_COUNTS,EXPECTED_NORMAL
    from .ud1k_boundary_remap_preview import prepare_boundary_preview
    from .ud1k_bry_schema_contract import write_synthetic_schema_fixture
    from .ud1k_vertical_flux_primitives import stretching4

TIME_UNITS="seconds since 2025-01-01 00:00:00"
TARGET_UNITS="days since 1858-11-17 00:00:00"
TARGET_CALENDAR="gregorian"
PARENT_TIMES=np.array([0.,3600.],dtype=np.float64)
TARGET_TIMES=np.asarray(date2num(
    [datetime(2025,1,1),datetime(2025,1,1,1)],
    units=TARGET_UNITS,calendar=TARGET_CALENDAR),dtype=np.float64)
PARENT_N=3
CHILD_N=4
CHILD_SIGMA={"hc":50.,"theta_s":5.,"theta_b":1.,"Vtransform":2,"Vstretching":4}
SOURCE_SIGMA={"theta_s":5.,"theta_b":1.,"hc":50.,"Tcline":50.}
SOURCE_RHO_SHAPE=PARENT_RHO_SHAPE


def make_explicitly_artificial_parent(grid_path:Path,history_path:Path)->None:
    """Small compressed 2-record constant-column source on 732x464 C-grid.

    ALL wet source cells are intentionally fictional and are NOT any
    substitute for actual ES3K native GSHHG mask or hydrodynamic solution.
    """
    if grid_path.resolve()==history_path.resolve() or grid_path.exists() or history_path.exists():
        raise ValueError("synthetic ES3K parent fixtures must not overwrite any file")
    ny,nx=SOURCE_RHO_SHAPE
    dims={"eta_rho":ny,"xi_rho":nx,"eta_u":ny,"xi_u":nx-1,
          "eta_v":ny-1,"xi_v":nx}
    grid_path.parent.mkdir(parents=True,exist_ok=True)
    with Dataset(grid_path,"w") as g:
        for d,n in dims.items():g.createDimension(d,n)
        for name,eta,xi in (
                ("mask_rho","eta_rho","xi_rho"),
                ("mask_u","eta_u","xi_u"),
                ("mask_v","eta_v","xi_v")):
            g.createVariable(name,"i1",(eta,xi),zlib=True,complevel=1)[:]=1
        y,x=np.indices((ny,nx),dtype=float)
        for name,data in (
                ("h",np.full((ny,nx),2800.,dtype=float)),
                ("angle",np.full((ny,nx),.12,dtype=float)),
                ("lon_rho",128.+x*.006),
                ("lat_rho",35.+y*.006)):
            g.createVariable(name,"f8",("eta_rho","xi_rho"),zlib=True,complevel=1)[:]=data
        g.setncattr("source_status","FICTIONAL_ALL_WET_PARENT_GRID_NOT_ACTUAL_ES3K")
        g.setncattr("WARNING","Synthetic index geometry only; NOT actual GEBCO/GSHHG ES3K source mask")
    with Dataset(history_path,"w") as h:
        h.createDimension("ocean_time",None)
        h.createDimension("s_rho",PARENT_N)
        h.createDimension("s_w",PARENT_N+1)
        for dim,length in dims.items():h.createDimension(dim,length)
        t=h.createVariable("ocean_time","f8",("ocean_time",))
        t.units=TIME_UNITS;t.calendar="gregorian";t[:]=PARENT_TIMES
        for name,val in {"Vtransform":2,"Vstretching":4,**SOURCE_SIGMA}.items():
            v=h.createVariable(name,"i4" if name in ("Vtransform","Vstretching") else "f8")
            v.assignValue(val)
        for at,d,svar,cvar in (("rho","s_rho","s_rho","Cs_r"),
                               ("w","s_w","s_w","Cs_w")):
            sigma,cs=stretching4(PARENT_N,SOURCE_SIGMA["theta_s"],
                                SOURCE_SIGMA["theta_b"],at=at)
            h.createVariable(svar,"f8",(d,))[:]=sigma
            h.createVariable(cvar,"f8",(d,))[:]=cs
        fields={
            "zeta":(("ocean_time","eta_rho","xi_rho"),(.2,.4)),
            "temp":(("ocean_time","s_rho","eta_rho","xi_rho"),(15.,16.)),
            "salt":(("ocean_time","s_rho","eta_rho","xi_rho"),(34.,34.2)),
            "u":(("ocean_time","s_rho","eta_u","xi_u"),(.15,.20)),
            "v":(("ocean_time","s_rho","eta_v","xi_v"),(-.05,-.06)),
            "ubar":(("ocean_time","eta_u","xi_u"),(.15,.20)),
            "vbar":(("ocean_time","eta_v","xi_v"),(-.05,-.06)),
        }
        for name,(axis,values) in fields.items():
            var=h.createVariable(name,"f4",axis,zlib=True,complevel=1,fill_value=1.e35)
            for idx,value in enumerate(values):var[idx,...]=value
        h.setncattr("source_status","FICTIONAL_ALL_WET_PARENT_TIME_HISTORY_NOT_ROMs")
        h.setncattr("WARNING","Synthetic short source, does not represent actual ES3K physics")


def run_artificial_parent_on_real_optionb(child_grid:Path,rho_json:Path,
                                         uv_json:Path,output_dir:Path)->dict:
    """Execute independent archived-grid manifest admission and complete remap."""
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    static=validate_real_candidate_b(child_grid,rho_json,uv_json)
    if static["option_b_status"]!="COMPARISON_CANDIDATE_NOT_ACTIVE":
        raise ValueError("attempted promotion of original candidate B grid")
    parent=out/"SYNTHETIC_all_wet_732x464_ES3K_grid.nc"
    history=out/"SYNTHETIC_two_time_ES3K_history.nc"
    mapped=out/"SYNTHETIC_only_real_optionb_28_field_bry.nc"
    if any(x.exists() for x in (parent,history,mapped)):
        raise ValueError("refuse to overwrite existing synthetic or production data")
    make_explicitly_artificial_parent(parent,history)
    admitted=validate_parent_history(parent,history,scan_values=True)
    rho=json.loads(Path(rho_json).read_text(encoding="utf-8"))
    uv=json.loads(Path(uv_json).read_text(encoding="utf-8"))
    prepared,diag=prepare_boundary_preview(
        parent,history,child_grid,rho,uv,TARGET_TIMES,child_n=CHILD_N,
        child_params=CHILD_SIGMA,target_time_units=TARGET_UNITS,
        target_time_calendar=TARGET_CALENDAR)
    if diag["source_target_CF_time_bridge"]["time_axis_mapping_status"]!=(
        "TARGET_CF_EPOCH_TO_SOURCE_HISTORY_EPOCH_CONVERTED"):
        raise ValueError("actual real-target MJD to parent time epoch conversion skipped")
    native=diag["native_normal_section_flux_diagnostic"]
    if native["normal_face_2d_vs_3d_integration_check"]!="PASS":
        raise ValueError("failed real geometry synthetic parent native transport integration")
    wanted_faces=len(PARENT_TIMES)*sum(EXPECTED_NORMAL.values())
    if native["total_wet_normal_face_samples"]!=wanted_faces:
        raise ValueError("real option B normal face/time count lost during donor remap")
    if diag["wet_receivers_by_native_kind"]!=EXPECTED_COUNTS:
        raise ValueError("source-to-child remap did not use all actual candidate B donors")
    schema=write_synthetic_schema_fixture(
        child_grid,mapped,prepared,TARGET_TIMES,n=CHILD_N,
        time_units=TARGET_UNITS,time_calendar=TARGET_CALENDAR,
        **{key:CHILD_SIGMA[key] for key in ("hc","theta_s","theta_b")})
    with Dataset(child_grid) as g,Dataset(mapped) as f:
        if f.getncattr("workflow_status")!="SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS":
            raise ValueError("synthetic source boundary falsely claims physical readiness")
        for side in ("south","north","west","east"):
            for kind,fields in (("rho",("zeta","temp","salt")),
                                ("u",("u","ubar")),("v",("v","vbar"))):
                mask=np.asarray(g["mask_"+kind][:],dtype=bool)
                wet=(mask[0] if side=="south" else mask[-1] if side=="north"
                     else mask[:,0] if side=="west" else mask[:,-1])
                for field in fields:
                    x=np.asarray(f[field+"_"+side][:],dtype=float)
                    if x.shape!=prepared[side][field].shape or not np.isfinite(x[...,wet]).all():
                        raise ValueError(f"missing real wet {kind} native boundary values in {side}")
                    np.testing.assert_allclose(x,prepared[side][field],rtol=1e-6,atol=1e-5)
        for t,surface in enumerate((.2,.4)):
            np.testing.assert_allclose(np.asarray(f["zeta_south"][t])[np.asarray(g["mask_rho"][0,:],dtype=bool)],
                                       surface,rtol=0,atol=1e-6)
        if f["bry_time"].units!=TARGET_UNITS or f["bry_time"].calendar!=TARGET_CALENDAR:
            raise ValueError("bry time metadata not preserved from MJD target")
    result={
        "status":"REAL_OPTIONB_DONORS_FULL_SYNTHETIC_SOURCE_TO_BRY_PASS",
        "real_target":"ORIGINAL_ARCHIVED_GEBCO_GSHHG_OPTION_B_COMPARISON_ONLY",
        "parent_grid_status":"FICTIONAL_ALL_WET_732X464_NOT_REAL_ES3K",
        "parent_hydrodynamic_history":"SYNTHETIC_2_FRAMES_NOT_REAL_OCEAN",
        "source_donor_certified_parent_mask_independent_recheck":"NOT_RUN_ON_ACTUAL_PARENT",
        "rho_u_v_receiver_counts":diag["wet_receivers_by_native_kind"],
        "real_wet_native_normal_faces_per_time":static["wet_native_open_normal_section_counts"],
        "normal_face_time_samples":native["total_wet_normal_face_samples"],
        "child_z_level_count":CHILD_N,
        "complete_bry_field_variables":schema["complete_field_variables"],
        "CF_target_MJD_to_source_seconds":"PASS",
        "individual_2D_vs_3D_face_relative_error_max":native[
            "max_individual_face_2d_vs_3d_relative_mismatch"],
        "synthetic_bry_file":mapped.name,
        "true_parent_child_transport_conservation":"NOT_RUN",
        "real_ES3K_and_UD1K_ocean_integrations":"NOT_RUN",
    }
    (out/"REAL_OPTIONB_SYNTHETIC_PARENT_TO_BRY_SMOKE_REPORT.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--child-grid",type=Path,required=True)
    p.add_argument("--rho-map",type=Path,required=True)
    p.add_argument("--native-uv-map",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    result=run_artificial_parent_on_real_optionb(
        args.child_grid,args.rho_map,args.native_uv_map,args.output_dir)
    print("REAL_OPTIONB_ALL_DONORS_SYNTHETIC_SOURCE_BRY_PASS",json.dumps({
        "r_u_v":result["rho_u_v_receiver_counts"],
        "normal_samples":result["normal_face_time_samples"],
        "bry_fields":result["complete_bry_field_variables"],
        "physical_parent":"NOT_RUN"},sort_keys=True))


if __name__=="__main__":
    main()
