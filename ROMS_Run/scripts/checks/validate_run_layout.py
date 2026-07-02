#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from run_context import ensure_case_layout, parse_cli, resolve_run_context  # type: ignore  # noqa: E402


def main() -> None:
    base = parse_cli(sys.argv[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-name", default=base.case_name)
    parser.add_argument("--case-root", default=base.case_root)
    parser.add_argument("--config", default=base.config)
    parser.add_argument("--mode", default=base.mode)
    parser.add_argument("--fix", action="store_true", help="Create missing standard directories")
    args = parser.parse_args()

    context = resolve_run_context(
        case_name=args.case_name,
        case_root=args.case_root,
        config_path=args.config,
        mode=args.mode,
    )
    if args.fix:
        ensure_case_layout(context)
    dirs = {
        "run": context.paths.run_dir,
        "input": context.paths.input_dir,
        "output": context.paths.output_dir,
        "logs": context.paths.logs_dir,
        "build": context.paths.build_root,
        "bin": context.paths.bin_dir,
    }
    missing = False
    for label, path in dirs.items():
        exists = path.exists()
        print(f"[{'OK' if exists else 'MISSING'}] {label}: {path}")
        if not exists:
            missing = True
    raise SystemExit(1 if missing else 0)


if __name__ == "__main__":
    main()
