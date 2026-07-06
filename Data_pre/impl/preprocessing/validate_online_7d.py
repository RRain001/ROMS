#!/usr/bin/env python3
"""Validate the FDNPP online MY25/UV tide 7-day run and write reports."""

from __future__ import annotations

import argparse
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

from case_context import get_case_root
from case_naming import load_case_naming, output_product_name
from ocean_source_utils import normalize_ocean_source
from pilot_grid_utils import locate_source_on_grid
from roms_preprocessing_utils import load_project_params, resolve_grid_path

ROOT = get_case_root()
PROFILE = "online_my25_uvtide"
SECONDS_PER_HOUR = 3600.0
NEAR_SOURCE_M = 5000.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    lon1_r, lat1_r, lon2_r, lat2_r = map(radians, (lon1, lat1, lon2, lat2))
    dlon = lon2_r - lon1_r
    dlat = lat2_r - lat1_r
    a = sin(dlat / 2.0) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2.0) ** 2
    return 2.0 * r * asin(sqrt(a))


def scalar_var(ds: Dataset, name: str, default: float) -> float:
    if name in ds.variables:
        return float(np.asarray(ds.variables[name][:]).squeeze())
    return float(getattr(ds, name, default))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocean-source", default="hycom")
    parser.add_argument("--profile", default=PROFILE)
    return parser.parse_args()


def report_stem(ocean_source: str, profile: str) -> str:
    suffix = "" if ocean_source == "hycom" else f"_{ocean_source}"
    return f"fdnpp_{profile}_7d{suffix}_validation"


def get_paths(ocean_source: str, profile: str) -> dict[str, Path]:
    source_for_name = None if ocean_source == "hycom" else ocean_source
    log_name = "online_7d.log" if ocean_source == "hycom" else f"online_7d_{ocean_source}.log"
    return {
        "grid": resolve_grid_path(None, prefer_smoothed=True),
        "history": ROOT / "output" / output_product_name("his", "online_7d", source_for_name, profile),
        "average": ROOT / "output" / output_product_name("avg", "online_7d", source_for_name, profile),
        "diagnostics": ROOT / "output" / output_product_name("dia", "online_7d", source_for_name, profile),
        "restart": ROOT / "output" / output_product_name("rst", "online_7d", source_for_name, profile),
        "river": ROOT / "input" / "roms_rivers_production_online_my25_uvtide.nc",
        "log": ROOT / "logs" / log_name,
    }


def log_status(path: Path) -> dict[str, object]:
    text = path.read_text(errors="ignore") if path.exists() else ""
    records = {}
    for label in ("HISTORY", "RESTART", "AVERAGE"):
        marker = f"number of time records written in {label} file ="
        for line in text.splitlines():
            if marker in line:
                records[label.lower()] = int(line.split("=")[-1].strip())
    return {
        "exists": path.exists(),
        "done": "ROMS: DONE" in text,
        "blowup": "BLOWUP" in text,
        "has_nan_text": "NaN" in text or "nan" in text,
        "has_error_text": "ERROR" in text or "Error" in text or "error" in text,
        "records": records,
        "done_line": next((line.strip() for line in text.splitlines() if "ROMS: DONE" in line), None),
    }


def source_summary(river_path: Path, source_lon: float, source_lat: float) -> dict[str, object]:
    with Dataset(river_path) as ds:
        x = int(np.asarray(ds.variables["river_Xposition"][:]).squeeze())
        if "river_Eposition" in ds.variables:
            y = int(np.asarray(ds.variables["river_Eposition"][:]).squeeze())
        else:
            y = int(np.asarray(ds.variables["river_Yposition"][:]).squeeze())
        vshape = np.asarray(ds.variables["river_Vshape"][:], dtype=float)
        transport = np.ma.filled(ds.variables["river_transport"][:], 0.0).astype(float)
        dye = np.ma.filled(ds.variables["river_dye_01"][:], 0.0).astype(float)
        concentration = np.einsum("ks,tks->ts", vshape, dye)
        rates = np.sum(transport * concentration, axis=-1)
        attrs = {name: getattr(ds, name) for name in ds.ncattrs()}
    return {
        "snapped_xi": x,
        "snapped_eta": y,
        "snapped_lon": float(attrs.get("snapped_source_lon", source_lon)),
        "snapped_lat": float(attrs.get("snapped_source_lat", source_lat)),
        "snapped_depth_m": float(attrs.get("snapped_source_depth_m", np.nan)),
        "configured_lon": float(attrs.get("configured_source_lon", source_lon)),
        "configured_lat": float(attrs.get("configured_source_lat", source_lat)),
        "placement_rule": attrs.get("source_placement_rule"),
        "vertical_nonzero_levels": int(np.count_nonzero(vshape[:, 0])),
        "vertical_sum": float(vshape[:, 0].sum()),
        "surface_only": bool(np.count_nonzero(vshape[:, 0]) == 1 and vshape[-1, 0] > 0.0),
        "mean_rate_bq_s": float(np.mean(rates)),
        "min_rate_bq_s": float(np.min(rates)),
        "max_rate_bq_s": float(np.max(rates)),
    }


def boundary_flags(grid_type: str, eta: int, xi: int, shape: tuple[int, int]) -> dict[str, object]:
    ny, nx = shape
    near = []
    if xi <= 1:
        near.append("west")
    if xi >= nx - 2:
        near.append("east")
    if eta <= 1:
        near.append("south")
    if eta >= ny - 2:
        near.append("north")
    open_near = [name for name in near if name in {"east", "south", "north"}]
    return {
        "grid_type": grid_type,
        "near_boundary": bool(near),
        "boundary_sides": near,
        "near_open_boundary": bool(open_near),
        "open_boundary_sides": open_near,
    }


def rho_context(ds: Dataset, eta: int, xi: int) -> tuple[float, float, float, int]:
    lon = float(ds.variables["lon_rho"][eta, xi])
    lat = float(ds.variables["lat_rho"][eta, xi])
    depth = float(ds.variables["h"][eta, xi])
    mask = int(ds.variables["mask_rho"][eta, xi])
    return lon, lat, depth, mask


def u_context(ds: Dataset, eta: int, xi: int) -> tuple[float, float, float, int]:
    lon1, lat1, depth1, mask1 = rho_context(ds, eta, xi)
    lon2, lat2, depth2, mask2 = rho_context(ds, eta, xi + 1)
    return (
        0.5 * (lon1 + lon2),
        0.5 * (lat1 + lat2),
        0.5 * (depth1 + depth2),
        int(mask1 and mask2),
    )


def v_context(ds: Dataset, eta: int, xi: int) -> tuple[float, float, float, int]:
    lon1, lat1, depth1, mask1 = rho_context(ds, eta, xi)
    lon2, lat2, depth2, mask2 = rho_context(ds, eta + 1, xi)
    return (
        0.5 * (lon1 + lon2),
        0.5 * (lat1 + lat2),
        0.5 * (depth1 + depth2),
        int(mask1 and mask2),
    )


def point_context(
    ds: Dataset,
    var_name: str,
    dims: tuple[str, ...],
    point_index: tuple[int, ...],
    source: dict[str, object],
) -> dict[str, object]:
    dim_index = {name: point_index[i] for i, name in enumerate(dims)}
    if "xi_u" in dims:
        eta = int(dim_index["eta_u"])
        xi = int(dim_index["xi_u"])
        lon, lat, depth, mask = u_context(ds, eta, xi)
        grid_type = "u"
        shape = (len(ds.dimensions["eta_u"]), len(ds.dimensions["xi_u"]))
    elif "xi_v" in dims:
        eta = int(dim_index["eta_v"])
        xi = int(dim_index["xi_v"])
        lon, lat, depth, mask = v_context(ds, eta, xi)
        grid_type = "v"
        shape = (len(ds.dimensions["eta_v"]), len(ds.dimensions["xi_v"]))
    else:
        eta = int(dim_index.get("eta_rho", 0))
        xi = int(dim_index.get("xi_rho", 0))
        lon, lat, depth, mask = rho_context(ds, eta, xi)
        grid_type = "rho"
        shape = (len(ds.dimensions["eta_rho"]), len(ds.dimensions["xi_rho"]))
    boundary = boundary_flags(grid_type, eta, xi, shape)
    distance_m = haversine_m(lon, lat, float(source["snapped_lon"]), float(source["snapped_lat"]))
    out = {
        "grid_type": grid_type,
        "eta_index": eta,
        "xi_index": xi,
        "lon": lon,
        "lat": lat,
        "h_m": depth,
        "mask_rho_like": mask,
        "distance_to_source_m": distance_m,
        "near_source_within_5km": bool(distance_m <= NEAR_SOURCE_M),
    }
    out.update(boundary)
    if "s_rho" in dims:
        k = int(dim_index["s_rho"])
        out["vertical_index"] = k
        out["s_coordinate"] = float(ds.variables["s_rho"][k])
    elif "s_w" in dims:
        k = int(dim_index["s_w"])
        out["vertical_index"] = k
        out["s_coordinate"] = float(ds.variables["s_w"][k])
    else:
        out["vertical_index"] = None
        out["s_coordinate"] = None
    return out


def valid_mask(ds: Dataset, dims: tuple[str, ...]) -> np.ndarray:
    mask_rho = np.asarray(ds.variables["mask_rho"][:], dtype=bool)
    if "xi_u" in dims:
        grid_mask = mask_rho[:, :-1] & mask_rho[:, 1:]
    elif "xi_v" in dims:
        grid_mask = mask_rho[:-1, :] & mask_rho[1:, :]
    else:
        grid_mask = mask_rho
    if "s_rho" in dims:
        return np.broadcast_to(grid_mask, (len(ds.dimensions["s_rho"]),) + grid_mask.shape)
    if "s_w" in dims:
        return np.broadcast_to(grid_mask, (len(ds.dimensions["s_w"]),) + grid_mask.shape)
    return grid_mask


def extrema_for_variable(path: Path, var_name: str, source: dict[str, object], chunk_size: int = 4) -> dict[str, object]:
    with Dataset(path) as ds:
        var = ds.variables[var_name]
        dims = var.dimensions[1:]
        time_var = ds.variables["ocean_time"]
        times = num2date(time_var[:], units=time_var.units, calendar=getattr(time_var, "calendar", "standard"))
        spatial_mask = valid_mask(ds, dims)
        global_min = None
        global_max = None
        min_idx = None
        max_idx = None
        nt = len(ds.dimensions["ocean_time"])
        for start in range(0, nt, chunk_size):
            stop = min(nt, start + chunk_size)
            data = np.ma.filled(var[start:stop], np.nan).astype(float, copy=False)
            data[:, ~spatial_mask] = np.nan
            finite_mask = np.isfinite(data)
            if not finite_mask.any():
                continue
            local_min = float(np.nanmin(data))
            local_max = float(np.nanmax(data))
            if global_min is None or local_min < global_min:
                flat = int(np.nanargmin(data))
                idx = np.unravel_index(flat, data.shape)
                global_min = local_min
                min_idx = (start + idx[0],) + idx[1:]
            if global_max is None or local_max > global_max:
                flat = int(np.nanargmax(data))
                idx = np.unravel_index(flat, data.shape)
                global_max = local_max
                max_idx = (start + idx[0],) + idx[1:]
        if min_idx is None or max_idx is None:
            return {"min": None, "max": None}

        def build_entry(kind: str, full_index: tuple[int, ...], value: float) -> dict[str, object]:
            time_index = int(full_index[0])
            point = tuple(int(v) for v in full_index[1:])
            item = {
                "value": float(value),
                "time_index": time_index,
                "time_iso": str(times[time_index].isoformat()),
            }
            item.update(point_context(ds, var_name, dims, point, source))
            return item

        return {
            "min": build_entry("min", min_idx, global_min),
            "max": build_entry("max", max_idx, global_max),
        }


def z_w(ds: Dataset, zeta: np.ndarray) -> np.ndarray:
    h = np.ma.filled(ds.variables["h"][:], np.nan).astype(float)
    hc = scalar_var(ds, "hc", 200.0)
    s_w = np.asarray(ds.variables["s_w"][:], dtype=float)
    cs_w = np.asarray(ds.variables["Cs_w"][:], dtype=float)
    zw = np.empty((len(s_w),) + h.shape, dtype=float)
    for k, (sval, cval) in enumerate(zip(s_w, cs_w, strict=True)):
        z0 = (hc * sval + h * cval) / (hc + h)
        zw[k, :, :] = zeta + (zeta + h) * z0
    return zw


def dye_inventory(path: Path) -> dict[str, float]:
    with Dataset(path) as ds:
        area = 1.0 / (
            np.ma.filled(ds.variables["pm"][:], np.nan).astype(float)
            * np.ma.filled(ds.variables["pn"][:], np.nan).astype(float)
        )
        mask = np.ma.filled(ds.variables["mask_rho"][:], 0.0).astype(float)

        def inventory(index: int) -> float:
            zeta = np.ma.filled(ds.variables["zeta"][index], np.nan).astype(float)
            zw = z_w(ds, zeta)
            dz = np.diff(zw, axis=0)
            dye = np.ma.filled(ds.variables["dye_01"][index], 0.0).astype(float)
            volume = dz * area[np.newaxis, :, :] * mask[np.newaxis, :, :]
            values = dye * volume
            finite = values[np.isfinite(values)]
            return float(finite.sum()) if finite.size else 0.0

        first = inventory(0)
        last = inventory(-1)
        return {"first_bq": first, "last_bq": last, "delta_bq": last - first}


def boundary_export_estimate(avg_path: Path) -> dict[str, float]:
    with Dataset(avg_path) as ds:
        huon = np.ma.filled(ds.variables["Huon"][:], 0.0).astype(float)
        hvom = np.ma.filled(ds.variables["Hvom"][:], 0.0).astype(float)
        dye = np.ma.filled(ds.variables["dye_01"][:], 0.0).astype(float)
        east_rate = np.sum(np.maximum(huon[:, :, :, -1], 0.0) * dye[:, :, :, -1], axis=(1, 2))
        north_rate = np.sum(np.maximum(hvom[:, :, -1, :], 0.0) * dye[:, :, -1, :], axis=(1, 2))
        south_rate = np.sum(np.maximum(-hvom[:, :, 0, :], 0.0) * dye[:, :, 0, :], axis=(1, 2))
        total_rate = east_rate + north_rate + south_rate
        cumulative = float(np.sum(total_rate) * SECONDS_PER_HOUR)
        return {
            "east_bq": float(np.sum(east_rate) * SECONDS_PER_HOUR),
            "north_bq": float(np.sum(north_rate) * SECONDS_PER_HOUR),
            "south_bq": float(np.sum(south_rate) * SECONDS_PER_HOUR),
            "total_bq": cumulative,
            "note": "Approximate outward dye export integrated from hourly-averaged Huon/Hvom times boundary-adjacent dye concentration.",
        }


def dataset_summary(path: Path, label: str, source: dict[str, object]) -> dict[str, object]:
    variable_names = ("zeta", "u", "v", "ubar", "vbar", "w", "omega", "temp", "salt", "rho", "dye_01", "AKv", "AKt", "AKs")
    return {
        "label": label,
        "path": str(path),
        "extrema": {name: extrema_for_variable(path, name, source) for name in variable_names},
    }


def build_interpretation(history: dict[str, object], average: dict[str, object], source: dict[str, object], inventory: dict[str, float], export: dict[str, float]) -> dict[str, object]:
    hist = history["extrema"]
    avg = average["extrema"]
    akt_max = max(hist["AKt"]["max"]["value"], avg["AKt"]["max"]["value"])
    aks_max = max(hist["AKs"]["max"]["value"], avg["AKs"]["max"]["value"])
    akv_max = max(hist["AKv"]["max"]["value"], avg["AKv"]["max"]["value"])
    dye_min = min(hist["dye_01"]["min"]["value"], avg["dye_01"]["min"]["value"])
    dye_max_hist = hist["dye_01"]["max"]
    temp_min = min(hist["temp"]["min"]["value"], avg["temp"]["min"]["value"])
    speed_scale = max(abs(hist["u"]["max"]["value"]), abs(hist["u"]["min"]["value"]), abs(hist["v"]["max"]["value"]), abs(hist["v"]["min"]["value"]))
    source_total = float(source["mean_rate_bq_s"]) * 7.0 * 86400.0
    inventory_delta = inventory["delta_bq"]
    closure = inventory_delta / source_total if source_total else np.nan
    return {
        "akv_akt_aks": {
            "AKv_max_gt_100": bool(akv_max > 100.0),
            "AKt_max_gt_100": bool(akt_max > 100.0),
            "AKs_max_gt_100": bool(aks_max > 100.0),
            "AKv_max_location": hist["AKv"]["max"] if hist["AKv"]["max"]["value"] >= avg["AKv"]["max"]["value"] else avg["AKv"]["max"],
            "AKt_max_location": hist["AKt"]["max"] if hist["AKt"]["max"]["value"] >= avg["AKt"]["max"]["value"] else avg["AKt"]["max"],
            "AKs_max_location": hist["AKs"]["max"] if hist["AKs"]["max"]["value"] >= avg["AKs"]["max"]["value"] else avg["AKs"]["max"],
        },
        "flow_scale": {
            "u_v_speed_order_m_s": float(speed_scale),
            "reaches_2m_s_scale": bool(speed_scale >= 2.0),
        },
        "temp_low": {
            "min_temp_c": float(temp_min),
            "near_freezing": bool(temp_min <= 0.5),
        },
        "dye": {
            "min_value": float(dye_min),
            "negative_roundoff_only": bool(dye_min >= -1.0e-9),
            "max_near_source": bool(dye_max_hist["near_source_within_5km"]),
            "max_distance_to_source_m": float(dye_max_hist["distance_to_source_m"]),
            "max_vertical_index": dye_max_hist["vertical_index"],
            "max_in_upper_quarter": bool(dye_max_hist["vertical_index"] is not None and dye_max_hist["vertical_index"] >= 30),
            "surface_source_profile": bool(source["surface_only"]),
        },
        "inventory": {
            "cumulative_source_bq": float(source_total),
            "inventory_delta_bq": float(inventory_delta),
            "inventory_over_source": float(closure),
            "approx_open_boundary_loss_bq": float(export["total_bq"]),
        },
    }


def write_reports(payload: dict[str, object], stem: str) -> tuple[Path, Path]:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{stem}.json"
    md_path = reports_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    lines = [
        f"# {stem}",
        "",
        f"- completed: {payload['run']['completed']}",
        f"- roms_done: {payload['run']['roms_done']}",
        f"- blowup: {payload['run']['blowup']}",
        f"- nan_in_log: {payload['run']['nan_in_log']}",
        f"- history_records: {payload['run']['records'].get('history')}",
        f"- average_records: {payload['run']['records'].get('average')}",
        f"- restart_records: {payload['run']['records'].get('restart')}",
        f"- recommend_online_month: {payload['recommend_online_month']}",
        "",
        "## Blocking issues",
        "",
    ]
    if payload["blocking_issues"]:
        lines.extend(f"- {item}" for item in payload["blocking_issues"])
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Interpretation",
        "",
        f"- AKv/AKt/AKs maxima above 100 m2/s: AKv={payload['interpretation']['akv_akt_aks']['AKv_max_gt_100']}, AKt={payload['interpretation']['akv_akt_aks']['AKt_max_gt_100']}, AKs={payload['interpretation']['akv_akt_aks']['AKs_max_gt_100']}",
        f"- flow reaches 2 m/s scale: {payload['interpretation']['flow_scale']['reaches_2m_s_scale']} (order {payload['interpretation']['flow_scale']['u_v_speed_order_m_s']:.3f} m/s)",
        f"- min temp near freezing: {payload['interpretation']['temp_low']['near_freezing']} (min {payload['interpretation']['temp_low']['min_temp_c']:.6f} C)",
        f"- dye negative roundoff only: {payload['interpretation']['dye']['negative_roundoff_only']} (min {payload['interpretation']['dye']['min_value']:.6e})",
        f"- dye max near source: {payload['interpretation']['dye']['max_near_source']} (distance {payload['interpretation']['dye']['max_distance_to_source_m']:.1f} m)",
        f"- source is surface-only and dye max in upper layers: source_surface_only={payload['interpretation']['dye']['surface_source_profile']}, max_vertical_index={payload['interpretation']['dye']['max_vertical_index']}",
        f"- inventory delta / cumulative source = {payload['interpretation']['inventory']['inventory_over_source']:.6f}",
        f"- approximate open-boundary loss Bq = {payload['interpretation']['inventory']['approx_open_boundary_loss_bq']:.6e}",
        "",
    ])
    for key in ("paths", "run", "source", "history", "average", "inventory", "open_boundary_export_estimate", "interpretation"):
        lines.append(f"## {key}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload[key], indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    md_path.write_text("\n".join(lines))
    return md_path, json_path


def main() -> None:
    args = parse_args()
    ocean_source = normalize_ocean_source(args.ocean_source)
    profile = args.profile
    params = load_project_params()
    naming = load_case_naming()
    paths = get_paths(ocean_source, profile)
    source_loc = locate_source_on_grid(paths["grid"], params["domain"]["source_lon"], params["domain"]["source_lat"])
    source = source_summary(paths["river"], source_loc.configured_lon, source_loc.configured_lat)
    log = log_status(paths["log"])
    history = dataset_summary(paths["history"], "history", source)
    average = dataset_summary(paths["average"], "average", source)
    inventory = dye_inventory(paths["history"])
    export = boundary_export_estimate(paths["average"])
    interpretation = build_interpretation(history, average, source, inventory, export)
    blocking = []
    if not log["done"]:
        blocking.append("online_7d log does not contain ROMS: DONE")
    if log["blowup"]:
        blocking.append("online_7d encountered BLOWUP")
    if log["has_nan_text"]:
        blocking.append("online_7d log contains NaN text")
    if log["has_error_text"]:
        blocking.append("online_7d log contains ERROR text")
    if log["records"].get("history") != 169:
        blocking.append(f"unexpected history record count: {log['records'].get('history')}")
    if log["records"].get("average") != 168:
        blocking.append(f"unexpected average record count: {log['records'].get('average')}")
    if log["records"].get("restart") is None:
        blocking.append("restart record count missing from log")
    payload = {
        "case": naming.case_name,
        "profile": profile,
        "ocean_source": ocean_source,
        "paths": {key: str(value) for key, value in paths.items()},
        "run": {
            "completed": not blocking,
            "roms_done": log["done"],
            "blowup": log["blowup"],
            "nan_in_log": log["has_nan_text"],
            "error_in_log": log["has_error_text"],
            "records": log["records"],
            "done_line": log["done_line"],
        },
        "source": source,
        "history": history,
        "average": average,
        "inventory": {
            **inventory,
            "cumulative_source_bq": float(source["mean_rate_bq_s"]) * 7.0 * 86400.0,
            "source_rate_bq_s": float(source["mean_rate_bq_s"]),
        },
        "open_boundary_export_estimate": export,
        "interpretation": interpretation,
        "blocking_issues": blocking,
        "recommend_online_month": not blocking,
    }
    md_path, json_path = write_reports(payload, report_stem(ocean_source, profile))
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
