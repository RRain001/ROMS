#!/usr/bin/env python3
"""Create hourly source activity time series for the active case."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from case_context import get_case_config_path, get_case_root
from case_naming import load_case_naming
from pilot_grid_utils import locate_source_on_grid, resolve_active_pilot_grid


ROOT = get_case_root()
PARAMS = get_case_config_path("project_parameters.json")
OUT = ROOT / "input" / load_case_naming().source_timeseries_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", default=None)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--profile", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    p = json.loads(PARAMS.read_text())
    d = p["domain"]
    s = p["source"]
    t = p["time"]
    grid_path = resolve_active_pilot_grid(args.grid)
    out_path = Path(args.output)
    if args.profile and args.output == str(OUT):
        out_path = out_path.with_name(f"{out_path.stem}_{args.profile}{out_path.suffix}")
    placement = locate_source_on_grid(grid_path, d["source_lon"], d["source_lat"])

    start = datetime.fromisoformat(t["start"])
    stop = datetime.fromisoformat(t["stop"])
    step = timedelta(hours=t["source_interval_hours"])
    annual_bq = s["annual_release_TBq_per_year"] * 1e12
    bq_s = annual_bq / (s["calendar_year_days"] * 24 * 3600)
    bq_step = bq_s * step.total_seconds()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "time_start",
                "time_end",
                "source_lon",
                "source_lat",
                "configured_source_lon",
                "configured_source_lat",
                "actual_source_lon",
                "actual_source_lat",
                "actual_source_xi",
                "actual_source_eta",
                "actual_source_depth_m",
                "source_snap_distance_m",
                "release_Bq_s",
                "release_Bq_this_step",
                "discharge_m3_s",
                "concentration_Bq_m3",
                "source_placement_rule",
                "note",
            ]
        )
        placement_note = (
            "configured point already on water cell"
            if placement.nearest_is_water
            else "configured point on land; actual source snapped to nearest water cell"
        )
        cur = start
        while cur < stop:
            nxt = cur + step
            writer.writerow(
                [
                    cur.isoformat(),
                    nxt.isoformat(),
                    f"{placement.snapped_lon:.6f}",
                    f"{placement.snapped_lat:.6f}",
                    f"{placement.configured_lon:.6f}",
                    f"{placement.configured_lat:.6f}",
                    f"{placement.snapped_lon:.6f}",
                    f"{placement.snapped_lat:.6f}",
                    str(placement.snapped_xi),
                    str(placement.snapped_eta),
                    f"{placement.snapped_depth_m:.3f}",
                    f"{placement.snapped_distance_m:.3f}",
                    f"{bq_s:.9f}",
                    f"{bq_step:.9f}",
                    "",
                    "",
                    placement.placement_rule,
                    (
                        f"{placement_note}; activity flux only; choose discharge before making "
                        "ROMS river_dye concentration"
                    ),
                ]
            )
            cur = nxt
    print(f"grid={grid_path}")
    print(
        "configured_source_lon_lat="
        f"({placement.configured_lon:.6f}, {placement.configured_lat:.6f})"
    )
    print(
        "actual_source_lon_lat="
        f"({placement.snapped_lon:.6f}, {placement.snapped_lat:.6f})"
    )
    print(f"actual_source_index_zero_based=(xi={placement.snapped_xi}, eta={placement.snapped_eta})")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
