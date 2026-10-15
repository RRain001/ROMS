#!/usr/bin/env python3
"""Fail-closed verification of external forcing time coverage.

A real ROMS run may only start when the boundary file that is actually written
into ``BRYNAME`` is provably able to cover the whole requested window.  This
module keeps apart two outcomes that used to collapse into one silent fallback:

``UNKNOWN``
    Coverage could not be established at all: file missing, no time axis,
    missing ``units``, undecodable calendar, empty axis, unreadable variable.
``INSUFFICIENT``
    Coverage was established and does not span the requested window.

Both are refusals.  Only ``OK`` permits a run.  Reporting a plan without real
forcing is still possible, but such a plan is stamped ``FORCING_UNVERIFIED`` and
the run gate refuses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from netCDF4 import Dataset, num2date


#: ROMS ``TIME_REF`` used by every generated ``.in`` in this repository.
ROMS_REFERENCE_DATE = datetime(1858, 11, 17)

OK = "OK"
UNKNOWN = "UNKNOWN"
INSUFFICIENT = "INSUFFICIENT"

#: Marker written into a generated plan whose forcing could not be verified.
UNVERIFIED_MARKER = "FORCING_UNVERIFIED"


def mjd_to_datetime(days: float) -> datetime:
    """Convert a ROMS MJD (days since ``TIME_REF``) to a datetime."""
    return ROMS_REFERENCE_DATE + timedelta(days=float(days))


def datetime_to_mjd(value: datetime) -> float:
    """Convert a datetime to a ROMS MJD (days since ``TIME_REF``)."""
    return (value - ROMS_REFERENCE_DATE).total_seconds() / 86400.0


@dataclass(frozen=True)
class TimeAxisReport:
    """What was actually inspected for one boundary time axis."""

    variable: str
    units: str | None
    calendar: str | None
    count: int
    start: datetime | None
    stop: datetime | None
    strictly_increasing: bool
    error: str | None


@dataclass(frozen=True)
class CoverageReport:
    """Verdict for one boundary file against one requested window."""

    status: str
    path: Path
    required_start: datetime
    required_stop: datetime
    axes: tuple[TimeAxisReport, ...]
    reasons: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == OK

    def describe(self) -> str:
        lines = [
            f"boundary coverage {self.status}: {self.path}",
            f"  required window: {self.required_start.isoformat()} -> {self.required_stop.isoformat()}",
        ]
        for axis in self.axes:
            if axis.error:
                lines.append(f"  {axis.variable}: ERROR {axis.error}")
            else:
                lines.append(
                    f"  {axis.variable}: n={axis.count} units={axis.units!r} "
                    f"calendar={axis.calendar!r} {axis.start.isoformat()} -> {axis.stop.isoformat()} "
                    f"strictly_increasing={axis.strictly_increasing}"
                )
        for reason in self.reasons:
            lines.append(f"  reason: {reason}")
        return "\n".join(lines)


def boundary_time_variables(ds: Dataset) -> list[str]:
    """Every boundary time axis actually present in the file.

    ROMS boundary files carry one time axis per field group (``zeta_time``,
    ``v2d_time``, ``v3d_time``, ``temp_time``, ``salt_time``, ``dye_time``, ...).
    Checking a single one of them, as an earlier revision did, is not coverage
    evidence: the axes can differ in length and span.
    """
    names = {name for name in ds.variables if name.endswith("_time")}
    names.add("ocean_time") if "ocean_time" in ds.variables else None
    return sorted(names)


def _inspect_axis(ds: Dataset, name: str) -> TimeAxisReport:
    var = ds.variables[name]
    units = getattr(var, "units", None)
    calendar = getattr(var, "calendar", None)
    try:
        raw = var[:]
    except Exception as exc:  # noqa: BLE001
        return TimeAxisReport(name, units, calendar, 0, None, None, False, f"unreadable time axis: {exc}")

    count = int(raw.size)
    if count == 0:
        return TimeAxisReport(name, units, calendar, 0, None, None, False, "time axis is empty")
    if not units:
        return TimeAxisReport(name, units, calendar, count, None, None, False, "time axis has no units attribute")
    try:
        parsed = num2date(raw, units=units, calendar=calendar or "standard")
    except Exception as exc:  # noqa: BLE001
        return TimeAxisReport(
            name, units, calendar, count, None, None, False, f"time axis cannot be decoded: {exc}"
        )

    values = [datetime(v.year, v.month, v.day, v.hour, v.minute, v.second) for v in parsed]
    strictly_increasing = all(later > earlier for earlier, later in zip(values, values[1:]))
    return TimeAxisReport(name, units, calendar, count, values[0], values[-1], strictly_increasing, None)


def check_boundary_coverage(
    path: Path | str,
    required_start: datetime,
    required_stop: datetime,
) -> CoverageReport:
    """Verify that ``path`` provably covers ``[required_start, required_stop]``.

    Never raises for bad data: every failure mode is reported as ``UNKNOWN`` or
    ``INSUFFICIENT`` so callers can fail closed with a specific message.
    """
    path = Path(path)
    reasons: list[str] = []

    if required_stop < required_start:
        return CoverageReport(
            INSUFFICIENT, path, required_start, required_stop, (),
            (f"requested window is inverted: {required_start.isoformat()} -> {required_stop.isoformat()}",),
        )
    if not path.is_file():
        return CoverageReport(
            UNKNOWN, path, required_start, required_stop, (),
            (f"boundary file not found: {path}",),
        )

    try:
        ds = Dataset(path)
    except Exception as exc:  # noqa: BLE001
        return CoverageReport(
            UNKNOWN, path, required_start, required_stop, (), (f"boundary file cannot be opened: {exc}",)
        )

    try:
        names = boundary_time_variables(ds)
        if not names:
            return CoverageReport(
                UNKNOWN, path, required_start, required_stop, (),
                ("no boundary time axis found (expected at least one *_time variable)",),
            )
        axes = tuple(_inspect_axis(ds, name) for name in names)
    finally:
        ds.close()

    undecidable = [axis for axis in axes if axis.error]
    if undecidable:
        reasons.extend(f"{axis.variable}: {axis.error}" for axis in undecidable)
        return CoverageReport(UNKNOWN, path, required_start, required_stop, axes, tuple(reasons))

    for axis in axes:
        if not axis.strictly_increasing:
            reasons.append(
                f"{axis.variable}: time axis is not strictly increasing "
                f"({axis.start.isoformat()} -> {axis.stop.isoformat()})"
            )
    if reasons:
        return CoverageReport(INSUFFICIENT, path, required_start, required_stop, axes, tuple(reasons))

    for axis in axes:
        if axis.start > required_start:
            reasons.append(
                f"{axis.variable}: starts at {axis.start.isoformat()}, "
                f"after the requested start {required_start.isoformat()}"
            )
        if axis.stop < required_stop:
            reasons.append(
                f"{axis.variable}: ends at {axis.stop.isoformat()}, "
                f"before the requested stop {required_stop.isoformat()}"
            )
    if reasons:
        return CoverageReport(INSUFFICIENT, path, required_start, required_stop, axes, tuple(reasons))

    return CoverageReport(OK, path, required_start, required_stop, axes, ())


def coverage_sidecar_path(infile: Path) -> Path:
    """Where the ``FORCING_UNVERIFIED`` record for ``infile`` is written."""
    return infile.with_suffix(infile.suffix + ".forcing_status.json")
