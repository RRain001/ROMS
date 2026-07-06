#!/usr/bin/env python3
"""Compare FDNPP HYCOM and GLORYS12V1 online 7-day validation outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

from case_context import get_case_root


ROOT = get_case_root()
PROFILE = "online_my25_uvtide"
VARIABLES = ("zeta", "temp", "salt", "u", "v", "dye_01")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=PROFILE)
    parser.add_argument("--allow-overlap-only", action="store_true")
    parser.add_argument("--variables", default=",".join(VARIABLES))
    return parser.parse_args()


def validation_path(ocean_source: str, profile: str) -> Path:
    suffix = "" if ocean_source == "hycom" else f"_{ocean_source}"
    return ROOT / "reports" / f"fdnpp_{profile}_7d{suffix}_validation.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"validation report not found: {path}")
    return json.loads(path.read_text())


def time_axis(path: Path) -> list[str]:
    with Dataset(path) as ds:
        var = ds.variables["ocean_time"]
        values = num2date(var[:], units=var.units, calendar=getattr(var, "calendar", "standard"))
    return [value.isoformat() for value in values]


def common_indices(left_times: list[str], right_times: list[str], allow_overlap_only: bool) -> tuple[list[int], list[int], list[str], str]:
    if left_times == right_times:
        return list(range(len(left_times))), list(range(len(right_times))), left_times, "exact"
    if not allow_overlap_only:
        raise SystemExit(
            "HYCOM and GLORYS time axes differ; rerun aligned cases or pass --allow-overlap-only"
        )
    left_lookup = {value: index for index, value in enumerate(left_times)}
    right_lookup = {value: index for index, value in enumerate(right_times)}
    common = sorted(set(left_lookup).intersection(right_lookup))
    if not common:
        raise SystemExit("HYCOM and GLORYS outputs have no common history times")
    return [left_lookup[value] for value in common], [right_lookup[value] for value in common], common, "overlap"


def compare_variable(hycom_path: Path, glorys_path: Path, name: str, hycom_indices: list[int], glorys_indices: list[int]) -> dict[str, float | int]:
    count = 0
    diff_sum = 0.0
    diff2_sum = 0.0
    abs_max = 0.0
    hycom_sum = 0.0
    glorys_sum = 0.0
    with Dataset(hycom_path) as hycom, Dataset(glorys_path) as glorys:
        if name not in hycom.variables:
            return {"available": 0, "reason": f"missing HYCOM variable {name}"}
        if name not in glorys.variables:
            return {"available": 0, "reason": f"missing GLORYS variable {name}"}
        hvar = hycom.variables[name]
        gvar = glorys.variables[name]
        if hvar.shape[1:] != gvar.shape[1:]:
            return {
                "available": 0,
                "reason": f"shape mismatch HYCOM {hvar.shape} vs GLORYS {gvar.shape}",
            }
        for hidx, gidx in zip(hycom_indices, glorys_indices, strict=True):
            h = np.ma.filled(hvar[hidx], np.nan).astype(float, copy=False)
            g = np.ma.filled(gvar[gidx], np.nan).astype(float, copy=False)
            finite = np.isfinite(h) & np.isfinite(g)
            if not finite.any():
                continue
            diff = h[finite] - g[finite]
            count += int(diff.size)
            diff_sum += float(diff.sum())
            diff2_sum += float(np.sum(diff * diff))
            abs_max = max(abs_max, float(np.max(np.abs(diff))))
            hycom_sum += float(h[finite].sum())
            glorys_sum += float(g[finite].sum())
    if count == 0:
        return {"available": 0, "reason": "no common finite values"}
    return {
        "available": 1,
        "count": count,
        "bias_hycom_minus_glorys": diff_sum / count,
        "rmse": float(np.sqrt(diff2_sum / count)),
        "max_abs_difference": abs_max,
        "hycom_mean": hycom_sum / count,
        "glorys_mean": glorys_sum / count,
    }


def write_reports(payload: dict) -> tuple[Path, Path]:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fdnpp_{payload['profile']}_7d_hycom_vs_glorys12v1_comparison"
    json_path = reports_dir / f"{stem}.json"
    md_path = reports_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    lines = [
        f"# {stem}",
        "",
        f"- time_alignment: {payload['time_alignment']}",
        f"- common_records: {payload['common_record_count']}",
        f"- first_common_time: {payload['first_common_time']}",
        f"- last_common_time: {payload['last_common_time']}",
        f"- hycom_completed: {payload['validations']['hycom']['run']['completed']}",
        f"- glorys_completed: {payload['validations']['glorys12v1']['run']['completed']}",
        "",
        "## Variable Differences",
        "",
        "| variable | bias HYCOM-GLORYS | RMSE | max abs | HYCOM mean | GLORYS mean |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, item in payload["variables"].items():
        if not item.get("available"):
            lines.append(f"| {name} | n/a | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            "| {name} | {bias:.6e} | {rmse:.6e} | {max_abs:.6e} | {hmean:.6e} | {gmean:.6e} |".format(
                name=name,
                bias=item["bias_hycom_minus_glorys"],
                rmse=item["rmse"],
                max_abs=item["max_abs_difference"],
                hmean=item["hycom_mean"],
                gmean=item["glorys_mean"],
            )
        )
    lines.extend([
        "",
        "## Inputs",
        "",
        "```json",
        json.dumps(payload["paths"], indent=2, sort_keys=True),
        "```",
        "",
    ])
    md_path.write_text("\n".join(lines))
    return md_path, json_path


def main() -> None:
    args = parse_args()
    variables = tuple(item.strip() for item in args.variables.split(",") if item.strip())
    hycom = read_json(validation_path("hycom", args.profile))
    glorys = read_json(validation_path("glorys12v1", args.profile))
    hycom_history = Path(hycom["paths"]["history"])
    glorys_history = Path(glorys["paths"]["history"])
    hycom_times = time_axis(hycom_history)
    glorys_times = time_axis(glorys_history)
    hycom_indices, glorys_indices, common, alignment = common_indices(
        hycom_times,
        glorys_times,
        args.allow_overlap_only,
    )
    comparisons = {
        name: compare_variable(hycom_history, glorys_history, name, hycom_indices, glorys_indices)
        for name in variables
    }
    payload = {
        "profile": args.profile,
        "time_alignment": alignment,
        "common_record_count": len(common),
        "first_common_time": common[0],
        "last_common_time": common[-1],
        "paths": {
            "hycom_validation": str(validation_path("hycom", args.profile)),
            "glorys_validation": str(validation_path("glorys12v1", args.profile)),
            "hycom_history": str(hycom_history),
            "glorys_history": str(glorys_history),
        },
        "validations": {
            "hycom": {
                "run": hycom["run"],
                "interpretation": hycom["interpretation"],
            },
            "glorys12v1": {
                "run": glorys["run"],
                "interpretation": glorys["interpretation"],
            },
        },
        "variables": comparisons,
    }
    md_path, json_path = write_reports(payload)
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
