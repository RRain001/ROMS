"""Local log-depth projection alternative for ES3K real I3 bathymetry.

Only repairs wet-wet face slope violations (4-neighbor C-grid); avoids
blanket diffusion of basins. Unlike a full physical optimization, this
deterministic alternating edge projection is a research *candidate* only.
Source/core mask, coastline, h dry cells, geometry and metrics are immutable.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import numpy as np
from netCDF4 import Dataset

from es3k_core_bathymetry_smoothing import _vertical, _sha256, adjacent_rx0
from es3k_core_bathymetry_smoothing import compute_rx0_rx1


DEFAULT_TARGETS = (0.35, 0.30, 0.27, 0.25, 0.23, 0.21, 0.20, 0.18)


def local_log_depth_projection(h: np.ndarray, wet: np.ndarray, *,
                               target_rx0: float = .35, hmin: float = 10.,
                               max_sweeps: int = 500) -> tuple[np.ndarray, int]:
    h=np.asarray(h,dtype=np.float64)
    wet=np.asarray(wet,dtype=bool)
    if h.ndim!=2 or wet.shape!=h.shape or min(h.shape)<3:
        raise ValueError("invalid h/wet shape")
    if not (h[wet]>=hmin).all() or not np.isfinite(h).all():
        raise ValueError("positive finite bathymetry and Hmin required")
    if not (0 < target_rx0 < .5 and hmin > 0 and 1<=max_sweeps<=2000):
        raise ValueError("invalid local smoothing parameters")
    work=np.log(h.copy())
    lower=np.log(hmin)
    # Work *slightly* inside the requested bound to avoid floating point
    # roundoff when checking the final staggered wet-neighbor slope.
    edge_limit=2*np.arctanh(max(target_rx0-0.0002,0.001))
    for count in range(max_sweeps+1):
        depth=np.exp(work)
        if adjacent_rx0(depth,wet)<=target_rx0:
            depth[~wet]=h[~wet]
            return depth,count
        if count==max_sweeps:
            break
        for axis in (1,0):
            for parity in (0,1):
                if axis==1:
                    a=work[:,parity:-1:2]
                    b=work[:,parity+1::2]
                    active=wet[:,parity:-1:2]&wet[:,parity+1::2]
                else:
                    a=work[parity:-1:2,:]
                    b=work[parity+1::2,:]
                    active=wet[parity:-1:2,:]&wet[parity+1::2,:]
                dif=a-b
                delta=0.5*np.sign(dif)*np.maximum(0,np.abs(dif)-edge_limit)
                delta*=active
                a-=delta
                b+=delta
            work[wet]=np.maximum(work[wet],lower)
    raise ValueError(f"local log-depth projection failed rx0 target={target_rx0}")


def local_slope_candidate(source: Path, output: Path, report_json: Path, *,
                          vertical: dict, targets: tuple[float,...]=DEFAULT_TARGETS,
                          rx1_limit: float = 8.0,
                          max_volume_change_fraction: float = .02,
                          max_p99_abs_depth_change_m: float = 350.0) -> dict:
    source,output,report_json = map(Path,(source,output,report_json))
    if source.resolve()==output.resolve() or source.resolve()==report_json.resolve():
        raise ValueError("refuse to overwrite source")
    if output.exists() or report_json.exists() or output.resolve()==report_json.resolve():
        raise FileExistsError("candidate output or report already exists")
    if not (source.exists() and len(targets)>0 and all(.04 < x <=.35 for x in targets)
            and all(a>b for a,b in zip(targets,targets[1:]))):
        raise ValueError("invalid source or target sequence")
    if not (.01 <= rx1_limit <=20 and 0<max_volume_change_fraction<=.1 and
            10<=max_p99_abs_depth_change_m<=1000):
        raise ValueError("invalid physical damage thresholds")
    v=_vertical(vertical)
    with Dataset(source) as src:
        if (getattr(src,"grid_id","")!="ES3K" or
            getattr(src,"geometry_status","")!="CANDIDATE_NOT_VALIDATED_FOR_ROMS" or
            getattr(src,"domain_mask_policy","")!="ONLY_JAPAN_BASIN_CONNECTED_COMPONENT_NO_FAKE_LAND" or
            "excluded_ocean_component_rho" not in src.variables):
            raise ValueError("expected filtered ES3K original core candidate")
        h0=np.asarray(src["h"][:],dtype=np.float64)
        wet=np.asarray(src["mask_rho"][:],dtype=bool)
        pm=np.asarray(src["pm"][:],dtype=np.float64)
        pn=np.asarray(src["pn"][:],dtype=np.float64)
        if not np.any(wet) or not np.isfinite(h0).all() or np.any(h0[wet] < v.Hmin_m-1e-8):
            raise ValueError("invalid core wet depth")
        if not (np.isfinite(pm).all() and np.isfinite(pn).all() and (pm>0).all() and (pn>0).all()):
            raise ValueError("invalid area metrics")
    area=1/(pm[wet]*pn[wet])
    before=float(np.sum(h0[wet]*area,dtype=np.float64))
    attempts=[]
    best=None
    for target in targets:
        h,n=local_log_depth_projection(h0,wet,target_rx0=target,hmin=v.Hmin_m)
        rx0,rx1=compute_rx0_rx1(h,wet.astype("i1"),v)
        volume=float(np.sum(h[wet]*area,dtype=np.float64))
        dist=np.abs(h[wet]-h0[wet])
        p99=float(np.quantile(dist,.99))
        attempt={
          "constraint_rx0":target,"sweeps":n,"rx0":float(rx0),"rx1":float(rx1),
          "volume_change_fraction":float(volume/before-1.),
          "p99_abs_depth_change_m":p99,
          "max_abs_depth_change_m":float(np.max(dist)),
          "number_wet_cells_changed_gt100m":int(np.count_nonzero(dist>100)),
          "meets_rx0":bool(rx0<=target),"meets_rx1":bool(rx1<=rx1_limit),
          "meets_volume":bool(abs(volume/before-1.)<=max_volume_change_fraction),
          "meets_p99_depth":bool(p99<=max_p99_abs_depth_change_m),
        }
        attempts.append(attempt)
        if all((attempt["meets_rx0"],attempt["meets_rx1"],
                attempt["meets_volume"],attempt["meets_p99_depth"])):
            best=(h,attempt)
            break
    if best is None:
        raise ValueError("no tested local-projection candidate passes all I3 static gates: "
                         + json.dumps(attempts))
    h,passed=best
    source_sha=_sha256(source)
    output.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,output)
    with Dataset(output,"r+") as dst:
        dst["h"][:]=h.astype(dst["h"].dtype)
        dst.bathymetry_smoothing_status="ES3K_LOCAL_LOG_DEPTH_I3_CANDIDATE_NOT_PHYSICS"
        dst.bathymetry_smoothing_method="ALTERNATING_FOUR_CONNECTED_LOG_DEPTH_EDGE_PROJECTION"
        dst.smoothing_vertical_json=json.dumps(vertical,sort_keys=True)
        dst.smoothing_original_sha256=source_sha
        dst.smoothing_effective_rx0_target=passed["constraint_rx0"]
        dst.smoothing_rx1_limit=rx1_limit
    with Dataset(output) as dst:
        wet_after=np.asarray(dst["mask_rho"][:],dtype=bool)
        h_after=np.asarray(dst["h"][:],dtype=np.float64)
        if not np.array_equal(wet,wet_after):
            output.unlink(missing_ok=True)
            raise AssertionError("wet mask modified")
        rx0,rx1=compute_rx0_rx1(h_after,wet_after.astype("i1"),v)
        if rx0>passed["constraint_rx0"] or rx1>rx1_limit or not np.isfinite(h_after).all():
            output.unlink(missing_ok=True)
            raise ValueError("post-write local smoothing slope gate failed")
    if _sha256(source)!=source_sha:
        output.unlink(missing_ok=True)
        raise AssertionError("input grid mutated")
    report={
       "status":"LOCAL_ES3K_CORE_SLOPE_STATIC_PASS_PHYSICS_NOT_RUN",
       "source":str(source),"output":str(output),
       "source_sha256":source_sha,"output_sha256":_sha256(output),
       "selected":passed,"attempts":attempts,
       "wet_rho_points":int(np.count_nonzero(wet)),
       "all_mask_geometry_metrics_preserved":True,
       "original_grid_unmodified":True,
       "real_data_verified_by_source":False,
       "I3_scientific_acceptance":"NOT_ACCEPTED",
       "ROMS_physics":"NOT_RUN",
    }
    report_json.parent.mkdir(parents=True,exist_ok=True)
    report_json.write_text(json.dumps(report,indent=2)+"\n")
    return report
