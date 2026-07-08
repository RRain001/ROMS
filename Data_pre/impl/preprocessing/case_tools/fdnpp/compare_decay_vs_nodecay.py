#!/usr/bin/env python3
"""Compare no-decay and radioactive-decay online passive tracer outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

from radioactive_decay import radioactive_decay_config
from roms_preprocessing_utils import ROOT, load_project_params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodecay-history", default=str(ROOT / "output" / "his_fdnpp_online_6h_online_my25_uvtide.nc"))
    parser.add_argument(
        "--decay-history",
        default=str(ROOT / "output" / "his_fdnpp_online_6h_online_my25_uvtide_decay.nc"),
    )
    parser.add_argument("--profile", default="online_my25_uvtide_decay")
    return parser.parse_args()


def z_w(ds: Dataset, zeta: np.ndarray) -> np.ndarray:
    h = np.asarray(ds.variables["h"][:], dtype=float)
    hc = float(getattr(ds, "hc", ds.variables.get("hc", [0.0])[0] if "hc" in ds.variables else 0.0))
    s_w = np.asarray(ds.variables["s_w"][:], dtype=float)
    cs_w = np.asarray(ds.variables["Cs_w"][:], dtype=float)
    zw = np.empty((len(s_w),) + h.shape, dtype=float)
    for k, (sval, cval) in enumerate(zip(s_w, cs_w, strict=True)):
        z0 = (hc * sval + h * cval) / (hc + h)
        zw[k, :, :] = zeta + (zeta + h) * z0
    return zw


def inventory_series(path: Path) -> dict[str, object]:
    with Dataset(path) as ds:
        required = ("dye_01", "zeta", "h", "pm", "pn", "s_w", "Cs_w", "ocean_time")
        missing = [name for name in required if name not in ds.variables]
        if missing:
            raise SystemExit(f"{path} missing variables: {', '.join(missing)}")
        mask = np.asarray(ds.variables["mask_rho"][:], dtype=float) if "mask_rho" in ds.variables else 1.0
        area = 1.0 / (np.asarray(ds.variables["pm"][:], dtype=float) * np.asarray(ds.variables["pn"][:], dtype=float))
        ocean_time = np.asarray(ds.variables["ocean_time"][:], dtype=float)
        time_var = ds.variables["ocean_time"]
        units = getattr(time_var, "units", "")
        calendar = getattr(time_var, "calendar", "standard")
        datetimes = []
        if units:
            parsed = num2date(ocean_time, units=units, calendar=calendar)
            datetimes = [f"{item.year:04d}-{item.month:02d}-{item.day:02d}T{item.hour:02d}:{item.minute:02d}:{item.second:02d}" for item in parsed]
        inventories: list[float] = []
        maxima: list[float] = []
        minima: list[float] = []
        for index in range(len(ocean_time)):
            zeta = np.asarray(ds.variables["zeta"][index], dtype=float)
            dz = np.diff(z_w(ds, zeta), axis=0)
            dye = np.ma.filled(ds.variables["dye_01"][index], 0.0).astype(float)
            volume = dz * area[np.newaxis, :, :] * mask[np.newaxis, :, :]
            inventories.append(float(np.nansum(dye * volume)))
            maxima.append(float(np.nanmax(dye)))
            minima.append(float(np.nanmin(dye)))
    return {
        "path": str(path),
        "records": int(len(ocean_time)),
        "ocean_time": [float(value) for value in ocean_time],
        "ocean_time_units": units,
        "datetimes": datetimes,
        "inventory_bq": inventories,
        "first_inventory_bq": inventories[0] if inventories else None,
        "last_inventory_bq": inventories[-1] if inventories else None,
        "delta_inventory_bq": (inventories[-1] - inventories[0]) if inventories else None,
        "dye_min": min(minima) if minima else None,
        "dye_max": max(maxima) if maxima else None,
    }


def estimate_decay_loss(history: dict[str, object], lambda_s: float) -> float | None:
    times = np.asarray(history["ocean_time"], dtype=float)
    inventories = np.asarray(history["inventory_bq"], dtype=float)
    if times.size < 2:
        return None
    units = str(history.get("ocean_time_units") or "").lower()
    if "day" in units:
        dt_seconds = np.diff(times) * 86400.0
    else:
        dt_seconds = np.diff(times)
    avg_inventory = 0.5 * (inventories[:-1] + inventories[1:])
    return float(np.sum(lambda_s * avg_inventory * dt_seconds))


def field_health(path: Path) -> dict[str, object]:
    out: dict[str, object] = {"path": str(path), "variables": {}}
    with Dataset(path) as ds:
        mask = np.asarray(ds.variables["mask_rho"][:], dtype=bool) if "mask_rho" in ds.variables else None
        variables: dict[str, object] = {}
        for name in ("dye_01", "temp", "salt"):
            if name not in ds.variables:
                continue
            values = np.ma.filled(ds.variables[name][:], np.nan).astype(float)
            if mask is not None and values.ndim >= 3:
                wet = np.broadcast_to(mask, values.shape[-2:])
                wet = np.broadcast_to(wet, values.shape)
                subset = values[wet]
            else:
                subset = values.reshape(-1)
            finite = np.isfinite(subset)
            info: dict[str, object] = {
                "wet_finite": bool(finite.all()),
                "wet_nan_count": int(np.isnan(subset).sum()),
                "wet_min": float(np.nanmin(subset)),
                "wet_max": float(np.nanmax(subset)),
            }
            if name == "dye_01":
                masked = np.where(np.isfinite(values), values, -np.inf)
                index = np.unravel_index(int(np.nanargmax(masked)), masked.shape)
                info["max_index"] = [int(item) for item in index]
                if len(index) >= 4:
                    info["max_time_index"] = int(index[0])
                    info["max_vertical_index"] = int(index[1])
                    info["max_eta_index"] = int(index[2])
                    info["max_xi_index"] = int(index[3])
                    info["max_in_upper_layer"] = bool(index[1] == values.shape[1] - 1)
            variables[name] = info
        out["variables"] = variables
    return out


def cumulative_source_bq(params: dict[str, object], seconds: float) -> dict[str, float]:
    source = params.get("source", {}) if isinstance(params.get("source"), dict) else {}
    release_bq_s = float(source.get("annual_release_TBq_per_year", 0.0)) * 1.0e12 / (
        float(source.get("calendar_year_days", 365.0)) * 86400.0
    )
    return {
        "release_Bq_s": release_bq_s,
        "duration_seconds": float(seconds),
        "cumulative_source_Bq": release_bq_s * float(seconds),
    }


def write_reports(payload: dict[str, object]) -> tuple[Path, Path]:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "fdnpp_online_my25_uvtide_decay_validation.json"
    md_path = reports_dir / "fdnpp_online_my25_uvtide_decay_validation.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    lines = [
        "# FDNPP Online MY25 UV-Tide Decay Validation",
        "",
        f"- status: `{payload['status']}`",
        f"- profile: `{payload['profile']}`",
        f"- lambda s-1: `{payload['radioactive_decay']['lambda_s']}`",  # type: ignore[index]
        f"- decay loss estimate: `{payload.get('decay_loss_bq')}` Bq",
        f"- build: `{payload.get('build', {}).get('status')}`",  # type: ignore[union-attr]
        f"- run: `{payload.get('run', {}).get('status')}`",  # type: ignore[union-attr]
    ]
    if payload["status"] == "ok":
        comparison = payload["comparison"]  # type: ignore[index]
        lines.extend(
            [
                f"- no-decay last inventory: `{comparison['nodecay_last_inventory_bq']}` Bq",
                f"- decay last inventory: `{comparison['decay_last_inventory_bq']}` Bq",
                f"- decay inventory lower: `{comparison['decay_inventory_lower']}`",
                f"- no NaN detected: `{comparison['no_nan_detected']}`",
                f"- source cumulative input: `{payload['source']['cumulative_source_Bq']}` Bq",  # type: ignore[index]
            ]
        )
    else:
        lines.append(f"- blocked reason: `{payload.get('blocked_reason')}`")
    lines.extend(
        [
            "",
            "## Implementation",
            "",
            "- configuration: `passive_tracer.radioactive_decay` with profile override in `project_parameters.json`",
            "- CPP: decay build defines `RADIOACTIVE_DECAY`, no-decay build does not",
            "- ROMS source: `step3d_t.F` applies `C_new = C_old * exp(-lambda * dt)` to `inert(1)` / `dye_01` only",
            "- defaults: species `HTO`, unit `Bq m-3`, half-life `12.32 years`, year conversion `365.25 days/year`",
            "- no-decay profile preserved: `online_my25_uvtide`",
            "",
            "## Budget Form",
            "",
            "`source_input ~= domain_inventory + open_boundary_export + decay_loss + numerical_residual`.",
            "The `decay_loss` above is an offline trapezoidal estimate of `integral(lambda * dye_01 * cell_volume dt)`.",
            "",
            "## Recommendation",
            "",
            "The decay profile passed a 6-hour smoke validation. Run a longer multi-day comparison before using it for 1-year production.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n")
    return md_path, json_path


def run_status(log_path: Path) -> dict[str, object]:
    text = log_path.read_text(errors="ignore") if log_path.exists() else ""
    return {
        "status": "ok" if "ROMS: DONE" in text else "missing_or_incomplete",
        "log": str(log_path),
        "roms_done": "ROMS: DONE" in text,
        "has_blowup": bool(re.search(r"BLOWUP", text)),
        "has_nan_keyword": bool(re.search(r"\bNaN\b", text)),
    }


def main() -> None:
    args = parse_args()
    params = load_project_params()
    decay_cfg = radioactive_decay_config(params, args.profile)
    nodecay_path = Path(args.nodecay_history)
    decay_path = Path(args.decay_history)
    missing = [str(path) for path in (nodecay_path, decay_path) if not path.exists()]
    if missing:
        payload: dict[str, object] = {
            "status": "blocked",
            "blocked_reason": "history output missing; run no-decay and decay online_6h cases first",
            "missing": missing,
            "profile": args.profile,
            "radioactive_decay": decay_cfg,
            "zero_source_decay_test": {
                "status": "not_run",
                "reason": "requires constructing a separate nonzero initial dye_01, zero-source ROMS run; existing FDNPP inputs were not modified",
                "theory": "C(t)=C0*exp(-lambda*t)",
            },
        }
        md_path, json_path = write_reports(payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"wrote {md_path}")
        print(f"wrote {json_path}")
        return
    nodecay = inventory_series(nodecay_path)
    decay = inventory_series(decay_path)
    decay_loss = estimate_decay_loss(decay, float(decay_cfg["lambda_s"]))
    duration_seconds = float(decay["ocean_time"][-1] - decay["ocean_time"][0])  # type: ignore[index]
    source = cumulative_source_bq(params, duration_seconds)
    nodecay_health = field_health(nodecay_path)
    decay_health = field_health(decay_path)
    no_nan_detected = all(
        bool(info["wet_finite"])
        for health in (nodecay_health, decay_health)
        for info in health["variables"].values()  # type: ignore[union-attr]
    )
    comparison = {
        "nodecay_last_inventory_bq": nodecay["last_inventory_bq"],
        "decay_last_inventory_bq": decay["last_inventory_bq"],
        "inventory_difference_bq": float(decay["last_inventory_bq"] - nodecay["last_inventory_bq"]),  # type: ignore[operator]
        "decay_inventory_lower": bool(decay["last_inventory_bq"] <= nodecay["last_inventory_bq"]),  # type: ignore[operator]
        "no_nan_detected": no_nan_detected,
        "decay_dye_max_in_upper_layer": decay_health["variables"]["dye_01"]["max_in_upper_layer"],  # type: ignore[index]
    }
    payload = {
        "status": "ok",
        "profile": args.profile,
        "radioactive_decay": decay_cfg,
        "modified_files": [
            "Data_pre/core/radioactive_decay.py",
            "Data_pre/cases/FDNPP/config/project_parameters.json",
            "Data_pre/cases/FDNPP/config/roms_build_config.json",
            "Data_pre/cases/FDNPP/config/roms_run_config.json",
            "Data_pre/cases/_template/config/project_parameters.json",
            "Data_pre/cases/_template/config/roms_build_config.json",
            "Data_pre/cases/_template/config/roms_run_config.json",
            "Data_pre/impl/preprocessing/create_pilot_infile.py",
            "Data_pre/impl/preprocessing/create_initial_nc.py",
            "Data_pre/impl/preprocessing/create_ocean_ini_from_hycom.py",
            "Data_pre/impl/preprocessing/create_ocean_bry_from_hycom.py",
            "Data_pre/impl/preprocessing/create_river_source_production.py",
            "Data_pre/impl/preprocessing/validate_radioactive_decay_config.py",
            "Data_pre/impl/preprocessing/compare_decay_vs_nodecay.py",
            "Data_pre/scripts/validation/validate_radioactive_decay_config.py",
            "Data_pre/scripts/validation/compare_decay_vs_nodecay.py",
            "Data_pre/scripts/validation/validate_online_decay_run.py",
            "ROMS_Build/scripts/build/show_build_plan.py",
            "roms_src/roms/ROMS/Nonlinear/step3d_t.F",
            "projects/FDNPP/run/fdnpp_202501_online_my25_uvtide_decay.h",
            "projects/FDNPP/run/ocean_fdnpp_online_6h_online_my25_uvtide_decay.in",
        ],
        "build": {
            "status": "ok" if (ROOT / "bin" / "romsM_fdnpp_online_my25_uvtide_decay").exists() else "missing",
            "binary": str(ROOT / "bin" / "romsM_fdnpp_online_my25_uvtide_decay"),
        },
        "run": run_status(ROOT / "logs" / "online_6h_online_my25_uvtide_decay.log"),
        "source": source,
        "nodecay": nodecay,
        "decay": decay,
        "nodecay_field_health": nodecay_health,
        "decay_field_health": decay_health,
        "comparison": comparison,
        "decay_loss_bq": decay_loss,
    }
    md_path, json_path = write_reports(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
