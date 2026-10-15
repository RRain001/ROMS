"""Create a separate ES3K *candidate* with non-core wet components excluded.

This operation never alters the input grid or the GEBCO/GSHHG source. It
does not treat excluded sea as natural land: new provenance variables make
that distinction explicit. Four-connected wet cells are the ROMS C-grid
face-adjacency criterion, not diagonal/vertex contact.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
from netCDF4 import Dataset
from scipy import ndimage

from es3k_wet_domain_audit import (FOUR_CONNECTED, REGIONS, STRAITS,
                                    analyze, audit_grid, save_report)


def core_component_only_candidate(source: Path, output: Path,
                                  report_path: Path) -> dict:
    source, output, report_path = Path(source), Path(output), Path(report_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == output.resolve():
        raise ValueError("refuse to overwrite ES3K original grid")
    if output.exists() or report_path.exists():
        raise FileExistsError("candidate output/report already exists")
    with Dataset(source) as nc:
        if getattr(nc,"grid_id","")!="ES3K":
            raise ValueError("expected ES3K candidate grid")
        lon=np.asarray(nc["lon_rho"][:])
        lat=np.asarray(nc["lat_rho"][:])
        wet=np.asarray(nc["mask_rho"][:],dtype=bool)
        pm=np.asarray(nc["pm"][:])
        pn=np.asarray(nc["pn"][:])
        original=dict(mask_u=np.asarray(nc["mask_u"][:]),
                      mask_v=np.asarray(nc["mask_v"][:]),
                      mask_psi=np.asarray(nc["mask_psi"][:]))
        baseline=analyze(lon,lat,wet,pm,pn,staggered=original)
    labelled,n=ndimage.label(wet,structure=FOUR_CONNECTED)
    core_window=REGIONS["japan_basin_core"].contains(lon,lat)
    wet_core_labels=labelled[wet&core_window]
    if not wet_core_labels.size:
        raise ValueError("Japan Basin core window has no wet cells")
    counts=np.bincount(wet_core_labels)
    counts[0]=0
    core_label=int(np.argmax(counts))
    full_counts=np.bincount(labelled.ravel())
    full_counts[0]=0
    if core_label!=int(np.argmax(full_counts)):
        raise ValueError("Japan Basin component is not dominant; review geometry")
    # Only retain one existing four-neighbor component; no boundary cut can
    # occur between two different components through a shared wet U/V face.
    keep=labelled==core_label
    drop=wet & ~keep
    if not drop.any():
        raise ValueError("no disconnected wet components to remove")
    if np.any(keep[:,:-1]&drop[:,1:]) or np.any(keep[:,1:]&drop[:,:-1]) or (
            np.any(keep[:-1,:]&drop[1:,:]) or np.any(keep[1:,:]&drop[:-1,:])):
        raise AssertionError("candidate would cut an existing wet-wet face")
    for name in STRAITS:
        window=REGIONS[name].contains(lon,lat)
        if not (keep&window).any():
            raise ValueError(f"core component does not include {name}")
    output.parent.mkdir(parents=True,exist_ok=True)
    # Byte-preserved source file: every nonmask variable is untouched,
    # including lon/lat/h/angle/metrics and user-defined GSHHG metadata.
    shutil.copyfile(source,output)
    with Dataset(output,"r+") as nc:
        nc["mask_rho"][:]=keep.astype("i1")
        nc["mask_u"][:]=(keep[:,:-1] & keep[:,1:]).astype("i1")
        nc["mask_v"][:]=(keep[:-1,:] & keep[1:,:]).astype("i1")
        nc["mask_psi"][:]=(keep[:-1,:-1] & keep[:-1,1:] & keep[1:,:-1] & keep[1:,1:]).astype("i1")
        nc.createVariable("excluded_ocean_component_rho","i1",("eta_rho","xi_rho"),zlib=True)[:]=drop.astype("i1")
        nc.mask_science_status="PRELIMINARY_ONLY_NOT_APPROVED_FOR_ROMS"
        nc.domain_mask_policy="ONLY_JAPAN_BASIN_CONNECTED_COMPONENT_NO_FAKE_LAND"
        nc.mask_zero_semantics="original land OR deliberately domain-excluded disconnected ocean"
        nc.excluded_wet_rho_points=int(drop.sum())
        nc.retained_core_wet_rho_points=int(keep.sum())
        nc.original_mask_preserved_in="source NetCDF; excluded_ocean_component_rho identifies modified sites"
        nc.original_grid_path_for_provenance=str(source)
    result=audit_grid(output)
    if result["wet_connected_component_count_4_neighbor"]!=1:
        raise AssertionError("derived ES3K component mask unexpectedly disconnected")
    if not all(result["strait_window_connected_to_core"].values()):
        raise AssertionError("derived mask lost a required strait window")
    if result["region_diagnostics"]["west_of_korea_yellow_sea_proxy"]["wet_rho_points"]!=0:
        raise AssertionError("derived core component still includes west Korea proxy")
    excluded_area=float((1e-6/(pm[drop]*pn[drop])).sum())
    record={
        "status":"CANDIDATE_MASK_REFINEMENT_NOT_PHYSICS_ACCEPTED",
        "source":str(source),
        "output":str(output),
        "original_wet_rho_points":int(wet.sum()),
        "retained_core_wet_rho_points":int(keep.sum()),
        "excluded_noncore_wet_rho_points":int(drop.sum()),
        "excluded_wet_area_km2_metrics_approx":excluded_area,
        "retained_wet_area_km2_metrics_approx":result["wet_area_km2_metrics_approx"],
        "number_of_original_four_neighbor_components":int(n),
        "baseline_yellow_sea_proxy_wet_rho":baseline["region_diagnostics"]["west_of_korea_yellow_sea_proxy"]["wet_rho_points"],
        "derived_yellow_sea_proxy_wet_rho":result["region_diagnostics"]["west_of_korea_yellow_sea_proxy"]["wet_rho_points"],
        "baseline_boundary":baseline["outer_boundary"],
        "derived_boundary":result["outer_boundary"],
        "straits_after_filter":result["strait_window_connected_to_core"],
        "no_existing_shared_wet_face_cut":True,
        "invariant_metadata_and_bathymetry":"h/lon/lat/angle/pm/pn unchanged",
        "source_file_unmodified":True,
        "bathymetry_smoothing":"NOT_RUN",
        "ROMS_physics":"NOT_RUN",
    }
    save_report(record,report_path)
    return record
