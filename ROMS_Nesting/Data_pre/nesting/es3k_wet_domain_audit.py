"""Read-only ES3K wet-domain, strait and boundary diagnostic (I3 only).

An unwanted wet sea cell must NEVER be reclassified as land simply to make
an area metric pass. Geographic windows below are screening proxies, not
official coastline, strait polygons, or scientifically accepted boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np
from netCDF4 import Dataset
from scipy import ndimage

SCHEMA_VERSION = 1
FOUR_CONNECTED = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)


@dataclass(frozen=True)
class Region:
    west: float
    east: float
    south: float
    north: float

    def contains(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        return ((lon >= self.west) & (lon <= self.east)
                & (lat >= self.south) & (lat <= self.north))


REGIONS = {
    "japan_basin_core": Region(134.0, 138.5, 39.5, 43.0),
    "ulleung_basin": Region(130.0, 133.8, 36.0, 39.3),
    "yamato_basin": Region(133.5, 137.8, 37.1, 40.2),
    "tsushima_strait": Region(128.4, 131.0, 33.5, 36.2),
    "tsugaru_strait": Region(139.6, 142.1, 40.6, 42.2),
    "soya_strait": Region(141.0, 143.5, 44.8, 46.5),
    "tatar_strait": Region(140.0, 142.9, 47.0, 51.5),
    # A conservative rectangular diagnostic proxy west of Korea;
    # never apply this geographical window as a land mask.
    "west_of_korea_yellow_sea_proxy": Region(123.5, 126.5, 34.0, 39.0),
}
STRAITS = ("tsushima_strait", "tsugaru_strait", "soya_strait", "tatar_strait")


def _runs(mask: np.ndarray) -> list[list[int]]:
    mask = np.asarray(mask, dtype=bool)
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False])
    return [[int(a), int(b)] for a, b in zip(starts, ends)]


def _check_shape(name: str, array: np.ndarray, shape: tuple[int, int]) -> None:
    if array.shape != shape:
        raise ValueError(f"{name} shape mismatch: {array.shape} != {shape}")


def analyze(lon: np.ndarray, lat: np.ndarray, mask: np.ndarray,
            pm: np.ndarray, pn: np.ndarray, *,
            staggered: dict[str, np.ndarray] | None = None,
            regions: dict[str, Region] | None = None) -> dict:
    """Audit WGS84 metric-based wet areas and four-neighbor connectivity."""
    lon, lat, mask = np.asarray(lon), np.asarray(lat), np.asarray(mask)
    pm, pn = np.asarray(pm), np.asarray(pn)
    if lon.ndim != 2 or min(lon.shape) < 3:
        raise ValueError("expected 2D ROMS rho array (>=3x3)")
    for name, a in (("latitude", lat), ("mask_rho", mask), ("pm", pm), ("pn", pn)):
        _check_shape(name, a, lon.shape)
    for name, a in (("lon", lon), ("lat", lat), ("pm", pm), ("pn", pn)):
        if not np.isfinite(a).all():
            raise ValueError(f"nonfinite {name}")
    if (np.abs(lat) > 90).any() or (np.abs(lon) > 180).any():
        raise ValueError("geographic coordinate outside valid range")
    if not (np.isin(mask, [0, 1]).all() and (pm > 0).all() and (pn > 0).all()):
        raise ValueError("nonbinary mask or nonpositive metrics")
    wet = mask.astype(bool)
    wet_before = wet.copy()
    area_km2 = 1.0 / (pm * pn * 1_000_000.0)
    labels, nlabels = ndimage.label(wet, structure=FOUR_CONNECTED)
    counts = np.bincount(labels.ravel(), minlength=nlabels + 1)
    cells = int(wet.sum())
    if cells == 0:
        raise ValueError("ES3K has no wet rho cells")
    areas = np.bincount(labels.ravel(), weights=area_km2.ravel(), minlength=nlabels + 1)
    dominant_label = int(np.argmax(counts[1:]) + 1)
    actual_staggers = {
        "mask_u": wet[:, :-1] & wet[:, 1:],
        "mask_v": wet[:-1, :] & wet[1:, :],
        "mask_psi": (wet[:-1, :-1] & wet[:-1, 1:]
                     & wet[1:, :-1] & wet[1:, 1:]),
    }
    stagger_errors = {}
    for name, expect in actual_staggers.items():
        if staggered is None or name not in staggered:
            stagger_errors[name] = None
        else:
            check = np.asarray(staggered[name])
            _check_shape(name, check, expect.shape)
            if not np.isin(check, [0, 1]).all():
                raise ValueError(f"nonbinary stagger {name}")
            stagger_errors[name] = int(np.count_nonzero(check != expect))
    if any(v for v in stagger_errors.values() if v is not None):
        raise ValueError(f"staggered masks disagree with rho: {stagger_errors}")

    windows = regions or REGIONS
    if ("japan_basin_core" not in windows or
            "west_of_korea_yellow_sea_proxy" not in windows):
        raise ValueError("audit windows must include core and unwanted-water proxy")
    core_geo = windows["japan_basin_core"].contains(lon, lat)
    core_labels = labels[core_geo & wet]
    core_label = int(np.bincount(core_labels).argmax()) if core_labels.size else 0
    if core_label == 0:
        raise ValueError("failed to identify Japan Basin core wet component")
    region_report = {}
    for name, box in windows.items():
        inside = box.contains(lon, lat)
        active = inside & wet
        touched = np.unique(labels[active])
        region_report[name] = {
            "diagnostic_bbox_wesn_deg": [box.west, box.east, box.south, box.north],
            "rho_points_inside": int(inside.sum()),
            "wet_rho_points": int(active.sum()),
            "wet_area_km2_metrics_approx": float(area_km2[active].sum()),
            "wet_components_seen": int(np.count_nonzero(touched)),
            "core_connected_wet_points": int(np.count_nonzero(active & (labels == core_label))),
            "connected_to_japan_basin": bool(np.any(active & (labels == core_label))),
            "interpretation": "GEOGRAPHIC_WINDOW_DIAGNOSTIC_NOT_A_COASTLINE_POLYGON",
        }
    boundary_report = {}
    for side, edge in (("west", wet[:, 0]), ("east", wet[:, -1]),
                       ("south", wet[0, :]), ("north", wet[-1, :])):
        runs = _runs(edge)
        boundary_report[side] = {
            "wet_rho_points": int(edge.sum()),
            "wet_segments_ij_inclusive": runs,
            "wet_segments": len(runs),
        }
    yellow = region_report["west_of_korea_yellow_sea_proxy"]["wet_rho_points"]
    straits = {name: region_report[name]["connected_to_japan_basin"]
               for name in STRAITS if name in windows}
    flags = []
    if any(v is False for v in straits.values()):
        flags.append("STRAIT_WINDOW_HAS_NO_CONNECTED_WET_PATH")
    if yellow:
        flags.append("UNWANTED_WEST_OF_KOREA_WET_CELLS_REVIEW_DOMAIN_GEOMETRY")
    if nlabels > 1:
        flags.append("ADDITIONAL_WET_COMPONENTS_REQUIRE_REVIEW")
    if not any(d["wet_rho_points"] for d in boundary_report.values()):
        flags.append("NO_WET_OPEN_BOUNDARY")
    if not np.array_equal(wet, wet_before):
        raise AssertionError("wet mask changed inside read-only analyzer")
    return {
        "schema_version": SCHEMA_VERSION,
        "grid_purpose": "I3_ES3K_SCIENTIFIC_WET_DOMAIN_DIAGNOSTIC",
        "result_status": "REVIEW_REQUIRED" if flags else "NO_FLAGS_DIAGNOSTIC_ONLY",
        "I3_physics_acceptance": "NOT_RUN",
        "mask_was_modified": False,
        "mask_semantics": "ROMS_MASK_0_IS_LAND_OR_USER_MASKED_NO_FAKE_LAND_APPLIED",
        "geographic_region_status": "PROXY_WINDOWS_NOT_EXACT_STRAIT_OR_BASIN_POLYGONS",
        "rho_shape_eta_xi": list(lon.shape),
        "total_rho_points": int(wet.size),
        "wet_rho_points": cells,
        "dry_rho_points": int(wet.size - cells),
        "wet_area_km2_metrics_approx": float(area_km2[wet].sum()),
        "wet_connected_component_count_4_neighbor": int(nlabels),
        "dominant_component_wet_rho_points": int(counts[dominant_label]),
        "dominant_component_wet_area_km2": float(areas[dominant_label]),
        "japan_basin_core_component_label": core_label,
        "japan_basin_core_component_size": int(counts[core_label]),
        "stagger_mask_disagreement_counts": stagger_errors,
        "region_diagnostics": region_report,
        "strait_window_connected_to_core": straits,
        "outer_boundary": boundary_report,
        "review_flags": flags,
        "perimeter_design_disposition": (
            "REVIEW_AND_POSSIBLY_REDESIGN_FOUR_CORNER_EDGES" if yellow
            else "CONTINUE_I3_REVIEW_WITHOUT_FORCED_SEA_MASKING"
        ),
    }


def audit_grid(path: Path, *, regions: dict[str, Region] | None = None) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"ES3K grid.nc required: {path}")
    with Dataset(path) as nc:
        if getattr(nc, "grid_id", "") != "ES3K":
            raise ValueError("expected ES3K grid_id; refusing to audit a different nesting level")
        names = ("lon_rho", "lat_rho", "mask_rho", "pm", "pn",
                 "mask_u", "mask_v", "mask_psi")
        if any(k not in nc.variables for k in names):
            raise ValueError("ES3K grid missing required variables")
        d = {k: np.asarray(nc[k][:]) for k in names}
        provenance = {
            "grid_path": str(path),
            "geometry_status": str(getattr(nc, "geometry_status", "UNKNOWN")),
            "bathymetry_source": str(getattr(nc, "bathymetry_source", "UNKNOWN")),
            "shoreline_status": str(getattr(nc, "shoreline_status", "UNKNOWN")),
            "shoreline_source": str(getattr(nc, "shoreline_source", "UNKNOWN")),
            "synthetic_test_only": str(getattr(nc, "synthetic_test_only", "UNKNOWN")),
            "bathymetry_smoothing_status": str(getattr(nc, "bathymetry_smoothing_status", "UNKNOWN")),
        }
    report = analyze(d["lon_rho"], d["lat_rho"], d["mask_rho"],
                     d["pm"], d["pn"],
                     staggered={k: d[k] for k in ("mask_u", "mask_v", "mask_psi")},
                     regions=regions)
    report["input_provenance"] = provenance
    report["source_is_approved_real_GEBCO_GSHHG"] = False
    report["real_inputs_review"] = (
        "SYNTHETIC_ONLY" if provenance["synthetic_test_only"] != "FALSE"
        else "PROVENANCE_MUST_BE_INDEPENDENTLY_VERIFIED"
    )
    return report


def save_report(report: dict, destination: Path) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
