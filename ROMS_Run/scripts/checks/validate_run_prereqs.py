#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from run_context import parse_cli, resolve_binary_path, resolve_run_context, validate_prereqs  # type: ignore  # noqa: E402


def main() -> None:
    base = parse_cli(sys.argv[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-name", default=base.case_name)
    parser.add_argument("--case-root", default=base.case_root)
    parser.add_argument("--config", default=base.config)
    parser.add_argument("--mode", default=base.mode)
    args = parser.parse_args()

    context = resolve_run_context(
        case_name=args.case_name,
        case_root=args.case_root,
        config_path=args.config,
        mode=args.mode,
    )
    issues, warnings, metadata = validate_prereqs(context)
    print(f"case: {context.case_name}")
    print(f"mode: {context.mode.name}")
    print(f"infile: {context.mode.infile}")
    print(f"binary: {resolve_binary_path(context) or 'missing'}")
    print(f"MyAppCPP: {metadata.my_app_cpp or 'missing'}")
    print(f"required_np: {metadata.required_np if metadata.required_np is not None else 'unknown'}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")
    if issues:
        print("issues:")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)
    print("status: OK")


if __name__ == "__main__":
    main()
