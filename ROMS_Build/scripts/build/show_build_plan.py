#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from build_context import build_environment, parse_cli, resolve_binary_candidates, resolve_build_context  # type: ignore  # noqa: E402


def main() -> None:
    args = parse_cli(sys.argv[1:])
    context = resolve_build_context(
        case_name=args.case_name,
        case_root=args.case_root,
        config_path=args.config,
        variant=args.variant,
    )
    plan = {
        "case_name": context.case_name,
        "case_root": str(context.case_root),
        "config": str(context.build_config_path),
        "variant": context.variant.name,
        "roms_application": context.variant.roms_application,
        "header": str(context.variant.header_path),
        "analytical_dir": str(context.variant.analytical_dir),
        "roms_src": str(context.roms_src),
        "build_dir": str(context.paths.build_dir),
        "bin_dir": str(context.paths.bin_dir),
        "expected_binary": str(context.expected_binary),
        "binary_candidates": [str(path) for path in resolve_binary_candidates(context)],
        "compiler": context.compiler,
        "environment": {
            key: value
            for key, value in build_environment(context).items()
            if key
            in {
                "ROMS_APPLICATION",
                "MY_HEADER_DIR",
                "MY_ANALYTICAL_DIR",
                "BUILD_DIR",
                "BINDIR",
                "FORT",
                "USE_MPI",
                "USE_MPIF90",
                "USE_PARALLEL_IO",
                "NETCDF",
                "HDF5",
                "MPI_ROOT",
            }
        },
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
