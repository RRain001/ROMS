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
from case_naming import load_case_naming, staged_atmosphere_name, staged_ocean_name, staged_source_csv_name, staged_tides_name
from formal_online_workflow import load_formal_online_workflow
from ocean_source_utils import build_glorys_paths, load_glorys_config, normalize_ocean_source
from roms_preprocessing_utils import load_project_params
from staged_data_utils import config_path_to_abs, load_download_config

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


def hycom_requirements(config_path: str | None) -> list[Requirement]:
    config = load_download_config(config_path)
    paths_cfg = config.get("paths", {})

    def configured_or_default(key: str, default_rel: str) -> Path:
        if key in paths_cfg:
            return config_path_to_abs(config, key)
        return ROOT / default_rel

    return [
        Requirement(
            "bathymetry",
            True,
            ROOT / "data" / "raw" / "bathymetry" / load_case_naming().grid_subset_name,
            ["lon", "lat", "elevation"],
            "GEBCO-style elevation, positive land and negative ocean",
        ),
        Requirement(
            "ocean_initial",
            True,
            configured_or_default("ocean_initial", f"data/raw/ocean/{staged_ocean_name('hycom', 'initial')}"),
            ["zeta", "u", "v", "temp", "salt"],
            "HYCOM-like source data before ROMS interpolation",
        ),
        Requirement(
            "ocean_boundary",
            True,
            configured_or_default("ocean_boundary", f"data/raw/ocean/{staged_ocean_name('hycom', 'boundary')}"),
            ["zeta", "u", "v", "temp", "salt"],
            "Open-boundary source data covering the active case window",
        ),
        Requirement(
            "atmosphere",
            True,
            configured_or_default("era5_atm", f"data/raw/atmosphere/{staged_atmosphere_name('atm')}"),
            ["Uwind", "Vwind", "Pair", "Tair", "Qair", "rain"],
            "ERA5 atmospheric forcing source or preprocessed ROMS forcing",
        ),
        Requirement(
            "radiation",
            True,
            configured_or_default("era5_rad", f"data/raw/atmosphere/{staged_atmosphere_name('rad')}"),
            ["swrad", "lwrad", "lwrad_down"],
            "Radiation forcing source or preprocessed ROMS forcing",
        ),
        Requirement(
            "tides",
            True,
            configured_or_default("tides", f"data/raw/tides/{staged_tides_name()}"),
            ["tide_period", "tide_Eamp", "tide_Ephase"],
            "TPXO-derived staged tidal elevation amplitudes/phases",
        ),
        Requirement(
            "source_discharge",
            True,
            configured_or_default("source_discharge", f"data/raw/source/{staged_source_csv_name()}"),
            ["time", "discharge_m3_s", "scenario"],
            "Numerical carrier discharge for converting annual release to Bq/m3",
        ),
    ]


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


def check_tide_metadata(path: Path) -> list[str]:
    if not path.exists():
        return []
    issues: list[str] = []
    with Dataset(path) as ds:
        for name in ("phase_convention", "source_phase_reference", "source_reference_date", "v0_handling", "nodal_correction", "phase_reconstruction"):
            if not getattr(ds, name, ""):
                issues.append(f"missing tidal metadata: {name}")
    return issues


def glorys_requirements(config_path: str | None) -> list[Requirement]:
    config = load_glorys_config(config_path)
    params = load_project_params()
    formal_cfg = params.get("formal_online_workflow", {})
    continuous = bool(formal_cfg.get("enabled") and formal_cfg.get("mode") == "continuous")
    workflow = load_formal_online_workflow(params) if continuous else None
    paths = build_glorys_paths(
        config,
        start=workflow.spinup_start if workflow else None,
        stop=workflow.production_end if workflow else None,
    )
    if continuous and workflow:
        atmosphere_start = workflow.spinup_start
        atmosphere_stop = workflow.production_end
        tides_path = ROOT / "data" / "raw" / "tides" / "tpxo9_fdnpp_continuous.nc"
    else:
        atmosphere_start = atmosphere_stop = None
        tides_path = ROOT / "data" / "raw" / "tides" / staged_tides_name()
    tide_variables = ["tide_period", "tide_Eamp", "tide_Ephase"]
    if bool(params.get("tides", {}).get("uv_tides", False)):
        tide_variables.extend(["tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase"])
    if continuous:
        tide_variables.extend(["tide_ERe", "tide_EIm", "tide_URe", "tide_UIm", "tide_VRe", "tide_VIm"])
    return [
        Requirement("ocean_static", True, paths.staged_static, list(config["static_variables"]), "GLORYS12V1 static subset"),
        Requirement("ocean_initial", True, paths.staged_initial, list(config["variables_3d"]) + list(config["variables_2d"]), "GLORYS12V1 staged initial subset"),
        Requirement("ocean_boundary", True, paths.staged_boundary, list(config["variables_3d"]) + list(config["variables_2d"]), "GLORYS12V1 staged boundary subset"),
        Requirement("atmosphere", True, ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("atm", start=atmosphere_start, stop=atmosphere_stop), ["Uwind", "Vwind", "Pair", "Tair", "Qair", "rain"], "ERA5 atmosphere covering the continuous window"),
        Requirement("radiation", True, ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("rad", start=atmosphere_start, stop=atmosphere_stop), ["swrad", "lwrad", "lwrad_down"], "ERA5 radiation covering the continuous window"),
        Requirement("tides", True, tides_path, tide_variables, "TPXO complex constants and derived ROMS tide fields"),
        Requirement("source_discharge", True, ROOT / "data" / "raw" / "source" / staged_source_csv_name(), ["time", "discharge_m3_s", "scenario"], "Numerical carrier discharge for converting annual release to Bq/m3"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=None, help="Optional legacy manifest override")
    parser.add_argument("--ocean-source", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    ocean_source = normalize_ocean_source(args.ocean_source)
    if ocean_source == "hycom":
        manifest = Path(args.manifest) if args.manifest else None
        if manifest is not None:
            if not manifest.exists():
                raise SystemExit(f"manifest not found: {manifest}")
            requirements = read_manifest(manifest)
        else:
            requirements = hycom_requirements(args.config)
    else:
        manifest = None
        requirements = glorys_requirements(args.config)
    required_missing = 0
    optional_missing = 0

    print(f"{load_case_naming().title} staged data validation")
    print(f"ocean_source: {ocean_source}")
    if ocean_source == "hycom" and manifest is None:
        print("requirements: generated from staged_download_config.json and case naming")
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
        if item.category == "tides" and item.path.name == "tpxo9_fdnpp_continuous.nc":
            for msg in check_tide_metadata(item.path):
                print(f"  - {msg}")
                if item.required:
                    required_missing += 1
        print()

    print("summary:")
    print(f"  required_missing={required_missing}")
    print(f"  optional_missing={optional_missing}")
    if required_missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
