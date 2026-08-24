#!/usr/bin/env python3
"""Run the LAHAGUE data and ROMS-ready preparation chain with resumable stages."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from case_context import get_case_root


REPO_ROOT = Path(os.environ["ROMS_DATA_PRE_ROOT"]).resolve().parent
CASE_ROOT = get_case_root()
STATUS_DIR = CASE_ROOT / "logs" / "data_stage"
CONTINUOUS_START = "2024-10-01T00:00:00"
CONTINUOUS_STOP = "2026-01-01T00:00:00"
PROFILE = "online_my25_uvtide"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="reuse completed stage markers and downloader caches")
    parser.add_argument("--from-stage", default=None, help="start at this stage name")
    parser.add_argument("--list-stages", action="store_true")
    return parser.parse_args()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_script(relative: str) -> str:
    return str(REPO_ROOT / "Data_pre" / "scripts" / relative)


def stage_commands() -> list[tuple[str, list[str], list[Path]]]:
    data_root = CASE_ROOT / "data" / "raw"
    input_root = CASE_ROOT / "input"
    return [
        (
            "source_continuous",
            [
                sys.executable,
                public_script("source/create_river_source_production.py"),
                "--case-name",
                "LAHAGUE",
                "--formal-continuous",
                "--profile",
                PROFILE,
            ],
            [input_root / "roms_rivers_lahague_online_continuous_my25_uvtide.nc"],
        ),
        (
            "glorys_continuous",
            [
                sys.executable,
                public_script("ocean/download_glorys12v1_staged.py"),
                "--case-name",
                "LAHAGUE",
                "--start",
                CONTINUOUS_START,
                "--stop",
                CONTINUOUS_STOP,
                "--mode",
                "both",
                "--resume",
            ],
            [data_root / "ocean" / "glorys12v1" / "glorys12v1_static_lahague.nc", data_root / "ocean" / "glorys12v1" / "glorys12v1_initial_20241001.nc", data_root / "ocean" / "glorys12v1" / "glorys12v1_boundary_20241001_20260101.nc"],
        ),
        (
            "era5_continuous",
            [
                sys.executable,
                public_script("atmosphere/download_era5_staged.py"),
                "--case-name",
                "LAHAGUE",
                "--start",
                CONTINUOUS_START,
                "--stop",
                CONTINUOUS_STOP,
                "--atm-output",
                str(data_root / "atmosphere" / "era5_atm_lahague_20241001_20260101.nc"),
                "--rad-output",
                str(data_root / "atmosphere" / "era5_rad_lahague_20241001_20260101.nc"),
            ],
            [data_root / "atmosphere" / "era5_atm_lahague_20241001_20260101.nc", data_root / "atmosphere" / "era5_rad_lahague_20241001_20260101.nc"],
        ),
        (
            "tpxo",
            [
                sys.executable,
                public_script("tides/stage_tpxo_elevation_atlas.py"),
                "--case-name",
                "LAHAGUE",
                "--include-uv",
                "--output",
                str(data_root / "tides" / "tpxo9_lahague_20241001_20260101.nc"),
            ],
            [data_root / "tides" / "tpxo9_lahague_20241001_20260101.nc"],
        ),
        (
            "ocean_ready_continuous",
            [
                sys.executable,
                public_script("ocean/create_ocean_ini_from_glorys.py"),
                "--case-name",
                "LAHAGUE",
                "--profile",
                PROFILE,
                "--time",
                CONTINUOUS_START,
                "--src",
                str(data_root / "ocean" / "glorys12v1" / "glorys12v1_initial_20241001.nc"),
                "--output",
                str(input_root / "roms_ini_lahague_glorys12v1_20241001_online_my25_uvtide.nc"),
            ],
            [input_root / "roms_ini_lahague_glorys12v1_20241001_online_my25_uvtide.nc"],
        ),
        (
            "boundary_ready_continuous",
            [
                sys.executable,
                public_script("ocean/create_ocean_bry_from_glorys.py"),
                "--case-name",
                "LAHAGUE",
                "--profile",
                PROFILE,
                "--start",
                CONTINUOUS_START,
                "--stop",
                CONTINUOUS_STOP,
                "--src",
                str(data_root / "ocean" / "glorys12v1" / "glorys12v1_boundary_20241001_20260101.nc"),
                "--output",
                str(input_root / "roms_bdy_lahague_glorys12v1_20241001_20260101_online_my25_uvtide.nc"),
            ],
            [input_root / "roms_bdy_lahague_glorys12v1_20241001_20260101_online_my25_uvtide.nc"],
        ),
        (
            "atmosphere_ready_continuous",
            [sys.executable, public_script("atmosphere/create_atm_forcing_from_era5.py"), "--case-name", "LAHAGUE", "--src", str(data_root / "atmosphere" / "era5_atm_lahague_20241001_20260101.nc"), "--output", str(input_root / "roms_atm_lahague_20241001_20260101.nc")],
            [input_root / "roms_atm_lahague_20241001_20260101.nc"],
        ),
        (
            "radiation_ready_continuous",
            [sys.executable, public_script("atmosphere/create_rad_forcing_from_era5.py"), "--case-name", "LAHAGUE", "--src", str(data_root / "atmosphere" / "era5_rad_lahague_20241001_20260101.nc"), "--output", str(input_root / "roms_rad_lahague_20241001_20260101.nc")],
            [input_root / "roms_rad_lahague_20241001_20260101.nc"],
        ),
        (
            "tides_ready_continuous",
            [sys.executable, public_script("tides/create_tides_from_tpxo.py"), "--case-name", "LAHAGUE", "--src", str(data_root / "tides" / "tpxo9_lahague_20241001_20260101.nc"), "--profile", PROFILE, "--require-uv", "--output", str(input_root / "roms_tides_lahague_online_my25_uvtide.nc")],
            [input_root / "roms_tides_lahague_online_my25_uvtide.nc"],
        ),
        (
            "run_inputs_continuous",
            [
                sys.executable,
                public_script("run_support/create_pilot_infile.py"),
                "--case-name",
                "LAHAGUE",
                "--ocean-source",
                "glorys12v1",
                "--forcing-mode",
                "external",
                "--mode",
                "online_continuous_my25_uvtide",
            ],
            [CASE_ROOT / "run" / "ocean_lahague_online_continuous_my25_uvtide_glorys12v1.in"],
        ),
    ]


def load_status() -> dict[str, Any]:
    path = STATUS_DIR / "status.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return {"case_name": "LAHAGUE", "pid": os.getpid(), "started_at": now(), "stages": {}}


def write_status(status: dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_DIR / "status.json.tmp"
    tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(STATUS_DIR / "status.json")


def run_stage(status: dict[str, Any], name: str, command: list[str], outputs: list[Path], resume: bool) -> bool:
    marker_done = STATUS_DIR / f"{name}.done"
    marker_failed = STATUS_DIR / f"{name}.failed"
    log_path = STATUS_DIR / f"{name}.log"
    entry = status["stages"].setdefault(name, {})
    if resume and marker_done.exists() and all(path.exists() and path.stat().st_size > 0 for path in outputs):
        entry.update({"status": "skipped", "reason": "completed marker and outputs exist", "checked_at": now()})
        write_status(status)
        return True

    marker_done.unlink(missing_ok=True)
    marker_failed.unlink(missing_ok=True)
    entry.update({"status": "running", "started_at": now(), "command": command, "log": str(log_path)})
    write_status(status)
    with log_path.open("w") as log:
        log.write(f"started_at={entry['started_at']}\n")
        log.write("command=" + " ".join(command) + "\n\n")
        result = subprocess.run(command, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        log.write(f"\nexit_code={result.returncode}\n")
    if result.returncode == 0 and all(path.exists() and path.stat().st_size > 0 for path in outputs):
        marker_done.write_text(now() + "\n")
        entry.update({"status": "done", "finished_at": now(), "returncode": 0, "outputs": [str(path) for path in outputs]})
        write_status(status)
        return True
    marker_failed.write_text(now() + "\n")
    entry.update({"status": "failed", "finished_at": now(), "returncode": result.returncode, "outputs": [str(path) for path in outputs]})
    write_status(status)
    return False


def main() -> None:
    args = parse_args()
    commands = stage_commands()
    if args.list_stages:
        for name, _, _ in commands:
            print(name)
        return
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (STATUS_DIR / "pid").write_text(f"{os.getpid()}\n")
    status = load_status()
    status.update({"case_name": "LAHAGUE", "pid": os.getpid(), "repo_root": str(REPO_ROOT), "case_root": str(CASE_ROOT), "last_update": now()})
    write_status(status)

    active = args.from_stage is None
    for name, command, outputs in commands:
        if not active and name == args.from_stage:
            active = True
        if not active:
            continue
        if not run_stage(status, name, command, outputs, resume=args.resume):
            status.update({"status": "failed", "finished_at": now(), "failed_stage": name})
            write_status(status)
            raise SystemExit(1)
    status.update({"status": "done", "finished_at": now()})
    status.pop("failed_stage", None)
    write_status(status)
    (STATUS_DIR / "pipeline.done").write_text(now() + "\n")
    print(f"LAHAGUE data stage completed; status={STATUS_DIR / 'status.json'}")


if __name__ == "__main__":
    main()
