#!/usr/bin/env python3
"""Case-aware helpers for the ROMS_Run framework."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netCDF4 import Dataset


FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = FRAMEWORK_ROOT.parent
DATA_PRE_CORE = WORKSPACE_ROOT / "Data_pre" / "core"
ROMS_BUILD_CORE = WORKSPACE_ROOT / "ROMS_Build" / "core"
for path in (DATA_PRE_CORE, ROMS_BUILD_CORE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from case_context import export_case_context, resolve_case_context  # type: ignore  # noqa: E402
from case_naming import run_infile_name  # type: ignore  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _expand_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve()


def _expand_text(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    return os.path.expandvars(os.path.expanduser(str(value)))


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
class RunMode:
    name: str
    build_variant: str
    binary_name: str
    infile: Path
    log_file: Path
    np: int
    launcher: str
    fallback_binaries: tuple[Path, ...]


@dataclass(frozen=True)
class RunContext:
    case_name: str
    case_root: Path
    case_dir: Path
    config_dir: Path
    project_params: dict[str, Any]
    run_config: dict[str, Any]
    run_config_path: Path
    paths: StandardCasePaths
    mode: RunMode
    shell_init_files: tuple[Path, ...]
    library_paths: tuple[Path, ...]
    extra_env: dict[str, str]


@dataclass(frozen=True)
class InfileMetadata:
    my_app_cpp: str | None
    lm: int | None
    mm: int | None
    n: int | None
    ntile_i: int | None
    ntile_j: int | None
    referenced_tokens: tuple[str, ...]
    optional_tokens: tuple[str, ...]
    keyed_tokens: tuple[tuple[str, str, bool], ...]

    @property
    def required_np(self) -> int | None:
        if self.ntile_i is None or self.ntile_j is None:
            return None
        return self.ntile_i * self.ntile_j


def parse_cli(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--case-root", default=None)
    parser.add_argument("--config", default=None, help="Override roms_run_config.json path")
    parser.add_argument("--mode", default=None, help="Run mode defined in roms_run_config.json")
    known, _ = parser.parse_known_args(argv)
    return known


def _case_paths(case_root: Path, project_params: dict[str, Any], run_config: dict[str, Any]) -> StandardCasePaths:
    paths_cfg = project_params.get("paths", {})
    build_cfg = run_config.get("build_layout", {})
    run_dir = case_root / "run"
    input_dir = case_root / paths_cfg.get("input_dir", "input")
    output_dir = case_root / paths_cfg.get("output_dir", "output")
    logs_dir = case_root / paths_cfg.get("logs_dir", "logs")
    build_root = case_root / build_cfg.get("build_root", "build")
    build_dir = case_root / build_cfg.get("build_dir", "build/Build_romsM")
    bin_dir = case_root / build_cfg.get("bin_dir", "bin")
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


def resolve_run_context(
    *,
    case_name: str | None = None,
    case_root: str | Path | None = None,
    config_path: str | Path | None = None,
    mode: str | None = None,
) -> RunContext:
    case_context = resolve_case_context(case_name=case_name, case_root=case_root)
    export_case_context(case_context)
    project_params = _load_json(case_context.config_dir / "project_parameters.json")
    if config_path is None:
        resolved_config_path = case_context.config_dir / "roms_run_config.json"
    else:
        raw_config_path = Path(os.path.expandvars(os.path.expanduser(str(config_path))))
        if raw_config_path.is_absolute():
            resolved_config_path = raw_config_path.resolve()
        else:
            resolved_config_path = (case_context.config_dir / raw_config_path).resolve()
    run_config = _load_json(resolved_config_path)
    paths = _case_paths(case_context.case_root, project_params, run_config)
    run_modes = run_config.get("run_modes", {})
    if not run_modes:
        raise SystemExit("roms_run_config.json must define at least one run mode")
    mode_name = mode or run_config.get("default_run_mode") or next(iter(run_modes))
    if mode_name not in run_modes:
        available = ", ".join(sorted(run_modes))
        raise SystemExit(f"unknown run mode {mode_name!r}; available: {available}")
    mode_cfg = run_modes[mode_name]
    default_launcher = _expand_text(str(run_config.get("launcher", "mpirun"))) or "mpirun"
    default_np = int(run_config.get("np", 1))
    infile_name = mode_cfg.get("infile") or run_infile_name("pilot" if mode_name == "pilot_month" else mode_name)
    infile = case_context.case_root / "run" / infile_name
    log_file = case_context.case_root / project_params.get("paths", {}).get("logs_dir", "logs") / mode_cfg.get("log_file", f"{mode_name}.log")
    run_mode = RunMode(
        name=mode_name,
        build_variant=mode_cfg.get("build_variant", "default"),
        binary_name=mode_cfg["binary"],
        infile=infile,
        log_file=log_file,
        np=int(mode_cfg.get("np", default_np)),
        launcher=_expand_text(str(mode_cfg.get("launcher", default_launcher))) or default_launcher,
        fallback_binaries=tuple(case_context.case_root / rel for rel in mode_cfg.get("fallback_binaries", [])),
    )
    shell_init_files = tuple(
        path for item in run_config.get("shell_init_files", []) if (path := _expand_path(item)) is not None
    )
    library_paths = tuple(
        path for item in run_config.get("library_paths", []) if (path := _expand_path(item)) is not None
    )
    extra_env = {str(key): os.path.expandvars(os.path.expanduser(str(value))) for key, value in run_config.get("env", {}).items()}
    return RunContext(
        case_name=case_context.case_name,
        case_root=case_context.case_root,
        case_dir=case_context.case_dir,
        config_dir=case_context.config_dir,
        project_params=project_params,
        run_config=run_config,
        run_config_path=resolved_config_path,
        paths=paths,
        mode=run_mode,
        shell_init_files=shell_init_files,
        library_paths=library_paths,
        extra_env=extra_env,
    )


def ensure_case_layout(context: RunContext) -> None:
    for directory in (context.paths.run_dir, context.paths.logs_dir, context.paths.output_dir, context.paths.input_dir, context.paths.bin_dir):
        directory.mkdir(parents=True, exist_ok=True)


def shell_prelude(context: RunContext) -> list[str]:
    lines: list[str] = []
    for path in context.shell_init_files:
        lines.append(f'if [ -f {shlex.quote(str(path))} ]; then source {shlex.quote(str(path))} --force >/dev/null; fi')
    return lines


def run_environment(context: RunContext) -> dict[str, str]:
    env = dict(os.environ)
    if context.library_paths:
        existing = env.get("LD_LIBRARY_PATH", "")
        parts = [str(path) for path in context.library_paths]
        if existing:
            parts.append(existing)
        env["LD_LIBRARY_PATH"] = ":".join(parts)
    env.update(context.extra_env)
    return env


def strip_comment(line: str) -> str:
    return line.split("!", 1)[0].rstrip()


def _parse_scalar(text: str, key: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=+\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    value = strip_comment(match.group(1)).strip()
    if not value:
        return None
    return value.split()[0]


def _parse_int(text: str, key: str) -> int | None:
    value = _parse_scalar(text, key)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_infile_metadata(path: Path) -> InfileMetadata:
    text = path.read_text(errors="ignore")
    required_tokens, optional_tokens, keyed_tokens = _extract_input_file_tokens(text)
    return InfileMetadata(
        my_app_cpp=_parse_scalar(text, "MyAppCPP"),
        lm=_parse_int(text, "Lm"),
        mm=_parse_int(text, "Mm"),
        n=_parse_int(text, "N"),
        ntile_i=_parse_int(text, "NtileI"),
        ntile_j=_parse_int(text, "NtileJ"),
        referenced_tokens=tuple(sorted(set(required_tokens))),
        optional_tokens=tuple(sorted(set(optional_tokens))),
        keyed_tokens=tuple(keyed_tokens),
    )


REQUIRED_INPUT_FILE_KEYS = {
    "VARNAME",
    "GRDNAME",
    "ININAME",
    "BRYNAME",
    "TIDENAME",
    "RIVERNAME",
    "FRCNAME",
    "SSFNAME",
}


OPTIONAL_INPUT_FILE_KEYS = {
    "CLMNAME",
    "NUDNAME",
    "APARNAM",
    "SPOSNAM",
}


def _extract_file_tokens(fragment: str) -> list[str]:
    return re.findall(r"([A-Za-z0-9_./-]+\.(?:nc|yaml|csv|dat))", fragment)


def _extract_input_file_tokens(text: str) -> tuple[list[str], list[str], list[tuple[str, str, bool]]]:
    required_tokens: list[str] = []
    optional_tokens: list[str] = []
    keyed_tokens: list[tuple[str, str, bool]] = []
    collecting = False
    current_optional = False
    current_key = ""
    for raw_line in text.splitlines():
        line = strip_comment(raw_line).strip()
        if not line:
            continue
        if "=" in line:
            lhs, rhs = line.split("=", 1)
            key = lhs.replace("=", "").strip().upper()
            collecting = key in REQUIRED_INPUT_FILE_KEYS or key in OPTIONAL_INPUT_FILE_KEYS
            current_optional = key in OPTIONAL_INPUT_FILE_KEYS
            current_key = key if collecting else ""
            if collecting:
                target = optional_tokens if current_optional else required_tokens
                tokens = _extract_file_tokens(rhs)
                target.extend(tokens)
                keyed_tokens.extend((key, token, current_optional) for token in tokens)
                collecting = line.endswith("\\") or line.endswith("|")
            continue
        if collecting:
            target = optional_tokens if current_optional else required_tokens
            tokens = _extract_file_tokens(line)
            target.extend(tokens)
            keyed_tokens.extend((current_key, token, current_optional) for token in tokens)
            collecting = line.endswith("\\") or line.endswith("|")
    return required_tokens, optional_tokens, keyed_tokens


def resolve_binary_path(context: RunContext) -> Path | None:
    primary = context.paths.bin_dir / context.mode.binary_name
    if primary.exists():
        return primary
    for candidate in context.mode.fallback_binaries:
        if candidate.exists():
            return candidate
    return None


def resolve_referenced_path(context: RunContext, token: str) -> Path | None:
    candidate = Path(token)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    search_order = (
        context.paths.run_dir / candidate,
        context.paths.input_dir / candidate,
        context.case_root / candidate,
    )
    for path in search_order:
        if path.exists():
            return path
    return None


def _dim(ds: Dataset, name: str) -> int | None:
    return len(ds.dimensions[name]) if name in ds.dimensions else None


def _first_keyed_path(context: RunContext, metadata: InfileMetadata, key: str) -> Path | None:
    for item_key, token, _ in metadata.keyed_tokens:
        if item_key == key:
            return resolve_referenced_path(context, token)
    return None


def _keyed_paths(context: RunContext, metadata: InfileMetadata, key: str) -> list[Path]:
    paths: list[Path] = []
    for item_key, token, _ in metadata.keyed_tokens:
        if item_key != key:
            continue
        resolved = resolve_referenced_path(context, token)
        if resolved is not None:
            paths.append(resolved)
    return paths


def validate_dimension_consistency(context: RunContext, metadata: InfileMetadata) -> list[str]:
    issues: list[str] = []
    vertical_n = context.project_params.get("vertical", {}).get("N")
    try:
        expected_n = int(vertical_n)
    except (TypeError, ValueError):
        expected_n = None
    if expected_n is not None and metadata.n != expected_n:
        issues.append(f"vertical mismatch: infile N={metadata.n}, case vertical.N={expected_n}")

    grid_path = _first_keyed_path(context, metadata, "GRDNAME")
    grid_dims: dict[str, int | None] = {}
    if grid_path is not None:
        try:
            with Dataset(grid_path) as grid:
                grid_dims = {
                    "xi_rho": _dim(grid, "xi_rho"),
                    "eta_rho": _dim(grid, "eta_rho"),
                    "xi_u": _dim(grid, "xi_u"),
                    "eta_u": _dim(grid, "eta_u"),
                    "xi_v": _dim(grid, "xi_v"),
                    "eta_v": _dim(grid, "eta_v"),
                }
        except Exception as exc:  # noqa: BLE001
            issues.append(f"cannot open grid NetCDF {grid_path}: {type(exc).__name__}: {exc}")
    if grid_dims:
        expected_lm = grid_dims.get("xi_rho") - 2 if grid_dims.get("xi_rho") is not None else None
        expected_mm = grid_dims.get("eta_rho") - 2 if grid_dims.get("eta_rho") is not None else None
        if metadata.lm != expected_lm:
            issues.append(f"grid mismatch: infile Lm={metadata.lm}, GRDNAME xi_rho-2={expected_lm}")
        if metadata.mm != expected_mm:
            issues.append(f"grid mismatch: infile Mm={metadata.mm}, GRDNAME eta_rho-2={expected_mm}")

    for key in ("ININAME", "BRYNAME", "RIVERNAME", "SSFNAME"):
        for path in _keyed_paths(context, metadata, key):
            try:
                with Dataset(path) as ds:
                    if expected_n is not None and _dim(ds, "s_rho") is not None and _dim(ds, "s_rho") != expected_n:
                        issues.append(f"{key} vertical mismatch: {path.name} s_rho={_dim(ds, 's_rho')}, case vertical.N={expected_n}")
                    for dim_name, expected in grid_dims.items():
                        actual = _dim(ds, dim_name)
                        if actual is not None and expected is not None and actual != expected:
                            issues.append(f"{key} grid mismatch: {path.name} {dim_name}={actual}, GRDNAME {dim_name}={expected}")
            except Exception as exc:  # noqa: BLE001
                issues.append(f"cannot open {key} NetCDF {path}: {type(exc).__name__}: {exc}")
    for key in ("FRCNAME", "TIDENAME"):
        for path in _keyed_paths(context, metadata, key):
            try:
                with Dataset(path):
                    pass
            except Exception as exc:  # noqa: BLE001
                issues.append(f"cannot open {key} NetCDF {path}: {type(exc).__name__}: {exc}")
    return issues


def validate_prereqs(context: RunContext) -> tuple[list[str], list[str], InfileMetadata]:
    issues: list[str] = []
    warnings: list[str] = []
    infile = context.mode.infile
    if not infile.exists():
        issues.append(f"missing run input file: {infile}")
        return issues, warnings, InfileMetadata(None, None, None, None, None, None, (), (), ())
    metadata = parse_infile_metadata(infile)
    binary = resolve_binary_path(context)
    if binary is None:
        issues.append(f"missing executable {context.mode.binary_name} in {context.paths.bin_dir} and fallback paths")
    elif not os.access(binary, os.X_OK):
        issues.append(f"executable is not runnable: {binary}")

    expected_cpp = str(context.project_params.get("case", {}).get("cpp_name") or "").strip()
    if expected_cpp and not metadata.my_app_cpp:
        issues.append(f"MyAppCPP missing: case expects {expected_cpp}")
    if metadata.my_app_cpp and metadata.my_app_cpp != expected_cpp:
        issues.append(f"MyAppCPP mismatch: infile={metadata.my_app_cpp}, case expects {expected_cpp}")
    required_np = metadata.required_np
    if required_np is not None and required_np != context.mode.np:
        issues.append(f"parallel mismatch: NtileI*NtileJ={required_np}, configured np={context.mode.np}")
    for token in metadata.referenced_tokens:
        resolved = resolve_referenced_path(context, token)
        if resolved is None:
            issues.append(f"missing referenced input file: {token}")
    for token in metadata.optional_tokens:
        resolved = resolve_referenced_path(context, token)
        if resolved is None:
            warnings.append(f"missing optional referenced input file: {token}")
    if any(context.mode.fallback_binaries):
        primary = context.paths.bin_dir / context.mode.binary_name
        if not primary.exists() and binary is not None:
            warnings.append(f"using fallback executable path: {binary}")
    issues.extend(validate_dimension_consistency(context, metadata))
    return issues, warnings, metadata


def launch_command(context: RunContext, binary: Path) -> str:
    launcher = context.mode.launcher
    infile_name = context.mode.infile.name
    binary_ref = str(binary)
    return f"{shlex.quote(launcher)} -np {context.mode.np} {shlex.quote(binary_ref)} {shlex.quote(infile_name)}"


def execute_run(context: RunContext, *, dry_run: bool = False) -> int:
    ensure_case_layout(context)
    issues, _, _ = validate_prereqs(context)
    binary = resolve_binary_path(context) or (context.paths.bin_dir / context.mode.binary_name)
    script_lines = [
        "set -euo pipefail",
        *shell_prelude(context),
        f"cd {shlex.quote(str(context.paths.run_dir))}",
        f"exec {launch_command(context, binary)}",
    ]
    script = "\n".join(script_lines)
    if dry_run:
        print(f"case: {context.case_name}")
        print(f"mode: {context.mode.name}")
        print(f"run_dir: {context.paths.run_dir}")
        print(f"infile: {context.mode.infile}")
        print(f"binary: {binary}")
        print(f"log_file: {context.mode.log_file}")
        print(script)
        if issues:
            for issue in issues:
                print(issue, file=sys.stderr)
            return 1
        return 0
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    binary = resolve_binary_path(context)
    assert binary is not None
    context.mode.log_file.parent.mkdir(parents=True, exist_ok=True)
    with context.mode.log_file.open("w") as handle:
        result = subprocess.run(
            ["bash", "-lc", script],
            env=run_environment(context),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return result.returncode
