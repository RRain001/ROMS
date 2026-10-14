#!/usr/bin/env python3
"""Shared shoreline loading and land/sea classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import struct
from typing import Iterable

import numpy as np


INSTALL_HINT = "Install shoreline dependencies with: python3 -m pip install shapely geopandas pyogrio"
VALID_GSHHG_RESOLUTIONS = ("c", "l", "i", "h", "f")


@dataclass(frozen=True)
class BoundingBox:
    west: float
    east: float
    south: float
    north: float

    def intersects(self, other: "BoundingBox") -> bool:
        return not (
            self.east < other.west
            or self.west > other.east
            or self.north < other.south
            or self.south > other.north
        )

    def contains_point(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north


@dataclass(frozen=True)
class ShorelineRecord:
    bbox: BoundingBox
    parts: tuple[np.ndarray, ...]
    point_count: int


@dataclass(frozen=True)
class ShorelineGeometry:
    dataset: str
    version: str
    shapefile_path: Path
    resolution: str
    level: int
    bbox: BoundingBox
    backend: str
    warnings: tuple[str, ...]
    records: tuple[ShorelineRecord, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def point_count(self) -> int:
        return int(sum(record.point_count for record in self.records))


def default_shoreline_config() -> dict[str, object]:
    return {
        "enabled": False,
        "dataset": "GSHHG",
        "version": "",
        "format": "shapefile",
        "base_dir": "",
        "default_resolution": "h",
        "nearshore_resolution": "f",
        "level": 1,
        "use_for_mask_cleanup": True,
        "use_for_bathymetry": False,
        "bbox_margin_deg": 0.05,
    }


def load_shoreline_config(params: dict[str, object]) -> dict[str, object]:
    cfg = default_shoreline_config()
    cfg.update(params.get("shoreline", {}))
    return cfg


def validate_grid_longitudes(lon: np.ndarray) -> None:
    lon_values = np.asarray(lon, dtype=float)
    if np.nanmin(lon_values) < -180.0 or np.nanmax(lon_values) > 180.0:
        raise SystemExit(
            "shoreline classification currently supports only [-180, 180] longitudes. "
            "Convert the grid or add explicit 0-360 handling before using shoreline cleanup."
        )


def bbox_from_grid(lon: np.ndarray, lat: np.ndarray, margin_deg: float = 0.05) -> BoundingBox:
    validate_grid_longitudes(lon)
    return BoundingBox(
        west=float(np.nanmin(lon) - margin_deg),
        east=float(np.nanmax(lon) + margin_deg),
        south=float(np.nanmin(lat) - margin_deg),
        north=float(np.nanmax(lat) + margin_deg),
    )


def resolve_gshhg_shapefile(
    shoreline_cfg: dict[str, object],
    resolution: str | None = None,
    level: int | None = None,
) -> tuple[Path, str, int]:
    dataset = str(shoreline_cfg.get("dataset", ""))
    if dataset.upper() != "GSHHG":
        raise SystemExit(f"unsupported shoreline dataset: {dataset!r}; only GSHHG is supported right now")
    selected_resolution = str(resolution or shoreline_cfg.get("default_resolution") or "h").strip().lower()
    selected_level = int(level or shoreline_cfg.get("level") or 1)
    if selected_resolution not in VALID_GSHHG_RESOLUTIONS:
        raise SystemExit(
            f"unsupported GSHHG resolution {selected_resolution!r}; expected one of {VALID_GSHHG_RESOLUTIONS}"
        )
    if selected_level != 1:
        raise SystemExit(f"unsupported GSHHG shoreline level L{selected_level}; only L1 is enabled right now")
    base_dir = Path(str(shoreline_cfg.get("base_dir", "")).strip())
    if not str(base_dir):
        raise SystemExit("shoreline.base_dir is not configured")
    shp_path = base_dir / selected_resolution / f"GSHHS_{selected_resolution}_L{selected_level}.shp"
    if not shp_path.exists():
        matches = sorted((base_dir / selected_resolution).glob(f"GSHHS_{selected_resolution}_L{selected_level}*.shp"))
        if len(matches) == 1:
            shp_path = matches[0]
        else:
            raise SystemExit(f"GSHHG shapefile not found: {shp_path}")
    return shp_path, selected_resolution, selected_level


def _geopandas_available() -> bool:
    return importlib.util.find_spec("geopandas") is not None and importlib.util.find_spec("shapely") is not None


def _iter_polygon_parts(geometry) -> Iterable[tuple[np.ndarray, ...]]:
    geom_type = geometry.geom_type
    if geom_type == "Polygon":
        yield _polygon_to_parts(geometry)
        return
    if geom_type == "MultiPolygon":
        for polygon in geometry.geoms:
            yield _polygon_to_parts(polygon)
        return
    raise SystemExit(f"unsupported geometry type in shoreline dataset: {geom_type}")


def _polygon_to_parts(polygon) -> tuple[np.ndarray, ...]:
    parts = [np.asarray(polygon.exterior.coords[:], dtype=float)]
    parts.extend(np.asarray(ring.coords[:], dtype=float) for ring in polygon.interiors)
    return tuple(parts)


def _load_records_geopandas(shp_path: Path, bbox: BoundingBox) -> tuple[tuple[ShorelineRecord, ...], str]:
    import geopandas as gpd  # type: ignore

    gdf = gpd.read_file(shp_path, bbox=(bbox.west, bbox.south, bbox.east, bbox.north))
    records: list[ShorelineRecord] = []
    for geometry in gdf.geometry:
        if geometry is None or geometry.is_empty:
            continue
        minx, miny, maxx, maxy = geometry.bounds
        for parts in _iter_polygon_parts(geometry):
            part_bbox = BoundingBox(west=minx, east=maxx, south=miny, north=maxy)
            point_count = int(sum(part.shape[0] for part in parts))
            records.append(ShorelineRecord(bbox=part_bbox, parts=parts, point_count=point_count))
    return tuple(records), "geopandas"


def _load_records_builtin(shp_path: Path, bbox: BoundingBox) -> tuple[tuple[ShorelineRecord, ...], str]:
    records: list[ShorelineRecord] = []
    with shp_path.open("rb") as handle:
        header = handle.read(100)
        if len(header) != 100:
            raise SystemExit(f"invalid shapefile header: {shp_path}")
        shape_type = struct.unpack("<i", header[32:36])[0]
        if shape_type not in (5, 15, 25):
            raise SystemExit(f"unsupported GSHHG shapefile type {shape_type} in {shp_path}")
        while True:
            record_header = handle.read(8)
            if not record_header:
                break
            _, content_length_words = struct.unpack(">2i", record_header)
            content = handle.read(content_length_words * 2)
            if len(content) != content_length_words * 2:
                raise SystemExit(f"truncated shapefile record in {shp_path}")
            record_shape_type = struct.unpack("<i", content[:4])[0]
            if record_shape_type == 0:
                continue
            if record_shape_type not in (5, 15, 25):
                raise SystemExit(f"unsupported polygon record type {record_shape_type} in {shp_path}")
            xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
            record_bbox = BoundingBox(west=xmin, east=xmax, south=ymin, north=ymax)
            if not record_bbox.intersects(bbox):
                continue
            num_parts, num_points = struct.unpack("<2i", content[36:44])
            parts_idx = struct.unpack(f"<{num_parts}i", content[44 : 44 + 4 * num_parts])
            points_offset = 44 + 4 * num_parts
            points = np.frombuffer(content, dtype="<f8", offset=points_offset, count=num_points * 2).reshape(num_points, 2).copy()
            slices = list(parts_idx) + [num_points]
            parts = tuple(points[start:stop] for start, stop in zip(slices[:-1], slices[1:]) if stop - start >= 3)
            if not parts:
                continue
            records.append(
                ShorelineRecord(
                    bbox=record_bbox,
                    parts=parts,
                    point_count=int(sum(part.shape[0] for part in parts)),
                )
            )
    return tuple(records), "builtin_shapefile_fallback"


def load_shoreline_geometry(
    shoreline_cfg: dict[str, object],
    bbox: BoundingBox,
    resolution: str | None = None,
    level: int | None = None,
) -> ShorelineGeometry:
    shp_path, selected_resolution, selected_level = resolve_gshhg_shapefile(shoreline_cfg, resolution=resolution, level=level)
    warnings: list[str] = []
    if _geopandas_available():
        records, backend = _load_records_geopandas(shp_path, bbox)
    else:
        warnings.append(
            "Standard GIS dependencies (geopandas/shapely/pyogrio) are unavailable; "
            f"using builtin shapefile fallback. {INSTALL_HINT}"
        )
        records, backend = _load_records_builtin(shp_path, bbox)
    return ShorelineGeometry(
        dataset=str(shoreline_cfg.get("dataset", "GSHHG")),
        version=str(shoreline_cfg.get("version", "")),
        shapefile_path=shp_path,
        resolution=selected_resolution,
        level=selected_level,
        bbox=bbox,
        backend=backend,
        warnings=tuple(warnings),
        records=records,
    )


def _points_in_ring(ring: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    x = ring[:, 0]
    y = ring[:, 1]
    inside = np.zeros(lon.shape, dtype=bool)
    last = x.shape[0] - 1
    for idx in range(x.shape[0]):
        xi, yi = x[idx], y[idx]
        xj, yj = x[last], y[last]
        crosses = (yi > lat) != (yj > lat)
        x_intersection = (xj - xi) * (lat - yi) / ((yj - yi) + 1.0e-300) + xi
        inside ^= crosses & (lon < x_intersection)
        last = idx
    return inside


def classify_land_mask(geometry: ShorelineGeometry, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon_values = np.asarray(lon, dtype=float)
    lat_values = np.asarray(lat, dtype=float)
    if lon_values.shape != lat_values.shape:
        raise SystemExit("lon/lat grid shapes do not match for shoreline classification")
    validate_grid_longitudes(lon_values)
    flat_lon = lon_values.ravel()
    flat_lat = lat_values.ravel()
    land = np.zeros(flat_lon.shape, dtype=bool)
    for record in geometry.records:
        candidates = (
            (flat_lon >= record.bbox.west)
            & (flat_lon <= record.bbox.east)
            & (flat_lat >= record.bbox.south)
            & (flat_lat <= record.bbox.north)
        )
        if not np.any(candidates):
            continue
        lon_subset = flat_lon[candidates]
        lat_subset = flat_lat[candidates]
        record_land = np.zeros(lon_subset.shape, dtype=bool)
        for part in record.parts:
            part_bbox = BoundingBox(
                west=float(np.min(part[:, 0])),
                east=float(np.max(part[:, 0])),
                south=float(np.min(part[:, 1])),
                north=float(np.max(part[:, 1])),
            )
            part_candidates = (
                (lon_subset >= part_bbox.west)
                & (lon_subset <= part_bbox.east)
                & (lat_subset >= part_bbox.south)
                & (lat_subset <= part_bbox.north)
            )
            if not np.any(part_candidates):
                continue
            part_land = _points_in_ring(part, lon_subset[part_candidates], lat_subset[part_candidates])
            record_land[part_candidates] ^= part_land
        land[candidates] |= record_land
    return land.reshape(lon_values.shape)


def contains_point(geometry: ShorelineGeometry, lon: float, lat: float) -> bool:
    land = classify_land_mask(geometry, np.asarray([[lon]], dtype=float), np.asarray([[lat]], dtype=float))
    return bool(land[0, 0])
