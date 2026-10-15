#!/usr/bin/env python3
"""Audit an actual case binary, its compiled CPP branches and its libraries.

Every run mode declared in ``roms_run_config.json`` is checked.  A mode is only
claimed PASS by the build that actually produced its executable: the case ships
a paired debug/release build, so a mode served by the other build is reported as
``NOT_CHECKED_IN_THIS_BUILD`` rather than being waved through with this build's
CPP list.  Run this once per build config to cover all five modes.

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

#: Verdict for a mode whose executable belongs to a build that was not audited.
NOT_CHECKED = "NOT_CHECKED_IN_THIS_BUILD"


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
    """Map every executable a case build config declares to the config naming it."""
    mapping: dict[str, str] = {}
    for path in sorted(config_dir.glob("roms_build_config*.json")):
        data = json.loads(path.read_text())
        for variant in data.get("variants", {}).values():
            name = variant.get("executable_name")
            if name:
                mapping.setdefault(str(name), path.name)
    return mapping


def latest_provenance(case_root: Path, config_name: str) -> dict | None:
    """The most recent provenance record written by a build of ``config_name``.

    The audit ties the executable to the build that produced it through this
    record.  Re-fingerprinting the very file under audit proves nothing on its
    own -- a swapped or hand-edited binary fingerprints consistently with itself.
    """
    directory = case_root / "logs" / "build_provenance"
    if not directory.is_dir():
        return None
    records: list[dict] = []
    for path in sorted(directory.glob(f"*_{Path(config_name).stem}_*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    return records[-1] if records else None


def _git_state(root: Path) -> dict:
    import subprocess

    def run(*argv: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *argv], capture_output=True, text=True, check=False
            )
        except OSError:
            return None
        return (result.stdout or "").strip() or None

    head = run("rev-parse", "HEAD")
    if head is None:
        return {"path": str(root), "head": None, "dirty": None}
    status = run("status", "--porcelain")
    return {"path": str(root), "head": head, "dirty": bool(status)}


def verify_mode(
    context,
    mode_name: str,
    active_cpp: set[str],
    app_name: str,
    audited_config_name: str,
    expected_sha: str | None,
) -> dict:
    """Per-mode verdict, scoped to what the audited build can actually prove."""
    run = resolve_run_context(
        case_name=context.case_name, case_root=context.case_root, mode=mode_name
    )
    issues: list[str] = []

    required = set(run.mode.required_cpp_defs)
    signature_cpp = sorted(required & {TIDE_SIGNATURE_CPP})

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

    in_this_build = serving_config is not None and serving_config == audited_config_name
    if in_this_build:
        for option in sorted(required - {TIDE_SIGNATURE_CPP}):
            if option not in active_cpp:
                issues.append(f"compiled CPP option missing: {option}")
        for option in sorted(set(FORBIDDEN_CPP) & active_cpp):
            issues.append(f"forbidden compiled CPP: {option}")
        if binary is not None and binary.is_file() and expected_sha is not None:
            actual = fingerprint(binary)
            if actual != expected_sha:
                issues.append(
                    f"mode executable {binary.name} sha256 {actual[:12]} is not the artifact this "
                    f"{audited_config_name} build recorded ({expected_sha[:12]})"
                )

    if issues:
        status = "FAIL"
    elif in_this_build:
        status = "PASS"
    else:
        status = NOT_CHECKED

    return {
        "mode": mode_name,
        "infile": str(run.mode.infile),
        "binary": str(binary) if binary else None,
        "binary_name": run.mode.binary_name,
        "served_by_build_config": serving_config,
        "checked_by_this_build": in_this_build,
        "build_variant": run.mode.build_variant,
        "np": run.mode.np,
        "tiles": tiles,
        "required_cpp_defs": sorted(required),
        "tide_signature_cpp": signature_cpp,
        "status": status,
        "issues": issues,
    }


def verify_build(context, probe=probe_shell_command) -> dict:
    """Audit one built configuration; returns the report it also writes to disk.

    ``probe`` is injected so a fault-injection test can exercise this without a
    compiler, an MPI runtime or a linked binary.
    """
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
    build_kind = "debug" if use_debug else "release"
    binary_sha = fingerprint(binary)

    # Tie the executable to the build that produced it.  A provenance record is
    # the only external reference: fingerprinting the file under audit again
    # would agree with itself no matter what the file contains.
    config_name = context.build_config_path.name
    provenance = latest_provenance(context.case_root, config_name)
    recorded_sha = provenance.get("binary_sha256") if provenance else None
    if provenance is None:
        issues.append(
            f"no build provenance recorded for {config_name}; the artifact cannot be tied to a build"
        )
    elif recorded_sha != binary_sha:
        issues.append(
            f"{binary.name} sha256 {binary_sha[:12]} does not match the provenance recorded by its "
            f"{config_name} build ({str(recorded_sha)[:12]})"
        )
    expected_sha = recorded_sha or binary_sha

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
    tide_issues: list[str] = []
    if names:
        tide_issues = list(
            validate_tide_build_artifacts(
                resolve_run_context(
                    case_name=context.case_name, case_root=context.case_root, mode=names[0]
                ),
                binary,
            )
        )
        issues.extend(tide_issues)

    command = ("otool -L" if sys.platform == "darwin" else "ldd") + " " + shlex.quote(str(binary))
    linked = probe(context, command)
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

    versions = probe(
        context,
        f'{context.compiler["fort"]} --version\nmpirun --version\n"$NF_CONFIG" --version\n"$NC_CONFIG" --version',
    )

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

    mode_verdicts = [
        verify_mode(context, name, active_cpp, app_name, config_name, expected_sha) for name in names
    ]
    for entry in mode_verdicts:
        issues.extend(f"{entry['mode']}: {item}" for item in entry["issues"])
    if not netcdf4_output:
        issues.append("NetCDF4/HDF5 output branch not compiled")

    checked = [e["mode"] for e in mode_verdicts if e["checked_by_this_build"]]
    not_checked = [e["mode"] for e in mode_verdicts if not e["checked_by_this_build"] and e["status"] != "FAIL"]

    stamp = f"{build_kind}.{binary_sha[:12]}"
    (log_dir / f"binary_links.{stamp}.log").write_text(linked.stdout + linked.stderr)
    (log_dir / f"compiler_versions.{stamp}.log").write_text(versions.stdout + versions.stderr)

    report = {
        "status": "CASE_BINARY_AND_CPP_LINK_PASS" if not issues else "FAIL",
        "issues": issues,
        "case": context.case_name,
        "application": app_name,
        "build_kind": build_kind,
        "use_debug": use_debug,
        "audited_build_config": config_name,
        "provenance_record": str(provenance.get("generated_utc")) if provenance else None,
        "provenance_binary_sha256": recorded_sha,
        "artifact_matches_provenance": bool(provenance) and recorded_sha == binary_sha,
        "use_parallel_io": bool(context.compiler.get("use_parallel_io", False)),
        "use_netcdf4": bool(context.compiler.get("use_netcdf4", False)),
        "io_policy": context.build_config.get("io_policy"),
        "fflags": compiled_string(strings_text, "my_fflags"),
        "compiler_fort": fort_name,
        "which_mpi": context.compiler.get("which_mpi"),
        # Two different repositories: the workflow repo carrying this fix and the
        # frozen ROMS sources that were compiled.  Never reported as one value.
        "workflow_repo": _git_state(Path(__file__).resolve().parents[3]),
        "roms_source_repo": _git_state(context.roms_src),
        "binary": str(binary),
        "binary_bytes": binary.stat().st_size,
        "binary_sha256": binary_sha,
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
        "modes_checked_in_this_build": checked,
        "modes_not_checked_in_this_build": not_checked,
        "all_modes_covered_by_this_run": not not_checked,
        "versions": versions.stdout + versions.stderr,
        "dynamic_links": linked.stdout,
        "evidence_files": {
            "verification": f"build_verification.{stamp}.json",
            "dynamic_links": f"binary_links.{stamp}.log",
            "compiler_versions": f"compiler_versions.{stamp}.log",
        },
        "ROMS_started": False,
        "physical_acceptance": "NOT_RUN",
    }
    (log_dir / f"build_verification.{stamp}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


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
    report = verify_build(context)
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
                    "audited_build_config",
                    "binary",
                    "binary_bytes",
                    "binary_sha256",
                    "tides_date_evidence",
                    "tide_build_issues",
                    "NetCDF4_output_compiled",
                    "all_modes_covered_by_this_run",
                    "ROMS_started",
                )
            },
            indent=2,
        )
    )
    print("mode verdicts:")
    for entry in report["mode_verdicts"]:
        print(
            f"  {entry['mode']:20s} {entry['status']:26s} tiles={entry['tiles']} np={entry['np']} "
            f"binary={entry['binary_name']} ({entry['served_by_build_config']})"
        )
    if report["modes_not_checked_in_this_build"]:
        print(
            "not covered by this build (run the paired config to cover them): "
            + ", ".join(report["modes_not_checked_in_this_build"])
        )
    raise SystemExit(int(bool(report["issues"])))


if __name__ == "__main__":
    main()
