#!/usr/bin/env python3
"""Validate the generic formal online passive-tracer two-stage workflow."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
from netCDF4 import Dataset, num2date

from case_naming import load_case_naming, output_product_name, roms_input_name, run_infile_name
from formal_online_workflow import (
    RESTART_OPTIONAL_TURBULENCE_VARIABLES,
    expected_restart_variables,
    load_formal_online_workflow,
    spinup_restart_name,
    spinup_zero_source_name,
)
from roms_preprocessing_utils import ROOT, load_project_params, to_builtin, to_mjd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pre-run", "post-spinup"], default="pre-run")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--spinup-infile", default=None)
    parser.add_argument("--production-infile", default=None)
    parser.add_argument("--decay-production-infile", default=None)
    parser.add_argument("--restart", default=None)
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--report-md", default=None)
    return parser.parse_args()


def _scalar(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}\s*=+\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).split("!", 1)[0].strip().split()[0]


def _flag(text: str, key: str) -> str | None:
    value = _scalar(text, key)
    return value.upper() if value else None


def _decode_first_last(ds: Dataset, name: str) -> tuple[datetime | None, datetime | None]:
    if name not in ds.variables:
        return None, None
    var = ds.variables[name]
    values = np.asarray(var[:])
    if values.size == 0:
        return None, None
    units = getattr(var, "units", None)
    if not units:
        return None, None
    calendar = getattr(var, "calendar", "standard")
    decoded = num2date([values.flat[0], values.flat[-1]], units=units, calendar=calendar)
    out = []
    for item in decoded:
        out.append(datetime(item.year, item.month, item.day, item.hour, item.minute, item.second))
    return out[0], out[1]


def _time_coverage(path: Path, time_name: str, start: datetime, end: datetime) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "time_name": time_name, "covers": False}
    if not path.exists():
        return result
    try:
        with Dataset(path) as ds:
            first, last = _decode_first_last(ds, time_name)
        result.update({"start": first.isoformat() if first else None, "end": last.isoformat() if last else None})
        result["covers"] = bool(first and last and first <= start and last >= end)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _river_zero(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "source_is_zero": False}
    if not path.exists():
        return result
    try:
        with Dataset(path) as ds:
            dye = np.asarray(ds.variables["river_dye_01"][:], dtype=float)
            result["release_Bq_s"] = float(getattr(ds, "release_Bq_s", np.nan))
            result["source_mode"] = getattr(ds, "source_mode", None)
            result["dye_min"] = float(np.nanmin(dye))
            result["dye_max"] = float(np.nanmax(dye))
            result["source_is_zero"] = bool(np.allclose(np.nan_to_num(dye), 0.0) and result["release_Bq_s"] == 0.0)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _infile_checks(path: Path, *, phase: str, dt_seconds: float, expected_ini: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "issues": []}
    if not path.exists():
        result["issues"].append(f"missing infile: {path}")
        return result
    text = path.read_text(errors="ignore")
    raw_dt = _scalar(text, "DT")
    if raw_dt:
        try:
            dt_seconds = float(raw_dt.replace("d0", "").replace("D0", ""))
        except ValueError:
            result["issues"].append(f"cannot parse DT value {raw_dt}")
    nhis = _scalar(text, "NHIS")
    navg = _scalar(text, "NAVG")
    ndia = _scalar(text, "NDIA")
    nrst = _scalar(text, "NRST")
    nrrec = _scalar(text, "NRREC")
    ini = _scalar(text, "ININAME")
    result.update(
        {
            "NHIS": nhis,
            "NAVG": navg,
            "NDIA": ndia,
            "NRST": nrst,
            "NRREC": nrrec,
            "DT": raw_dt,
            "ININAME": ini,
            "Hout_idFsur": _flag(text, "Hout(idFsur)"),
            "Hout_inert": _flag(text, "Hout(inert)"),
            "Aout_idUvel": _flag(text, "Aout(idUvel)"),
            "Aout_idVvel": _flag(text, "Aout(idVvel)"),
            "Aout_idUbar": _flag(text, "Aout(idUbar)"),
            "Aout_idVbar": _flag(text, "Aout(idVbar)"),
            "Aout_inert": _flag(text, "Aout(inert)"),
        }
    )
    restart_5d = str(max(1, int(round(5 * 24 * 3600 / dt_seconds))))
    if phase == "spinup":
        if nhis != "0":
            result["issues"].append("spin-up history is not off (NHIS != 0)")
        if navg != "0":
            result["issues"].append("spin-up average is not off (NAVG != 0)")
        if ndia != "0":
            result["issues"].append("spin-up diagnostics is not off (NDIA != 0)")
        if nrst != restart_5d:
            result["issues"].append(f"spin-up restart interval is not 5 d (NRST {nrst}, expected {restart_5d})")
    else:
        hourly = str(max(1, int(round(3600 / dt_seconds))))
        daily = str(max(1, int(round(24 * 3600 / dt_seconds))))
        if nrrec not in {"-1", "1"}:
            result["issues"].append(f"production is not configured as restart hot start (NRREC={nrrec})")
        if expected_ini and ini != expected_ini:
            result["issues"].append(f"production ININAME {ini} does not match expected {expected_ini}")
        if nhis != hourly:
            result["issues"].append(f"production history interval is not 1 h (NHIS {nhis}, expected {hourly})")
        if result["Hout_idFsur"] != "T" or result["Hout_inert"] != "F":
            result["issues"].append("production history is not limited to zeta")
        if navg != daily:
            result["issues"].append(f"production average interval is not 24 h (NAVG {navg}, expected {daily})")
        for key in ("Aout_idUvel", "Aout_idVvel", "Aout_idUbar", "Aout_idVbar", "Aout_inert"):
            if result[key] != "T":
                result["issues"].append(f"production average missing expected {key}")
        if ndia != "0":
            result["issues"].append("production diagnostics is not off (NDIA != 0)")
        if nrst != restart_5d:
            result["issues"].append(f"production restart interval is not 5 d (NRST {nrst}, expected {restart_5d})")
    return result


def _restart_checks(path: Path, production_start: datetime) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "issues": [], "required_variables": list(expected_restart_variables(True))}
    if not path.exists():
        result["issues"].append("spin-up final restart does not exist yet")
        return result
    try:
        with Dataset(path) as ds:
            variables = set(ds.variables)
            missing = [name for name in expected_restart_variables(True) if name not in variables]
            result["missing_variables"] = missing
            result["turbulence_variables_present"] = [name for name in RESTART_OPTIONAL_TURBULENCE_VARIABLES if name in variables]
            first, last = _decode_first_last(ds, "ocean_time")
            result["ocean_time_start"] = first.isoformat() if first else None
            result["ocean_time_end"] = last.isoformat() if last else None
            if missing:
                result["issues"].append(f"restart missing variables: {', '.join(missing)}")
            if last != production_start:
                result["issues"].append(
                    f"restart ocean_time end {last.isoformat() if last else 'missing'} != production_start {production_start.isoformat()}"
                )
    except Exception as exc:  # noqa: BLE001
        result["issues"].append(f"cannot inspect restart: {type(exc).__name__}: {exc}")
    return result


def _audit_payload(params: dict[str, Any]) -> dict[str, Any]:
    hardcoded_hits: list[str] = []
    for path in (Path("Data_pre"), Path("ROMS_Run"), Path("ROMS_Build")):
        for item in path.rglob("*"):
            if item.is_file() and item.suffix in {".py", ".json", ".md"}:
                text = item.read_text(errors="ignore")
                if "online_spinup_3mo_my25_uvtide" in text or "FDNPP Spin-up" in text:
                    hardcoded_hits.append(str(item))
    return {
        "spinup_flow_supported": "partial",
        "data_window_rule_supported": "true",
        "zero_source_spinup_supported": "true",
        "restart_hotstart_supported": "true",
        "formal_minimal_output_supported": "true",
        "case_specific_hardcoding_found": bool(hardcoded_hits),
        "case_specific_hardcoding_remaining": sorted(hardcoded_hits),
        "note": "FDNPP may appear in case config/docs; shared workflow logic is case-driven.",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=to_builtin) + "\n", encoding="utf-8")


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    wf = payload["workflow"]
    lines = [
        "# Formal Online Passive Tracer Workflow",
        "",
        "## Generic Definition",
        "",
        f"- spin-up duration: `{wf['spinup_duration_months']} months`",
        f"- spinup_start: `{wf['spinup_start']}`",
        f"- spinup_end / production_start: `{wf['production_start']}`",
        f"- production_end: `{wf['production_end']}`",
        "- spin-up is hydrodynamic adjustment before formal online tracer production.",
        "- formal production source and optional radioactive decay are enabled only in production.",
        "",
        "## History And Restart",
        "",
        "- spin-up hot-start state comes from restart, not history.",
        "- formal spin-up can use `history off + restart 5 d + diagnostics off` because restart is the complete model state used by production.",
        "- required restart variables: `zeta`, `ubar`, `vbar`, `u`, `v`, `temp`, `salt`, `dye_01`, `ocean_time`, plus turbulence variables when required by the compiled physics.",
        "",
        "## Run Modes",
        "",
        f"- spin-up: `{wf['spinup_mode']}`",
        f"- production no-decay: `{wf['production_mode']}`",
        f"- production decay: `{wf['production_decay_mode']}`",
        "",
        "## Validation",
        "",
        f"- status: `{payload['status']}`",
        f"- validation phase: `{payload['validation_phase']}`",
        f"- no-decay and decay production supported: `{payload['production']['decay_supported']}`",
        "",
        "## Current Flow Audit",
        "",
    ]
    for key, value in payload["current_audit"].items():
        if key != "case_specific_hardcoding_remaining":
            lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Blocking Issues", ""])
    if payload["blocking_issues"]:
        lines.extend(f"- {issue}" for issue in payload["blocking_issues"])
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    params = load_project_params()
    naming = load_case_naming()
    workflow = load_formal_online_workflow(params)
    if args.profile:
        params.setdefault("formal_online_workflow", {})["profile"] = args.profile
        workflow = load_formal_online_workflow(params)
    dt_seconds = float(params["time"]["pilot_dt_seconds"])
    spinup_infile = Path(args.spinup_infile) if args.spinup_infile else ROOT / "run" / run_infile_name(workflow.spinup_mode)
    prod_infile = Path(args.production_infile) if args.production_infile else ROOT / "run" / run_infile_name(workflow.production_mode)
    decay_infile = Path(args.decay_production_infile) if args.decay_production_infile else ROOT / "run" / run_infile_name(workflow.production_decay_mode)
    restart = Path(args.restart) if args.restart else ROOT / "output" / spinup_restart_name(naming.roms_prefix, workflow)
    expected_ini = f"../output/{spinup_restart_name(naming.roms_prefix, workflow)}"
    input_dir = ROOT / "input"
    paths = {
        "spinup_ini": input_dir / roms_input_name("ini", profile=workflow.profile, start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_bdy": input_dir / roms_input_name("bdy", profile=workflow.profile, start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_atm": input_dir / roms_input_name("atm", start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_rad": input_dir / roms_input_name("rad", start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_source": input_dir / spinup_zero_source_name(naming.roms_prefix, workflow),
        "production_source": input_dir / f"roms_rivers_production_{workflow.profile}.nc",
    }
    checks = {
        "spinup_ini": _time_coverage(paths["spinup_ini"], "ocean_time", workflow.spinup_start, workflow.spinup_start),
        "spinup_bdy": _time_coverage(paths["spinup_bdy"], "zeta_time", workflow.spinup_start, workflow.spinup_end),
        "spinup_atm": _time_coverage(paths["spinup_atm"], "wind_time", workflow.spinup_start, workflow.spinup_end),
        "spinup_rad": _time_coverage(paths["spinup_rad"], "srf_time", workflow.spinup_start, workflow.spinup_end),
        "spinup_source": _river_zero(paths["spinup_source"]),
        "spinup_infile": _infile_checks(spinup_infile, phase="spinup", dt_seconds=dt_seconds),
        "production_infile": _infile_checks(prod_infile, phase="production", dt_seconds=dt_seconds, expected_ini=expected_ini),
        "decay_production_infile": _infile_checks(decay_infile, phase="production", dt_seconds=dt_seconds, expected_ini=expected_ini),
    }
    restart_checks = _restart_checks(restart, workflow.production_start)
    blocking: list[str] = []
    for label, check in checks.items():
        if label in {"spinup_infile", "production_infile", "decay_production_infile"}:
            blocking.extend(f"{label}: {issue}" for issue in check["issues"])
        elif label == "spinup_source":
            if check["exists"] and not check["source_is_zero"]:
                blocking.append("spinup_source: source is not zero")
        elif check["exists"] and not check["covers"]:
            blocking.append(f"{label}: time coverage does not span expected window")
    if args.phase == "post-spinup":
        blocking.extend(f"restart: {issue}" for issue in restart_checks["issues"])
    payload = {
        "case_name": naming.case_name,
        "validation_phase": args.phase,
        "status": "ready" if not blocking else "blocked",
        "workflow": {
            "enabled": workflow.enabled,
            "profile": workflow.profile,
            "profile_token": workflow.profile_token,
            "spinup_duration_months": workflow.spinup_duration_months,
            "spinup_start": workflow.spinup_start.isoformat(),
            "spinup_end": workflow.spinup_end.isoformat(),
            "production_start": workflow.production_start.isoformat(),
            "production_end": workflow.production_end.isoformat(),
            "production_duration_label": workflow.production_duration_label,
            "spinup_mode": workflow.spinup_mode,
            "production_mode": workflow.production_mode,
            "production_decay_mode": workflow.production_decay_mode,
        },
        "paths": {key: str(value) for key, value in paths.items()},
        "checks": checks,
        "restart": restart_checks,
        "production": {
            "hot_start_from_spinup": True,
            "expected_ININAME": expected_ini,
            "source_expected": str(paths["production_source"]),
            "decay_supported": decay_infile.exists() or workflow.production_decay_mode,
            "no_decay_decay_difference": "build/profile decay switch only; input/output policy and spin-up restart path are shared",
        },
        "current_audit": _audit_payload(params),
        "blocking_issues": blocking,
        "notes": [
            "Spin-up history is not used for hot start; production starts from final restart.",
            "If restart is absent, pre-run validation reports expected paths; post-spinup validation requires file content.",
        ],
    }
    reports_dir = ROOT / "reports"
    report_json = Path(args.report_json) if args.report_json else reports_dir / "formal_online_spinup_output_flow.json"
    report_md = Path(args.report_md) if args.report_md else reports_dir / "formal_online_spinup_output_flow.md"
    audit_json = reports_dir / "formal_online_spinup_flow_current_audit.json"
    audit_md = reports_dir / "formal_online_spinup_flow_current_audit.md"
    _write_json(report_json, payload)
    _write_md(report_md, payload)
    _write_json(audit_json, payload["current_audit"])
    audit_lines = ["# Formal Online Spin-up Flow Current Audit", ""]
    for key, value in payload["current_audit"].items():
        if key == "case_specific_hardcoding_remaining":
            continue
        audit_lines.append(f"- {key}: `{value}`")
    audit_md.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    print(f"report_md={report_md}")
    print(f"report_json={report_json}")
    print(f"audit_md={audit_md}")
    print(f"audit_json={audit_json}")
    if blocking:
        for issue in blocking:
            print(issue)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
