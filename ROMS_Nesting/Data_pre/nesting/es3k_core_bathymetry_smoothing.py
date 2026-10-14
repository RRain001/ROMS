"""Fail-closed, nesting-only bathymetry smoothing for ES3K *core* grid.

Does not change mask, geometry, metrics, rotation, external data, or source.
ROMS-ready claims require separate coast, open boundary, parent/child and
dynamical acceptance; this is an I3 *candidate* slope treatment only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from netCDF4 import Dataset

_CORE = Path(__file__).resolve().parents[1] / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
from roms_preprocessing_utils import VerticalConfig, compute_rx0_rx1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def adjacent_rx0(depth: np.ndarray, wet: np.ndarray) -> float:
    a = np.asarray(depth, dtype=float)
    w = np.asarray(wet, dtype=bool)
    if a.ndim != 2 or a.shape != w.shape or min(a.shape) < 3:
        raise ValueError("invalid ES3K depth/wet array shape")
    total = 0.0
    for ax in (0, 1):
        aa, bb = (a[:-1], a[1:]) if ax == 0 else (a[:, :-1], a[:, 1:])
        wa, wb = (w[:-1], w[1:]) if ax == 0 else (w[:, :-1], w[:, 1:])
        valid = wa & wb
        if valid.any():
            total = max(total, float(np.max(np.abs(aa[valid] - bb[valid]) /
                                              (aa[valid] + bb[valid]))))
    return total


def smooth_once(h: np.ndarray, wet: np.ndarray, *, blend: float,
                min_depth_m: float) -> np.ndarray:
    neighbor_sum = np.zeros_like(h)
    neighbor_count = np.zeros_like(h, dtype=np.int8)
    for dst, src in ((np.s_[1:, :], np.s_[:-1, :]),
                     (np.s_[:-1, :], np.s_[1:, :]),
                     (np.s_[:, 1:], np.s_[:, :-1]),
                     (np.s_[:, :-1], np.s_[:, 1:])):
        neighbor_sum[dst] += h[src] * wet[src]
        neighbor_count[dst] += wet[src]
    avg = h.copy()
    np.divide(neighbor_sum, neighbor_count, out=avg, where=neighbor_count != 0)
    new = h.copy()
    new[wet] = np.maximum(min_depth_m,
                          (1 - blend) * h[wet] + blend * avg[wet])
    return new


def _vertical(spec: dict) -> VerticalConfig:
    required = ("N", "theta_s", "theta_b", "Tcline_m", "Hmin_m",
                "Vtransform", "Vstretching")
    if any(x not in spec for x in required):
        raise ValueError(f"explicit vertical parameters required: {required}")
    v = VerticalConfig(N=int(spec["N"]),
                       theta_s=float(spec["theta_s"]),
                       theta_b=float(spec["theta_b"]),
                       Tcline=float(spec["Tcline_m"]),
                       Hmin_m=float(spec["Hmin_m"]),
                       Vtransform=int(spec["Vtransform"]),
                       Vstretching=int(spec["Vstretching"]))
    if not (v.N == 41 and v.Vtransform == 2 and v.Vstretching == 4 and
            v.Hmin_m > 0 and v.Tcline > 0):
        raise ValueError("ES3K I3 must use explicit 41-layer Vtransform2 / Vstretching4")
    return v


def smooth_core_candidate(source: Path, output: Path, report_path: Path, *,
                          vertical: dict, rx0_target: float = 0.35,
                          rx1_target: float = 8.0, max_iterations: int = 120,
                          blend: float = 0.85,
                          max_volume_change_fraction: float = 0.02) -> dict:
    source, output, report_path = map(Path, (source, output, report_path))
    if source.resolve() in (output.resolve(), report_path.resolve()):
        raise ValueError("refuse to overwrite source grid")
    if output.resolve() == report_path.resolve() or output.exists() or report_path.exists():
        raise FileExistsError("output or report already exists")
    if not source.is_file():
        raise FileNotFoundError(source)
    if not (0 < rx0_target <= 0.5 and 0 < rx1_target <= 20 and
            0 < blend <= 1 and 1 <= max_iterations <= 1000 and
            0 < max_volume_change_fraction <= 0.1):
        raise ValueError("invalid smoothing numerical constraints")
    v = _vertical(vertical)
    with Dataset(source) as ds:
        if (getattr(ds, "grid_id", "") != "ES3K" or
            getattr(ds, "geometry_status", "") != "CANDIDATE_NOT_VALIDATED_FOR_ROMS" or
            "excluded_ocean_component_rho" not in ds.variables or
            getattr(ds, "domain_mask_policy", "") != "ONLY_JAPAN_BASIN_CONNECTED_COMPONENT_NO_FAKE_LAND"):
            raise ValueError("expected reversible I3 ES3K core-component-only candidate")
        h0 = np.asarray(ds["h"][:], dtype=np.float64)
        wet = np.asarray(ds["mask_rho"][:], dtype=bool)
        pm = np.asarray(ds["pm"][:], dtype=np.float64)
        pn = np.asarray(ds["pn"][:], dtype=np.float64)
        if (not wet.any() or not np.isfinite(h0).all() or
            not np.isfinite(pm).all() or not np.isfinite(pn).all() or
            np.any(h0[wet] < v.Hmin_m - 1e-8) or
            np.any(pm <= 0) or np.any(pn <= 0)):
            raise ValueError("invalid positive wet bathymetry / metrics / Hmin")
        source_status = str(getattr(ds, "synthetic_test_only", "UNKNOWN"))
        source_geometry = str(getattr(ds, "geometry_reference_status", "UNKNOWN"))
    area = 1.0 / (pm[wet] * pn[wet])
    volume_before = float(np.sum(h0[wet] * area, dtype=np.float64))
    initial_rx0 = adjacent_rx0(h0, wet)
    h = h0.copy()
    iterations = 0
    rx0 = initial_rx0
    rx1 = None
    for n in range(max_iterations + 1):
        rx0 = adjacent_rx0(h, wet)
        if rx0 <= rx0_target:
            full_rx0, rx1 = compute_rx0_rx1(h, wet.astype("i1"), v)
            if full_rx0 <= rx0_target and rx1 <= rx1_target:
                iterations = n
                break
        if n == max_iterations:
            raise ValueError(f"smoothing target NOT_MET: rx0={rx0}, rx1={rx1}")
        h = smooth_once(h, wet, blend=blend, min_depth_m=v.Hmin_m)
    assert np.array_equal(h[~wet], h0[~wet])
    volume_after = float(np.sum(h[wet] * area, dtype=np.float64))
    relative_volume = float(volume_after / volume_before - 1.0)
    if abs(relative_volume) > max_volume_change_fraction:
        raise ValueError("smoothing wet-volume drift exceeds explicit budget gate")
    if not (np.all(np.isfinite(h)) and (h[wet] >= v.Hmin_m).all()):
        raise ValueError("invalid smoothed bathymetry")
    source_sha = _sha256(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    with Dataset(output, "r+") as ds:
        ds["h"][:] = h.astype(ds["h"].dtype)
        ds.bathymetry_smoothing_status = "ES3K_CORE_I3_SLOPE_CANDIDATE_NOT_ROMs_PHYSICS_PASS"
        ds.smoothing_method = "FOUR_CONNECTED_WET_NEIGHBOR_LAPLACIAN_FIXED_MASK"
        ds.smoothing_rx0_target = float(rx0_target)
        ds.smoothing_rx1_target = float(rx1_target)
        ds.smoothing_iterations = int(iterations)
        ds.smoothing_vertical_json = json.dumps(vertical, sort_keys=True)
        ds.smoothing_volume_relative_change = relative_volume
        ds.smoothing_original_sha256 = source_sha
    with Dataset(output) as check:
        output_h = np.asarray(check["h"][:], dtype=np.float64)
        out_rx0, out_rx1 = compute_rx0_rx1(output_h,
                                            np.asarray(check["mask_rho"][:]), v)
        if out_rx0 > rx0_target or out_rx1 > rx1_target:
            output.unlink(missing_ok=True)
            raise ValueError("post-write float dtype caused slope gate failure")
        if not np.array_equal(np.asarray(check["mask_rho"][:]), wet.astype("i1")):
            output.unlink(missing_ok=True)
            raise AssertionError("mask mutated")
    report = {
        "status": "ES3K_CORE_SLOPE_PRELIMINARY_PASS_ONLY",
        "source_grid": str(source),
        "candidate_grid": str(output),
        "original_sha256": source_sha,
        "output_sha256": _sha256(output),
        "input_synthetic": source_status,
        "source_geometry_reference_status": source_geometry,
        "wet_rho_points": int(wet.sum()),
        "iterations": iterations,
        "rx0_initial": initial_rx0,
        "rx0_final": float(out_rx0),
        "rx1_final": float(out_rx1),
        "rx0_target": rx0_target,
        "rx1_target": rx1_target,
        "max_abs_depth_change_m": float(np.max(np.abs((h-h0)[wet]))),
        "volume_before_m3_metric": volume_before,
        "volume_after_m3_metric": volume_after,
        "volume_change_fraction": relative_volume,
        "original_grid_unchanged": _sha256(source) == source_sha,
        "mask_geometry_angle_metrics_unchanged": True,
        "I3_scientific_acceptance": "NOT_ACCEPTED",
        "ROMS_physics": "NOT_RUN",
    }
    if not report["original_grid_unchanged"]:
        output.unlink(missing_ok=True)
        raise AssertionError("input grid mutated")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report
