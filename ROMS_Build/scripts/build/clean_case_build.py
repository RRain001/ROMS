#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from build_context import clean_build_tree, parse_cli, resolve_build_context  # type: ignore  # noqa: E402


def main() -> None:
    base = parse_cli(sys.argv[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-name", default=base.case_name)
    parser.add_argument("--case-root", default=base.case_root)
    parser.add_argument("--config", default=base.config)
    parser.add_argument("--variant", default=base.variant)
    args = parser.parse_args()

    context = resolve_build_context(
        case_name=args.case_name,
        case_root=args.case_root,
        config_path=args.config,
        variant=args.variant,
    )
    clean_build_tree(context)
    print(f"cleaned build tree: {context.paths.build_root}")


if __name__ == "__main__":
    main()
