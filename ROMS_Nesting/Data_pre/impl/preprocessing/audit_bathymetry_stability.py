#!/usr/bin/env python3
"""Audit bathymetry stability and optional DT smoke trials for the active case."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from case_context import get_case_root
from case_naming import load_case_naming, output_product_name, run_infile_name
from pilot_grid_utils import locate_source_on_grid
from roms_preprocessing_utils import compute_rx0_rx1, load_grid, load_vertical_config, local_rx0, resolve_grid_path

ROOT = get_case_root()
RUN_DIR = ROOT / "run"
DEFAULT_JSON = ROOT / "output" / "bathymetry_stability_audit.json"
DEFAULT_MD = ROOT / "docs" / "bathymetry_stability_audit.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--dt-list", default="10,20,30,60")
    parser.add_argument("--report-json", default=str(DEFAULT_JSON))
    parser.add_argument("--report-md", default=str(DEFAULT_MD))
    parser.add_argument("--rx0-threshold", type=float, default=0.35)
    parser.add_argument("--rx1-threshold", type=float, default=8.0)
    parser.add_argument("--skip-dt-trials", action="store_true")
    return parser.parse_args()


def parse_dt_list(text: str) -> list[float]:
    return [float(item) for item in text.split(",") if item.strip()]


def hotspot_rows(grid, local_factor: np.ndarray, count: int = 5) -> list[dict]:
    rows: list[dict] = []
    valid = np.isfinite(local_factor)
    if not np.any(valid):
        return rows
    values = local_factor[valid]
    if values.size > count:
        threshold = np.partition(values, -count)[-count]
        selected = np.argwhere(np.where(valid, local_factor >= threshold, False))
    else:
        selected = np.argwhere(valid)
    scored = []
    for eta, xi in selected:
        scored.append((float(local_factor[eta, xi]), int(eta), int(xi)))
    scored.sort(reverse=True)
    for value, eta, xi in scored[:count]:
        rows.append(
            {
                "eta": eta,
                "xi": xi,
                "lon": float(grid.lon_rho[eta, xi]),
                "lat": float(grid.lat_rho[eta, xi]),
                "depth_m": float(grid.h[eta, xi]),
                "local_rx0": value,
            }
        )
    return rows


def run_dt_trial(grid_path: Path, dt_seconds: float) -> dict:
    roms_exe = RUN_DIR / "romsM"
    smoke_in = RUN_DIR / run_infile_name("smoke")
    if not roms_exe.exists():
        return {"dt_seconds": dt_seconds, "status": "skipped", "reason": f"missing executable: {roms_exe}"}
    if not smoke_in.exists():
        return {"dt_seconds": dt_seconds, "status": "skipped", "reason": f"missing smoke template: {smoke_in}"}

    text = smoke_in.read_text()
    text = re.sub(r"^(\s*GRDNAME\s*==).*$", rf"\1 {os.path.relpath(grid_path, RUN_DIR)}", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*DT\s*==).*$", rf"\1 {dt_seconds:.1f}d0", text, flags=re.MULTILINE)
    suffix = f"dt{int(dt_seconds)}"
    replacements = {
        "RSTNAME": f"../output/{output_product_name('rst', f'smoke_{suffix}')}",
        "HISNAME": f"../output/{output_product_name('his', f'smoke_{suffix}')}",
        "AVGNAME": f"../output/{output_product_name('avg', f'smoke_{suffix}')}",
        "DIANAME": f"../output/{output_product_name('dia', f'smoke_{suffix}')}",
    }
    for key, value in replacements.items():
        text = re.sub(rf"^(\s*{key}\s*==).*$", rf"\1 {value}", text, flags=re.MULTILINE)

    with tempfile.TemporaryDirectory(prefix=f"{load_case_naming().slug}_dt_trial_") as tmpdir:
        trial_in = Path(tmpdir) / f"smoke_{suffix}.in"
        trial_log = ROOT / "output" / f"smoke_trial_{suffix}.log"
        trial_in.write_text(text)
        command = (
            "if [ -f \"$HOME/intel/oneapi/setvars.sh\" ]; then "
            "source \"$HOME/intel/oneapi/setvars.sh\" --force >/dev/null; "
            "fi; "
            "export LD_LIBRARY_PATH=\"$HOME/roms_build/install/lib:"
            "$HOME/intel/oneapi/compiler/2023.1.0/linux/compiler/lib/intel64_lin:${LD_LIBRARY_PATH:-}\"; "
            "\"$HOME/intel/oneapi/mpi/2021.9.0/bin/mpirun\" -np 4 "
            f"./romsM {trial_in} > {trial_log} 2>&1"
        )
        result = subprocess.run(["bash", "-lc", command], cwd=RUN_DIR, capture_output=True, text=True)
        log_text = trial_log.read_text() if trial_log.exists() else ""
        status = "success" if "ROMS: DONE" in log_text else "failed"
        return {
            "dt_seconds": dt_seconds,
            "status": status,
            "return_code": result.returncode,
            "log_path": str(trial_log),
            "roms_done": "ROMS: DONE" in log_text,
            "blowup": "BLOWUP" in log_text or "Blowing-up" in log_text,
            "max_speed_infinity": "MaxSpeed = Infinity" in log_text,
            "reason": "" if status == "success" else (result.stderr.strip() or "trial did not reach ROMS: DONE"),
        }


def write_markdown(report_path: Path, report: dict) -> None:
    hotspots = report["slope_hotspots"]
    dt_trials = report["dt_trials"]
    lines = [
        "# Bathymetry Stability Audit",
        "",
        f"- generated: {report['generated_at']}",
        f"- grid: `{report['grid_path']}`",
        f"- water_fraction: `{report['water_fraction']:.4f}`",
        f"- h_min_m: `{report['h_min_m']:.3f}`",
        f"- h_max_m: `{report['h_max_m']:.3f}`",
        f"- rx0: `{report['rx0']:.6f}`",
        f"- rx1: `{report['rx1']:.6f}`",
        f"- grid_acceptable_for_1day: `{report['grid_acceptable_for_1day']}`",
        f"- raw_grid_acceptable_for_1day: `{report['raw_grid_acceptable_for_1day']}`",
        "",
        "## Source",
        "",
        f"- configured lon/lat: `{report['source']['configured_lon']:.6f}`, `{report['source']['configured_lat']:.6f}`",
        f"- snapped xi/eta: `{report['source']['snapped_xi']}`, `{report['source']['snapped_eta']}`",
        f"- snapped lon/lat: `{report['source']['snapped_lon']:.6f}`, `{report['source']['snapped_lat']:.6f}`",
        f"- snapped depth m: `{report['source']['snapped_depth_m']:.3f}`",
        "",
        "## Steepest Local rx0 Hotspots",
        "",
    ]
    for row in hotspots:
        lines.append(
            f"- eta={row['eta']}, xi={row['xi']}, lon={row['lon']:.6f}, lat={row['lat']:.6f}, "
            f"h={row['depth_m']:.3f} m, local_rx0={row['local_rx0']:.6f}"
        )
    lines.extend(["", "## DT Trials", ""])
    for row in dt_trials:
        reason = row.get("reason", "")
        lines.append(f"- dt={row['dt_seconds']:.1f}s status={row['status']} reason={reason}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    grid_path = resolve_grid_path(args.grid, prefer_smoothed=True, prefer_maskclean=True)
    grid = load_grid(grid_path)
    vertical = load_vertical_config()
    placement = locate_source_on_grid(grid_path, load_project_params()["domain"]["source_lon"], load_project_params()["domain"]["source_lat"])
    wet = grid.mask_rho == 1
    rx0, rx1 = compute_rx0_rx1(grid.h, grid.mask_rho, vertical)
    local_factor = local_rx0(grid.h, grid.mask_rho)
    dt_trials = [] if args.skip_dt_trials else [run_dt_trial(grid_path, dt) for dt in parse_dt_list(args.dt_list)]
    successful_trials = [trial["dt_seconds"] for trial in dt_trials if trial["status"] == "success"]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "grid": str(grid_path),
        "grid_path": str(grid_path),
        "water_fraction": float(np.mean(wet)),
        "h_min_m": float(np.min(grid.h[wet])) if np.any(wet) else float(np.min(grid.h)),
        "h_max_m": float(np.max(grid.h[wet])) if np.any(wet) else float(np.max(grid.h)),
        "rx0": float(rx0),
        "rx1": float(rx1),
        "rx0_threshold": args.rx0_threshold,
        "rx1_threshold": args.rx1_threshold,
        "slope_hotspots": hotspot_rows(grid, local_factor),
        "source": {
            "configured_lon": placement.configured_lon,
            "configured_lat": placement.configured_lat,
            "snapped_xi": placement.snapped_xi,
            "snapped_eta": placement.snapped_eta,
            "snapped_lon": placement.snapped_lon,
            "snapped_lat": placement.snapped_lat,
            "snapped_depth_m": placement.snapped_depth_m,
            "snap_distance_m": placement.snapped_distance_m,
        },
        "dt_trials": dt_trials,
        "largest_successful_dt_seconds": max(successful_trials) if successful_trials else None,
        "grid_acceptable_for_1day": bool(rx0 <= args.rx0_threshold and rx1 <= args.rx1_threshold and successful_trials),
    }
    report["raw_grid_acceptable_for_1day"] = report["grid_acceptable_for_1day"]
    json_path = Path(args.report_json)
    md_path = Path(args.report_md)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    write_markdown(md_path, report)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"rx0={report['rx0']:.6f}")
    print(f"rx1={report['rx1']:.6f}")
    print(f"raw_grid_acceptable_for_1day={report['raw_grid_acceptable_for_1day']}")


if __name__ == "__main__":
    from roms_preprocessing_utils import load_project_params

    main()
