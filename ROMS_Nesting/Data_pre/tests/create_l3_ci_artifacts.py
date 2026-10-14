#!/usr/bin/env python3
"""Archive USER-ANCHORED L3 geometry with explicitly SYNTHETIC bathymetry.

Never use this CI artifact for real water dynamics, emissions or Bq
conservation; replace with GEBCO_2026 and GSHHG first.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from l3_square import square_grid_geometry
from bathymetry_grid import build_grid
from validate_nesting_geometries import check_pair
from test_l3_square import synthetic_sea

def main():
    args=argparse.ArgumentParser()
    args.add_argument("--output",required=True)
    opt=args.parse_args()
    output=Path(opt.output)
    output.mkdir(parents=True,exist_ok=True)
    spec=json.loads((ROOT.parent/"configs/l3_coastal_square_candidate.json").read_text())
    parent=json.loads((ROOT.parent/"configs/ud1k_candidate.json").read_text())
    _,_,_,metadata=square_grid_geometry(spec)
    c=metadata["corners_lat_lon"]
    # GeoJSON polygon order is CCW, lon first.
    geojson={
      "type":"FeatureCollection",
      "features":[{
        "type":"Feature",
        "properties":{
          "name":"L3_300m_USER_AB_OFFSHORE_SQUARE_CANDIDATE",
          "nominal_resolution_fraction":"1/324 deg",
          "geometry_science_status":"NOT_VALIDATED",
          "actual_mesh_resolution":"local WGS84 angular-metric equivalent",
        },
        "geometry":{"type":"Polygon","coordinates":[[
            [c[k][1],c[k][0]] for k in ("A","D","C","B","A")]]},
      }]
    }
    (output/"L3_square_candidate.geojson").write_text(json.dumps(geojson,indent=2)+"\n")
    fake=output/"SYNTHETIC_NOT_REAL_GEBCO.nc"
    synthetic_sea(fake)
    child=output/"L3_SYNTHETIC_ONLY.nc"
    build_grid(spec,fake,child,allow_gebco_only_mask=True,synthetic_fixture=True)
    study_parent={**parent,"lon_min":129.15,"lon_max":130.3,
                  "lat_min":35.35,"lat_max":36.15}
    parent_path=output/"UD1K_SOUTH_EXTENDED_SYNTHETIC_ONLY.nc"
    build_grid(study_parent,fake,parent_path,allow_gebco_only_mask=True,synthetic_fixture=True)
    pair=check_pair(parent_path,child,margin_parent_rho_cells=2)
    if pair["status"]!="PASS_PRELIMINARY_ONLY":
        raise RuntimeError("synthetic geometric parent-child L3 fail: "+repr(pair))
    report={
        "geometry":metadata,
        "parent_child_geometric_preflight":pair,
        "reference_parent_original_south_deg":35.5,
        "proposed_real_UD1K_south_deg":35.35,
        "real_GEBCO_and_GSHHG":"NOT_RUN",
        "ROMS_hydrodynamics":"NOT_RUN",
        "real_offline_HTO":"NOT_RUN",
        "Bq_conservation":"NOT_RUN",
        "provenance":"user supplied A B, all other corners geodetically derived",
    }
    (output/"L3_geometry_preflight.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":"SYNTHETIC_GEOMETRY_PASS_ONLY",
                      "rho_shape":metadata["rho_shape"],
                      "square_corners":c,"parent_containment":pair["status"]},indent=2))

if __name__=="__main__":
    main()
