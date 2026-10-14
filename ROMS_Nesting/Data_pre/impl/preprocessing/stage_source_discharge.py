#!/usr/bin/env python3
"""Normalize a user-supplied discharge CSV into the staged raw layout."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path

from roms_preprocessing_utils import load_project_params
from staged_data_utils import config_path_to_abs, ensure_parent, get_time_window, load_download_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--src", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--time-column", default="time")
    parser.add_argument("--discharge-column", default="discharge_m3_s")
    parser.add_argument("--scenario-column", default="scenario")
    parser.add_argument("--allow-scenario-baseline", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_download_config(args.config)
    window = get_time_window(config)
    out = Path(args.output) if args.output else config_path_to_abs(config, "source_discharge")
    rows: list[dict[str, str]] = []
    source_label = "derived_release_carrier"
    if args.src:
        src = Path(args.src)
        if not src.exists():
            raise SystemExit(f"source discharge CSV not found: {src}")
        with src.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if args.time_column not in reader.fieldnames or args.discharge_column not in reader.fieldnames:
                raise SystemExit(
                    f"source CSV must contain {args.time_column!r} and {args.discharge_column!r} columns"
                )
            for row in reader:
                timestamp = datetime.fromisoformat(row[args.time_column])
                discharge = float(row[args.discharge_column])
                if discharge <= 0.0:
                    raise SystemExit("all discharge_m3_s values must be positive")
                scenario = (row.get(args.scenario_column) or "").strip()
                if scenario.lower() == "scenario_baseline" and not args.allow_scenario_baseline:
                    raise SystemExit("scenario_baseline is not allowed for real staged discharge data")
                rows.append(
                    {
                        "time": timestamp.isoformat(),
                        "discharge_m3_s": f"{discharge:.12g}",
                        "scenario": scenario,
                    }
                )
        source_label = str(src)
    else:
        params = load_project_params()
        discharge = float(params["source"]["nominal_discharge_m3_s"])
        scenario = "derived_release_carrier"
        cursor = window.start
        while cursor <= window.stop:
            rows.append(
                {
                    "time": cursor.isoformat(),
                    "discharge_m3_s": f"{discharge:.12g}",
                    "scenario": scenario,
                }
            )
            cursor += timedelta(hours=1)

    if not rows:
        raise SystemExit("source discharge CSV has no data rows")

    first_time = datetime.fromisoformat(rows[0]["time"])
    last_time = datetime.fromisoformat(rows[-1]["time"])
    if first_time > window.start or last_time < window.stop:
        raise SystemExit(
            f"discharge time coverage {first_time.isoformat()} to {last_time.isoformat()} "
            f"does not cover required window {window.start.isoformat()} to {window.stop.isoformat()}"
        )

    ensure_parent(out)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "discharge_m3_s", "scenario"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"source={source_label}")
    print(f"output={out}")
    print(f"records={len(rows)}")
    if not args.src:
        print("mode=derived_release_carrier")


if __name__ == "__main__":
    main()
