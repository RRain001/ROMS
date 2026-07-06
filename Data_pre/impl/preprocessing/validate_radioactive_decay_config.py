#!/usr/bin/env python3
"""Validate radioactive-decay configuration for online passive tracers."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from case_context import get_case_config_path, get_case_root
from radioactive_decay import radioactive_decay_config
from roms_preprocessing_utils import load_project_params


ROOT = get_case_root()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="online_my25_uvtide_decay")
    parser.add_argument("--nodecay-profile", default="online_my25_uvtide")
    parser.add_argument("--write-report", action="store_true", default=True)
    return parser.parse_args()


def cpp_defs(path: Path) -> list[str]:
    if not path.exists():
        return []
    defs: list[str] = []
    for line in path.read_text(errors="ignore").splitlines():
        match = re.match(r"\s*#\s*define\s+([A-Za-z0-9_]+)(?:\s+(.*))?$", line)
        if match:
            value = match.group(2)
            defs.append(match.group(1) if value is None else f"{match.group(1)}={value.strip()}")
    return defs


def write_reports(payload: dict[str, object]) -> tuple[Path, Path]:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "online_tracer_radioactive_decay_plan.json"
    md_path = reports_dir / "online_tracer_radioactive_decay_plan.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    decay = payload["decay_profile"]  # type: ignore[index]
    nodecay = payload["nodecay_profile"]  # type: ignore[index]
    checks = payload["checks"]  # type: ignore[index]
    lines = [
        "# Online Passive Tracer Radioactive Decay Plan",
        "",
        f"- decay profile: `{decay['profile']}` enabled={decay['radioactive_decay']['enabled']}",  # type: ignore[index]
        f"- no-decay profile: `{nodecay['profile']}` enabled={nodecay['radioactive_decay']['enabled']}",  # type: ignore[index]
        f"- species: `{decay['radioactive_decay']['species']}`",  # type: ignore[index]
        f"- target tracer: `{decay['radioactive_decay']['target_tracer']}`",  # type: ignore[index]
        f"- half-life years: `{decay['radioactive_decay']['half_life_years']}`",  # type: ignore[index]
        f"- lambda s-1: `{decay['radioactive_decay']['lambda_s']}`",  # type: ignore[index]
        f"- year conversion: `{decay['radioactive_decay']['days_per_year']}` days/year",
        f"- CPP switch: `RADIOACTIVE_DECAY` in decay header only",
        f"- implementation: `roms_src/roms/ROMS/Nonlinear/step3d_t.F`, exponential sink on `inert(1)` / `dye_01`",
        f"- no-decay profile preserved: `{checks['nodecay_disabled']}`",  # type: ignore[index]
        "",
        "## Checks",
        "",
    ]
    for key, value in checks.items():  # type: ignore[union-attr]
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Mass Budget Note",
            "",
            "For decay runs, use `source_input ~= domain_inventory + open_boundary_export + decay_loss + numerical_residual`.",
            "`decay_loss` is estimated offline as `integral(lambda * dye_01 * cell_volume dt)`.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n")
    return md_path, json_path


def main() -> None:
    args = parse_args()
    params = load_project_params()
    build_config_path = get_case_config_path("roms_build_config.json")
    build_config = json.loads(build_config_path.read_text())
    variants = build_config.get("variants", {})

    decay_cfg = radioactive_decay_config(params, args.profile)
    nodecay_cfg = radioactive_decay_config(params, args.nodecay_profile)
    decay_variant = variants.get(args.profile, {})
    nodecay_variant = variants.get(args.nodecay_profile, {})
    decay_header = ROOT / decay_variant.get("header_dir", "run") / decay_variant.get("header_name", "")
    nodecay_header = ROOT / nodecay_variant.get("header_dir", "run") / nodecay_variant.get("header_name", "")
    decay_defs = cpp_defs(decay_header)
    nodecay_defs = cpp_defs(nodecay_header)

    checks = {
        "hto_half_life_years": abs(float(decay_cfg["half_life_years"]) - 12.32) < 1.0e-12,
        "lambda_positive": float(decay_cfg["lambda_s"]) > 0.0,
        "nodecay_disabled": bool(nodecay_cfg["enabled"]) is False,
        "decay_enabled": bool(decay_cfg["enabled"]) is True,
        "target_is_dye_01": decay_cfg["target_tracer"] == "dye_01",
        "apply_to_temp_salt_false": bool(decay_cfg["apply_to_temp_salt"]) is False,
        "decay_header_has_cpp": any(item.startswith("RADIOACTIVE_DECAY") for item in decay_defs),
        "nodecay_header_lacks_cpp": not any(item.startswith("RADIOACTIVE_DECAY") for item in nodecay_defs),
        "build_variant_distinct": decay_variant.get("roms_application") != nodecay_variant.get("roms_application"),
    }
    payload: dict[str, object] = {
        "case_root": str(ROOT),
        "config": str(get_case_config_path("project_parameters.json")),
        "year_to_second_conversion": {
            "days_per_year": decay_cfg["days_per_year"],
            "seconds_per_year": decay_cfg["seconds_per_year"],
        },
        "nodecay_profile": {
            "profile": args.nodecay_profile,
            "build_variant": nodecay_variant,
            "header": str(nodecay_header),
            "cpp_defs": nodecay_defs,
            "radioactive_decay": nodecay_cfg,
        },
        "decay_profile": {
            "profile": args.profile,
            "build_variant": decay_variant,
            "header": str(decay_header),
            "cpp_defs": decay_defs,
            "radioactive_decay": decay_cfg,
        },
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    md_path, json_path = write_reports(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
