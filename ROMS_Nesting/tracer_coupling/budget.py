"""Synthetic accounting contract for offline HTO inter-grid coupling.

This is NOT the coupled ROMS transport solver. It verifies a signed Bq
ledger that the future Fortran flux hooks must populate from actual
discrete face fluxes. Concentration fields cannot be post-hoc spliced.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

DOMAINS = ("ES3K_only", "UD1K_only", "L3_300m")
INTERFACES = ("ES3K_UD1K", "UD1K_L3")


@dataclass(frozen=True)
class InterfaceWindow:
    interface: str
    parent_outward_bq: float
    child_outward_bq: float

    @property
    def residual_bq(self) -> float:
        """Both fluxes use their *own* domain's outward normal."""
        return self.parent_outward_bq + self.child_outward_bq

    @property
    def exchanged_bq(self) -> float:
        return max(abs(self.parent_outward_bq), abs(self.child_outward_bq))


@dataclass(frozen=True)
class ReleaseEvent:
    """Only one active physical domain may account for an emission event."""
    event_id: str
    owner_domain: str
    activity_bq: float


@dataclass(frozen=True)
class BudgetWindow:
    initial_by_domain_bq: dict[str, float]
    final_by_domain_bq: dict[str, float]
    emissions: tuple[ReleaseEvent, ...] = ()
    outer_in_bq: float = 0.0
    outer_out_bq: float = 0.0
    radioactive_decay_bq: float = 0.0
    other_physical_sink_bq: float = 0.0
    numerical_adjustment_bq: float = 0.0
    interfaces: tuple[InterfaceWindow, ...] = ()


def evaluate_budget(window: BudgetWindow, *, reference_bq: float,
                    tolerance: float) -> dict[str, object]:
    """Audit inventory and internal-interface cancellation.

    For a zero-inventory, zero-source case, reference_bq must be an
    explicitly pre-registered positive Bq number; never infer a large
    denominator from model output to hide a discrepancy.
    """
    if not math.isfinite(reference_bq) or reference_bq <= 0:
        raise ValueError("reference_bq must be finite and positive")
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    if set(window.initial_by_domain_bq) != set(DOMAINS) or set(window.final_by_domain_bq) != set(DOMAINS):
        raise ValueError("inventory must use exactly the three disjoint active domains")
    amounts = [*window.initial_by_domain_bq.values(), *window.final_by_domain_bq.values(),
               window.outer_in_bq, window.outer_out_bq, window.radioactive_decay_bq,
               window.other_physical_sink_bq, window.numerical_adjustment_bq]
    ids = set()
    for e in window.emissions:
        if e.owner_domain not in DOMAINS:
            raise ValueError("emission owner is not an active domain")
        if not e.event_id or e.event_id in ids:
            raise ValueError("duplicated or empty emission event id")
        ids.add(e.event_id)
        if not math.isfinite(e.activity_bq) or e.activity_bq < 0:
            raise ValueError("invalid injected activity")
        amounts.append(e.activity_bq)
    for x in window.interfaces:
        if x.interface not in INTERFACES:
            raise ValueError("unrecognized internal interface")
        amounts += [x.parent_outward_bq, x.child_outward_bq]
    if not all(map(math.isfinite, amounts)):
        raise ValueError("nonfinite budget field")
    if min(window.initial_by_domain_bq.values()) < 0 or min(window.final_by_domain_bq.values()) < 0:
        raise ValueError("negative active physical-domain inventory")
    if min(window.radioactive_decay_bq, window.outer_in_bq, window.outer_out_bq, window.other_physical_sink_bq) < 0:
        raise ValueError("loss and outer flux magnitudes must be nonnegative")
    seen = set()
    iface_errors = {}
    for x in window.interfaces:
        if x.interface in seen:
            raise ValueError("duplicated interface entry")
        seen.add(x.interface)
        # Normalize by the registered reference, not by a freely variable flux.
        rel = abs(x.residual_bq) / reference_bq
        iface_errors[x.interface] = {"residual_bq": x.residual_bq,
                                     "relative_residual": rel,
                                     "pass": rel <= tolerance}
    initial = math.fsum(window.initial_by_domain_bq.values())
    final = math.fsum(window.final_by_domain_bq.values())
    injected = math.fsum(x.activity_bq for x in window.emissions)
    expected = (initial + injected + window.outer_in_bq - window.outer_out_bq
                - window.radioactive_decay_bq - window.other_physical_sink_bq
                + window.numerical_adjustment_bq)
    residual = final - expected
    return {
        "source_of_fluxes": "SYNTHETIC_CONTRACT_ONLY",
        "inventory_initial_bq": initial,
        "inventory_final_bq": final,
        "injected_bq": injected,
        "whole_domain_residual_bq": residual,
        "whole_domain_relative_residual": abs(residual) / reference_bq,
        "interfaces": iface_errors,
        "pass": abs(residual) / reference_bq <= tolerance and all(v["pass"] for v in iface_errors.values()),
    }


def decay_exact(initial_bq: float, elapsed_seconds: float, half_life_years: float = 12.32,
                days_per_year: float = 365.25) -> tuple[float, float]:
    """Analytical HTO decay reference only; actual ROMS time-discretization is separate."""
    if min(initial_bq, elapsed_seconds, half_life_years, days_per_year) < 0 or half_life_years == 0 or days_per_year == 0:
        raise ValueError("invalid decay inputs")
    rate = math.log(2) / (half_life_years * days_per_year * 86400)
    remaining = initial_bq * math.exp(-rate * elapsed_seconds)
    return remaining, initial_bq - remaining
