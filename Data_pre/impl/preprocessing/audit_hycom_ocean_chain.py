#!/usr/bin/env python3
"""Audit HYCOM raw and ROMS ocean files for the active case."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

from case_naming import load_case_naming, roms_input_name, staged_ocean_name
from roms_preprocessing_utils import (
    PREPROCESSING_VERSION,
    ROOT,
    infer_variable,
    load_grid,
    read_time_values,
    resolve_grid_path,
    summarize_numeric,
)


DEFAULT_OUTPUT_DIR = ROOT / "diagnostics" / f"hycom_boundary_audit_{load_case_naming().slug}"
DEFAULT_RAW_INITIAL = ROOT / "data" / "raw" / "ocean" / staged_ocean_name("hycom", "initial")
DEFAULT_RAW_BOUNDARY = ROOT / "data" / "raw" / "ocean" / staged_ocean_name("hycom", "boundary")
DEFAULT_ROMS_INITIAL = ROOT / "input" / roms_input_name("ini")
DEFAULT_ROMS_BOUNDARY = ROOT / "input" / roms_input_name("bdy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-initial", default=str(DEFAULT_RAW_INITIAL))
    parser.add_argument("--raw-boundary", default=str(DEFAULT_RAW_BOUNDARY))
    parser.add_argument("--roms-initial", default=str(DEFAULT_ROMS_INITIAL))
    parser.add_argument("--roms-boundary", default=str(DEFAULT_ROMS_BOUNDARY))
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat()


def json_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return value


def file_stub(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else None,
        "mtime": iso_mtime(path),
    }


def attr_dict(ds: Dataset) -> dict[str, object]:
    return {name: json_builtin(getattr(ds, name)) for name in ds.ncattrs()}


def dim_dict(ds: Dataset) -> dict[str, int]:
    return {name: len(dim) for name, dim in ds.dimensions.items()}


def coord_summary(ds: Dataset, name: str) -> dict[str, object] | None:
    if name not in ds.variables:
        return None
    values = np.asarray(ds.variables[name][:], dtype=float)
    return {
        "size": int(values.size),
        "min": float(np.nanmin(values)),
        "max": float(np.nanmax(values)),
        "first": float(values.flat[0]),
        "last": float(values.flat[-1]),
    }


def time_summary(ds: Dataset, candidates: tuple[str, ...]) -> dict[str, object] | None:
    try:
        values, _, time_name = read_time_values(ds, candidates)
    except Exception:  # noqa: BLE001
        return None
    return {
        "name": time_name,
        "count": int(len(values)),
        "start": values[0].isoformat(),
        "end": values[-1].isoformat(),
    }


def canonical_stats(ds: Dataset, mapping: dict[str, tuple[str, ...]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for canonical, candidates in mapping.items():
        try:
            name = infer_variable(ds, candidates)
        except Exception:  # noqa: BLE001
            continue
        raw = ds.variables[name][:]
        values = np.ma.filled(raw, np.nan) if np.ma.isMaskedArray(raw) else np.asarray(raw, dtype=float)
        out[canonical] = {
            "source_name": name,
            "dimensions": list(ds.variables[name].dimensions),
            "attrs": {attr: json_builtin(getattr(ds.variables[name], attr)) for attr in ds.variables[name].ncattrs()},
            "stats": summarize_numeric(values),
        }
    return out


def audit_raw_source(path: Path) -> dict[str, object]:
    result = file_stub(path)
    if not path.exists():
        return result
    with Dataset(path) as ds:
        result["global_attrs"] = attr_dict(ds)
        result["dimensions"] = dim_dict(ds)
        result["coord_ranges"] = {
            name: coord_summary(ds, name)
            for name in ("time", "depth", "lat", "lon")
            if name in ds.variables
        }
        result["time"] = time_summary(ds, ("time", "ocean_time", "mt"))
        result["variables"] = list(ds.variables)
        result["canonical"] = canonical_stats(
            ds,
            {
                "zeta": ("zeta", "ssh", "surf_el"),
                "temp": ("temp", "water_temp", "temperature"),
                "salt": ("salt", "salinity"),
                "u": ("u", "water_u", "u_velocity"),
                "v": ("v", "water_v", "v_velocity"),
            },
        )
    return result


def audit_roms_initial(path: Path, grid_path: Path) -> dict[str, object]:
    result = file_stub(path)
    if not path.exists():
        return result
    grid = load_grid(grid_path)
    mask_rho = grid.mask_rho == 1
    mask_u = mask_rho[:, :-1] & mask_rho[:, 1:]
    mask_v = mask_rho[:-1, :] & mask_rho[1:, :]
    with Dataset(path) as ds:
        result["global_attrs"] = attr_dict(ds)
        result["dimensions"] = dim_dict(ds)
        result["time"] = time_summary(ds, ("ocean_time", "time"))
        result["variables"] = list(ds.variables)
        result["wet_stats"] = {}
        for name, mask in (
            ("zeta", mask_rho),
            ("temp", mask_rho),
            ("salt", mask_rho),
            ("u", mask_u),
            ("v", mask_v),
            ("ubar", mask_u),
            ("vbar", mask_v),
        ):
            values = np.ma.filled(ds.variables[name][:], np.nan)
            result["wet_stats"][name] = {
                "full": summarize_numeric(values),
                "wet": summarize_numeric(values, mask),
            }
    return result


def boundary_masks(grid) -> dict[str, dict[str, np.ndarray]]:
    mask_rho = grid.mask_rho == 1
    mask_u = mask_rho[:, :-1] & mask_rho[:, 1:]
    mask_v = mask_rho[:-1, :] & mask_rho[1:, :]
    return {
        "rho": {
            "west": mask_rho[:, 0],
            "east": mask_rho[:, -1],
            "south": mask_rho[0, :],
            "north": mask_rho[-1, :],
        },
        "u": {
            "west": mask_u[:, 0],
            "east": mask_u[:, -1],
            "south": mask_u[0, :],
            "north": mask_u[-1, :],
        },
        "v": {
            "west": mask_v[:, 0],
            "east": mask_v[:, -1],
            "south": mask_v[0, :],
            "north": mask_v[-1, :],
        },
    }


def audit_roms_boundary(path: Path, grid_path: Path) -> dict[str, object]:
    result = file_stub(path)
    if not path.exists():
        return result
    grid = load_grid(grid_path)
    masks = boundary_masks(grid)
    with Dataset(path) as ds:
        result["global_attrs"] = attr_dict(ds)
        result["dimensions"] = dim_dict(ds)
        result["time"] = {
            name: time_summary(ds, (name,))
            for name in ("zeta_time", "v2d_time", "v3d_time", "temp_time", "salt_time", "dye_time")
            if name in ds.variables
        }
        result["variables"] = list(ds.variables)
        result["boundary_stats"] = {}
        for prefix, mask_kind in (
            ("zeta", "rho"),
            ("temp", "rho"),
            ("salt", "rho"),
            ("u", "u"),
            ("v", "v"),
            ("ubar", "u"),
            ("vbar", "v"),
        ):
            for edge in ("west", "east", "south", "north"):
                name = f"{prefix}_{edge}"
                values = np.ma.filled(ds.variables[name][:], np.nan)
                wet_mask = masks[mask_kind][edge]
                result["boundary_stats"][name] = {
                    "full": summarize_numeric(values),
                    "wet": summarize_numeric(values, wet_mask),
                    "wet_count": int(np.asarray(wet_mask, dtype=bool).sum()),
                }
    return result


def suspicion_flags(report: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    raw_boundary = report["files"]["raw_boundary"]
    roms_boundary = report["files"]["roms_boundary"]
    raw_salt = raw_boundary.get("canonical", {}).get("salt", {}).get("stats")
    raw_temp = raw_boundary.get("canonical", {}).get("temp", {}).get("stats")
    if raw_salt:
        out["raw_boundary_salt_mean_lt_30"] = raw_salt["mean"] is not None and raw_salt["mean"] < 30.0
    if raw_salt and raw_temp and raw_salt["mean"] is not None and raw_temp["mean"] is not None:
        out["raw_boundary_temp_salt_mean_gap_lt_3"] = abs(raw_salt["mean"] - raw_temp["mean"]) < 3.0
    boundary_stats = roms_boundary.get("boundary_stats", {})
    salt_means = {}
    for edge in ("west", "east", "south", "north"):
        key = f"salt_{edge}"
        if key in boundary_stats:
            salt_means[edge] = boundary_stats[key]["wet"]["mean"]
    out["roms_boundary_salt_means"] = salt_means
    out["roms_boundary_salt_any_mean_lt_30"] = any(
        value is not None and value < 30.0 for value in salt_means.values()
    )
    return out


def compare_boundary_ranges(report: dict[str, object]) -> dict[str, object]:
    raw_boundary = report["files"]["raw_boundary"]
    roms_boundary = report["files"]["roms_boundary"]
    raw_salt = raw_boundary.get("canonical", {}).get("salt", {}).get("stats", {})
    out = {
        "raw_hycom_boundary_salt_range": {
            "min": raw_salt.get("min"),
            "max": raw_salt.get("max"),
            "mean": raw_salt.get("mean"),
        },
        "roms_boundary_salt_ranges": {},
    }
    for edge in ("west", "east", "south", "north"):
        stats = roms_boundary.get("boundary_stats", {}).get(f"salt_{edge}", {})
        out["roms_boundary_salt_ranges"][edge] = stats.get("wet", {})
    return out


def render_stats(summary: dict[str, object]) -> str:
    return (
        f"min={summary.get('min')} max={summary.get('max')} mean={summary.get('mean')} "
        f"finite={summary.get('finite_count')} nan={summary.get('nan_count')}"
    )


def write_markdown(report: dict[str, object], path: Path) -> None:
    lines: list[str] = []
    lines.append("# HYCOM Ocean Chain Audit")
    lines.append("")
    lines.append(f"- generated_at: {report['generated_at']}")
    lines.append(f"- preprocessing_version: {PREPROCESSING_VERSION}")
    lines.append("")
    lines.append("## Files")
    for label, info in report["files"].items():
        lines.append(f"### {label}")
        lines.append(f"- path: `{info['path']}`")
        lines.append(f"- exists: `{info['exists']}`")
        lines.append(f"- size: `{info.get('size')}`")
        lines.append(f"- mtime: `{info.get('mtime')}`")
        if not info["exists"]:
            lines.append("")
            continue
        attrs = info.get("global_attrs", {})
        lines.append(f"- cache_format_version: `{attrs.get('cache_format_version')}`")
        lines.append(f"- preprocessing_version: `{attrs.get('preprocessing_version')}`")
        lines.append(f"- dimensions: `{info.get('dimensions')}`")
        lines.append(f"- time: `{info.get('time')}`")
        lines.append(f"- variables: `{info.get('variables')}`")
        if label.startswith("raw_"):
            for canonical, entry in info.get("canonical", {}).items():
                lines.append(f"- {canonical}: {render_stats(entry['stats'])}")
        if label == "roms_initial":
            for name, entry in info.get("wet_stats", {}).items():
                lines.append(f"- {name} wet: {render_stats(entry['wet'])}")
        if label == "roms_boundary":
            for name, entry in info.get("boundary_stats", {}).items():
                lines.append(
                    f"- {name} wet_count={entry['wet_count']}: {render_stats(entry['wet'])}"
                )
        lines.append("")
    lines.append("## Boundary Comparison")
    comparison = report["boundary_comparison"]
    lines.append(f"- raw HYCOM boundary salt range: `{comparison['raw_hycom_boundary_salt_range']}`")
    for edge, stats in comparison["roms_boundary_salt_ranges"].items():
        lines.append(f"- ROMS {edge} boundary salt range: `{stats}`")
    lines.append("")
    lines.append("## Suspicion Flags")
    for key, value in report["suspicion_flags"].items():
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    report = {
        "generated_at": datetime.now().isoformat(),
        "preprocessing_version": PREPROCESSING_VERSION,
        "grid_path": str(grid_path),
        "files": {
            "raw_initial": audit_raw_source(Path(args.raw_initial)),
            "raw_boundary": audit_raw_source(Path(args.raw_boundary)),
            "roms_initial": audit_roms_initial(Path(args.roms_initial), grid_path),
            "roms_boundary": audit_roms_boundary(Path(args.roms_boundary), grid_path),
        },
    }
    report["boundary_comparison"] = compare_boundary_ranges(report)
    report["suspicion_flags"] = suspicion_flags(report)
    md_path = output_dir / "hycom_ocean_chain_audit.md"
    json_path = output_dir / "hycom_ocean_chain_audit.json"
    write_markdown(report, md_path)
    json_path.write_text(json.dumps(report, indent=2, default=json_builtin) + "\n")
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
