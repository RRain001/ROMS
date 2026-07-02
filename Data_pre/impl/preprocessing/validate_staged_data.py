#!/usr/bin/env python3
"""Validate staged external data for the active ROMS case.

This script does not download data and does not modify raw inputs. It checks
whether the files needed for a scientific run have been staged under data/raw.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from netCDF4 import Dataset

from case_context import get_case_config_path, get_case_root
from case_naming import load_case_naming
from ocean_source_utils import build_glorys_paths, load_glorys_config, normalize_ocean_source

ROOT = get_case_root()
DEFAULT_MANIFEST = get_case_config_path("staged_data_manifest.csv")


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


def glorys_requirements(config_path: str | None) -> list[Requirement]:
    config = load_glorys_config(config_path)
    paths = build_glorys_paths(config)
    return [
        Requirement("ocean_static", True, paths.staged_static, list(config["static_variables"]), "GLORYS12V1 static subset"),
        Requirement("ocean_initial", True, paths.staged_initial, list(config["variables_3d"]) + list(config["variables_2d"]), "GLORYS12V1 staged initial subset"),
        Requirement("ocean_boundary", True, paths.staged_boundary, list(config["variables_3d"]) + list(config["variables_2d"]), "GLORYS12V1 staged boundary subset"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--ocean-source", default="hycom")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    ocean_source = normalize_ocean_source(args.ocean_source)
    if ocean_source == "hycom":
        manifest = Path(args.manifest)
        if not manifest.exists():
            raise SystemExit(f"manifest not found: {manifest}")
        requirements = read_manifest(manifest)
    else:
        manifest = None
        requirements = glorys_requirements(args.config)
    required_missing = 0
    optional_missing = 0

    print(f"{load_case_naming().title} staged data validation")
    print(f"ocean_source: {ocean_source}")
    if manifest is not None:
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
