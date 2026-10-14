#!/usr/bin/env python3
"""Thin runner that dispatches public/legacy entrypoints to shared implementations."""

from __future__ import annotations

from pathlib import Path
import sys

from case_context import DATA_PRE_ROOT, export_case_context, parse_case_args, resolve_case_context


IMPLEMENTATION_DIR = DATA_PRE_ROOT / "impl" / "preprocessing"
CORE_DIR = DATA_PRE_ROOT / "core"


def run_entrypoint(script_name: str) -> None:
    impl_path = IMPLEMENTATION_DIR / script_name
    if not impl_path.exists():
        raise SystemExit(f"implementation not found: {impl_path}")

    case_name, case_root, remaining = parse_case_args(sys.argv[1:])
    context = export_case_context(resolve_case_context(case_name=case_name, case_root=case_root))

    if any(arg in {"-h", "--help"} for arg in remaining):
        print("Shared wrapper options:")
        print("  --case-name CASE_NAME")
        print("  --case-root /path/to/project")
        print()

    for candidate in (str(CORE_DIR), str(IMPLEMENTATION_DIR)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    fake_file = context.case_root / "preprocessing" / script_name
    sys.argv = [str(fake_file)] + remaining
    globals_dict = {
        "__name__": "__main__",
        "__file__": str(fake_file),
        "__package__": None,
        "__cached__": None,
    }
    code = compile(impl_path.read_text(), str(fake_file), "exec")
    exec(code, globals_dict)
