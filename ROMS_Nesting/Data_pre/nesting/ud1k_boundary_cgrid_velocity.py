"""Explicit C-grid face support and native-to-geographic vector rotation.

Physics staging only: these routines collocate source ROMS U/V face values
to parent RHO donors, rotate each donor using the *local* parent grid angle,
apply existing wet-only RHO scalar stencils, then rotate into child RHO
directions using the *local* child angle.

IMPORTANT: This produces **RHO diagnostic vectors**, NOT staggered child
U/V or barotropic `bry.nc`. A follow-on *independent* destination U-face
and V-face remap plus wet normal-volume transport checks is mandatory.
"""
from __future__ import annotations

import numpy as np


def _valid_adjacent_faces(wet:np.ndarray,j:int,i:int,axis:str)->list[tuple[int,int]]:
    """Face(s) touching wet RHO donor, using exact ROMS mask_u/mask_v."""
    if not wet[j,i]:
        raise ValueError("cannot reconstruct native velocity at a dry RHO donor")
    ny,nx=wet.shape
    faces=[]
    if axis=="u":
        for ii in (i-1,i):
            if 0<=ii<nx-1 and wet[j,ii] and wet[j,ii+1]:
                faces.append((j,ii))
    elif axis=="v":
        for jj in (j-1,j):
            if 0<=jj<ny-1 and wet[jj,i] and wet[jj+1,i]:
                faces.append((jj,i))
    else:
        raise ValueError("axis must be u or v")
    return faces


def face_support_report(wet:np.ndarray,records:list[dict])->dict:
    """All required donor RHO points must have native U and V face support."""
    m=np.asarray(wet,dtype=bool)
    problem=[]
    total_nonzero=0
    one_face_u=one_face_v=0
    for r in records:
        bad=[]
        for (j,i),w in zip(r["donor_eta_xi_zero_based"],r["weights"]):
            if w<=0:
                continue
            total_nonzero+=1
            j,i=int(j),int(i)
            u=_valid_adjacent_faces(m,j,i,"u")
            v=_valid_adjacent_faces(m,j,i,"v")
            if len(u)==1:
                one_face_u+=1
            if len(v)==1:
                one_face_v+=1
            if not u or not v:
                bad.append({"donor_eta_xi":[j,i],
                            "missing_u":not bool(u),"missing_v":not bool(v),
                            "weight":float(w)})
        if bad:
            problem.append({"child_eta_rho_zero_based":int(r["child_eta_rho_zero_based"]),
                            "child_xi_rho_zero_based":int(r["child_xi_rho_zero_based"]),
                            "unsupported_nonzero_donors":bad})
    return {
        "scope":"PARENT_RHO_FACE_SUPPORT_FOR_CHILD_RHO_VECTOR_DIAGNOSTIC_ONLY",
        "donor_samples_checked":total_nonzero,
        "u_one_wet_face_samples":one_face_u,
        "v_one_wet_face_samples":one_face_v,
        "receiver_RHO_points_with_missing_U_or_V_donor":len(problem),
        "problem_points":problem,
        "physical_velocity_flux_acceptance":"NOT_RUN",
    }


def _collocate_component(arr:np.ndarray,faces:list[tuple[int,int]])->np.ndarray:
    if not faces:
        raise ValueError("insufficient parent C-grid wet-face support")
    values=np.stack([arr[...,j,i] for j,i in faces],axis=-1)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite native velocity at an accepted wet C-grid face")
    return np.mean(values,axis=-1)


def rotate_parent_to_child_rho(u_parent:np.ndarray,v_parent:np.ndarray,
                               mask_parent:np.ndarray,angle_parent:np.ndarray,
                               angle_child:np.ndarray,records:list[dict])->dict:
    """Native C-grid face input -> East/North -> child *RHO* vector diagnostics.

    Input u[...,eta_rho,xi_rho-1], v[...,eta_rho-1,xi_rho].
    Output (..., receiver wet boundary point) for all components.
    """
    wet=np.asarray(mask_parent,dtype=bool)
    u=np.asarray(u_parent,dtype=float)
    v=np.asarray(v_parent,dtype=float)
    ap=np.asarray(angle_parent,dtype=float)
    ac=np.asarray(angle_child,dtype=float)
    ny,nx=wet.shape
    if u.shape[-2:]!=(ny,nx-1) or v.shape[-2:]!=(ny-1,nx) or u.shape[:-2]!=v.shape[:-2]:
        raise ValueError("ROMS U/V fields must use valid staggered dimensions and common leading dims")
    if ap.shape!=wet.shape or ac.ndim!=2:
        raise ValueError("invalid local parent/child angle shape")
    if not np.isfinite(ap).all() or not np.isfinite(ac).all():
        raise ValueError("nonfinite velocity angle")
    out_east=[]
    out_north=[]
    out_u=[]
    out_v=[]
    for r in records:
        cj=int(r["child_eta_rho_zero_based"])
        ci=int(r["child_xi_rho_zero_based"])
        if not (0<=cj<ac.shape[0] and 0<=ci<ac.shape[1]):
            raise ValueError("receiver RHO outside destination grid")
        nodes=np.asarray(r["donor_eta_xi_zero_based"],dtype=int)
        weight=np.asarray(r["weights"],dtype=float)
        if (not len(nodes) or len(weight)!=len(nodes)
                or (weight<0).any() or not np.isfinite(weight).all()
                or abs(float(weight.sum())-1)>1e-10):
            raise ValueError("invalid donor weights")
        east=north=None
        for (j,i),w in zip(nodes,weight):
            if w==0:
                continue
            j,i=int(j),int(i)
            if not (0<=j<ny and 0<=i<nx):
                raise ValueError("source RHO index invalid")
            ur=_collocate_component(u,_valid_adjacent_faces(wet,j,i,"u"))
            vr=_collocate_component(v,_valid_adjacent_faces(wet,j,i,"v"))
            a=ap[j,i]
            e=w*(ur*np.cos(a)-vr*np.sin(a))
            n=w*(ur*np.sin(a)+vr*np.cos(a))
            east=e if east is None else east+e
            north=n if north is None else north+n
        if east is None:
            raise ValueError("no nonzero wet RHO donor")
        a=ac[cj,ci]
        out_east.append(east)
        out_north.append(north)
        out_u.append(east*np.cos(a)+north*np.sin(a))
        out_v.append(-east*np.sin(a)+north*np.cos(a))
    return {
        "east_at_child_rho":np.stack(out_east,axis=-1),
        "north_at_child_rho":np.stack(out_north,axis=-1),
        "child_u_axis_at_rho_only":np.stack(out_u,axis=-1),
        "child_v_axis_at_rho_only":np.stack(out_v,axis=-1),
        "scope":"COLLOCATED_RHO_VECTOR_DIAGNOSTIC_NOT_STAGGERED_UV_OR_BRY",
    }
