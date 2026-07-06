#!/usr/bin/env python3
"""Shared radioactive-decay configuration helpers for passive tracers."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


SECONDS_PER_DAY = 86400.0
DAYS_PER_YEAR = 365.25
SECONDS_PER_YEAR = DAYS_PER_YEAR * SECONDS_PER_DAY

DEFAULT_PASSIVE_TRACER_NAME = "dye_01"
DEFAULT_PASSIVE_TRACER_UNIT = "Bq m-3"
DEFAULT_RADIONUCLIDE = "HTO"
DEFAULT_HALF_LIFE_YEARS = 12.32


def lambda_from_half_life_years(half_life_years: float) -> float:
    """Return first-order decay constant in s-1."""
    if half_life_years <= 0.0:
        raise ValueError("half_life_years must be positive")
    return math.log(2.0) / (half_life_years * SECONDS_PER_YEAR)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def params_for_profile(params: dict[str, Any], profile: str | None) -> dict[str, Any]:
    """Return params with optional profile override merged in."""
    if not profile:
        return params
    profiles = params.get("profiles", {}) if isinstance(params.get("profiles"), dict) else {}
    override = profiles.get(profile, {}) if isinstance(profiles.get(profile), dict) else {}
    return _deep_merge(params, override) if override else params


def passive_tracer_config(params: dict[str, Any], profile: str | None = None) -> dict[str, Any]:
    """Return passive tracer config with stable defaults."""
    params = params_for_profile(params, profile)
    source = params.get("source", {}) if isinstance(params.get("source"), dict) else {}
    cfg = params.get("passive_tracer", {}) if isinstance(params.get("passive_tracer"), dict) else {}
    return {
        "name": cfg.get("name") or DEFAULT_PASSIVE_TRACER_NAME,
        "unit": cfg.get("unit") or DEFAULT_PASSIVE_TRACER_UNIT,
        "species": cfg.get("species") or source.get("species") or DEFAULT_RADIONUCLIDE,
        "radioactive_decay": cfg.get("radioactive_decay", {}) if isinstance(cfg.get("radioactive_decay"), dict) else {},
    }


def radioactive_decay_config(params: dict[str, Any], profile: str | None = None) -> dict[str, Any]:
    """Return normalized radioactive decay config and computed lambda."""
    tracer = passive_tracer_config(params, profile)
    raw = tracer["radioactive_decay"]
    half_life_years = float(raw.get("half_life_years", DEFAULT_HALF_LIFE_YEARS))
    lambda_value = raw.get("lambda_s")
    lambda_source = "lambda_s" if lambda_value is not None else "half_life_years"
    lambda_s = float(lambda_value) if lambda_value is not None else lambda_from_half_life_years(half_life_years)
    if lambda_s < 0.0:
        raise ValueError("lambda_s must be non-negative")
    return {
        "enabled": bool(raw.get("enabled", False)),
        "species": raw.get("species") or tracer["species"] or DEFAULT_RADIONUCLIDE,
        "half_life_years": half_life_years,
        "lambda_s": lambda_s,
        "lambda_source": lambda_source,
        "target_tracer": raw.get("target_tracer") or tracer["name"] or DEFAULT_PASSIVE_TRACER_NAME,
        "apply_to_temp_salt": bool(raw.get("apply_to_temp_salt", False)),
        "tracer_name": tracer["name"],
        "tracer_unit": tracer["unit"],
        "days_per_year": DAYS_PER_YEAR,
        "seconds_per_year": SECONDS_PER_YEAR,
    }


def radioactive_decay_attrs(params: dict[str, Any], profile: str | None = None) -> dict[str, str | float | int]:
    """Return NetCDF/report metadata attributes for radioactive decay."""
    cfg = radioactive_decay_config(params, profile)
    return {
        "tracer_species": str(cfg["species"]),
        "tracer_unit": str(cfg["tracer_unit"]),
        "radioactive_decay_enabled": int(bool(cfg["enabled"])),
        "radioactive_decay_half_life_years": float(cfg["half_life_years"]),
        "radioactive_decay_lambda_s": float(cfg["lambda_s"]),
        "radioactive_decay_lambda_source": str(cfg["lambda_source"]),
        "radioactive_decay_target": str(cfg["target_tracer"]),
        "radioactive_decay_note": "first-order radioactive decay applied online"
        if cfg["enabled"]
        else "radioactive decay disabled",
    }
