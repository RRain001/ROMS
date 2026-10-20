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
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = FRAMEWORK_ROOT.parent
DATA_PRE_CORE = WORKSPACE_ROOT / "Data_pre" / "core"
ROMS_BUILD_CORE = WORKSPACE_ROOT / "ROMS_Build" / "core"
for path in (DATA_PRE_CORE, ROMS_BUILD_CORE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from case_context import export_case_context, init_nesting_root, resolve_case_context  # type: ignore  # noqa: E402
from case_naming import run_infile_name  # type: ignore  # noqa: E402
from external_forcing_coverage import (  # type: ignore  # noqa: E402
    UNVERIFIED_MARKER,
    check_boundary_coverage,
    mjd_to_datetime,
)
from formal_online_workflow import load_formal_online_workflow, parse_formal_online_mode, spinup_restart_name  # type: ignore  # noqa: E402


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
    required_cpp_defs: tuple[str, ...]


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
    init_nesting_root()
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
        required_cpp_defs=tuple(str(item) for item in mode_cfg.get("required_cpp_defs", [])),
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


OUTPUT_FILE_KEYS = {
    "RSTNAME",
    "HISNAME",
    "AVGNAME",
    "DIANAME",
    "XTRNAME",
    "QCKNAME",
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
    current_kind = ""
    current_key = ""
    for raw_line in text.splitlines():
        line = strip_comment(raw_line).strip()
        if not line:
            continue
        if "=" in line:
            lhs, rhs = line.split("=", 1)
            key = lhs.replace("=", "").strip().upper()
            if key in REQUIRED_INPUT_FILE_KEYS:
                current_kind = "required"
            elif key in OPTIONAL_INPUT_FILE_KEYS:
                current_kind = "optional"
            elif key in OUTPUT_FILE_KEYS:
                current_kind = "output"
            else:
                current_kind = ""
            collecting = bool(current_kind)
            current_key = key if collecting else ""
            if collecting:
                tokens = _extract_file_tokens(rhs)
                if current_kind == "required":
                    required_tokens.extend(tokens)
                elif current_kind == "optional":
                    optional_tokens.extend(tokens)
                keyed_tokens.extend((key, token, current_kind != "required") for token in tokens)
                collecting = line.endswith("\\") or line.endswith("|")
            continue
        if collecting:
            tokens = _extract_file_tokens(line)
            if current_kind == "required":
                required_tokens.extend(tokens)
            elif current_kind == "optional":
                optional_tokens.extend(tokens)
            keyed_tokens.extend((current_key, token, current_kind != "required") for token in tokens)
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


def _variable_all_zero(ds: Dataset, names: tuple[str, ...]) -> tuple[bool, str | None]:
    for name in names:
        if name not in ds.variables:
            continue
        data = np.ma.filled(ds.variables[name][:], np.nan).astype(float, copy=False)
        finite = data[np.isfinite(data)]
        if finite.size == 0:
            return False, name
        return bool(np.allclose(finite, 0.0)), name
    return False, None


def validate_online_profile_content(context: RunContext, metadata: InfileMetadata) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    uv_tides = bool(context.project_params.get("tides", {}).get("uv_tides", False))
    if uv_tides:
        for path in _keyed_paths(context, metadata, "TIDENAME"):
            try:
                with Dataset(path) as ds:
                    for name in ("tide_Cmax", "tide_Cmin", "tide_Cangle", "tide_Cphase"):
                        if name not in ds.variables:
                            issues.append(f"TIDENAME missing UV tide variable {name}: {path.name}")
            except Exception as exc:  # noqa: BLE001
                issues.append(f"cannot inspect TIDENAME NetCDF {path}: {type(exc).__name__}: {exc}")

    for path in _keyed_paths(context, metadata, "ININAME"):
        try:
            with Dataset(path) as ds:
                ok, found = _variable_all_zero(ds, ("dye_01",))
                if found is None:
                    issues.append(f"ININAME missing dye_01: {path.name}")
                elif not ok:
                    issues.append(f"ININAME dye_01 is not all zero: {path.name}")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"cannot inspect ININAME NetCDF {path}: {type(exc).__name__}: {exc}")

    for path in _keyed_paths(context, metadata, "BRYNAME"):
        try:
            with Dataset(path) as ds:
                for edge in ("west", "east", "south", "north"):
                    ok, found = _variable_all_zero(ds, (f"dye_{edge}_01", f"dye_01_{edge}"))
                    if found is None:
                        issues.append(f"BRYNAME missing dye boundary for {edge}: {path.name}")
                    elif not ok:
                        issues.append(f"BRYNAME {found} is not all zero: {path.name}")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"cannot inspect BRYNAME NetCDF {path}: {type(exc).__name__}: {exc}")

    for key in ("RIVERNAME", "SSFNAME"):
        for path in _keyed_paths(context, metadata, key):
            try:
                with Dataset(path) as ds:
                    if "river_Vshape" in ds.variables:
                        profile = np.asarray(ds.variables["river_Vshape"][:], dtype=float)
                        sums = profile.sum(axis=0)
                        if not np.allclose(sums, 1.0):
                            issues.append(f"{key} river_Vshape column sums are not 1: {path.name}")
                        surface_index = profile.shape[0] - 1
                        if not np.all(profile[surface_index, :] > 0.0):
                            warnings.append(f"{key} river_Vshape does not inject at surface index {surface_index}: {path.name}")
                    else:
                        issues.append(f"{key} missing river_Vshape: {path.name}")
            except Exception as exc:  # noqa: BLE001
                issues.append(f"cannot inspect {key} NetCDF {path}: {type(exc).__name__}: {exc}")

    for key, token, _ in metadata.keyed_tokens:
        if key not in OUTPUT_FILE_KEYS:
            continue
        candidate = Path(token)
        resolved = candidate if candidate.is_absolute() else (context.paths.run_dir / candidate).resolve()
        if resolved.exists():
            warnings.append(f"output file already exists and may be overwritten: {resolved}")
    return issues, warnings


def validate_formal_online_content(context: RunContext, metadata: InfileMetadata) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    formal = parse_formal_online_mode(context.mode.name, context.project_params)
    if not formal or not context.mode.infile.exists():
        return issues, warnings
    workflow = load_formal_online_workflow(context.project_params)
    text = context.mode.infile.read_text(errors="ignore")
    dt = _parse_scalar(text, "DT")
    try:
        dt_seconds = float(str(dt).replace("d0", "").replace("D0", ""))
    except (TypeError, ValueError):
        dt_seconds = float(context.project_params.get("time", {}).get("pilot_dt_seconds", 60.0))
    restart_steps = str(max(1, int(round(5 * 24 * 3600 / dt_seconds))))
    if formal["phase"] == "spinup":
        if _parse_scalar(text, "NHIS") != "0":
            issues.append("formal spin-up must disable history output (NHIS=0)")
        if _parse_scalar(text, "NAVG") != "0":
            issues.append("formal spin-up must disable average output (NAVG=0)")
        if _parse_scalar(text, "NDIA") != "0":
            issues.append("formal spin-up must disable diagnostics (NDIA=0)")
        if _parse_scalar(text, "NRST") != restart_steps:
            issues.append(f"formal spin-up restart interval must be 5 d (NRST={restart_steps})")
    elif formal["phase"] == "continuous":
        hourly_steps = str(max(1, int(round(3600 / dt_seconds))))
        daily_steps = str(max(1, int(round(24 * 3600 / dt_seconds))))
        if _parse_scalar(text, "NRREC") != "0":
            issues.append("formal continuous run must start with NRREC=0")
        if (_parse_scalar(text, "ININAME") or "").startswith("../output/"):
            issues.append("formal continuous ININAME must not point to a restart output")
        if _parse_scalar(text, "NHIS") != hourly_steps:
            issues.append("formal continuous history interval must be 1 h")
        if _parse_scalar(text, "NAVG") != daily_steps:
            issues.append("formal continuous average interval must be 24 h")
        if _parse_scalar(text, "NDIA") != "0":
            issues.append("formal continuous diagnostics must be disabled (NDIA=0)")
        if _parse_scalar(text, "NRST") != restart_steps:
            issues.append(f"formal continuous restart interval must be 5 d (NRST={restart_steps})")
    else:
        hourly_steps = str(max(1, int(round(3600 / dt_seconds))))
        daily_steps = str(max(1, int(round(24 * 3600 / dt_seconds))))
        expected_ini = f"../output/{spinup_restart_name(context.project_params.get('naming', {}).get('roms_prefix', context.case_name), workflow)}"
        if _parse_scalar(text, "NRREC") not in {"-1", "1"}:
            issues.append("formal production must hot start from restart (NRREC=-1 or 1)")
        if _parse_scalar(text, "ININAME") != expected_ini:
            issues.append(f"formal production ININAME must be {expected_ini}")
        if _parse_scalar(text, "NHIS") != hourly_steps:
            issues.append("formal production history interval must be 1 h")
        if _parse_scalar(text, "NAVG") != daily_steps:
            issues.append("formal production average interval must be 24 h")
        if _parse_scalar(text, "NDIA") != "0":
            issues.append("formal production diagnostics must be disabled (NDIA=0)")
        if _parse_scalar(text, "NRST") != restart_steps:
            issues.append(f"formal production restart interval must be 5 d (NRST={restart_steps})")
    for key, token, _ in metadata.keyed_tokens:
        if key not in OUTPUT_FILE_KEYS:
            continue
        candidate = Path(token)
        resolved = candidate if candidate.is_absolute() else (context.paths.run_dir / candidate).resolve()
        if resolved.exists():
            warnings.append(f"formal output target already exists and may be overwritten: {resolved}")
    return issues, warnings


def validate_tide_build_artifacts(context: RunContext, binary: Path | None) -> list[str]:
    """Check the generated sources used to build the active tide executable."""
    required = context.mode.required_cpp_defs
    if not required:
        return []
    issues: list[str] = []
    set_tides = context.paths.build_dir / "set_tides.f90"
    tides_date = context.paths.build_dir / "tides_date.f90"
    source_text: dict[str, str] = {}
    for path in (set_tides, tides_date):
        if not path.exists():
            issues.append(f"missing generated build source for tide validation: {path}")
        else:
            source_text[path.name] = path.read_text(errors="ignore")
    signatures = {
        "SSH_TIDES": ("set_tides.f90", ("Etide(:,:)=0.0_r8", "SSH_Tamp")),
        "UV_TIDES": ("set_tides.f90", ("Utide(:,:)=0.0_r8", "UV_Tmajor", "Vtide(:,:)=0.0_r8")),
        "RAMP_TIDES": ("set_tides.f90", ("ramp=TANH((tdays(ng)-dstart)/1.0_r8)",)),
        "TIDES_DATE": ("tides_date.f90", ("zero_phase_date", "netcdf_get_fvar")),
    }
    for macro in required:
        signature = signatures.get(macro)
        if signature is None:
            continue
        filename, needles = signature
        text = source_text.get(filename, "")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            issues.append(f"generated build source for {macro} is missing: {', '.join(missing)}")
    if binary is not None and binary.exists():
        source_mtime = max((path.stat().st_mtime for path in (set_tides, tides_date) if path.exists()), default=0.0)
        if source_mtime and binary.stat().st_mtime < source_mtime:
            issues.append(f"executable {binary.name} is older than generated tide build sources")
    return issues


def _parse_float_scalar(text: str, key: str) -> float | None:
    value = _parse_scalar(text, key)
    if value is None:
        return None
    try:
        return float(value.replace("d", "e").replace("D", "e"))
    except ValueError:
        return None


#: LBC types that read a boundary file.  ``Clo`` and ``Per`` do not.
DATA_BOUNDARY_TYPES = {"Cha", "Fla", "Nud", "RadNud", "Rad", "Gra", "Mar"}


def infile_data_boundary_types(infile_text: str) -> list[str]:
    """Boundary conditions in the infile that need boundary data."""
    found: set[str] = set()
    for raw_line in infile_text.splitlines():
        line = strip_comment(raw_line)
        match = re.match(r"\s*LBC\(\s*\w+\s*\)\s*=+\s*(.*)", line)
        if not match:
            continue
        found.update(token for token in match.group(1).split() if token in DATA_BOUNDARY_TYPES)
    return sorted(found)


def validate_external_forcing_coverage(
    context: RunContext, metadata: InfileMetadata, infile_text: str
) -> list[str]:
    """Fail closed unless ``BRYNAME`` provably covers the window this run requests.

    Applies to any mode whose infile names a real boundary file -- the external
    test modes and an explicitly external smoke run alike.  The requested window
    is taken from the infile itself (``DSTART``/``NTIMES``/``DT``), not from the
    case configuration, so the check follows what ROMS will actually integrate.

    A declared external mode cannot sidestep the gate by naming no boundary file,
    and a mode that asks ROMS for data boundaries cannot either.  Only genuinely
    closed or periodic setups are exempt.
    """
    issues: list[str] = []
    if UNVERIFIED_MARKER in infile_text:
        issues.append(
            f"infile is stamped {UNVERIFIED_MARKER}: it was generated without proven boundary "
            "coverage and must not be run"
        )
        return issues

    declared_external = str(context.mode.name).startswith("external_")
    data_boundaries = infile_data_boundary_types(infile_text)
    bry_tokens = [
        token
        for key, token, _ in metadata.keyed_tokens
        if key == "BRYNAME" and Path(token).name.lower() not in {"none", "null"}
    ]

    if not bry_tokens:
        if declared_external:
            issues.append(
                f"mode {context.mode.name} is an external-forcing mode but its infile declares no "
                "boundary file (BRYNAME); the external coverage gate cannot be satisfied"
            )
        elif data_boundaries:
            issues.append(
                "infile requests data boundary conditions ("
                + ", ".join(data_boundaries)
                + ") but declares no boundary file (BRYNAME)"
            )
        return issues

    dstart = _parse_float_scalar(infile_text, "DSTART")
    ntimes = _parse_int(infile_text, "NTIMES")
    dt = _parse_float_scalar(infile_text, "DT")
    if dstart is None or ntimes is None or dt is None:
        issues.append("cannot verify external boundary coverage: infile must define DSTART, NTIMES and DT")
        return issues

    required_start = mjd_to_datetime(dstart)
    required_stop = required_start + timedelta(seconds=ntimes * dt)

    for token in bry_tokens:
        resolved = resolve_referenced_path(context, token)
        if resolved is None:
            issues.append(f"boundary file referenced by BRYNAME cannot be resolved: {token}")
            continue
        report = check_boundary_coverage(resolved, required_start, required_stop)
        if not report.ok:
            issues.append(
                f"external boundary coverage {report.status} for {resolved} "
                f"(run window {required_start.isoformat()} -> {required_stop.isoformat()}): "
                + "; ".join(report.reasons)
            )
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

    expected_cpp_names: list[str] = []
    build_config_path = context.config_dir / "roms_build_config.json"
    build_config: dict[str, Any] = {}
    if build_config_path.exists():
        try:
            build_config = _load_json(build_config_path)
            variant_cpp = build_config.get("variants", {}).get(context.mode.build_variant, {}).get("roms_application")
            if variant_cpp:
                expected_cpp_names.append(str(variant_cpp).strip())
        except Exception:
            pass
    if context.mode.required_cpp_defs:
        variant_cfg = build_config.get("variants", {}).get(context.mode.build_variant, {})
        header_path = context.case_root / variant_cfg.get("header_dir", "run") / variant_cfg.get(
            "header_name", f"{context.case_name.lower()}.h"
        )
        if not header_path.exists():
            issues.append(f"missing CPP header for required tide macros: {header_path}")
        else:
            header_text = header_path.read_text(errors="ignore")
            for macro in context.mode.required_cpp_defs:
                defined = re.search(rf"^\s*#\s*define\s+{re.escape(macro)}(?:\s|$)", header_text, flags=re.MULTILINE)
                undefined = re.search(rf"^\s*#\s*undef\s+{re.escape(macro)}(?:\s|$)", header_text, flags=re.MULTILINE)
                if not defined or undefined:
                    issues.append(f"CPP header {header_path.name} does not define required macro {macro}")
        issues.extend(validate_tide_build_artifacts(context, binary))
    case_cpp = str(context.project_params.get("case", {}).get("cpp_name") or "").strip()
    if case_cpp:
        expected_cpp_names.append(case_cpp)
    expected_cpp_names = [name for index, name in enumerate(expected_cpp_names) if name and name not in expected_cpp_names[:index]]
    if expected_cpp_names and not metadata.my_app_cpp:
        issues.append(f"MyAppCPP missing: case expects one of {', '.join(expected_cpp_names)}")
    if metadata.my_app_cpp and expected_cpp_names and metadata.my_app_cpp not in expected_cpp_names:
        issues.append(f"MyAppCPP mismatch: infile={metadata.my_app_cpp}, case expects one of {', '.join(expected_cpp_names)}")
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
    issues.extend(
        validate_external_forcing_coverage(context, metadata, infile.read_text(errors="ignore"))
    )
    if any(context.mode.fallback_binaries):
        primary = context.paths.bin_dir / context.mode.binary_name
        if not primary.exists() and binary is not None:
            warnings.append(f"using fallback executable path: {binary}")
    issues.extend(validate_dimension_consistency(context, metadata))
    content_issues, content_warnings = validate_online_profile_content(context, metadata)
    issues.extend(content_issues)
    warnings.extend(content_warnings)
    formal_issues, formal_warnings = validate_formal_online_content(context, metadata)
    issues.extend(formal_issues)
    warnings.extend(formal_warnings)
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
