#!/usr/bin/env python3
"""Clean a ROMS land/sea mask with shoreline-assisted diagnostics and manual edits."""

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

from case_context import get_case_config_dir, get_case_root
from case_naming import load_case_naming
from pilot_grid_utils import locate_source_on_grid
from roms_preprocessing_utils import (
    derive_staggered_masks,
    load_grid,
    load_project_params,
    load_vertical_config,
    resolve_grid_path,
)
from shoreline import (
    INSTALL_HINT,
    BoundingBox,
    bbox_from_grid,
    classify_land_mask,
    contains_point,
    load_shoreline_config,
    load_shoreline_geometry,
    resolve_gshhg_shapefile,
)


ROOT = get_case_root()
CONFIG_DIR = get_case_config_dir()
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
    parser.add_argument("--output", default=None)
    parser.add_argument("--shoreline-resolution", choices=["c", "l", "i", "h", "f"], default=None)
    parser.add_argument("--shoreline-level", type=int, default=None)
    parser.add_argument("--shoreline-margin-deg", type=float, default=None)
    parser.add_argument("--manual-edits", default=None)
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--report-md", default=None)
    parser.add_argument("--figures-dir", default=None)
    parser.add_argument("--source-review-threshold-m", type=float, default=500.0)
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
    wet_values = np.asarray(mask, dtype=bool)
    wet_points = int(wet_values.sum())
    land_points = int(wet_values.size - wet_points)
    wet_segments = count_segments(wet_values)
    wet_indices = np.where(wet_values)[0]
    first_wet = int(wet_indices[0]) if wet_indices.size else None
    last_wet = int(wet_indices[-1]) if wet_indices.size else None
    return BoundarySummary(
        wet_points=wet_points,
        land_points=land_points,
        wet_segments=wet_segments,
        first_wet_index=first_wet,
        last_wet_index=last_wet,
        continuous=wet_segments <= 1,
    )


def mask_diagnostics(mask_rho: np.ndarray) -> dict[str, object]:
    wet = np.asarray(mask_rho, dtype=np.int8) == 1
    dry = ~wet
    wet_neighbors = neighbor_count(wet)
    dry_neighbors = neighbor_count(dry)
    wet_labels, wet_component_count = ndimage.label(wet)
    _, dry_component_count = ndimage.label(dry)
    return {
        "wet_count": int(np.count_nonzero(wet)),
        "land_count": int(np.count_nonzero(dry)),
        "wet_connected_components": int(wet_component_count),
        "land_connected_components": int(dry_component_count),
        "isolated_wet_count": int(np.count_nonzero(wet & (wet_neighbors == 0))),
        "weakly_connected_wet_count": int(np.count_nonzero(wet & (wet_neighbors <= 1))),
        "isolated_land_hole_count": int(np.count_nonzero(dry & (dry_neighbors == 4))),
        "weakly_connected_land_hole_count": int(np.count_nonzero(dry & (dry_neighbors >= 3))),
        "boundaries": {
            "west": asdict(summarize_boundary(wet[:, 0])),
            "east": asdict(summarize_boundary(wet[:, -1])),
            "south": asdict(summarize_boundary(wet[0, :])),
            "north": asdict(summarize_boundary(wet[-1, :])),
        },
        "wet_labels": wet_labels,
    }


def hotspot_regions(diff_mask: np.ndarray, lon: np.ndarray, lat: np.ndarray, limit: int = 8) -> list[dict[str, object]]:
    labels, count = ndimage.label(diff_mask)
    rows: list[dict[str, object]] = []
    for label_id in range(1, count + 1):
        idx = np.argwhere(labels == label_id)
        if idx.size == 0:
            continue
        eta_min = int(idx[:, 0].min())
        eta_max = int(idx[:, 0].max())
        xi_min = int(idx[:, 1].min())
        xi_max = int(idx[:, 1].max())
        eta_mid = int(round(float(idx[:, 0].mean())))
        xi_mid = int(round(float(idx[:, 1].mean())))
        rows.append(
            {
                "grid_points": int(idx.shape[0]),
                "eta_min": eta_min,
                "eta_max": eta_max,
                "xi_min": xi_min,
                "xi_max": xi_max,
                "lon_center": float(lon[eta_mid, xi_mid]),
                "lat_center": float(lat[eta_mid, xi_mid]),
                "lon_min": float(np.min(lon[idx[:, 0], idx[:, 1]])),
                "lon_max": float(np.max(lon[idx[:, 0], idx[:, 1]])),
                "lat_min": float(np.min(lat[idx[:, 0], idx[:, 1]])),
                "lat_max": float(np.max(lat[idx[:, 0], idx[:, 1]])),
            }
        )
    rows.sort(key=lambda row: row["grid_points"], reverse=True)
    return rows[:limit]


def meters_per_degree_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def distance_field_m(lon: np.ndarray, lat: np.ndarray, lon0: float, lat0: float) -> np.ndarray:
    dx = (lon - lon0) * meters_per_degree_lon(lat0)
    dy = (lat - lat0) * 111_320.0
    return np.hypot(dx, dy)


def locate_source_on_arrays(
    lon: np.ndarray,
    lat: np.ndarray,
    h: np.ndarray,
    mask: np.ndarray,
    source_lon: float,
    source_lat: float,
) -> dict[str, object]:
    distance = distance_field_m(lon, lat, source_lon, source_lat)
    nearest_eta, nearest_xi = np.unravel_index(np.argmin(distance), distance.shape)
    nearest_is_water = bool(mask[nearest_eta, nearest_xi] == 1)
    if nearest_is_water:
        snapped_eta, snapped_xi = nearest_eta, nearest_xi
        placement_rule = "configured source already on water rho cell"
    else:
        wet = mask == 1
        if not np.any(wet):
            raise SystemExit("mask cleanup cannot locate source: no wet rho cells remain")
        snapped_eta, snapped_xi = np.unravel_index(np.argmin(np.where(wet, distance, np.inf)), distance.shape)
        placement_rule = "configured source on land; snapped to nearest mask_rho=1 rho cell"
    return {
        "configured_lon": float(source_lon),
        "configured_lat": float(source_lat),
        "nearest_xi": int(nearest_xi),
        "nearest_eta": int(nearest_eta),
        "nearest_lon": float(lon[nearest_eta, nearest_xi]),
        "nearest_lat": float(lat[nearest_eta, nearest_xi]),
        "nearest_is_water": nearest_is_water,
        "snapped_xi": int(snapped_xi),
        "snapped_eta": int(snapped_eta),
        "snapped_lon": float(lon[snapped_eta, snapped_xi]),
        "snapped_lat": float(lat[snapped_eta, snapped_xi]),
        "snapped_distance_m": float(distance[snapped_eta, snapped_xi]),
        "snapped_depth_m": float(h[snapped_eta, snapped_xi]),
        "placement_rule": placement_rule,
    }


def default_manual_edits_path() -> Path:
    naming = load_case_naming()
    explicit = CONFIG_DIR / f"mask_edits_{naming.case_name}.json"
    if explicit.exists():
        return explicit
    slugged = CONFIG_DIR / f"mask_edits_{naming.slug}.json"
    return slugged


def load_manual_edits(path_arg: str | None) -> tuple[Path | None, dict[str, object], bool]:
    path = Path(path_arg).expanduser().resolve() if path_arg else default_manual_edits_path()
    default = {
        "force_wet_points": [],
        "force_land_points": [],
        "force_wet_ij_ranges": [],
        "force_land_ij_ranges": [],
    }
    if not path.exists():
        return None, default, False
    data = json.loads(path.read_text())
    for key, value in default.items():
        data.setdefault(key, value)
    return path, data, True


def apply_manual_edits(
    mask: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    h: np.ndarray,
    hmin: float,
    edits: dict[str, object],
) -> tuple[np.ndarray, list[dict[str, object]]]:
    updated = np.asarray(mask, dtype=np.int8).copy()
    changes: list[dict[str, object]] = []

    def set_points(entries: list[dict[str, object]], target_value: int, label: str) -> None:
        for index, entry in enumerate(entries, start=1):
            lon0 = float(entry["lon"])
            lat0 = float(entry["lat"])
            radius_m = float(entry.get("radius_m", 0.0))
            reason = str(entry.get("reason", ""))
            distance = distance_field_m(lon, lat, lon0, lat0)
            target = distance <= radius_m
            if target_value == 1:
                target &= h >= hmin
            before = int(np.count_nonzero(updated[target] != target_value))
            updated[target] = target_value
            changes.append(
                {
                    "type": label,
                    "index": index,
                    "lon": lon0,
                    "lat": lat0,
                    "radius_m": radius_m,
                    "changed_points": before,
                    "reason": reason,
                }
            )

    def set_ranges(entries: list[dict[str, object]], target_value: int, label: str) -> None:
        for index, entry in enumerate(entries, start=1):
            xi_start = int(entry["xi_start"])
            xi_end = int(entry["xi_end"])
            eta_start = int(entry["eta_start"])
            eta_end = int(entry["eta_end"])
            region = np.s_[eta_start : eta_end + 1, xi_start : xi_end + 1]
            if target_value == 1:
                target = h[region] >= hmin
                before = int(np.count_nonzero(updated[region][target] != target_value))
                region_values = updated[region]
                region_values[target] = target_value
                updated[region] = region_values
            else:
                before = int(np.count_nonzero(updated[region] != target_value))
                updated[region] = target_value
            changes.append(
                {
                    "type": label,
                    "index": index,
                    "xi_start": xi_start,
                    "xi_end": xi_end,
                    "eta_start": eta_start,
                    "eta_end": eta_end,
                    "changed_points": before,
                    "reason": str(entry.get("reason", "")),
                }
            )

    set_points(list(edits.get("force_wet_points", [])), 1, "force_wet_points")
    set_points(list(edits.get("force_land_points", [])), 0, "force_land_points")
    set_ranges(list(edits.get("force_wet_ij_ranges", [])), 1, "force_wet_ij_ranges")
    set_ranges(list(edits.get("force_land_ij_ranges", [])), 0, "force_land_ij_ranges")
    return updated, changes


def auto_cleanup_mask(mask_rho: np.ndarray, shoreline_land: np.ndarray, h: np.ndarray, hmin: float) -> tuple[np.ndarray, dict[str, int]]:
    updated = np.asarray(mask_rho, dtype=np.int8).copy()
    wet = updated == 1
    wet_neighbors = neighbor_count(wet)
    shoreline_sea = ~shoreline_land

    wet_to_land = wet & shoreline_land & (wet_neighbors <= 1)
    land_to_wet = (~wet) & shoreline_sea & (wet_neighbors >= 3) & (h >= hmin)

    updated[wet_to_land] = 0
    updated[land_to_wet] = 1
    return updated, {
        "auto_wet_to_land": int(np.count_nonzero(wet_to_land)),
        "auto_land_to_wet": int(np.count_nonzero(land_to_wet)),
    }


def source_component_reaches_open_boundary(mask_rho: np.ndarray, source_eta: int, source_xi: int) -> tuple[bool, list[str]]:
    wet = np.asarray(mask_rho, dtype=np.int8) == 1
    labels, _ = ndimage.label(wet)
    label = int(labels[source_eta, source_xi])
    if label == 0:
        return False, []
    reached: list[str] = []
    if np.any(labels[:, 0] == label):
        reached.append("west")
    if np.any(labels[:, -1] == label):
        reached.append("east")
    if np.any(labels[0, :] == label):
        reached.append("south")
    if np.any(labels[-1, :] == label):
        reached.append("north")
    return bool(reached), reached


def copy_grid_with_mask_updates(
    source_grid: Path,
    output_grid: Path,
    mask_rho: np.ndarray,
    attrs: dict[str, object],
) -> None:
    mask_u, mask_v, mask_psi = derive_staggered_masks(mask_rho)
    output_grid.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(source_grid) as src, Dataset(output_grid, "w", format="NETCDF4") as dst:
        for name, dimension in src.dimensions.items():
            dst.createDimension(name, len(dimension) if not dimension.isunlimited() else None)
        dst.setncatts({attr: src.getncattr(attr) for attr in src.ncattrs()})
        for key, value in attrs.items():
            dst.setncattr(key, value)
        for name, variable in src.variables.items():
            dst_var = dst.createVariable(name, variable.datatype, variable.dimensions, zlib=True, complevel=1)
            dst_var.setncatts({attr: variable.getncattr(attr) for attr in variable.ncattrs()})
            if name == "mask_rho":
                dst_var[:] = mask_rho.astype(variable.dtype)
            elif name == "mask_u":
                dst_var[:] = mask_u.astype(variable.dtype)
            elif name == "mask_v":
                dst_var[:] = mask_v.astype(variable.dtype)
            elif name == "mask_psi":
                dst_var[:] = mask_psi.astype(variable.dtype)
            else:
                dst_var[:] = variable[:]


def _scale_canvas(rgb: np.ndarray, title: str, scale: int = 4) -> Image.Image:
    image = Image.fromarray(rgb, mode="RGB").resize((rgb.shape[1] * scale, rgb.shape[0] * scale), NEAREST_RESAMPLE)
    canvas = Image.new("RGB", (image.width, image.height + 30), "white")
    canvas.paste(image, (0, 30))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="black")
    return canvas


def _draw_marker(draw: ImageDraw.ImageDraw, x: float, y: float, color: str, shape: str) -> None:
    if shape == "cross":
        draw.line((x - 8, y, x + 8, y), fill=color, width=2)
        draw.line((x, y - 8, x, y + 8), fill=color, width=2)
    elif shape == "circle":
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline=color, width=2)
    else:
        draw.rectangle((x - 7, y - 7, x + 7, y + 7), outline=color, width=2)


def _mask_rgb(mask: np.ndarray) -> np.ndarray:
    wet = np.asarray(mask, dtype=bool)
    rgb = np.zeros((*wet.shape, 3), dtype=np.uint8)
    rgb[:] = np.array([180, 180, 180], dtype=np.uint8)
    rgb[wet] = np.array([40, 110, 220], dtype=np.uint8)
    return rgb


def _diff_rgb(current_wet: np.ndarray, shoreline_land: np.ndarray) -> np.ndarray:
    shoreline_sea = ~shoreline_land
    rgb = np.zeros((*current_wet.shape, 3), dtype=np.uint8)
    rgb[:] = np.array([180, 180, 180], dtype=np.uint8)
    rgb[current_wet & shoreline_sea] = np.array([40, 110, 220], dtype=np.uint8)
    rgb[current_wet & shoreline_land] = np.array([220, 70, 50], dtype=np.uint8)
    rgb[(~current_wet) & shoreline_sea] = np.array([70, 170, 90], dtype=np.uint8)
    return rgb


def save_mask_png(path: Path, title: str, mask: np.ndarray) -> None:
    canvas = _scale_canvas(_mask_rgb(mask), title)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def save_diff_png(path: Path, title: str, current_wet: np.ndarray, shoreline_land: np.ndarray) -> None:
    canvas = _scale_canvas(_diff_rgb(current_wet, shoreline_land), title)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def _fractional_index(lon: np.ndarray, lat: np.ndarray, point_lon: float, point_lat: float) -> tuple[float, float]:
    xi = (point_lon - float(lon[0, 0])) / max(float(lon[0, -1] - lon[0, 0]), 1.0e-12) * (lon.shape[1] - 1)
    eta = (point_lat - float(lat[0, 0])) / max(float(lat[-1, 0] - lat[0, 0]), 1.0e-12) * (lat.shape[0] - 1)
    return xi, eta


def _draw_shoreline(
    draw: ImageDraw.ImageDraw,
    geometry,
    lon_crop: np.ndarray,
    lat_crop: np.ndarray,
    panel_left: int,
    panel_top: int,
    scale: int,
    color: str,
) -> None:
    crop_bbox = BoundingBox(
        west=float(np.min(lon_crop)),
        east=float(np.max(lon_crop)),
        south=float(np.min(lat_crop)),
        north=float(np.max(lat_crop)),
    )
    xi_offset = 0.0
    eta_offset = 0.0
    full_lon = lon_crop
    full_lat = lat_crop
    for record in geometry.records:
        if not record.bbox.intersects(crop_bbox):
            continue
        for part in record.parts:
            xs: list[float] = []
            ys: list[float] = []
            for point_lon, point_lat in part:
                if (
                    point_lon < crop_bbox.west - 0.05
                    or point_lon > crop_bbox.east + 0.05
                    or point_lat < crop_bbox.south - 0.05
                    or point_lat > crop_bbox.north + 0.05
                ):
                    continue
                xi, eta = _fractional_index(full_lon, full_lat, float(point_lon), float(point_lat))
                xs.append(panel_left + (xi - xi_offset) * scale)
                ys.append(panel_top + (eta - eta_offset) * scale)
            if len(xs) >= 2:
                draw.line(list(zip(xs, ys)), fill=color, width=1)


def save_source_zoom_png(
    path: Path,
    lon: np.ndarray,
    lat: np.ndarray,
    h: np.ndarray,
    mask_before: np.ndarray,
    mask_after: np.ndarray,
    shoreline_geometry,
    source_lon: float,
    source_lat: float,
    source_before: dict[str, object],
    source_after: dict[str, object],
    hmin: float,
) -> None:
    nearest_xi = int(source_before["nearest_xi"])
    nearest_eta = int(source_before["nearest_eta"])
    snapped_xi = int(source_before["snapped_xi"])
    snapped_eta = int(source_before["snapped_eta"])
    post_xi = int(source_after["snapped_xi"])
    post_eta = int(source_after["snapped_eta"])
    x0 = max(min(nearest_xi, snapped_xi, post_xi) - 18, 0)
    x1 = min(max(nearest_xi, snapped_xi, post_xi) + 19, lon.shape[1])
    y0 = max(min(nearest_eta, snapped_eta, post_eta) - 18, 0)
    y1 = min(max(nearest_eta, snapped_eta, post_eta) + 19, lon.shape[0])
    lon_crop = lon[y0:y1, x0:x1]
    lat_crop = lat[y0:y1, x0:x1]
    before_crop = mask_before[y0:y1, x0:x1]
    after_crop = mask_after[y0:y1, x0:x1]
    scale = 8
    panel_gap = 20
    panel_width = before_crop.shape[1] * scale
    panel_height = before_crop.shape[0] * scale
    shallow_before = (h[y0:y1, x0:x1] <= hmin + 1.0e-6) & (before_crop == 1)
    shallow_after = (h[y0:y1, x0:x1] <= hmin + 1.0e-6) & (after_crop == 1)

    left_image = Image.fromarray(_mask_rgb(before_crop), mode="RGB").resize((panel_width, panel_height), NEAREST_RESAMPLE)
    right_image = Image.fromarray(_mask_rgb(after_crop), mode="RGB").resize((panel_width, panel_height), NEAREST_RESAMPLE)
    canvas = Image.new("RGB", (panel_width * 2 + panel_gap + 20, panel_height + 60), "white")
    canvas.paste(left_image, (10, 40))
    canvas.paste(right_image, (panel_width + panel_gap + 10, 40))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), "Source neighborhood zoom: pre-cleanup (left) and post-cleanup (right)", fill="black")
    draw.text((10, 24), "red=candidate source, cyan=pre snap, magenta=post snap, black=GSHHG shoreline, yellow=h=10 m wet cell", fill="black")

    for panel_left, shallow in ((10, shallow_before), (panel_width + panel_gap + 10, shallow_after)):
        for eta_idx, xi_idx in np.argwhere(shallow):
            x = panel_left + xi_idx * scale
            y = 40 + eta_idx * scale
            draw.rectangle((x, y, x + scale - 1, y + scale - 1), outline="yellow", width=1)
        _draw_shoreline(draw, shoreline_geometry, lon_crop, lat_crop, panel_left, 40, scale, "black")

    src_x, src_y = _fractional_index(lon_crop, lat_crop, source_lon, source_lat)
    _draw_marker(draw, 10 + src_x * scale, 40 + src_y * scale, "red", "cross")
    _draw_marker(draw, panel_width + panel_gap + 10 + src_x * scale, 40 + src_y * scale, "red", "cross")

    pre_x = (snapped_xi - x0) * scale + 10
    pre_y = (snapped_eta - y0) * scale + 40
    post_x = (post_xi - x0) * scale + panel_width + panel_gap + 10
    post_y = (post_eta - y0) * scale + 40
    _draw_marker(draw, pre_x, pre_y, "cyan", "circle")
    _draw_marker(draw, post_x, post_y, "magenta", "square")

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def write_markdown(report_path: Path, report: dict[str, object]) -> None:
    boundary_lines = report["mask_after"]["boundaries"]
    lines = [
        "# ROMS GSHHG Mask Workflow",
        "",
        "## Dataset",
        "",
        f"- case: `{report['case_name']}`",
        f"- source grid: `{report['source_grid']}`",
        f"- output grid: `{report['output_grid']}`",
        f"- GSHHG base dir: `{report['shoreline']['base_dir']}`",
        f"- GSHHG shapefile used: `{report['shoreline']['shapefile']}`",
        f"- shoreline resolution: `{report['shoreline']['resolution']}`",
        f"- shoreline level: `L{report['shoreline']['level']}`",
        f"- shoreline backend: `{report['shoreline']['backend']}`",
        f"- shoreline read success: `{report['shoreline']['read_success']}`",
        "",
        "## GEBCO vs GSHHG",
        "",
        f"- GEBCO sea / GSHHG land points: `{report['difference']['gebco_sea_gshhg_land']}`",
        f"- GEBCO land / GSHHG sea points: `{report['difference']['gebco_land_gshhg_sea']}`",
        f"- difference points: `{report['difference']['difference_points']}`",
        f"- difference ratio: `{report['difference']['difference_ratio']:.6f}`",
        "",
        "Top hotspots:",
        "",
    ]
    for row in report["difference"]["hotspots"][:5]:
        lines.append(
            f"- `{row['grid_points']}` pts near lon `{row['lon_center']:.6f}`, lat `{row['lat_center']:.6f}` "
            f"(xi `{row['xi_min']}-{row['xi_max']}`, eta `{row['eta_min']}-{row['eta_max']}`)"
        )
    lines.extend(
        [
            "",
            "## Source Review",
            "",
            f"- configured lon/lat: `{report['source_review']['configured_lon']:.6f}`, `{report['source_review']['configured_lat']:.6f}`",
            f"- configured point in GSHHG land: `{report['source_review']['configured_point_gshhg_land']}`",
            f"- nearest rho point lon/lat: `{report['source_review']['nearest_rho_lon']:.6f}`, `{report['source_review']['nearest_rho_lat']:.6f}`",
            f"- current nearest rho mask: `{report['source_review']['current_nearest_rho_mask']}`",
            f"- current nearest rho GSHHG land: `{report['source_review']['current_nearest_rho_gshhg_land']}`",
            f"- pre-cleanup snapped distance m: `{report['source_review']['pre_cleanup_snapped_distance_m']:.3f}`",
            f"- post-cleanup snapped distance m: `{report['source_review']['post_cleanup_snapped_distance_m']:.3f}`",
            f"- manual edit recommended: `{report['source_review']['manual_edit_recommended']}`",
            "",
            "## Manual Edits",
            "",
            f"- manual edits enabled: `{report['manual_edits']['enabled']}`",
            f"- manual edits path: `{report['manual_edits']['path']}`",
            f"- manual edit operations applied: `{report['manual_edits']['applied_operations']}`",
            "",
            "## Cleanup Result",
            "",
            f"- wet points before: `{report['mask_before']['wet_count']}`",
            f"- wet points after: `{report['mask_after']['wet_count']}`",
            f"- land points before: `{report['mask_before']['land_count']}`",
            f"- land points after: `{report['mask_after']['land_count']}`",
            f"- isolated wet before/after: `{report['mask_before']['isolated_wet_count']}` / `{report['mask_after']['isolated_wet_count']}`",
            f"- isolated land holes before/after: `{report['mask_before']['isolated_land_hole_count']}` / `{report['mask_after']['isolated_land_hole_count']}`",
            f"- wet connected components before/after: `{report['mask_before']['wet_connected_components']}` / `{report['mask_after']['wet_connected_components']}`",
            f"- source component reaches boundary: `{report['source_component']['reaches_open_boundary']}`",
            f"- source component boundaries: `{', '.join(report['source_component']['boundaries']) or 'none'}`",
            f"- proceed to smoothing: `{report['next_step']['proceed_to_smoothing']}`",
            "",
            "Boundary continuity after cleanup:",
            "",
        ]
    )
    for edge_name in ("west", "east", "south", "north"):
        edge = boundary_lines[edge_name]
        lines.append(
            f"- {edge_name}: wet_points=`{edge['wet_points']}`, wet_segments=`{edge['wet_segments']}`, continuous=`{edge['continuous']}`"
        )
    lines.extend(
        [
            "",
        "## Figures",
        "",
        ]
    )
    for key, value in report["figures"].items():
        lines.append(f"- {key}: `{value}`")
    warnings = list(report["shoreline"]["warnings"])
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "## Workflow Reminder",
            "",
            "- Standard sequence: `stage_and_subset_bathymetry.py -> create_grid_from_bathymetry.py -> clean_roms_mask.py -> smooth_bathymetry.py -> audit_bathymetry_stability.py -> check_roms_grid_quality.py`",
            "- If this grid becomes the new active grid, regenerate downstream forcing, boundary, initial, tides, and source products.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    params = load_project_params()
    vertical = load_vertical_config()
    naming = load_case_naming()
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=False, prefer_maskclean=False)
    output_grid = Path(args.output) if args.output else grid_path.with_name(f"{grid_path.stem}_maskclean.nc")
    figures_dir = Path(args.figures_dir) if args.figures_dir else ROOT / "output" / "mask_cleanup"
    report_json = Path(args.report_json) if args.report_json else figures_dir / "mask_cleanup_summary.json"
    report_md = Path(args.report_md) if args.report_md else ROOT / "docs" / "roms_gshhg_mask_workflow.md"

    grid = load_grid(grid_path)
    shoreline_cfg = load_shoreline_config(params)
    if not bool(shoreline_cfg.get("enabled", False)):
        raise SystemExit("shoreline cleanup is disabled in project_parameters.json; set shoreline.enabled=true first")
    if not bool(shoreline_cfg.get("use_for_mask_cleanup", True)):
        raise SystemExit("shoreline.use_for_mask_cleanup=false; this script only supports shoreline-assisted mask cleanup")

    margin_deg = float(args.shoreline_margin_deg if args.shoreline_margin_deg is not None else shoreline_cfg.get("bbox_margin_deg", 0.05))
    shoreline_bbox = bbox_from_grid(grid.lon_rho, grid.lat_rho, margin_deg=margin_deg)
    shp_path, resolution, level = resolve_gshhg_shapefile(
        shoreline_cfg,
        resolution=args.shoreline_resolution,
        level=args.shoreline_level,
    )
    geometry = load_shoreline_geometry(shoreline_cfg, shoreline_bbox, resolution=resolution, level=level)
    shoreline_land = classify_land_mask(geometry, grid.lon_rho, grid.lat_rho)

    mask_before = grid.mask_rho.astype(np.int8)
    wet_before = mask_before == 1
    shoreline_sea = ~shoreline_land
    gebco_sea_gshhg_land = wet_before & shoreline_land
    gebco_land_gshhg_sea = (~wet_before) & shoreline_sea
    diff_mask = gebco_sea_gshhg_land | gebco_land_gshhg_sea

    auto_cleaned, auto_stats = auto_cleanup_mask(mask_before, shoreline_land, grid.h, vertical.Hmin_m)
    manual_path, manual_edits, manual_enabled = load_manual_edits(args.manual_edits)
    cleaned_mask, manual_changes = apply_manual_edits(auto_cleaned, grid.lon_rho, grid.lat_rho, grid.h, vertical.Hmin_m, manual_edits)

    source_lon = float(params["domain"]["source_lon"])
    source_lat = float(params["domain"]["source_lat"])
    source_before = locate_source_on_arrays(grid.lon_rho, grid.lat_rho, grid.h, mask_before, source_lon, source_lat)
    source_after = locate_source_on_arrays(grid.lon_rho, grid.lat_rho, grid.h, cleaned_mask, source_lon, source_lat)
    current_loc = locate_source_on_grid(grid_path, source_lon, source_lat)
    nearest_eta = int(source_before["nearest_eta"])
    nearest_xi = int(source_before["nearest_xi"])
    source_review = {
        "configured_lon": source_lon,
        "configured_lat": source_lat,
        "configured_point_gshhg_land": contains_point(geometry, source_lon, source_lat),
        "nearest_rho_lon": float(grid.lon_rho[nearest_eta, nearest_xi]),
        "nearest_rho_lat": float(grid.lat_rho[nearest_eta, nearest_xi]),
        "current_nearest_rho_mask": int(mask_before[nearest_eta, nearest_xi]),
        "current_nearest_rho_gshhg_land": bool(shoreline_land[nearest_eta, nearest_xi]),
        "pre_cleanup_snapped_distance_m": float(source_before["snapped_distance_m"]),
        "post_cleanup_snapped_distance_m": float(source_after["snapped_distance_m"]),
        "current_grid_rule": current_loc.placement_rule,
        "manual_edit_recommended": bool(
            contains_point(geometry, source_lon, source_lat)
            or float(source_after["snapped_distance_m"]) > float(args.source_review_threshold_m)
        ),
    }

    before_diag = mask_diagnostics(mask_before)
    after_diag = mask_diagnostics(cleaned_mask)
    source_reaches_boundary, source_boundaries = source_component_reaches_open_boundary(
        cleaned_mask,
        int(source_after["snapped_eta"]),
        int(source_after["snapped_xi"]),
    )

    figure_paths = {
        "mask_before": str(figures_dir / "mask_before.png"),
        "shoreline_mask": str(figures_dir / "gshhg_land_sea.png"),
        "mask_difference": str(figures_dir / "gebco_vs_gshhg_difference.png"),
        "mask_after": str(figures_dir / "mask_after.png"),
        "source_zoom": str(figures_dir / "source_zoom.png"),
    }
    save_mask_png(Path(figure_paths["mask_before"]), "Original mask_rho from GEBCO sign", mask_before)
    save_mask_png(Path(figure_paths["shoreline_mask"]), "GSHHG shoreline-assisted land/sea judgement", shoreline_sea)
    save_diff_png(Path(figure_paths["mask_difference"]), "GEBCO vs GSHHG mask difference", wet_before, shoreline_land)
    save_mask_png(Path(figure_paths["mask_after"]), "Mask after shoreline cleanup and manual edits", cleaned_mask)
    save_source_zoom_png(
        Path(figure_paths["source_zoom"]),
        grid.lon_rho,
        grid.lat_rho,
        grid.h,
        mask_before,
        cleaned_mask,
        geometry,
        source_lon,
        source_lat,
        source_before,
        source_after,
        vertical.Hmin_m,
    )

    attrs = {
        "mask_cleanup_source_grid": str(grid_path),
        "shoreline_dataset": geometry.dataset,
        "shoreline_version": geometry.version,
        "shoreline_format": shoreline_cfg.get("format", "shapefile"),
        "shoreline_base_dir": str(shoreline_cfg.get("base_dir", "")),
        "shoreline_shapefile": str(shp_path),
        "shoreline_resolution": geometry.resolution,
        "shoreline_level": geometry.level,
        "shoreline_backend": geometry.backend,
        "shoreline_bbox": f"{shoreline_bbox.west},{shoreline_bbox.east},{shoreline_bbox.south},{shoreline_bbox.north}",
        "mask_cleanup_note": "shoreline-assisted cleanup with conservative auto-fixes plus optional manual edits",
        "manual_mask_edits_path": str(manual_path) if manual_path else "",
        "downstream_regeneration_required": "If this grid replaces the active grid, regenerate forcing, bry, ini, tide, and source files.",
    }
    if geometry.warnings:
        attrs["shoreline_backend_warnings"] = " | ".join(geometry.warnings)
    copy_grid_with_mask_updates(grid_path, output_grid, cleaned_mask, attrs)

    difference_points = int(np.count_nonzero(diff_mask))
    total_points = int(diff_mask.size)
    report = {
        "case_name": naming.case_name,
        "source_grid": str(grid_path),
        "output_grid": str(output_grid),
        "shoreline": {
            "dataset": geometry.dataset,
            "version": geometry.version,
            "format": shoreline_cfg.get("format", "shapefile"),
            "base_dir": str(shoreline_cfg.get("base_dir", "")),
            "shapefile": str(geometry.shapefile_path),
            "resolution": geometry.resolution,
            "level": geometry.level,
            "backend": geometry.backend,
            "warnings": list(geometry.warnings),
            "read_success": True,
            "record_count": geometry.record_count,
            "point_count": geometry.point_count,
            "bbox": asdict(shoreline_bbox),
        },
        "difference": {
            "gebco_sea_gshhg_land": int(np.count_nonzero(gebco_sea_gshhg_land)),
            "gebco_land_gshhg_sea": int(np.count_nonzero(gebco_land_gshhg_sea)),
            "difference_points": difference_points,
            "difference_ratio": difference_points / total_points,
            "hotspots": hotspot_regions(diff_mask, grid.lon_rho, grid.lat_rho),
        },
        "source_review": source_review,
        "manual_edits": {
            "enabled": manual_enabled,
            "path": str(manual_path) if manual_path else "",
            "applied_operations": len(manual_changes),
            "changes": manual_changes,
        },
        "auto_cleanup": auto_stats,
        "mask_before": {key: value for key, value in before_diag.items() if key != "wet_labels"},
        "mask_after": {key: value for key, value in after_diag.items() if key != "wet_labels"},
        "source_component": {
            "reaches_open_boundary": source_reaches_boundary,
            "boundaries": source_boundaries,
        },
        "next_step": {
            "proceed_to_smoothing": bool(
                int(cleaned_mask[int(source_after["snapped_eta"]), int(source_after["snapped_xi"])]) == 1
                and source_reaches_boundary
                and after_diag["isolated_wet_count"] <= before_diag["isolated_wet_count"] + 2
            ),
            "reason": (
                "Mask cleanup preserved a wet source-connected component that reaches an open boundary; "
                "bathymetry smoothing can proceed next without changing mask."
                if source_reaches_boundary
                else "Source-connected wet component does not reach any open boundary; review mask before smoothing."
            ),
        },
        "figures": figure_paths,
        "install_hint": INSTALL_HINT,
    }

    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    write_markdown(report_md, report)

    print(f"source_grid={grid_path}")
    print(f"output_grid={output_grid}")
    print(f"shoreline_shapefile={geometry.shapefile_path}")
    print(f"shoreline_backend={geometry.backend}")
    print(f"shoreline_records={geometry.record_count}")
    print(f"shoreline_points={geometry.point_count}")
    print(f"gebco_sea_gshhg_land={report['difference']['gebco_sea_gshhg_land']}")
    print(f"gebco_land_gshhg_sea={report['difference']['gebco_land_gshhg_sea']}")
    print(f"difference_ratio={report['difference']['difference_ratio']:.6f}")
    print(f"auto_wet_to_land={auto_stats['auto_wet_to_land']}")
    print(f"auto_land_to_wet={auto_stats['auto_land_to_wet']}")
    print(f"manual_edits_enabled={manual_enabled}")
    print(f"manual_edit_operations={len(manual_changes)}")
    print(f"source_pre_cleanup_snap_m={source_review['pre_cleanup_snapped_distance_m']:.3f}")
    print(f"source_post_cleanup_snap_m={source_review['post_cleanup_snapped_distance_m']:.3f}")
    print(f"manual_edit_recommended={source_review['manual_edit_recommended']}")
    print(f"wet_before={report['mask_before']['wet_count']}")
    print(f"wet_after={report['mask_after']['wet_count']}")
    print(f"isolated_wet_before={report['mask_before']['isolated_wet_count']}")
    print(f"isolated_wet_after={report['mask_after']['isolated_wet_count']}")
    print(f"source_component_boundaries={','.join(source_boundaries) if source_boundaries else 'none'}")
    print(f"proceed_to_smoothing={report['next_step']['proceed_to_smoothing']}")
    print(f"report_json={report_json}")
    print(f"report_md={report_md}")
    for key, value in figure_paths.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
