#!/usr/bin/env python3
"""Compute grid and source metrics for the active ROMS case."""

from __future__ import annotations

import json
import math
from datetime import datetime

from case_context import get_case_config_path, get_case_root
from source_activity import annual_release_bq, release_rate_bq_s


ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")


def grid_metrics(lon_min, lon_max, lat_min, lat_max, resolution_m, layers):
    lat_mid = 0.5 * (lat_min + lat_max)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat_mid))
    width_m = (lon_max - lon_min) * m_per_deg_lon
    height_m = (lat_max - lat_min) * m_per_deg_lat
    lm = math.ceil(width_m / resolution_m)
    mm = math.ceil(height_m / resolution_m)
    xi_rho = lm + 2
    eta_rho = mm + 2
    rho_points = xi_rho * eta_rho
    return {
        "resolution_m": resolution_m,
        "width_m": width_m,
        "height_m": height_m,
        "Lm": lm,
        "Mm": mm,
        "xi_rho": xi_rho,
        "eta_rho": eta_rho,
        "rho_points": rho_points,
        "cells_3d": rho_points * layers,
    }


def main() -> None:
    p = json.loads(PARAMS.read_text())
    d = p["domain"]
    t = p["time"]
    v = p["vertical"]
    s = p["source"]

    start = datetime.fromisoformat(t["start"])
    stop = datetime.fromisoformat(t["stop"])
    seconds = (stop - start).total_seconds()

    annual_bq = annual_release_bq(p)
    bq_per_s = release_rate_bq_s(p)
    period_bq = bq_per_s * seconds

    for label, res in [("target", d["target_resolution_m"]), ("pilot", d["pilot_resolution_m"])]:
        g = grid_metrics(d["lon_min"], d["lon_max"], d["lat_min"], d["lat_max"], res, v["N"])
        print(f"[{label}]")
        for key, val in g.items():
            if isinstance(val, float):
                print(f"{key}={val:.3f}")
            else:
                print(f"{key}={val}")

    ntimes = int(seconds / t["pilot_dt_seconds"])
    nhis = int(t["output_interval_hours"] * 3600 / t["pilot_dt_seconds"])
    print("[time]")
    print(f"period_seconds={int(seconds)}")
    print(f"pilot_DT_seconds={t['pilot_dt_seconds']}")
    print(f"pilot_NTIMES={ntimes}")
    print(f"pilot_NHIS_NAVG={nhis}")
    print("[source]")
    print(f"annual_release_Bq={annual_bq:.6e}")
    print(f"release_Bq_s={bq_per_s:.6f}")
    print(f"period_release_Bq={period_bq:.6e}")


if __name__ == "__main__":
    main()
