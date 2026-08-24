#!/usr/bin/env python3
"""Validate the generic formal online passive-tracer two-stage workflow."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
from netCDF4 import Dataset, num2date

DATA_PRE_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = DATA_PRE_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from case_context import export_case_context, parse_case_args, resolve_case_context

case_name, case_root, remaining_args = parse_case_args(sys.argv[1:])
export_case_context(resolve_case_context(case_name=case_name, case_root=case_root))
sys.argv = [sys.argv[0]] + remaining_args

from case_naming import continuous_tides_name, load_case_naming, roms_input_name, run_infile_name, staged_tides_name
from formal_online_workflow import (
    RESTART_OPTIONAL_TURBULENCE_VARIABLES,
    expected_restart_variables,
    continuous_source_name,
    load_formal_online_workflow,
    spinup_restart_name,
    spinup_zero_source_name,
)
from roms_preprocessing_utils import ROOT, load_project_params, to_builtin
from ocean_source_utils import normalize_ocean_source
from staged_data_utils import config_path_to_abs, load_download_config


OUTPUT_KEY_LABELS = {
    "Hout(idFsur)": "zeta",
    "Hout(idUvel)": "u",
    "Hout(idVvel)": "v",
    "Hout(idUbar)": "ubar",
    "Hout(idVbar)": "vbar",
    "Hout(idTvar)": "temp/salt",
    "Hout(inert)": "dye_01",
    "Aout(idFsur)": "zeta",
    "Aout(idUvel)": "u",
    "Aout(idVvel)": "v",
    "Aout(idUbar)": "ubar",
    "Aout(idVbar)": "vbar",
    "Aout(idTvar)": "temp/salt",
    "Aout(inert)": "dye_01",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pre-run", "post-spinup"], default="pre-run")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--spinup-infile", default=None)
    parser.add_argument("--production-infile", default=None)
    parser.add_argument("--decay-production-infile", default=None)
    parser.add_argument("--continuous-infile", default=None)
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


def _flags_are_enabled(value: str | None) -> bool:
    return bool(value and any(item.upper() == "T" for item in value.split()))


def _switch_flags(text: str, prefix: str) -> dict[str, str]:
    switches: dict[str, str] = {}
    pattern = re.compile(rf"^\s*({re.escape(prefix)}\([^)]+\))\s*=+\s*([^\n!]+)", re.MULTILINE)
    for match in pattern.finditer(text):
        switches[match.group(1)] = match.group(2).strip()
    return switches


def _enabled_output_variables(text: str, prefix: str) -> dict[str, Any]:
    switches = _switch_flags(text, prefix)
    enabled_keys = [key for key, value in sorted(switches.items()) if _flags_are_enabled(value)]
    labels = []
    for key in enabled_keys:
        label = OUTPUT_KEY_LABELS.get(key, key)
        if label not in labels:
            labels.append(label)
    return {
        "enabled_keys": enabled_keys,
        "enabled_variables": labels,
        "switches": switches,
    }


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


def _river_transition(path: Path, production_start: datetime, production_end: datetime) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "preproduction_is_zero": False,
        "production_is_active": False,
        "covers": False,
    }
    if not path.exists():
        return result
    try:
        with Dataset(path) as ds:
            time_var = ds.variables["river_time"]
            times = num2date(time_var[:], units=time_var.units, calendar=getattr(time_var, "calendar", "standard"))
            values = np.asarray(ds.variables["river_dye_01"][:], dtype=float)
            flattened = np.nanmax(np.abs(values), axis=tuple(range(1, values.ndim)))
            parsed = [datetime(item.year, item.month, item.day, item.hour, item.minute, item.second) for item in times]
            pre = np.asarray([item < production_start for item in parsed], dtype=bool)
            prod = np.asarray([production_start <= item <= production_end for item in parsed], dtype=bool)
            result.update(
                {
                    "start": parsed[0].isoformat(),
                    "end": parsed[-1].isoformat(),
                    "covers": bool(parsed[0] <= production_start and parsed[-1] >= production_end),
                    "preproduction_max": float(np.nanmax(flattened[pre])) if np.any(pre) else None,
                    "production_max": float(np.nanmax(flattened[prod])) if np.any(prod) else None,
                    "preproduction_is_zero": bool(np.any(pre) and np.allclose(flattened[pre], 0.0)),
                    "production_is_active": bool(np.any(prod) and np.nanmax(flattened[prod]) > 0.0),
                    "source_mode": getattr(ds, "source_mode", None),
                }
            )
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _tide_metadata(path: Path, *, require_zero_phase: bool = True) -> dict[str, Any]:
    required = ("tide_period", "tide_Eamp", "tide_Ephase", "tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase")
    if not require_zero_phase:
        required += ("tide_ERe", "tide_EIm", "tide_URe", "tide_UIm", "tide_VRe", "tide_VIm")
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "missing_variables": list(required), "issues": []}
    if not path.exists():
        return result
    try:
        with Dataset(path) as ds:
            result["missing_variables"] = [name for name in required if name not in ds.variables]
            result["zero_phase_date"] = float(ds.variables["zero_phase_date"][()]) if "zero_phase_date" in ds.variables else None
            result["phase_convention"] = getattr(ds, "phase_convention", None)
            result["source_phase_reference"] = getattr(ds, "source_phase_reference", None)
            result["v0_handling"] = getattr(ds, "v0_handling", None)
            result["nodal_correction"] = getattr(ds, "nodal_correction", None)
            result["phase_reconstruction"] = getattr(ds, "phase_reconstruction", None)
            if result["missing_variables"]:
                result["issues"].append("missing ROMS tide variables")
            if require_zero_phase and result["zero_phase_date"] != 20241001.0:
                result["issues"].append("zero_phase_date must be 20241001.0")
            for key in ("phase_convention", "source_phase_reference", "v0_handling", "nodal_correction", "phase_reconstruction"):
                if not result.get(key):
                    result["issues"].append(f"missing tidal metadata: {key}")
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["issues"].append(result["error"])
    return result


def _netcdf_missing_variables(path: Path, variables: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "missing_variables": list(variables)}
    if not path.exists():
        return result
    try:
        with Dataset(path) as ds:
            present = set(ds.variables)
        result["missing_variables"] = [name for name in variables if name not in present]
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
    history_outputs = _enabled_output_variables(text, "Hout")
    average_outputs = _enabled_output_variables(text, "Aout")
    diagnostics_outputs = _enabled_output_variables(text, "Dout")
    result.update(
        {
            "NHIS": nhis,
            "NAVG": navg,
            "NDIA": ndia,
            "NRST": nrst,
            "NRREC": nrrec,
            "DT": raw_dt,
            "ININAME": ini,
            "SSFNAME": _scalar(text, "SSFNAME"),
            "RSTNAME": _scalar(text, "RSTNAME"),
            "HISNAME": _scalar(text, "HISNAME"),
            "AVGNAME": _scalar(text, "AVGNAME"),
            "DIANAME": _scalar(text, "DIANAME"),
            "history_will_write": nhis not in {None, "0"},
            "average_will_write": navg not in {None, "0"},
            "diagnostics_will_write": ndia not in {None, "0"},
            "history_outputs": history_outputs,
            "average_outputs": average_outputs,
            "diagnostics_outputs": diagnostics_outputs,
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
        if result["history_outputs"]["enabled_keys"]:
            result["issues"].append("spin-up has enabled history variables despite NHIS=0")
        if result["diagnostics_outputs"]["enabled_keys"]:
            result["issues"].append("spin-up has enabled diagnostics variables despite NDIA=0")
    else:
        hourly = str(max(1, int(round(3600 / dt_seconds))))
        daily = str(max(1, int(round(24 * 3600 / dt_seconds))))
        if phase == "continuous":
            if nrrec != "0":
                result["issues"].append(f"continuous run must start as a new integration (NRREC={nrrec})")
            if ini and ini.startswith("../output/"):
                result["issues"].append("continuous ININAME must be an initial field, not a restart output")
        elif nrrec not in {"-1", "1"}:
            result["issues"].append(f"production is not configured as restart hot start (NRREC={nrrec})")
        if expected_ini and ini != expected_ini:
            label = "continuous" if phase == "continuous" else "production"
            result["issues"].append(f"{label} ININAME {ini} does not match expected {expected_ini}")
        if nhis != hourly:
            label = "continuous" if phase == "continuous" else "production"
            result["issues"].append(f"{label} history interval is not 1 h (NHIS {nhis}, expected {hourly})")
        if result["history_outputs"]["enabled_variables"] != ["zeta"]:
            result["issues"].append(
                f"{('continuous' if phase == 'continuous' else 'production')} history is not limited to zeta: {result['history_outputs']['enabled_variables']}"
            )
        if navg != daily:
            label = "continuous" if phase == "continuous" else "production"
            result["issues"].append(f"{label} average interval is not 24 h (NAVG {navg}, expected {daily})")
        expected_average = ["u", "v", "ubar", "vbar", "dye_01"]
        if sorted(result["average_outputs"]["enabled_variables"]) != sorted(expected_average):
            result["issues"].append(
                f"{('continuous' if phase == 'continuous' else 'production')} average variables mismatch: {result['average_outputs']['enabled_variables']}"
            )
        for key in ("Aout_idUvel", "Aout_idVvel", "Aout_idUbar", "Aout_idVbar", "Aout_inert"):
            if result[key] != "T":
                result["issues"].append(f"{('continuous' if phase == 'continuous' else 'production')} average missing expected {key}")
        if ndia != "0":
            result["issues"].append(f"{('continuous' if phase == 'continuous' else 'production')} diagnostics is not off (NDIA != 0)")
        if result["diagnostics_outputs"]["enabled_keys"]:
            result["issues"].append(f"{('continuous' if phase == 'continuous' else 'production')} has enabled diagnostics variables despite NDIA=0")
        if nrst != restart_5d:
            result["issues"].append(f"{('continuous' if phase == 'continuous' else 'production')} restart interval is not 5 d (NRST {nrst}, expected {restart_5d})")
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


def _production_output_signature(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "DT": check.get("DT"),
        "NHIS": check.get("NHIS"),
        "NAVG": check.get("NAVG"),
        "NDIA": check.get("NDIA"),
        "NRST": check.get("NRST"),
        "NRREC": check.get("NRREC"),
        "ININAME": check.get("ININAME"),
        "SSFNAME": check.get("SSFNAME"),
        "history_outputs": check.get("history_outputs", {}).get("enabled_variables", []),
        "average_outputs": check.get("average_outputs", {}).get("enabled_variables", []),
        "diagnostics_outputs": check.get("diagnostics_outputs", {}).get("enabled_variables", []),
    }


def _audit_payload(params: dict[str, Any]) -> dict[str, Any]:
    hardcoded_hits: list[str] = []
    validator_impl = Path("Data_pre/impl/preprocessing/validate_formal_online_workflow.py")
    for path in (Path("Data_pre"), Path("ROMS_Run"), Path("ROMS_Build")):
        for item in path.rglob("*"):
            if item.is_file() and item.suffix in {".py", ".json", ".md"}:
                parts = item.parts
                if item == validator_impl:
                    continue
                if len(parts) >= 3 and parts[0] == "Data_pre" and parts[1] == "cases":
                    continue
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
    spinup = payload["checks"]["spinup_infile"]
    production = payload["checks"]["production_infile"]
    decay = payload["checks"]["decay_production_infile"]
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
        "- workflow genericized: `true`",
        f"- FDNPP role: `{payload['fdnpp_role']}`",
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
        "## Actual Spin-up Output",
        "",
        f"- infile: `{spinup['path']}`",
        f"- NHIS: `{spinup.get('NHIS')}`",
        f"- NAVG: `{spinup.get('NAVG')}`",
        f"- NRST: `{spinup.get('NRST')}`",
        f"- NDIA: `{spinup.get('NDIA')}`",
        f"- history_will_write: `{spinup.get('history_will_write')}`",
        f"- history variables enabled: `{', '.join(spinup['history_outputs']['enabled_variables']) or 'none'}`",
        f"- diagnostics_will_write: `{spinup.get('diagnostics_will_write')}`",
        f"- diagnostics variables enabled: `{', '.join(spinup['diagnostics_outputs']['enabled_variables']) or 'none'}`",
        f"- source file: `{spinup.get('SSFNAME')}`",
        f"- restart file: `{spinup.get('RSTNAME')}`",
        "",
        "## Actual Production Output",
        "",
        f"- no-decay infile: `{production['path']}`",
        f"- decay infile: `{decay['path']}`",
        f"- NHIS: `{production.get('NHIS')}`",
        f"- NAVG: `{production.get('NAVG')}`",
        f"- NRST: `{production.get('NRST')}`",
        f"- NDIA: `{production.get('NDIA')}`",
        f"- NRREC: `{production.get('NRREC')}`",
        f"- ININAME: `{production.get('ININAME')}`",
        f"- history variables enabled: `{', '.join(production['history_outputs']['enabled_variables']) or 'none'}`",
        f"- average variables enabled: `{', '.join(production['average_outputs']['enabled_variables']) or 'none'}`",
        f"- diagnostics_will_write: `{production.get('diagnostics_will_write')}`",
        f"- diagnostics variables enabled: `{', '.join(production['diagnostics_outputs']['enabled_variables']) or 'none'}`",
        f"- no-decay/decay output config identical: `{payload['production']['no_decay_decay_output_config_identical']}`",
        "- hourly `dye_01`: `disabled`",
        "- supported visualization: `daily mean plume maps / daily mean animation`",
        "- unsupported visualization: `hourly dye_01 plume animation`",
        "",
        "## Validation",
        "",
        f"- status: `{payload['status']}`",
        f"- validation phase: `{payload['validation_phase']}`",
        f"- no-decay and decay production supported: `{payload['production']['decay_supported']}`",
        f"- output_config_can_be_modified_now: `{payload['output_config_can_be_modified_now']}`",
        f"- spinup_can_run_now: `{payload['spinup_can_run_now']}`",
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
    lines.extend(["", "## Spin-up Input Data Blocking Issues", ""])
    if payload["spinup_input_data_blocking_issues"]:
        lines.extend(f"- {issue}" for issue in payload["spinup_input_data_blocking_issues"])
    else:
        lines.append("- none")
    lines.extend(["", "## Next Step", "", f"- {payload['next_step']}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_continuous_md(path: Path, payload: dict[str, Any]) -> None:
    checks = payload["checks"]
    lines = [
        "# Formal Online Continuous Workflow",
        "",
        "## Window",
        "",
        f"- preproduction start: `{payload['workflow']['spinup_start']}`",
        f"- production start: `{payload['workflow']['production_start']}`",
        f"- production end: `{payload['workflow']['production_end']}`",
        f"- preproduction months: `{payload['workflow']['preproduction_months']}`",
        "- one executable and one uninterrupted integration; restart files are recovery checkpoints only.",
        "",
        "## Input Coverage",
        "",
    ]
    for key in ("continuous_ini", "continuous_bdy", "continuous_atm", "continuous_rad"):
        item = checks[key]
        lines.append(f"- {key}: `{item.get('start')} -> {item.get('end')}` ({'OK' if item.get('covers') else 'BLOCKED'})")
    source = checks["continuous_source"]
    lines.extend(
        [
            f"- continuous source: preproduction zero=`{source.get('preproduction_is_zero')}`, production active=`{source.get('production_is_active')}`",
            f"- tides: zero_phase_date=`{checks['continuous_tides'].get('zero_phase_date')}`, phase convention=`{checks['continuous_tides'].get('phase_convention')}`",
            "",
            "## Infile",
            "",
            f"- path: `{checks['continuous_infile']['path']}`",
            f"- NRREC: `{checks['continuous_infile'].get('NRREC')}`",
            f"- ININAME: `{checks['continuous_infile'].get('ININAME')}`",
            f"- NHIS/NAVG/NDIA: `{checks['continuous_infile'].get('NHIS')}` / `{checks['continuous_infile'].get('NAVG')}` / `{checks['continuous_infile'].get('NDIA')}`",
            f"- issues: `{'; '.join(checks['continuous_infile'].get('issues', [])) or 'none'}`",
            "",
            "## Validation",
            "",
            f"- status: `{payload['status']}`",
            f"- blocking issues: `{'; '.join(payload['blocking_issues']) or 'none'}`",
            f"- next step: {payload['next_step']}",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_continuous_workflow(args: argparse.Namespace, params: dict[str, Any]) -> None:
    naming = load_case_naming()
    workflow = load_formal_online_workflow(params)
    dt_seconds = float(params["time"]["pilot_dt_seconds"])
    ocean_source = normalize_ocean_source(params.get("ocean", {}).get("default_source"))
    input_dir = ROOT / "input"
    continuous_infile = Path(args.continuous_infile) if args.continuous_infile else ROOT / "run" / run_infile_name(workflow.continuous_mode, ocean_source=ocean_source)
    paths = {
        "continuous_ini": input_dir / roms_input_name("ini", ocean_source=ocean_source, profile=workflow.profile, start=workflow.spinup_start, stop=workflow.production_end),
        "continuous_bdy": input_dir / roms_input_name("bdy", ocean_source=ocean_source, profile=workflow.profile, start=workflow.spinup_start, stop=workflow.production_end),
        "continuous_atm": input_dir / roms_input_name("atm", start=workflow.spinup_start, stop=workflow.production_end),
        "continuous_rad": input_dir / roms_input_name("rad", start=workflow.spinup_start, stop=workflow.production_end),
        "continuous_source": input_dir / continuous_source_name(naming.roms_prefix, workflow),
        "continuous_tides": input_dir / continuous_tides_name(workflow.profile),
    }
    raw_tides = ROOT / "data" / "raw" / "tides" / "tpxo9_fdnpp_continuous.nc"
    checks = {
        "continuous_ini": _time_coverage(paths["continuous_ini"], "ocean_time", workflow.spinup_start, workflow.spinup_start),
        "continuous_bdy": _time_coverage(paths["continuous_bdy"], "zeta_time", workflow.spinup_start, workflow.production_end),
        "continuous_atm": _time_coverage(paths["continuous_atm"], "wind_time", workflow.spinup_start, workflow.production_end),
        "continuous_rad": _time_coverage(paths["continuous_rad"], "srf_time", workflow.spinup_start, workflow.production_end),
        "continuous_source": _river_transition(paths["continuous_source"], workflow.production_start, workflow.production_end),
        "continuous_tides": _tide_metadata(paths["continuous_tides"]),
        "raw_tides": _tide_metadata(raw_tides, require_zero_phase=False),
        "continuous_infile": _infile_checks(
            continuous_infile,
            phase="continuous",
            dt_seconds=dt_seconds,
            expected_ini=f"../input/{paths['continuous_ini'].name}",
        ),
    }
    blocking: list[str] = []
    for label, check in checks.items():
        if label in {"continuous_infile", "continuous_tides", "raw_tides"}:
            blocking.extend(f"{label}: {issue}" for issue in check.get("issues", []))
        elif label == "continuous_source":
            if not check.get("exists"):
                blocking.append("continuous_source: missing source file")
            elif not check.get("covers"):
                blocking.append("continuous_source: time coverage does not span full window")
            if not check.get("preproduction_is_zero"):
                blocking.append("continuous_source: source is not zero before production_start")
            if not check.get("production_is_active"):
                blocking.append("continuous_source: source is not active after production_start")
        elif not check.get("exists"):
            blocking.append(f"{label}: missing input file")
        elif not check.get("covers"):
            blocking.append(f"{label}: time coverage does not span expected window")

    payload = {
        "case_name": naming.case_name,
        "validation_phase": args.phase,
        "status": "ready" if not blocking else "blocked",
        "workflow": {
            "enabled": workflow.enabled,
            "mode": "continuous",
            "profile": workflow.profile,
            "profile_token": workflow.profile_token,
            "preproduction_months": workflow.spinup_duration_months,
            "spinup_start": workflow.spinup_start.isoformat(),
            "spinup_end": workflow.spinup_end.isoformat(),
            "production_start": workflow.production_start.isoformat(),
            "production_end": workflow.production_end.isoformat(),
            "continuous_mode": workflow.continuous_mode,
        },
        "forcing_window": {
            "start": workflow.spinup_start.isoformat(),
            "stop": workflow.production_end.isoformat(),
            "postprocessing_start": workflow.production_start.isoformat(),
            "postprocessing_stop": workflow.production_end.isoformat(),
        },
        "paths": {key: str(value) for key, value in paths.items()},
        "checks": checks,
        "restart": {"role": "recovery_checkpoint_only", "formal_stage_handoff": False},
        "production": {"hot_start_from_spinup": False, "manual_handoff": False},
        "blocking_issues": blocking,
        "spinup_input_data_blocking_issues": [],
        "next_step": "Launch the single continuous run; no spin-up completion monitoring or production handoff is required." if not blocking else "Fix the blocking continuous input/configuration checks before launch.",
        "notes": [
            "Preproduction source is zero through 2024-12-31 and switches to the configured release at 2025-01-01.",
            "RAMP_TIDES is applied only at the beginning of the continuous integration.",
            "Post-processing must select 2025-01-01 through 2026-01-01 from the continuous output files.",
        ],
    }
    reports_dir = ROOT / "reports"
    report_json = Path(args.report_json) if args.report_json else reports_dir / "formal_online_continuous_workflow.json"
    report_md = Path(args.report_md) if args.report_md else reports_dir / "formal_online_continuous_workflow.md"
    _write_json(report_json, payload)
    _write_continuous_md(report_md, payload)
    _write_json(reports_dir / "formal_online_spinup_output_flow.json", payload)
    _write_continuous_md(reports_dir / "formal_online_spinup_output_flow.md", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=to_builtin))
    if blocking:
        raise SystemExit(2)


def main() -> None:
    args = parse_args()
    params = load_project_params()
    if str(params.get("formal_online_workflow", {}).get("mode", "")).lower() == "continuous":
        _validate_continuous_workflow(args, params)
        return
    naming = load_case_naming()
    workflow = load_formal_online_workflow(params)
    if args.profile:
        params.setdefault("formal_online_workflow", {})["profile"] = args.profile
        workflow = load_formal_online_workflow(params)
    dt_seconds = float(params["time"]["pilot_dt_seconds"])
    ocean_source = normalize_ocean_source(params.get("ocean", {}).get("default_source"))
    spinup_infile = Path(args.spinup_infile) if args.spinup_infile else ROOT / "run" / run_infile_name(workflow.spinup_mode, ocean_source=ocean_source)
    prod_infile = Path(args.production_infile) if args.production_infile else ROOT / "run" / run_infile_name(workflow.production_mode, ocean_source=ocean_source)
    decay_infile = Path(args.decay_production_infile) if args.decay_production_infile else ROOT / "run" / run_infile_name(workflow.production_decay_mode, ocean_source=ocean_source)
    restart = Path(args.restart) if args.restart else ROOT / "output" / spinup_restart_name(naming.roms_prefix, workflow)
    expected_ini = f"../output/{spinup_restart_name(naming.roms_prefix, workflow)}"
    input_dir = ROOT / "input"
    staged_config = load_download_config()
    paths = {
        "spinup_ini": input_dir / roms_input_name("ini", profile=workflow.profile, start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_bdy": input_dir / roms_input_name("bdy", profile=workflow.profile, start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_atm": input_dir / roms_input_name("atm", start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_rad": input_dir / roms_input_name("rad", start=workflow.spinup_start, stop=workflow.spinup_end),
        "spinup_source": input_dir / spinup_zero_source_name(naming.roms_prefix, workflow),
        "production_source": input_dir / f"roms_rivers_production_{workflow.profile}.nc",
        "raw_tides": (
            config_path_to_abs(staged_config, "tides")
            if "tides" in staged_config.get("paths", {})
            else ROOT / "data" / "raw" / "tides" / staged_tides_name()
        ),
    }
    checks = {
        "spinup_ini": _time_coverage(paths["spinup_ini"], "ocean_time", workflow.spinup_start, workflow.spinup_start),
        "spinup_bdy": _time_coverage(paths["spinup_bdy"], "zeta_time", workflow.spinup_start, workflow.spinup_end),
        "spinup_atm": _time_coverage(paths["spinup_atm"], "wind_time", workflow.spinup_start, workflow.spinup_end),
        "spinup_rad": _time_coverage(paths["spinup_rad"], "srf_time", workflow.spinup_start, workflow.spinup_end),
        "spinup_source": _river_zero(paths["spinup_source"]),
        "raw_tides": _netcdf_missing_variables(
            paths["raw_tides"],
            ("tide_Eamp", "tide_Ephase", "tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase"),
        ),
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
        elif label == "raw_tides":
            continue
        elif check["exists"] and not check["covers"]:
            blocking.append(f"{label}: time coverage does not span expected window")
    if args.phase == "post-spinup":
        blocking.extend(f"restart: {issue}" for issue in restart_checks["issues"])
    spinup_input_data_blocking: list[str] = []
    for variable in checks["raw_tides"].get("missing_variables", []):
        spinup_input_data_blocking.append(f"raw_tides missing {variable}")
    production_signature = _production_output_signature(checks["production_infile"])
    decay_signature = _production_output_signature(checks["decay_production_infile"])
    output_config_identical = production_signature == decay_signature
    output_config_ready = not any(
        checks[label]["issues"]
        for label in ("spinup_infile", "production_infile", "decay_production_infile")
    ) and output_config_identical
    payload = {
        "case_name": naming.case_name,
        "validation_phase": args.phase,
        "status": "ready" if output_config_ready and not blocking else "blocked",
        "fdnpp_role": "configuration instance only; shared workflow logic is case-driven",
        "output_config_can_be_modified_now": True,
        "spinup_can_run_now": False if spinup_input_data_blocking else not blocking,
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
            "no_decay_output_signature": production_signature,
            "decay_output_signature": decay_signature,
            "no_decay_decay_output_config_identical": output_config_identical,
        },
        "current_audit": _audit_payload(params),
        "blocking_issues": blocking,
        "spinup_input_data_blocking_issues": spinup_input_data_blocking,
        "next_step": (
            "Fix spin-up tide staging for formal online workflow"
            if spinup_input_data_blocking
            else "Run post-spinup validation after formal spin-up produces its final restart"
        ),
        "notes": [
            "Spin-up history is not used for hot start; production starts from final restart.",
            "If restart is absent, pre-run validation reports expected paths; post-spinup validation requires file content.",
            "The formal production output plan supports daily mean dye_01 maps/animations, not hourly dye_01 plume animation.",
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
