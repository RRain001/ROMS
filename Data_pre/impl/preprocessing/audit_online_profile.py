#!/usr/bin/env python3
"""Write preread/final reports for the online MY25/UV tide profile."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import get_case_config_path, get_case_root
from case_naming import load_case_naming, roms_input_name
from pilot_grid_utils import locate_source_on_grid
from roms_preprocessing_utils import load_project_params, resolve_grid_path


ROOT = get_case_root()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="online_my25_uvtide")
    parser.add_argument("--stage", choices=["preread", "final"], default="preread")
    parser.add_argument("--grid", default=None)
    parser.add_argument("--infile", default=None)
    parser.add_argument("--header", default=None)
    return parser.parse_args()


def nc_dims(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    with Dataset(path) as ds:
        return {name: len(dim) for name, dim in ds.dimensions.items()}


def nc_vars(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    with Dataset(path) as ds:
        return sorted(ds.variables)


def variable_minmax(path: Path, name: str) -> dict[str, float | None]:
    if not path.exists():
        return {"min": None, "max": None}
    with Dataset(path) as ds:
        if name not in ds.variables:
            return {"min": None, "max": None}
        values = np.ma.filled(ds.variables[name][:], np.nan).astype(float, copy=False)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return {"min": None, "max": None}
        return {"min": float(finite.min()), "max": float(finite.max())}


def variable_stats(path: Path, name: str) -> dict[str, float | int | None]:
    if not path.exists():
        return {"finite_count": 0, "min": None, "max": None, "mean": None}
    with Dataset(path) as ds:
        if name not in ds.variables:
            return {"finite_count": 0, "min": None, "max": None, "mean": None}
        values = np.ma.filled(ds.variables[name][:], np.nan).astype(float, copy=False)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return {"finite_count": 0, "min": None, "max": None, "mean": None}
        return {
            "finite_count": int(finite.size),
            "min": float(finite.min()),
            "max": float(finite.max()),
            "mean": float(finite.mean()),
        }


def resolve_infile_path(infile: Path, value: str | None) -> Path | None:
    if not value or value.lower() == "none":
        return None
    raw = value.split()[0].strip()
    path = Path(raw)
    if path.is_absolute():
        return path
    return (infile.parent / path).resolve()


def log_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "missing"}
    text = path.read_text(errors="ignore")
    records = {}
    for label in ("HISTORY", "RESTART", "AVERAGE"):
        match = re.search(rf"number of time records written in {label} file =\s*(\d+)", text)
        if match:
            records[label.lower()] = int(match.group(1))
    model_times = re.findall(r"^\s*\d+\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{2})", text, flags=re.MULTILINE)
    status = "done" if "ROMS: DONE" in text else "running_or_incomplete"
    if "BLOWUP" in text:
        status = "blowup"
    elif re.search(r"\b(ERROR|Error|error)\b", text) and "ROMS: DONE" not in text:
        status = "error"
    return {
        "path": str(path),
        "exists": True,
        "status": status,
        "done": "ROMS: DONE" in text,
        "blowup": "BLOWUP" in text,
        "records": records,
        "last_model_time": model_times[-1] if model_times else None,
    }


def output_summary(path: Path) -> dict[str, object]:
    fields = ("zeta", "ubar", "vbar", "u", "v", "temp", "salt", "dye_01", "AKv", "AKt", "AKs")
    if not path.exists():
        return {"path": str(path), "exists": False}
    with Dataset(path) as ds:
        dims = {name: len(dim) for name, dim in ds.dimensions.items()}
    return {
        "path": str(path),
        "exists": True,
        "dims": dims,
        "stats": {name: variable_stats(path, name) for name in fields},
        "dye_inventory_bq": dye_inventory(path),
    }


def _attr_scalar(ds: Dataset, name: str, default: float) -> float:
    if name in ds.variables:
        return float(np.asarray(ds.variables[name][:]).squeeze())
    return float(getattr(ds, name, default))


def dye_inventory(path: Path) -> dict[str, float | None]:
    if not path.exists():
        return {"first": None, "last": None, "delta": None}
    with Dataset(path) as ds:
        required = ("dye_01", "zeta", "h", "pm", "pn", "s_w", "Cs_w")
        if any(name not in ds.variables for name in required):
            return {"first": None, "last": None, "delta": None}
        area = 1.0 / (
            np.ma.filled(ds.variables["pm"][:], np.nan).astype(float)
            * np.ma.filled(ds.variables["pn"][:], np.nan).astype(float)
        )
        h = np.ma.filled(ds.variables["h"][:], np.nan).astype(float)
        mask = np.ones_like(h)
        if "mask_rho" in ds.variables:
            mask = np.ma.filled(ds.variables["mask_rho"][:], 0.0).astype(float)
        s_w = np.asarray(ds.variables["s_w"][:], dtype=float)
        cs_w = np.asarray(ds.variables["Cs_w"][:], dtype=float)
        hc = _attr_scalar(ds, "hc", 200.0)

        def inventory_at(index: int) -> float:
            zeta = np.ma.filled(ds.variables["zeta"][index, :, :], np.nan).astype(float)
            z_w = np.empty((len(s_w),) + h.shape, dtype=float)
            for k, (sval, cval) in enumerate(zip(s_w, cs_w, strict=True)):
                z0 = (hc * sval + h * cval) / (hc + h)
                z_w[k, :, :] = zeta + (zeta + h) * z0
            dz = np.diff(z_w, axis=0)
            dye = np.ma.filled(ds.variables["dye_01"][index, :, :, :], 0.0).astype(float)
            volume = dz * area[np.newaxis, :, :] * mask[np.newaxis, :, :]
            values = dye * volume
            finite = values[np.isfinite(values)]
            return float(finite.sum()) if finite.size else 0.0

        first = inventory_at(0)
        last = inventory_at(-1)
        return {"first": first, "last": last, "delta": last - first}


def source_rate_summary(path: Path) -> dict[str, float | int | None]:
    if not path.exists():
        return {"mean_bq_s": None, "min_bq_s": None, "max_bq_s": None, "records": 0}
    with Dataset(path) as ds:
        if "river_transport" not in ds.variables or "river_dye_01" not in ds.variables:
            return {"mean_bq_s": None, "min_bq_s": None, "max_bq_s": None, "records": 0}
        transport = np.ma.filled(ds.variables["river_transport"][:], 0.0).astype(float)
        dye = np.ma.filled(ds.variables["river_dye_01"][:], 0.0).astype(float)
        if dye.ndim == 3 and "river_Vshape" in ds.variables:
            vshape = np.ma.filled(ds.variables["river_Vshape"][:], 0.0).astype(float)
            concentration = np.einsum("ks,tks->ts", vshape, dye)
        elif dye.ndim == 3:
            concentration = dye.max(axis=1)
        else:
            concentration = dye
        rates = np.sum(transport * concentration, axis=-1)
        finite = rates[np.isfinite(rates)]
        if finite.size == 0:
            return {"mean_bq_s": None, "min_bq_s": None, "max_bq_s": None, "records": 0}
        return {
            "mean_bq_s": float(finite.mean()),
            "min_bq_s": float(finite.min()),
            "max_bq_s": float(finite.max()),
            "records": int(finite.size),
        }


def rho_cell_summary(grid_path: Path, eta: int, xi: int) -> dict[str, float | int | bool | None]:
    if not grid_path.exists():
        return {"mask_rho": None, "is_water": None, "h": None}
    with Dataset(grid_path) as ds:
        if "mask_rho" not in ds.variables:
            return {"mask_rho": None, "is_water": None, "h": None}
        mask = int(ds.variables["mask_rho"][eta, xi])
        depth = float(ds.variables["h"][eta, xi]) if "h" in ds.variables else None
        return {"mask_rho": mask, "is_water": bool(mask == 1), "h": depth}


def run_seconds(infile: Path) -> float | None:
    scalars = infile_scalars(infile)
    try:
        ntimes = float(scalars["NTIMES"].replace("d", "e").replace("D", "e"))
        dt = float(scalars["DT"].replace("d", "e").replace("D", "e"))
    except (KeyError, ValueError):
        return None
    return ntimes * dt


def cpp_defs(path: Path) -> list[str]:
    if not path.exists():
        return []
    defs: list[str] = []
    for line in path.read_text(errors="ignore").splitlines():
        match = re.match(r"\s*#\s*define\s+([A-Za-z0-9_]+)", line)
        if match:
            defs.append(match.group(1))
    return defs


def infile_scalars(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(errors="ignore")
    out: dict[str, str] = {}
    for key in ("MyAppCPP", "N", "NPT", "Vtransform", "Vstretching", "THETA_S", "THETA_B", "TCLINE", "NTIMES", "DT", "NHIS", "NAVG", "NDIA", "NtileI", "NtileJ", "TIDENAME", "ININAME", "BRYNAME", "SSFNAME", "RSTNAME", "HISNAME", "AVGNAME", "DIANAME"):
        match = re.search(rf"^\s*{re.escape(key)}\s*=+\s*(.*?)\s*(?:!.*)?$", text, flags=re.MULTILINE)
        if match:
            out[key] = match.group(1).strip()
    return out


def write_reports(stage: str, profile: str, payload: dict) -> tuple[Path, Path]:
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    if stage == "preread":
        stem = f"{load_case_naming().slug}_online_reconfig_preread"
    else:
        stem = f"{load_case_naming().slug}_{profile}_reconfig"
    json_path = reports / f"{stem}.json"
    md_path = reports / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    lines = [
        f"# {stem}",
        "",
        f"- stage: {stage}",
        f"- profile: {profile}",
        f"- case: {payload['case']}",
        f"- status: {payload['status']}",
        "",
        "## Blocking issues",
        "",
    ]
    if payload["blocking_issues"]:
        lines.extend(f"- {issue}" for issue in payload["blocking_issues"])
    else:
        lines.append("- none")
    lines.extend(["", "## Summary", ""])
    for key in ("vertical", "physics", "tides", "source", "cpp_defs", "infile", "files", "build", "run_modes", "run_results", "source_rate", "dye_01_initial", "smagorinsky_source_level_coefficient"):
        lines.append(f"### {key}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload.get(key), indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    md_path.write_text("\n".join(lines))
    return md_path, json_path


def main() -> None:
    args = parse_args()
    params = load_project_params()
    naming = load_case_naming()
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True)
    input_dir = ROOT / "input"
    if args.stage == "preread":
        infile = Path(args.infile) if args.infile else ROOT / "run" / f"ocean_{naming.roms_prefix}_pilot.in"
        header = Path(args.header) if args.header else ROOT / "run" / f"{naming.roms_prefix}_202501.h"
        profile_for_files = None
    else:
        infile = Path(args.infile) if args.infile else ROOT / "run" / f"ocean_{naming.roms_prefix}_online_6h_{args.profile}.in"
        header = Path(args.header) if args.header else ROOT / "run" / f"{naming.roms_prefix}_202501_online_my25_uvtide.h"
        profile_for_files = args.profile
    if not header.exists() and args.stage != "preread":
        header = ROOT / "run" / f"{naming.roms_prefix}_online_my25_uvtide.h"

    source = locate_source_on_grid(grid_path, params["domain"]["source_lon"], params["domain"]["source_lat"])
    files = {
        "grid": str(grid_path),
        "ini": str(input_dir / roms_input_name("ini", profile=profile_for_files)),
        "bdy": str(input_dir / roms_input_name("bdy", profile=profile_for_files)),
        "tides": str(input_dir / roms_input_name("tides", profile=profile_for_files)),
        "river": str(input_dir / (f"roms_rivers_production_{args.profile}.nc" if profile_for_files else "roms_rivers_production.nc")),
        "header": str(header),
        "infile": str(infile),
    }
    blocking: list[str] = []
    for label, raw_path in files.items():
        if label in {"header", "infile"} and args.stage == "preread":
            continue
        if not Path(raw_path).exists():
            blocking.append(f"missing {label}: {raw_path}")
    tide_path = Path(files["tides"])
    if tide_path.exists():
        variables = nc_vars(tide_path) or []
        for name in ("tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase"):
            if name not in variables:
                blocking.append(f"UV tide variable missing: {name}")

    build_config_path = get_case_config_path("roms_build_config.json")
    run_config_path = get_case_config_path("roms_run_config.json")
    build: dict[str, object] = {}
    run_modes: dict[str, object] = {}
    run_results: dict[str, object] = {}
    if build_config_path.exists():
        build_config = json.loads(build_config_path.read_text())
        variant = build_config.get("variants", {}).get(args.profile, {})
        binary = ROOT / build_config.get("build", {}).get("bin_subdir", "bin") / variant.get("executable_name", "")
        build = {
            "variant": args.profile,
            "roms_application": variant.get("roms_application"),
            "header_name": variant.get("header_name"),
            "executable": str(binary),
            "executable_exists": binary.exists(),
            "build_dir": str(ROOT / build_config.get("build", {}).get("build_subdir", "build/Build_romsM")),
            "status": "ok" if binary.exists() else "blocked",
        }
        if args.stage == "final" and not binary.exists():
            blocking.append(f"missing executable: {binary}")
    if run_config_path.exists():
        run_config = json.loads(run_config_path.read_text())
        missing_tide = f"missing referenced input file: {infile_scalars(infile).get('TIDENAME')}"
        for mode_name in ("online_6h", "online_3d", "online_month"):
            mode_cfg = run_config.get("run_modes", {}).get(mode_name, {})
            mode_infile = ROOT / "run" / mode_cfg.get("infile", "")
            mode_binary = ROOT / "bin" / mode_cfg.get("binary", "")
            mode_log = ROOT / "logs" / mode_cfg.get("log_file", f"{mode_name}.log")
            mode_scalars = infile_scalars(mode_infile)
            mode_blockers: list[str] = []
            if not mode_infile.exists():
                mode_blockers.append(f"missing infile: {mode_infile}")
            if not mode_binary.exists():
                mode_blockers.append(f"missing executable: {mode_binary}")
            if not tide_path.exists():
                mode_blockers.append(missing_tide)
            outputs = {
                "history": resolve_infile_path(mode_infile, mode_scalars.get("HISNAME")),
                "average": resolve_infile_path(mode_infile, mode_scalars.get("AVGNAME")),
                "diagnostics": resolve_infile_path(mode_infile, mode_scalars.get("DIANAME")),
                "restart": resolve_infile_path(mode_infile, mode_scalars.get("RSTNAME")),
            }
            if args.stage == "final" and mode_name in {"online_6h", "online_3d"}:
                log = log_summary(mode_log)
                if log.get("status") != "done":
                    mode_blockers.append(f"{mode_name} run not complete: {mode_log}")
                for output_label, output_path in outputs.items():
                    if output_path is not None and output_label in {"history", "average", "diagnostics"} and not output_path.exists():
                        mode_blockers.append(f"missing {mode_name} {output_label} output: {output_path}")
                source_rate = source_rate_summary(Path(files["river"]))
                seconds = run_seconds(mode_infile)
                mean_rate = source_rate.get("mean_bq_s")
                estimated_source = float(mean_rate * seconds) if isinstance(mean_rate, float) and seconds is not None else None
                history_path = outputs.get("history")
                run_results[mode_name] = {
                    "log": log,
                    "outputs": {
                        label: output_summary(path) if path is not None and label == "history" else {
                            "path": str(path) if path is not None else None,
                            "exists": bool(path and path.exists()),
                            "dims": nc_dims(path) if path is not None and path.exists() and path.suffix == ".nc" else None,
                        }
                        for label, path in outputs.items()
                    },
                    "duration_seconds": seconds,
                    "estimated_cumulative_source_bq": estimated_source,
                    "dye_inventory_vs_source": {
                        "history_inventory_bq": output_summary(history_path)["dye_inventory_bq"] if history_path is not None else None,
                        "estimated_cumulative_source_bq": estimated_source,
                    },
                }
            run_modes[mode_name] = {
                "infile": str(mode_infile),
                "infile_exists": mode_infile.exists(),
                "binary": str(mode_binary),
                "binary_exists": mode_binary.exists(),
                "log": str(mode_log),
                "outputs": {label: str(path) if path is not None else None for label, path in outputs.items()},
                "np": mode_cfg.get("np", run_config.get("np")),
                "status": "blocked" if mode_blockers else "ready",
                "blocking_issues": mode_blockers,
            }

    snapped_cell = rho_cell_summary(grid_path, int(source.snapped_eta), int(source.snapped_xi))
    payload = {
        "case": naming.case_name,
        "profile": args.profile,
        "stage": args.stage,
        "status": "blocked" if blocking else "ok",
        "blocking_issues": blocking,
        "vertical": params.get("vertical", {}),
        "physics": params.get("physics", {}),
        "tides": params.get("tides", {}),
        "source": {
            "configured_lon": source.configured_lon,
            "configured_lat": source.configured_lat,
            "snapped_lon": source.snapped_lon,
            "snapped_lat": source.snapped_lat,
            "snapped_xi": source.snapped_xi,
            "snapped_eta": source.snapped_eta,
            "snapped_depth_m": source.snapped_depth_m,
            "snap_distance_m": source.snapped_distance_m,
            "nearest_is_water": source.nearest_is_water,
            "snapped_cell": snapped_cell,
        },
        "cpp_defs": cpp_defs(header),
        "infile": infile_scalars(infile),
        "files": {label: {"path": raw_path, "exists": Path(raw_path).exists(), "dims": nc_dims(Path(raw_path)) if raw_path.endswith(".nc") else None} for label, raw_path in files.items()},
        "build": build,
        "run_modes": run_modes,
        "run_results": run_results,
        "source_rate": source_rate_summary(Path(files["river"])),
        "dye_01_initial": variable_minmax(Path(files["ini"]), "dye_01"),
        "smagorinsky_source_level_coefficient": 0.2,
    }
    md_path, json_path = write_reports(args.stage, args.profile, payload)
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
