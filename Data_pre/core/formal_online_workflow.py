#!/usr/bin/env python3
"""Shared rules for formal online passive-tracer spin-up and production runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import calendar
import re
from pathlib import Path
from typing import Any


RESTART_REQUIRED_BASE_VARIABLES = (
    "zeta",
    "ubar",
    "vbar",
    "u",
    "v",
    "temp",
    "salt",
    "ocean_time",
)
RESTART_REQUIRED_PASSIVE_VARIABLES = ("dye_01",)
RESTART_OPTIONAL_TURBULENCE_VARIABLES = ("AKv", "AKt", "AKs", "tke", "gls")


@dataclass(frozen=True)
class FormalOnlineWorkflow:
    enabled: bool
    profile: str
    profile_token: str
    spinup_duration_months: int
    production_start: datetime
    production_end: datetime
    spinup_start: datetime
    spinup_end: datetime
    production_duration_label: str
    spinup_mode: str
    production_mode: str
    production_decay_mode: str


def subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 - months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def profile_token(profile: str | None) -> str:
    token = (profile or "default").strip()
    if token.startswith("online_"):
        token = token[len("online_") :]
    return token


def profile_name_from_token(token: str, *, decay: bool = False) -> str:
    if token.startswith("online_"):
        profile = token
    else:
        profile = f"online_{token}"
    if decay and not profile.endswith("_decay"):
        profile = f"{profile}_decay"
    if not decay and profile.endswith("_decay"):
        profile = profile[: -len("_decay")]
    return profile


def production_duration_label(start: datetime, end: datetime) -> str:
    seconds = int((end - start).total_seconds())
    days = seconds / 86400.0
    if 364 <= days <= 366:
        return "1y"
    if seconds % (30 * 86400) == 0:
        months = seconds // (30 * 86400)
        if months > 0:
            return f"{months}mo"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds}s"


def load_formal_online_workflow(params: dict[str, Any]) -> FormalOnlineWorkflow:
    cfg = params.get("formal_online_workflow", {})
    if not isinstance(cfg, dict):
        cfg = {}
    spinup_cfg = cfg.get("spinup", {}) if isinstance(cfg.get("spinup"), dict) else {}
    production_cfg = cfg.get("production", {}) if isinstance(cfg.get("production"), dict) else {}
    physics_cfg = params.get("physics", {}) if isinstance(params.get("physics"), dict) else {}
    profile = str(cfg.get("profile") or physics_cfg.get("profile") or "online_my25_uvtide")
    token = profile_token(profile)
    production_start = datetime.fromisoformat(
        str(production_cfg.get("start") or params.get("time", {}).get("start"))
    )
    production_end = datetime.fromisoformat(
        str(production_cfg.get("end") or params.get("time", {}).get("stop"))
    )
    months = int(spinup_cfg.get("duration_months", 3))
    spinup_start = subtract_months(production_start, months)
    duration = production_duration_label(production_start, production_end)
    return FormalOnlineWorkflow(
        enabled=bool(cfg.get("enabled", False)),
        profile=profile,
        profile_token=token,
        spinup_duration_months=months,
        production_start=production_start,
        production_end=production_end,
        spinup_start=spinup_start,
        spinup_end=production_start,
        production_duration_label=duration,
        spinup_mode=f"online_spinup_{months}mo_{token}",
        production_mode=f"online_production_{duration}_{token}_from_spinup",
        production_decay_mode=f"online_production_{duration}_{token}_decay_from_spinup",
    )


def parse_formal_online_mode(mode: str, params: dict[str, Any]) -> dict[str, Any] | None:
    workflow = load_formal_online_workflow(params)
    if mode == workflow.spinup_mode or mode == "online_spinup_3mo":
        return {"phase": "spinup", "workflow": workflow, "profile": workflow.profile, "decay": False}
    if mode == workflow.production_mode:
        return {"phase": "production", "workflow": workflow, "profile": workflow.profile, "decay": False}
    if mode == workflow.production_decay_mode:
        return {
            "phase": "production",
            "workflow": workflow,
            "profile": profile_name_from_token(workflow.profile_token, decay=True),
            "decay": True,
        }
    spinup_match = re.fullmatch(r"online_spinup_(\d+)mo_(.+)", mode)
    if spinup_match:
        months = int(spinup_match.group(1))
        token = spinup_match.group(2)
        return {
            "phase": "spinup",
            "workflow": workflow,
            "profile": profile_name_from_token(token, decay=False),
            "profile_token": token,
            "duration_months": months,
            "decay": False,
        }
    production_match = re.fullmatch(r"online_production_([^_]+)_(.+?)(_decay)?_from_spinup", mode)
    if production_match:
        token = production_match.group(2)
        decay = bool(production_match.group(3))
        return {
            "phase": "production",
            "workflow": workflow,
            "profile": profile_name_from_token(token, decay=decay),
            "profile_token": token,
            "duration_label": production_match.group(1),
            "decay": decay,
        }
    return None


def spinup_restart_name(case_prefix: str, workflow: FormalOnlineWorkflow) -> str:
    return f"rst_{case_prefix}_{workflow.spinup_mode}.nc"


def spinup_zero_source_name(case_prefix: str, workflow: FormalOnlineWorkflow) -> str:
    return f"roms_rivers_{case_prefix}_{workflow.spinup_mode}_zero_source.nc"


def expected_restart_variables(passive_tracer_enabled: bool = True) -> tuple[str, ...]:
    variables = list(RESTART_REQUIRED_BASE_VARIABLES)
    if passive_tracer_enabled:
        variables.extend(RESTART_REQUIRED_PASSIVE_VARIABLES)
    return tuple(variables)


def path_exists_or_expected(path: Path) -> str:
    return "exists" if path.exists() else "expected"
