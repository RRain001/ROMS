#!/usr/bin/env python3
"""Shared annual source-activity unit conversion helpers."""

from __future__ import annotations

from typing import Any


SECONDS_PER_DAY = 86400.0
TBQ_TO_BQ = 1.0e12
PBQ_TO_BQ = 1.0e15


def _source_config(params_or_source: dict[str, Any]) -> dict[str, Any]:
    source = params_or_source.get("source")
    return source if isinstance(source, dict) else params_or_source


def annual_release_bq(params_or_source: dict[str, Any]) -> float:
    """Return annual activity in Bq, accepting exactly one PBq/TBq field."""
    source = _source_config(params_or_source)
    has_pbq = source.get("annual_release_PBq_per_year") is not None
    has_tbq = source.get("annual_release_TBq_per_year") is not None
    if has_pbq and has_tbq:
        raise ValueError(
            "source must define only one of annual_release_PBq_per_year or "
            "annual_release_TBq_per_year"
        )
    if has_pbq:
        value = float(source["annual_release_PBq_per_year"])
        if value < 0.0:
            raise ValueError("annual_release_PBq_per_year must be non-negative")
        return value * PBQ_TO_BQ
    if has_tbq:
        value = float(source["annual_release_TBq_per_year"])
        if value < 0.0:
            raise ValueError("annual_release_TBq_per_year must be non-negative")
        return value * TBQ_TO_BQ
    raise ValueError(
        "source must define annual_release_PBq_per_year or "
        "annual_release_TBq_per_year"
    )


def calendar_year_days(params_or_source: dict[str, Any]) -> float:
    source = _source_config(params_or_source)
    days = float(source.get("calendar_year_days", 365.0))
    if days <= 0.0:
        raise ValueError("source.calendar_year_days must be positive")
    return days


def release_rate_bq_s(params_or_source: dict[str, Any]) -> float:
    """Return the configured constant annual activity rate in Bq s-1."""
    return annual_release_bq(params_or_source) / (calendar_year_days(params_or_source) * SECONDS_PER_DAY)

