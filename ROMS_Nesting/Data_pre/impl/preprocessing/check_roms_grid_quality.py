#!/usr/bin/env python3
"""Audit ROMS grid geometry, mask, shallow depths, and source placement."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
from PIL import Image, ImageDraw
from scipy import ndimage
from pyproj import Geod

from case_naming import load_case_naming
from pilot_grid_utils import locate_source_on_grid
from roms_preprocessing_utils import (
    compute_rx0_rx1,
    load_grid,
    load_project_params,
    load_vertical_config,
    resolve_grid_path,
)


ROOT = Path(__file__).resolve().parents[3] / "projects"
NEAREST_RESAMPLE = getattr(getattr(Image, "Resampling", Image), "NEAREST")


@dataclass(frozen=True)
class BoundarySummary:
    wet_points: int
    land_points: int
    wet_segments: int
    first_wet_index: int | None
    last_wet_index: int | None
    continuous: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--json-output", default=None)
    return parser.parse_args()


def neighbor_count(mask: np.ndarray) -> np.ndarray:
    kernel = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=int)
    return ndimage.convolve(mask.astype(int), kernel, mode="constant", cval=0)


def count_segments(edge_mask: np.ndarray) -> int:
    values = np.asarray(edge_mask, dtype=bool)
    if values.size == 0:
        return 0
    starts = np.where(values & ~np.r_[False, values[:-1]])[0]
    return int(starts.size)


def summarize_boundary(mask: np.ndarray) -> BoundarySummary:
    wet_points = int(mask.sum())
    land_points = int(mask.size - wet_points)
    segments = count_segments(mask)
    wet_indices = np.where(mask)[0]
    first = int(wet_indices[0]) if wet_indices.size else None
    last = int(wet_indices[-1]) if wet_indices.size else None
    return BoundarySummary(
        wet_points=wet_points,
        land_points=land_points,
        wet_segments=segments,
        first_wet_index=first,
        last_wet_index=last,
        continuous=segments <= 1,
    )


def projected_xy(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lat0 = float(np.nanmean(lat))
    meters_per_degree_lon = 111_320.0 * math.cos(math.radians(lat0))
    meters_per_degree_lat = 111_320.0
    x = (lon - lon[0, 0]) * meters_per_degree_lon
    y = (lat - lat[0, 0]) * meters_per_degree_lat
    return x, y


def orthogonality_metrics(lon: np.ndarray, lat: np.ndarray) -> dict[str, float]:
    x, y = projected_xy(lon, lat)
    dxi_x = np.gradient(x, axis=1)
    dxi_y = np.gradient(y, axis=1)
    deta_x = np.gradient(x, axis=0)
    deta_y = np.gradient(y, axis=0)
    dot = dxi_x * deta_x + dxi_y * deta_y
    mag_xi = np.hypot(dxi_x, dxi_y)
    mag_eta = np.hypot(deta_x, deta_y)
    denom = np.where((mag_xi > 0.0) & (mag_eta > 0.0), mag_xi * mag_eta, np.nan)
    cosine = np.clip(dot / denom, -1.0, 1.0)
    orth_angle = np.degrees(np.arccos(cosine))
    orth_error = np.abs(90.0 - orth_angle)
    finite = orth_error[np.isfinite(orth_error)]
    return {
        "max_deg": float(np.nanmax(finite)) if finite.size else float("nan"),
        "mean_deg": float(np.nanmean(finite)) if finite.size else float("nan"),
        "p95_deg": float(np.nanpercentile(finite, 95.0)) if finite.size else float("nan"),
    }


def angle_metrics(angle: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> dict[str, float]:
    x, y = projected_xy(lon, lat)
    dxi_x = np.gradient(x, axis=1)
    dxi_y = np.gradient(y, axis=1)
    computed = np.arctan2(dxi_y, dxi_x)
    diff = np.abs(np.degrees(np.arctan2(np.sin(angle - computed), np.cos(angle - computed))))
    finite = diff[np.isfinite(diff)]
    return {
        "stored_min_deg": float(np.degrees(np.nanmin(angle))),
        "stored_max_deg": float(np.degrees(np.nanmax(angle))),
        "consistency_max_deg": float(np.nanmax(finite)) if finite.size else float("nan"),
        "consistency_mean_deg": float(np.nanmean(finite)) if finite.size else float("nan"),
    }


def metric_consistency(pm, pn, lon, lat, dndx=None, dmde=None) -> dict:
    """Independent geometry audit; does not call the production metric builder.

    1e-6 relative metric tolerance permits float32 storage (<6e-8 rounding)
    with margin. Derivative tolerance bounds cancellation of rounded spacings:
    16 storage eps * largest spacing, with a 1e-7 metre floor for f8 geodesy.
    Derivatives are compared in metres per grid index, never divided by dx/dy.
    """
    info = {"status": "FAIL", "metric_relative_tolerance": 1e-6}
    geod = Geod(ellps="WGS84")
    lon = np.asarray(np.ma.filled(lon, np.nan), dtype=float)
    lat = np.asarray(np.ma.filled(lat, np.nan), dtype=float)
    if lon.shape != lat.shape or lon.ndim != 2 or min(lon.shape) < 2:
        info["reason"] = "invalid coordinate shapes"
        return info
    if not np.isfinite(lon).all() or not np.isfinite(lat).all() or (np.abs(lat) > 90).any():
        info["reason"] = "invalid coordinates"
        return info
    # Flatten each edge pair independently of the generator's vectorized calls.
    xi = geod.inv(lon[:, :-1].ravel(), lat[:, :-1].ravel(),
                  lon[:, 1:].ravel(), lat[:, 1:].ravel())[2].reshape(lon.shape[0], -1)
    eta = geod.inv(lon[:-1].ravel(), lat[:-1].ravel(),
                   lon[1:].ravel(), lat[1:].ravel())[2].reshape(-1, lon.shape[1])
    if any(not np.isfinite(e).all() or (e <= 0).any() for e in (xi, eta)):
        info["reason"] = "invalid geodesic edge lengths"
        return info
    # Pad with the nearest incident edge, then take adjacent means.
    px = np.pad(xi, ((0, 0), (1, 1)), mode="edge")
    py = np.pad(eta, ((1, 1), (0, 0)), mode="edge")
    dx = (px[:, :-1] + px[:, 1:]) / 2
    dy = (py[:-1] + py[1:]) / 2
    expected = {"pm": 1 / dx, "pn": 1 / dy}
    ex = np.empty_like(dx)
    ey = np.empty_like(dy)
    ex[:, 1:-1] = (dy[:, 2:] - dy[:, :-2]) / 2
    ex[:, 0], ex[:, -1] = dy[:, 1] - dy[:, 0], dy[:, -1] - dy[:, -2]
    ey[1:-1] = (dx[2:] - dx[:-2]) / 2
    ey[0], ey[-1] = dx[1] - dx[0], dx[-1] - dx[-2]
    expected.update(dndx=ex, dmde=ey)
    passed = True
    eps = max((np.finfo(np.asarray(v).dtype).eps for v in (pm, pn)
               if np.asarray(v).dtype.kind == "f"), default=np.finfo(float).eps)
    derivative_tol = max(1e-7, 16 * eps * max(dx.max(), dy.max()))
    info["derivative_absolute_tolerance_m"] = float(derivative_tol)
    for name, stored in (("pm", pm), ("pn", pn), ("dndx", dndx), ("dmde", dmde)):
        if stored is None or np.shape(stored) != lon.shape:
            info[name + "_missing_or_wrong_shape"] = True
            passed = False
            continue
        arr = np.asarray(np.ma.filled(stored, np.nan), dtype=float)
        invalid = ~np.isfinite(arr)
        info[name + "_nonfinite_count"] = int(invalid.sum())
        if name in ("pm", "pn"):
            info[name + "_nonpositive_count"] = int((arr <= 0).sum())
            invalid |= arr <= 0
            err = np.abs(arr - expected[name]) / expected[name]
            suffix, tol = "_relerr", 1e-6
        else:
            err = np.abs(arr - expected[name])
            suffix, tol = "_abserr_m", derivative_tol
        finite = err[np.isfinite(err)]
        info[name + suffix + "_max"] = float(finite.max()) if finite.size else None
        info[name + suffix + "_p95"] = float(np.percentile(finite, 95)) if finite.size else None
        info[name + suffix + "_mean"] = float(finite.mean()) if finite.size else None
        passed &= not invalid.any() and bool(finite.size) and bool(np.all(finite <= tol))
    info["status"] = "PASS" if passed else "FAIL"
    return info


def local_rx0_field(h: np.ndarray, mask_rho: np.ndarray) -> np.ndarray:
    def merge_factor(target: np.ndarray, factor: np.ndarray) -> np.ndarray:
        out = target.copy()
        incoming = np.isfinite(factor)
        missing = incoming & ~np.isfinite(out)
        out[missing] = factor[missing]
        update = incoming & np.isfinite(out)
        out[update] = np.maximum(out[update], factor[update])
        return out

    water = mask_rho == 1
    out = np.full(h.shape, np.nan, dtype=float)
    if h.shape[1] > 1:
        valid = water[:, :-1] & water[:, 1:]
        denom = h[:, :-1] + h[:, 1:]
        factor = np.full(denom.shape, np.nan, dtype=float)
        np.divide(np.abs(h[:, :-1] - h[:, 1:]), denom, out=factor, where=denom != 0.0)
        factor = np.where(valid, factor, np.nan)
        out[:, :-1] = merge_factor(out[:, :-1], factor)
        out[:, 1:] = merge_factor(out[:, 1:], factor)
    if h.shape[0] > 1:
        valid = water[:-1, :] & water[1:, :]
        denom = h[:-1, :] + h[1:, :]
        factor = np.full(denom.shape, np.nan, dtype=float)
        np.divide(np.abs(h[:-1, :] - h[1:, :]), denom, out=factor, where=denom != 0.0)
        factor = np.where(valid, factor, np.nan)
        out[:-1, :] = merge_factor(out[:-1, :], factor)
        out[1:, :] = merge_factor(out[1:, :], factor)
    out[~water] = np.nan
    return out


def save_scalar_png(
    data: np.ndarray,
    path: Path,
    title: str,
    source_xy: tuple[int, int] | None = None,
    crop: tuple[slice, slice] | None = None,
    palette: str = "terrain",
) -> None:
    arr = np.asarray(data, dtype=float)
    if crop is not None:
        arr = arr[crop]
        offset_y = crop[0].start or 0
        offset_x = crop[1].start or 0
    else:
        offset_y = 0
        offset_x = 0

    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        norm = np.zeros(arr.shape, dtype=np.uint8)
    else:
        lo = float(np.nanpercentile(finite, 2.0))
        hi = float(np.nanpercentile(finite, 98.0))
        if hi <= lo:
            hi = lo + 1.0
        scaled = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
        norm = np.where(np.isfinite(arr), np.round(scaled * 255.0), 0).astype(np.uint8)

    if palette == "mask":
        rgb = np.zeros((*norm.shape, 3), dtype=np.uint8)
        rgb[:, :, :] = np.array([180, 180, 180], dtype=np.uint8)
        rgb[arr > 0.5] = np.array([40, 110, 220], dtype=np.uint8)
    elif palette == "rx0":
        rgb = np.zeros((*norm.shape, 3), dtype=np.uint8)
        rgb[:, :, 0] = norm
        rgb[:, :, 1] = 255 - norm
        rgb[:, :, 2] = 255 - norm
    else:
        rgb = np.zeros((*norm.shape, 3), dtype=np.uint8)
        rgb[:, :, 0] = norm
        rgb[:, :, 1] = np.clip(norm * 0.8, 0, 255).astype(np.uint8)
        rgb[:, :, 2] = np.clip(255 - norm * 0.5, 0, 255).astype(np.uint8)

    image = Image.fromarray(rgb, mode="RGB").resize((rgb.shape[1] * 4, rgb.shape[0] * 4), NEAREST_RESAMPLE)
    canvas = Image.new("RGB", (image.width, image.height + 30), "white")
    canvas.paste(image, (0, 30))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")

    if source_xy is not None:
        xi, eta = source_xy
        xi -= offset_x
        eta -= offset_y
        if 0 <= xi < rgb.shape[1] and 0 <= eta < rgb.shape[0]:
            x = xi * 4
            y = eta * 4 + 30
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline="red", width=2)
            draw.line((x - 10, y, x + 10, y), fill="red", width=2)
            draw.line((x, y - 10, x, y + 10), fill="red", width=2)

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def main() -> None:
    args = parse_args()
    params = load_project_params()
    vertical = load_vertical_config()
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    grid = load_grid(grid_path)
    case_root = grid_path.parents[1]
    output_dir = Path(args.output_dir) if args.output_dir else case_root / "output" / "grid_quality_audit"
    json_output = Path(args.json_output) if args.json_output else output_dir / "grid_quality_summary.json"

    with Dataset(grid_path) as ds:
        stored_metrics = {name: ds.variables[name][:] for name in ("pm", "pn")}
        derivatives = {name: ds.variables[name][:] if name in ds.variables else None
                       for name in ("dndx", "dmde")}
        x_rho = np.asarray(ds.variables["x_rho"][:, :], dtype=float) if "x_rho" in ds.variables else None
        y_rho = np.asarray(ds.variables["y_rho"][:, :], dtype=float) if "y_rho" in ds.variables else None
        mask_u_file = np.asarray(ds.variables["mask_u"][:, :], dtype=np.int8)
        mask_v_file = np.asarray(ds.variables["mask_v"][:, :], dtype=np.int8)
        mask_psi_file = np.asarray(ds.variables["mask_psi"][:, :], dtype=np.int8) if "mask_psi" in ds.variables else None
        bathy_source = getattr(ds, "bathymetry_source", "")
        resolution_m = float(getattr(ds, "resolution_m", np.nan))
        shoreline_dataset = getattr(ds, "shoreline_dataset", "")
        shoreline_shapefile = getattr(ds, "shoreline_shapefile", "")
        shoreline_resolution = getattr(ds, "shoreline_resolution", "")
        shoreline_level = getattr(ds, "shoreline_level", "")
        shoreline_backend = getattr(ds, "shoreline_backend", "")
        mask_cleanup_source = getattr(ds, "mask_cleanup_source_grid", "")

    wet = grid.mask_rho == 1
    dry = ~wet
    h_wet = grid.h[wet]
    rx0_max, rx1_max = compute_rx0_rx1(grid.h, grid.mask_rho, vertical)
    rx0_local = local_rx0_field(grid.h, grid.mask_rho)
    rx0_values = rx0_local[np.isfinite(rx0_local)]

    expected_mask_u = ((grid.mask_rho[:, :-1] == 1) & (grid.mask_rho[:, 1:] == 1)).astype(np.int8)
    expected_mask_v = ((grid.mask_rho[:-1, :] == 1) & (grid.mask_rho[1:, :] == 1)).astype(np.int8)
    expected_mask_psi = (
        (grid.mask_rho[:-1, :-1] == 1)
        & (grid.mask_rho[1:, :-1] == 1)
        & (grid.mask_rho[:-1, 1:] == 1)
        & (grid.mask_rho[1:, 1:] == 1)
    ).astype(np.int8)
    mask_u_mismatch = int(np.count_nonzero(mask_u_file != expected_mask_u))
    mask_v_mismatch = int(np.count_nonzero(mask_v_file != expected_mask_v))
    mask_psi_mismatch = int(np.count_nonzero(mask_psi_file != expected_mask_psi)) if mask_psi_file is not None else 0

    wet_neighbors = neighbor_count(wet)
    dry_neighbors = neighbor_count(dry)
    isolated_wet = int(np.count_nonzero(wet & (wet_neighbors == 0)))
    weakly_connected_wet = int(np.count_nonzero(wet & (wet_neighbors <= 1)))
    isolated_dry = int(np.count_nonzero(dry & (dry_neighbors == 4)))
    weakly_connected_dry = int(np.count_nonzero(dry & (dry_neighbors >= 3)))
    wet_components, wet_component_count = ndimage.label(wet)
    dry_components, dry_component_count = ndimage.label(dry)
    del wet_components, dry_components

    boundaries = {
        "west": summarize_boundary(wet[:, 0]),
        "east": summarize_boundary(wet[:, -1]),
        "south": summarize_boundary(wet[0, :]),
        "north": summarize_boundary(wet[-1, :]),
    }

    placement = locate_source_on_grid(grid_path, params["domain"]["source_lon"], params["domain"]["source_lat"])
    source_mask_value = int(grid.mask_rho[placement.snapped_eta, placement.snapped_xi])

    orth_metrics = orthogonality_metrics(grid.lon_rho, grid.lat_rho)
    angle_info = angle_metrics(grid.angle, grid.lon_rho, grid.lat_rho)
    pm_pn_info = metric_consistency(stored_metrics["pm"], stored_metrics["pn"], grid.lon_rho, grid.lat_rho, **derivatives)

    figures = {
        "bathymetry": output_dir / "grid_h.png",
        "mask": output_dir / "grid_mask_rho.png",
        "rx0": output_dir / "grid_rx0.png",
        "source_zoom": output_dir / "grid_source_zoom.png",
    }
    save_scalar_png(grid.h, figures["bathymetry"], "Bathymetry h (m)", (placement.snapped_xi, placement.snapped_eta))
    save_scalar_png(grid.mask_rho, figures["mask"], "mask_rho (blue=wet, gray=land)", (placement.snapped_xi, placement.snapped_eta), palette="mask")
    save_scalar_png(rx0_local, figures["rx0"], "Local rx0", (placement.snapped_xi, placement.snapped_eta), palette="rx0")
    y0 = max(placement.snapped_eta - 15, 0)
    y1 = min(placement.snapped_eta + 16, grid.h.shape[0])
    x0 = max(placement.snapped_xi - 15, 0)
    x1 = min(placement.snapped_xi + 16, grid.h.shape[1])
    save_scalar_png(
        grid.h,
        figures["source_zoom"],
        "Bathymetry near source",
        (placement.snapped_xi, placement.snapped_eta),
        crop=(slice(y0, y1), slice(x0, x1)),
    )

    summary = {
        "case_name": params["case"]["name"],
        "case_title": params["case"]["title"],
        "grid_path": str(grid_path),
        "bathymetry_source": bathy_source,
        "horizontal_resolution_m": resolution_m,
        "vertical_levels_N": int(vertical.N),
        "hmin_config_m": float(vertical.Hmin_m),
        "variables_present": {
            "lon_rho": True,
            "lat_rho": True,
            "lon_u": True,
            "lat_u": True,
            "lon_v": True,
            "lat_v": True,
            "pm": True,
            "pn": True,
            "angle": True,
            "mask_rho": True,
            "mask_u": True,
            "mask_v": True,
            "h": True,
        },
        "h_stats": {
            "all_min": float(np.nanmin(grid.h)),
            "all_max": float(np.nanmax(grid.h)),
            "all_mean": float(np.nanmean(grid.h)),
            "wet_min": float(np.nanmin(h_wet)),
            "wet_max": float(np.nanmax(h_wet)),
            "wet_mean": float(np.nanmean(h_wet)),
            "wet_lt_10m_count": int(np.count_nonzero(wet & (grid.h < 10.0))),
            "wet_eq_10m_count": int(np.count_nonzero(wet & np.isclose(grid.h, 10.0))),
        },
        "mask_stats": {
            "wet_count": int(np.count_nonzero(wet)),
            "land_count": int(np.count_nonzero(dry)),
            "mask_u_mismatch_count": mask_u_mismatch,
            "mask_v_mismatch_count": mask_v_mismatch,
            "mask_psi_mismatch_count": mask_psi_mismatch,
            "wet_connected_components": int(wet_component_count),
            "land_connected_components": int(dry_component_count),
            "isolated_wet_count": isolated_wet,
            "weakly_connected_wet_count": weakly_connected_wet,
            "isolated_dry_hole_count": isolated_dry,
            "weakly_connected_dry_hole_count": weakly_connected_dry,
        },
        "rx0_stats": {
            "max": float(rx0_max),
            "rx1_max": float(rx1_max),
            "mean": float(np.nanmean(rx0_values)) if rx0_values.size else float("nan"),
            "p95": float(np.nanpercentile(rx0_values, 95.0)) if rx0_values.size else float("nan"),
        },
        "orthogonality": orth_metrics,
        "angle_metrics": angle_info,
        "pm_pn_consistency": pm_pn_info,
        "boundary_masks": {name: asdict(value) for name, value in boundaries.items()},
        "source": {
            "configured_lon": placement.configured_lon,
            "configured_lat": placement.configured_lat,
            "nearest_xi": placement.nearest_xi,
            "nearest_eta": placement.nearest_eta,
            "nearest_is_water": placement.nearest_is_water,
            "snapped_xi": placement.snapped_xi,
            "snapped_eta": placement.snapped_eta,
            "snapped_lon": placement.snapped_lon,
            "snapped_lat": placement.snapped_lat,
            "snapped_depth_m": placement.snapped_depth_m,
            "snapped_distance_m": placement.snapped_distance_m,
            "mask_rho_value": source_mask_value,
            "placement_rule": placement.placement_rule,
        },
        "shoreline_source": (
            f"{shoreline_dataset} {shoreline_resolution}/L{shoreline_level} via {shoreline_backend}; shapefile={shoreline_shapefile}"
            if shoreline_dataset
            else "Derived from GEBCO elevation sign only; no external shoreline dataset used by current grid-generation code."
        ),
        "mask_cleanup_source_grid": mask_cleanup_source,
        "x_y_present": bool(x_rho is not None and y_rho is not None),
        "figures": {key: str(path) for key, path in figures.items()},
    }

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    print(f"case={summary['case_name']}")
    print(f"grid={grid_path}")
    print(f"h_min_all={summary['h_stats']['all_min']:.3f}")
    print(f"h_max_all={summary['h_stats']['all_max']:.3f}")
    print(f"h_mean_all={summary['h_stats']['all_mean']:.3f}")
    print(f"h_min_wet={summary['h_stats']['wet_min']:.3f}")
    print(f"h_lt_10m_wet={summary['h_stats']['wet_lt_10m_count']}")
    print(f"h_eq_10m_wet={summary['h_stats']['wet_eq_10m_count']}")
    print(f"mask_rho_wet={summary['mask_stats']['wet_count']}")
    print(f"mask_rho_land={summary['mask_stats']['land_count']}")
    print(f"mask_u_mismatch={mask_u_mismatch}")
    print(f"mask_v_mismatch={mask_v_mismatch}")
    print(f"mask_psi_mismatch={mask_psi_mismatch}")
    print(f"rx0_max={summary['rx0_stats']['max']:.6f}")
    print(f"rx0_mean={summary['rx0_stats']['mean']:.6f}")
    print(f"rx0_p95={summary['rx0_stats']['p95']:.6f}")
    print(f"rx1_max={summary['rx0_stats']['rx1_max']:.6f}")
    for edge_name, edge in summary["boundary_masks"].items():
        print(
            f"boundary_{edge_name}=wet_points:{edge['wet_points']},land_points:{edge['land_points']},"
            f"wet_segments:{edge['wet_segments']},continuous:{edge['continuous']}"
        )
    print(
        "source_snapped="
        f"xi:{placement.snapped_xi},eta:{placement.snapped_eta},"
        f"mask:{source_mask_value},depth_m:{placement.snapped_depth_m:.3f},"
        f"distance_m:{placement.snapped_distance_m:.3f}"
    )
    print(f"orthogonality_error_max_deg={summary['orthogonality']['max_deg']:.6f}")
    print(f"pm_relerr_max={pm_pn_info.get('pm_relerr_max')}")
    print(f"pn_relerr_max={pm_pn_info.get('pn_relerr_max')}")
    print(f"geometry_metrics_status={pm_pn_info['status']}")
    print(f"shoreline_source={summary['shoreline_source']}")
    print(f"json_output={json_output}")
    for key, path in figures.items():
        print(f"{key}_png={path}")
    if pm_pn_info["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
