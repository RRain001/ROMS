#!/usr/bin/env python3
"""Case-aware helpers for the ROMS_Build framework."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = FRAMEWORK_ROOT.parent
DATA_PRE_CORE = WORKSPACE_ROOT / "Data_pre" / "core"
if str(DATA_PRE_CORE) not in sys.path:
    sys.path.insert(0, str(DATA_PRE_CORE))

from case_context import export_case_context, init_nesting_root, resolve_case_context  # type: ignore  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _expand_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve()


def _bool_env(env: dict[str, str], name: str, enabled: bool, value: str = "on") -> None:
    if enabled:
        env[name] = value
    else:
        env.pop(name, None)


@dataclass(frozen=True)
class StandardCasePaths:
    case_root: Path
    run_dir: Path
    input_dir: Path
    output_dir: Path
    logs_dir: Path
    build_root: Path
    build_dir: Path
    bin_dir: Path


@dataclass(frozen=True)
class BuildVariant:
    name: str
    roms_application: str
    header_dir: Path
    analytical_dir: Path
    header_name: str
    executable_name: str
    fallback_binary_paths: tuple[Path, ...]

    @property
    def header_path(self) -> Path:
        return self.header_dir / self.header_name


@dataclass(frozen=True)
class BuildContext:
    case_name: str
    case_root: Path
    case_dir: Path
    config_dir: Path
    project_params: dict[str, Any]
    build_config: dict[str, Any]
    build_config_path: Path
    variant: BuildVariant
    paths: StandardCasePaths
    roms_src: Path
    compilers_dir: Path
    oneapi_setvars: Path | None
    my_local_paths: Path | None
    netcdf_root: Path | None
    hdf5_root: Path | None
    mpi_root: Path | None

    @property
    def compiler(self) -> dict[str, Any]:
        return self.build_config.get("compiler", {})

    @property
    def build(self) -> dict[str, Any]:
        return self.build_config.get("build", {})

    @property
    def expected_binary(self) -> Path:
        return self.paths.bin_dir / self.variant.executable_name

    @property
    def default_clean_first(self) -> bool:
        return bool(self.build.get("clean_first_default", True))

    @property
    def default_jobs(self) -> int | None:
        value = self.build.get("jobs", self.build.get("make_jobs"))
        if value is None:
            return None
        try:
            jobs = int(value)
        except (TypeError, ValueError):
            return None
        return jobs if jobs > 0 else None


def parse_cli(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--case-root", default=None)
    parser.add_argument("--config", default=None, help="Override roms_build_config.json path")
    parser.add_argument("--variant", default=None, help="Build variant key defined in roms_build_config.json")
    known, _ = parser.parse_known_args(argv)
    return known


def _case_paths(case_root: Path, project_params: dict[str, Any], build_config: dict[str, Any]) -> StandardCasePaths:
    paths_cfg = project_params.get("paths", {})
    build_cfg = build_config.get("build", {})
    run_dir = case_root / "run"
    input_dir = case_root / paths_cfg.get("input_dir", "input")
    output_dir = case_root / paths_cfg.get("output_dir", "output")
    logs_dir = case_root / paths_cfg.get("logs_dir", "logs")
    build_root = case_root / "build"
    build_dir = case_root / build_cfg.get("build_subdir", "build/Build_romsM")
    bin_dir = case_root / build_cfg.get("bin_subdir", "bin")
    return StandardCasePaths(
        case_root=case_root,
        run_dir=run_dir,
        input_dir=input_dir,
        output_dir=output_dir,
        logs_dir=logs_dir,
        build_root=build_root,
        build_dir=build_dir,
        bin_dir=bin_dir,
    )


def resolve_build_context(
    *,
    case_name: str | None = None,
    case_root: str | Path | None = None,
    config_path: str | Path | None = None,
    variant: str | None = None,
) -> BuildContext:
    init_nesting_root()
    case_context = resolve_case_context(case_name=case_name, case_root=case_root)
    export_case_context(case_context)
    project_params = _load_json(case_context.config_dir / "project_parameters.json")
    if config_path is None:
        resolved_config_path = case_context.config_dir / "roms_build_config.json"
    else:
        raw_config_path = Path(os.path.expandvars(os.path.expanduser(str(config_path))))
        if raw_config_path.is_absolute():
            resolved_config_path = raw_config_path.resolve()
        else:
            resolved_config_path = (case_context.config_dir / raw_config_path).resolve()
    build_config = _load_json(resolved_config_path)
    paths = _case_paths(case_context.case_root, project_params, build_config)

    build_paths_cfg = build_config.get("paths", {})
    roms_src = _expand_path(build_paths_cfg.get("roms_src") or project_params.get("paths", {}).get("roms_src"))
    if roms_src is None:
        raise SystemExit("roms_src must be set in project_parameters.json or roms_build_config.json")
    compilers_dir = roms_src / "Compilers"

    variants_cfg = build_config.get("variants", {})
    if not variants_cfg:
        raise SystemExit("roms_build_config.json must define a non-empty variants object")
    variant_name = variant or build_config.get("default_variant") or next(iter(variants_cfg))
    if variant_name not in variants_cfg:
        available = ", ".join(sorted(variants_cfg))
        raise SystemExit(f"unknown build variant {variant_name!r}; available: {available}")
    variant_cfg = variants_cfg[variant_name]
    case_cpp_name = project_params.get("case", {}).get("cpp_name") or case_context.case_name.upper()
    roms_application = variant_cfg.get("roms_application") or case_cpp_name
    header_dir = case_context.case_root / variant_cfg.get("header_dir", "run")
    analytical_dir = case_context.case_root / variant_cfg.get("analytical_dir", variant_cfg.get("header_dir", "run"))
    fallback_binary_paths = tuple(case_context.case_root / rel for rel in variant_cfg.get("fallback_binary_paths", []))
    build_variant = BuildVariant(
        name=variant_name,
        roms_application=roms_application,
        header_dir=header_dir,
        analytical_dir=analytical_dir,
        header_name=variant_cfg.get("header_name") or f"{case_cpp_name.lower()}.h",
        executable_name=variant_cfg.get("executable_name") or "romsM",
        fallback_binary_paths=fallback_binary_paths,
    )
    return BuildContext(
        case_name=case_context.case_name,
        case_root=case_context.case_root,
        case_dir=case_context.case_dir,
        config_dir=case_context.config_dir,
        project_params=project_params,
        build_config=build_config,
        build_config_path=resolved_config_path,
        variant=build_variant,
        paths=paths,
        roms_src=roms_src,
        compilers_dir=compilers_dir,
        oneapi_setvars=_expand_path(build_paths_cfg.get("oneapi_setvars")),
        my_local_paths=_expand_path(build_paths_cfg.get("my_local_paths")),
        netcdf_root=_expand_path(build_paths_cfg.get("netcdf_root")),
        hdf5_root=_expand_path(build_paths_cfg.get("hdf5_root")),
        mpi_root=_expand_path(build_paths_cfg.get("mpi_root")),
    )


def ensure_case_layout(context: BuildContext) -> None:
    for directory in (
        context.paths.build_root,
        context.paths.build_dir,
        context.paths.bin_dir,
        context.paths.logs_dir,
        context.paths.output_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def build_environment(context: BuildContext) -> dict[str, str]:
    compiler = context.compiler
    env = dict(os.environ)
    env["TMPDIR"] = str(context.paths.build_root)
    env["TMP"] = str(context.paths.build_root)
    env["TEMP"] = str(context.paths.build_root)
    env["ROMS_APPLICATION"] = context.variant.roms_application
    env["MY_ROOT_DIR"] = str(context.roms_src)
    env["MY_PROJECT_DIR"] = str(context.case_root)
    env["MY_ROMS_SRC"] = str(context.roms_src)
    env["COMPILERS"] = str(context.compilers_dir)
    env["MY_HEADER_DIR"] = str(context.variant.header_dir)
    env["MY_ANALYTICAL_DIR"] = str(context.variant.analytical_dir)
    env["BINDIR"] = str(context.paths.bin_dir)
    env["BUILD_DIR"] = str(context.paths.build_dir)
    env["SCRATCH_DIR"] = str(context.paths.build_dir)
    env["myBIN"] = str(context.expected_binary)
    env["USE_MY_LIBS"] = "yes"

    if context.netcdf_root is not None:
        env["NETCDF"] = str(context.netcdf_root)
    if context.hdf5_root is not None:
        env["HDF5"] = str(context.hdf5_root)
    if context.mpi_root is not None:
        env["MPI_ROOT"] = str(context.mpi_root)
    if compiler.get("fort"):
        env["FORT"] = str(compiler["fort"])
    if compiler.get("which_mpi"):
        env["which_MPI"] = str(compiler["which_mpi"])
    _bool_env(env, "USE_MPI", bool(compiler.get("use_mpi", True)))
    _bool_env(env, "USE_MPIF90", bool(compiler.get("use_mpif90", True)))
    _bool_env(env, "USE_LARGE", bool(compiler.get("use_large", True)))
    _bool_env(env, "STATIC", bool(compiler.get("static", True)))
    _bool_env(env, "EXEC", bool(compiler.get("exec", True)))
    _bool_env(env, "USE_NETCDF4", bool(compiler.get("use_netcdf4", True)))
    _bool_env(env, "USE_PARALLEL_IO", bool(compiler.get("use_parallel_io", True)))
    _bool_env(env, "USE_DEBUG", bool(compiler.get("use_debug", False)))
    return env


def shell_prelude(context: BuildContext) -> list[str]:
    lines: list[str] = []
    if context.oneapi_setvars is not None:
        lines.append(f'if [ -f {shlex.quote(str(context.oneapi_setvars))} ]; then source {shlex.quote(str(context.oneapi_setvars))} --force >/dev/null; fi')
    if context.my_local_paths is not None:
        lines.append(f'if [ -f {shlex.quote(str(context.my_local_paths))} ]; then source {shlex.quote(str(context.my_local_paths))}; fi')
    elif context.build_config.get("use_legacy_library_paths", True):
        fallback = context.compilers_dir / "my_build_paths.sh"
        lines.append(
            f'if [ -f {shlex.quote(str(fallback))} ]; then source {shlex.quote(str(fallback))} {shlex.quote(str(fallback))}; fi'
        )
    return lines


def probe_shell_command(context: BuildContext, command: str) -> subprocess.CompletedProcess[str]:
    script = "\n".join(["set -euo pipefail", *shell_prelude(context), command])
    return subprocess.run(
        ["bash", "-lc", script],
        env=build_environment(context),
        text=True,
        capture_output=True,
        check=False,
    )


def execute_build(context: BuildContext, *, clean: bool, jobs: int | None = None, dry_run: bool = False) -> int:
    ensure_case_layout(context)
    effective_jobs = jobs or context.default_jobs
    make_cmd = "make"
    if effective_jobs and effective_jobs > 0:
        make_cmd = f"make -j {effective_jobs}"
    # Case/platform overrides, without patching the frozen ROMS makefiles.
    variables = {"MAKE_MACROS": str(context.paths.build_root / "make_macros.mk"),
                 **context.build.get("make_variables", {})}
    assignments = ""
    for key, value in variables.items():
        if not key.replace("_", "").isalnum():
            raise ValueError(f"invalid make variable: {key}")
        expanded = os.path.expandvars(os.path.expanduser(str(value)))
        assignments += " " + shlex.quote(f"{key}={expanded}")
    make_cmd += assignments
    script_lines = ["set -euo pipefail", *shell_prelude(context), f"cd {shlex.quote(str(context.roms_src))}"]
    if clean:
        script_lines.append("make clean" + assignments)
    script_lines.append(make_cmd)
    script = "\n".join(script_lines)
    if dry_run:
        print(script)
        return 0
    result = subprocess.run(["bash", "-lc", script], env=build_environment(context), text=True)
    if result.returncode == 0:
        actual_binary = context.paths.bin_dir / ("romsG" if context.compiler.get("use_debug") else "romsM")
        if actual_binary.exists() and actual_binary != context.expected_binary:
            shutil.copy2(actual_binary, context.expected_binary)
            context.expected_binary.chmod(actual_binary.stat().st_mode)
        if not context.expected_binary.is_file():
            raise RuntimeError(f"make succeeded but expected executable is missing: {context.expected_binary}")
        write_build_provenance(context, script)
    return result.returncode


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(source_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    head = (result.stdout or "").strip()
    return head or None


def write_build_provenance(context: BuildContext, build_command: str) -> Path:
    """Record what this build actually produced.

    One uniquely named file per build, so a stale snapshot can never be read as
    evidence for the current artifact.  Everything here is measured from the
    build that just ran -- nothing is copied from the configuration alone.
    """
    provenance_dir = context.case_root / "logs" / "build_provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)

    checkdefs = context.paths.build_dir / "checkdefs.f90"
    strings = context.paths.build_dir / "mod_strings.f90"
    fflags = None
    if strings.is_file():
        match = re.search(r'my_fflags\s*=\s*"([^"]*)"', strings.read_text(errors="ignore"))
        fflags = match.group(1) if match else None
    compiled_options: list[str] = []
    if checkdefs.is_file():
        compiled_options = sorted(set(re.findall(r"Coptions[^=]*='\s*([A-Z_0-9]+),", checkdefs.read_text(errors="ignore"))))

    use_debug = bool(context.compiler.get("use_debug", False))
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    record = {
        "generated_utc": now.isoformat(),
        "case": context.case_name,
        "build_kind": "debug" if use_debug else "release",
        "use_debug": use_debug,
        "use_parallel_io": bool(context.compiler.get("use_parallel_io", False)),
        "use_netcdf4": bool(context.compiler.get("use_netcdf4", False)),
        "io_policy": context.build_config.get("io_policy"),
        "git_head": _git_head(context.roms_src),
        "build_config": str(context.build_config_path),
        "build_config_sha256": _sha256(context.build_config_path),
        "roms_src": str(context.roms_src),
        "header": str(context.variant.header_path),
        "header_sha256": _sha256(context.variant.header_path),
        "compiler": dict(context.compiler),
        "fflags": fflags,
        "compiled_options": compiled_options,
        "binary": str(context.expected_binary),
        "binary_bytes": context.expected_binary.stat().st_size if context.expected_binary.is_file() else None,
        "binary_sha256": _sha256(context.expected_binary),
        "build_directory": str(context.paths.build_dir),
        "build_command": build_command,
    }
    path = provenance_dir / f"{stamp}_{context.build_config_path.stem}_{context.variant.name}.json"
    suffix = 0
    while path.exists():
        suffix += 1
        path = provenance_dir / (
            f"{stamp}_{context.build_config_path.stem}_{context.variant.name}.{suffix}.json"
        )
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path


def clean_build_tree(context: BuildContext) -> None:
    if context.paths.build_root.exists():
        shutil.rmtree(context.paths.build_root)
    context.paths.build_root.mkdir(parents=True, exist_ok=True)


def resolve_binary_candidates(context: BuildContext) -> list[Path]:
    candidates = [context.expected_binary]
    default_binary = context.paths.bin_dir / "romsM"
    if default_binary not in candidates:
        candidates.append(default_binary)
    for path in context.variant.fallback_binary_paths:
        if path not in candidates:
            candidates.append(path)
    return candidates
