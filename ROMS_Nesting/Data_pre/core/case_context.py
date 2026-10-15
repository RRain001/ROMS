#!/usr/bin/env python3
"""Case-aware path resolution for shared ROMS preprocessing entrypoints."""

from __future__ import annotations

import argparse
import os
import json
from dataclasses import dataclass
from pathlib import Path


DATA_PRE_ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = DATA_PRE_ROOT / "cases"
PROJECTS_ROOT = DATA_PRE_ROOT.parents[0] / "projects"
DEFAULT_CASE_FILE = CASES_ROOT / "default_case.txt"

#: Environment variable the case configuration files expand as ``${ROMS_NESTING_ROOT}``.
NESTING_ROOT_ENV = "ROMS_NESTING_ROOT"

#: Directories that identify a checkout as a ROMS nesting tree.
NESTING_ROOT_MARKERS = ("Data_pre", "ROMS_Build", "ROMS_Run")


def default_nesting_root() -> Path:
    """The checkout this module was imported from."""
    return DATA_PRE_ROOT.parent


def is_nesting_root(path: Path | str) -> bool:
    candidate = Path(path)
    return candidate.is_dir() and all((candidate / marker).is_dir() for marker in NESTING_ROOT_MARKERS)


def init_nesting_root() -> Path:
    """Resolve ``ROMS_NESTING_ROOT`` once, at an explicit initialisation point.

    Importing this module must not mutate the process environment.  Callers that
    need ``${ROMS_NESTING_ROOT}`` expanded (the build and run frameworks, and the
    preprocessing entrypoints) call this first.

    The value must name *this* checkout.  Pointing it at a different tree is
    refused rather than honoured: `DATA_PRE_ROOT`, `CASES_ROOT` and the
    implementation directory stay relative to the Python modules that are
    actually running, so accepting another root would silently pair one tree's
    code and configuration with another tree's data.  Any mismatch -- a typo, a
    plain directory, a stale export, a second checkout -- fails closed instead
    of being silently replaced.  Because the root is resolved once and every
    consumer reads it back from the environment, one process never mixes two
    different worktrees.
    """
    default = default_nesting_root().resolve()
    configured = (os.environ.get(NESTING_ROOT_ENV) or "").strip()
    if not configured:
        root = default
    else:
        candidate = Path(configured).expanduser()
        candidate = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()
        if not is_nesting_root(candidate):
            raise SystemExit(
                f"{NESTING_ROOT_ENV}={configured!r} is not a ROMS nesting checkout: "
                f"expected {', '.join(NESTING_ROOT_MARKERS)} under {candidate}. "
                f"This checkout is {default}. Unset it or point it at a real nesting tree."
            )
        if candidate != default:
            raise SystemExit(
                f"{NESTING_ROOT_ENV}={configured!r} names a different checkout than the running "
                f"code ({default}). Cross-checkout rebinding is not supported: the Data_pre cases "
                "root and the implementation directory stay relative to the running modules, so "
                "this would mix one tree's configuration with another tree's data. "
                f"Run from {candidate} instead, or unset {NESTING_ROOT_ENV}."
            )
        root = candidate
    os.environ[NESTING_ROOT_ENV] = str(root)
    return root


@dataclass(frozen=True)
class CaseContext:
    case_name: str
    case_root: Path
    case_dir: Path
    config_dir: Path
    docs_dir: Path
    manifests_dir: Path


def _normalize_case_name(name: str | None) -> str:
    value = (name or _discover_default_case_name()).strip()
    if not value:
        return _discover_default_case_name()
    return value


def _discover_default_case_name() -> str:
    env_name = (os.environ.get("ROMS_CASE_NAME") or "").strip()
    if env_name:
        return env_name
    if DEFAULT_CASE_FILE.exists():
        configured = DEFAULT_CASE_FILE.read_text().strip()
        if configured:
            return configured
    case_names = sorted(
        path.name
        for path in CASES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    )
    if len(case_names) == 1:
        return case_names[0]
    raise SystemExit("unable to infer default case; pass --case-name or set ROMS_CASE_NAME")


def resolve_case_context(case_name: str | None = None, case_root: str | Path | None = None) -> CaseContext:
    # Explicit initialisation point: ``paths.case_root`` in project_parameters.json
    # expands ${ROMS_NESTING_ROOT}, so the root must be resolved *before* any case
    # configuration is read.  Importing this module does not do it for you.
    init_nesting_root()
    resolved_name = _normalize_case_name(case_name or os.environ.get("ROMS_CASE_NAME"))
    resolved_root = case_root or os.environ.get("ROMS_CASE_ROOT")
    case_dir = (CASES_ROOT / resolved_name).resolve()
    config_dir = case_dir / "config"
    if resolved_root:
        project_root = Path(resolved_root).expanduser().resolve()
    else:
        project_root = _configured_case_root(config_dir / "project_parameters.json", resolved_name)
    return CaseContext(
        case_name=resolved_name,
        case_root=project_root,
        case_dir=case_dir,
        config_dir=config_dir,
        docs_dir=case_dir / "docs",
        manifests_dir=case_dir / "manifests",
    )


def _configured_case_root(project_params_path: Path, case_name: str) -> Path:
    if project_params_path.exists():
        try:
            params = json.loads(project_params_path.read_text())
            configured = params.get("paths", {}).get("case_root") or params.get("paths", {}).get("project_dir")
            if configured:
                expanded = os.path.expandvars(os.path.expanduser(str(configured)))
                if "${" in expanded:
                    raise SystemExit(
                        f"unresolved variable in paths.case_root: {configured!r}. "
                        f"Set {NESTING_ROOT_ENV} or call init_nesting_root() before reading the case configuration."
                    )
                return Path(expanded).resolve()
        except json.JSONDecodeError:
            pass
    return (PROJECTS_ROOT / case_name).resolve()


def export_case_context(context: CaseContext) -> CaseContext:
    os.environ["ROMS_DATA_PRE_ROOT"] = str(DATA_PRE_ROOT)
    os.environ["ROMS_CASE_NAME"] = context.case_name
    os.environ["ROMS_CASE_ROOT"] = str(context.case_root)
    os.environ["ROMS_CASE_DIR"] = str(context.case_dir)
    os.environ["ROMS_CASE_CONFIG_DIR"] = str(context.config_dir)
    os.environ["ROMS_CASE_DOCS_DIR"] = str(context.docs_dir)
    os.environ["ROMS_CASE_MANIFESTS_DIR"] = str(context.manifests_dir)
    return context


def current_case_context() -> CaseContext:
    return resolve_case_context()


def get_case_root() -> Path:
    return current_case_context().case_root


def get_case_dir() -> Path:
    return current_case_context().case_dir


def get_case_config_dir() -> Path:
    return current_case_context().config_dir


def get_case_config_path(name: str) -> Path:
    return get_case_config_dir() / name


def resolve_case_config_path(path: str | Path | None, default_name: str) -> Path:
    if path is None:
        return get_case_config_path(default_name)
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    config_candidate = get_case_config_dir() / candidate
    if config_candidate.exists():
        return config_candidate
    return get_case_root() / candidate


def parse_case_args(argv: list[str]) -> tuple[str | None, str | None, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--case-root", default=None)
    known, remaining = parser.parse_known_args(argv)
    return known.case_name, known.case_root, remaining
