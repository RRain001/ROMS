#!/usr/bin/env python3
"""Audit an actual case binary, its compiled CPP branches and its libraries.

Every run mode declared in ``roms_run_config.json`` is checked.  An earlier
revision hardcoded ``external_startup`` and reported one verdict for five
modes, and derived the compiled header name from a literal string.

Nothing here launches ROMS or constructs missing runtime forcing.  The tide
report is explicitly *build* evidence: generated-source signatures and compiled
CPP options are not tidal-dynamics acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from build_context import probe_shell_command, resolve_build_context  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ROMS_Run" / "core"))
from run_context import (  # noqa: E402
    parse_infile_metadata,
    resolve_binary_path,
    resolve_run_context,
    validate_tide_build_artifacts,
)

#: Compiling any of these means the case is not the frozen single-grid app.
FORBIDDEN_CPP = ("ANA_GRID", "ANA_INITIAL", "ANA_SMFLUX", "ANA_STFLUX", "NESTING")

#: Checked through generated tide sources, not through the compiled list alone.
TIDE_SIGNATURE_CPP = "TIDES_DATE"


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compiled_cpp_options(checkdefs_text: str) -> list[str]:
    return sorted(set(re.findall(r"Coptions[^=]*='\s*([A-Z_0-9]+),", checkdefs_text)))


def compiled_string(mod_strings_text: str, name: str) -> str | None:
    match = re.search(rf'{re.escape(name)}\s*=\s*"([^"]*)"', mod_strings_text)
    return match.group(1) if match else None


def mode_names(context) -> list[str]:
    run_config_path = context.config_dir / "roms_run_config.json"
    if not run_config_path.is_file():
        return []
    return list(json.loads(run_config_path.read_text()).get("run_modes", {}))


def declared_executables(config_dir: Path) -> dict[str, str]:
    """Map every executable a case build config declares to the config naming it.

    The case ships a paired debug/release build, so a mode's binary is checked
    against the set of declared executables rather than against one variant.
    """
    mapping: dict[str, str] = {}
    for path in sorted(config_dir.glob("roms_build_config*.json")):
        data = json.loads(path.read_text())
        for variant in data.get("variants", {}).values():
            name = variant.get("executable_name")
            if name:
                mapping.setdefault(str(name), path.name)
    return mapping


def verify_mode(context, mode_name: str, active_cpp: set[str], app_name: str) -> dict:
    """Per-mode verdict: CPP requirements, tiling, .in identity and binary."""
    run = resolve_run_context(case_name=context.case_name, mode=mode_name)
    issues: list[str] = []

    required = set(run.mode.required_cpp_defs)
    signature_cpp = sorted(required & {TIDE_SIGNATURE_CPP})
    for option in sorted(required - {TIDE_SIGNATURE_CPP}):
        if option not in active_cpp:
            issues.append(f"compiled CPP option missing: {option}")
    for option in sorted(set(FORBIDDEN_CPP) & active_cpp):
        issues.append(f"forbidden compiled CPP: {option}")

    if run.mode.build_variant != context.variant.name:
        issues.append(
            f"mode build_variant={run.mode.build_variant} does not match audited variant {context.variant.name}"
        )
    declared = declared_executables(context.config_dir)
    serving_config = declared.get(run.mode.binary_name)
    if serving_config is None:
        issues.append(
            f"mode binary={run.mode.binary_name} is not declared by any case build config "
            f"(known: {', '.join(sorted(declared)) or 'none'})"
        )

    binary = resolve_binary_path(run)
    if binary is None:
        issues.append(f"missing executable {run.mode.binary_name}")
    elif not binary.is_file():
        issues.append(f"executable is not a file: {binary}")

    tiles = None
    if not run.mode.infile.is_file():
        issues.append(f"missing run input file: {run.mode.infile}")
    else:
        metadata = parse_infile_metadata(run.mode.infile)
        tiles = metadata.required_np
        if metadata.my_app_cpp != app_name:
            issues.append(f"MyAppCPP mismatch: infile={metadata.my_app_cpp}, variant={app_name}")
        if tiles is not None and tiles != run.mode.np:
            issues.append(f"parallel mismatch: NtileI*NtileJ={tiles}, configured np={run.mode.np}")

    return {
        "mode": mode_name,
        "infile": str(run.mode.infile),
        "binary": str(binary) if binary else None,
        "binary_name": run.mode.binary_name,
        "served_by_build_config": serving_config,
        "build_variant": run.mode.build_variant,
        "np": run.mode.np,
        "tiles": tiles,
        "required_cpp_defs": sorted(required),
        "tide_signature_cpp": signature_cpp,
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-name", required=True)
    parser.add_argument(
        "--config",
        default=None,
        help="Build config to audit (default roms_build_config.json). The case ships a "
             "paired debug/release build, so run this once per config.",
    )
    args = parser.parse_args()

    context = resolve_build_context(case_name=args.case_name, config_path=args.config)
    log_dir = context.case_root / "logs" / "external_test"
    log_dir.mkdir(parents=True, exist_ok=True)

    issues: list[str] = []
    binary = context.expected_binary
    if not binary.is_file():
        raise SystemExit(f"case executable missing: {binary}")

    build_dir = context.paths.build_dir
    checkdefs_path = build_dir / "checkdefs.f90"
    strings_path = build_dir / "mod_strings.f90"
    active_cpp = set(compiled_cpp_options(checkdefs_path.read_text()))
    strings_text = strings_path.read_text()

    header_name = context.variant.header_name
    app_name = context.variant.roms_application
    fort_name = str(context.compiler.get("fort", ""))
    use_debug = bool(context.compiler.get("use_debug", False))

    for name, expected in (("my_fort", fort_name), ("Hfile", header_name)):
        actual = compiled_string(strings_text, name)
        if actual != expected:
            issues.append(f"compiled identity mismatch: {name}={actual!r}, expected {expected!r}")

    if binary.stat().st_mtime < checkdefs_path.stat().st_mtime:
        issues.append("binary older than compiled CPP source")

    names = mode_names(context)
    if not names:
        issues.append("no run modes declared in roms_run_config.json")
    # Tide evidence is build evidence only, and is collected exactly once.
    tide_issues = (
        validate_tide_build_artifacts(
            resolve_run_context(case_name=context.case_name, mode=names[0]), binary
        )
        if names
        else []
    )

    command = ("otool -L" if sys.platform == "darwin" else "ldd") + " " + shlex.quote(str(binary))
    linked = probe_shell_command(context, command)
    (log_dir / "binary_links.log").write_text(linked.stdout + linked.stderr)
    if linked.returncode or "not found" in linked.stdout:
        issues.append("unresolved dynamic library")
    for name in ("libnetcdf", "libnetcdff", "libmpi"):
        if name not in linked.stdout:
            issues.append("dynamic dependency absent: " + name)
    if context.compiler.get("which_mpi") == "intel":
        if "openmpi" in linked.stdout.lower() or "libmpi.so.40" in linked.stdout:
            issues.append("OpenMPI unexpectedly linked into Intel application")
        for name, prefix in (
            ("libnetcdf", context.netcdf_root),
            ("libnetcdff", context.netcdf_root),
            ("libmpi", context.mpi_root),
        ):
            if prefix and not any(name in line and str(prefix) in line for line in linked.stdout.splitlines()):
                issues.append("dependency resolved outside configured prefix: " + name)

    versions = probe_shell_command(
        context,
        f'{context.compiler["fort"]} --version\nmpirun --version\n"$NF_CONFIG" --version\n"$NC_CONFIG" --version',
    )
    (log_dir / "compiler_versions.log").write_text(versions.stdout + versions.stderr)

    netcdf4_output = "CMODE = nf90_netcdf4" in (build_dir / "mod_netcdf.f90").read_text()

    # TIDES_DATE is not enumerated in checkdefs.f90's Coptions list (ROMS only
    # lists a subset), so its evidence is the header macro plus the generated
    # and compiled source.  These are build facts, not tidal-dynamics checks.
    header_text = context.variant.header_path.read_text(errors="ignore")
    tides_date_defined = bool(
        re.search(rf"^\s*#\s*define\s+{TIDE_SIGNATURE_CPP}(?:\s|$)", header_text, flags=re.MULTILINE)
    )
    tides_date_source = build_dir / "tides_date.f90"
    tides_date_object = build_dir / "tides_date.o"
    if not tides_date_defined:
        issues.append(f"{TIDE_SIGNATURE_CPP} is not defined in {context.variant.header_path.name}")
    if not tides_date_source.is_file():
        issues.append("generated tide source is missing: tides_date.f90")
    if not tides_date_object.is_file():
        issues.append("generated tide object is missing: tides_date.o")

    mode_verdicts = [verify_mode(context, name, active_cpp, app_name) for name in names]
    for entry in mode_verdicts:
        issues.extend(f"{entry['mode']}: {item}" for item in entry["issues"])
    if not netcdf4_output:
        issues.append("NetCDF4/HDF5 output branch not compiled")

    report = {
        "status": "CASE_BINARY_AND_CPP_LINK_PASS" if not issues else "FAIL",
        "issues": issues,
        "case": args.case_name,
        "application": app_name,
        "build_kind": "debug" if use_debug else "release",
        "use_debug": use_debug,
        "use_parallel_io": bool(context.compiler.get("use_parallel_io", False)),
        "use_netcdf4": bool(context.compiler.get("use_netcdf4", False)),
        "io_policy": context.build_config.get("io_policy"),
        "fflags": compiled_string(strings_text, "my_fflags"),
        "compiler_fort": fort_name,
        "which_mpi": context.compiler.get("which_mpi"),
        "binary": str(binary),
        "binary_bytes": binary.stat().st_size,
        "binary_sha256": fingerprint(binary),
        "header_name": header_name,
        "header_sha256": fingerprint(context.variant.header_path),
        "compiled_checkdefs_sha256": fingerprint(checkdefs_path),
        "build_config_sha256": fingerprint(context.build_config_path),
        "compiled_options": sorted(active_cpp),
        "forbidden_options_present": sorted(set(FORBIDDEN_CPP) & active_cpp),
        "tides_date_evidence": {
            "cpp_in_checkdefs_list": TIDE_SIGNATURE_CPP in active_cpp,
            "defined_in_header": tides_date_defined,
            "source_generated": tides_date_source.is_file(),
            "object_compiled": tides_date_object.is_file(),
            "note": "build evidence only; not tidal-dynamics acceptance",
        },
        "tide_build_issues": tide_issues,
        "NetCDF4_output_compiled": netcdf4_output,
        "mode_verdicts": mode_verdicts,
        "versions": versions.stdout + versions.stderr,
        "dynamic_links": linked.stdout,
        "ROMS_started": False,
        "physical_acceptance": "NOT_RUN",
    }
    (log_dir / "build_verification.json").write_text(json.dumps(report, indent=2) + "\n")

    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "issues",
                    "application",
                    "build_kind",
                    "use_debug",
                    "binary",
                    "binary_bytes",
                    "binary_sha256",
                    "tides_date_evidence",
                    "NetCDF4_output_compiled",
                    "ROMS_started",
                )
            },
            indent=2,
        )
    )
    print("mode verdicts:")
    for entry in mode_verdicts:
        print(
            f"  {entry['mode']:20s} {entry['status']}  tiles={entry['tiles']} np={entry['np']} "
            f"binary={entry['binary_name']} ({entry['served_by_build_config']})"
        )
    raise SystemExit(int(bool(issues)))


if __name__ == "__main__":
    main()
