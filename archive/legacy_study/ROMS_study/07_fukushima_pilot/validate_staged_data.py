#!/usr/bin/env python3
"""Validate staged external data for the Fukushima ROMS project.

This script does not download data and does not modify raw inputs. It checks
whether the files needed for a scientific run have been staged under data/raw.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from netCDF4 import Dataset


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config" / "staged_data_manifest.csv"


@dataclass(frozen=True)
class Requirement:
    category: str
    required: bool
    path: Path
    variables: list[str]
    note: str


def read_manifest(path: Path) -> list[Requirement]:
    rows: list[Requirement] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rel = Path(row["path"])
            rows.append(
                Requirement(
                    category=row["category"],
                    required=row["required"].strip().lower() in {"1", "true", "yes", "required"},
                    path=ROOT / rel,
                    variables=[v for v in row["variables"].split() if v],
                    note=row.get("note", ""),
                )
            )
    return rows


def check_netcdf(path: Path, variables: list[str]) -> tuple[bool, list[str]]:
    if not path.exists():
        return False, [f"missing file: {path}"]
    if path.suffix.lower() not in {".nc", ".cdf", ".netcdf"}:
        return True, ["exists; variable check skipped for non-NetCDF file"]
    problems: list[str] = []
    try:
        with Dataset(path) as ds:
            available = set(ds.variables)
            for var in variables:
                if var not in available:
                    problems.append(f"missing variable: {var}")
    except Exception as exc:  # noqa: BLE001 - report validation failure, do not hide it.
        return False, [f"cannot open NetCDF: {type(exc).__name__}: {exc}"]
    return not problems, problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise SystemExit(f"manifest not found: {manifest}")

    requirements = read_manifest(manifest)
    required_missing = 0
    optional_missing = 0

    print("Fukushima staged data validation")
    print(f"manifest: {manifest}")
    print()
    for item in requirements:
        ok, messages = check_netcdf(item.path, item.variables)
        status = "OK" if ok else ("MISSING_REQUIRED" if item.required else "MISSING_OPTIONAL")
        if not ok and item.required:
            required_missing += 1
        if not ok and not item.required:
            optional_missing += 1
        print(f"[{status}] {item.category}: {item.path.relative_to(ROOT)}")
        if item.variables:
            print(f"  expected variables: {' '.join(item.variables)}")
        if item.note:
            print(f"  note: {item.note}")
        for msg in messages:
            print(f"  - {msg}")
        print()

    print("summary:")
    print(f"  required_missing={required_missing}")
    print(f"  optional_missing={optional_missing}")
    if required_missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
