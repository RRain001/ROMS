#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from build_context import parse_cli, resolve_binary_candidates, resolve_build_context  # type: ignore  # noqa: E402


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
    print(f"case: {context.case_name}")
    print(f"variant: {context.variant.name}")
    for index, candidate in enumerate(resolve_binary_candidates(context)):
        exists = candidate.exists()
        role = "primary" if index == 0 else "fallback"
        print(f"{role}_candidate: {candidate}")
        print(f"  exists: {exists}")
        if not exists:
            continue
        stat = candidate.stat()
        print(f"  size_bytes: {stat.st_size}")
        print(f"  mtime: {datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}")
        print(f"  executable: {os.access(candidate, os.X_OK)}")
        probe = subprocess.run(["ldd", str(candidate)], text=True, capture_output=True, check=False)
        if probe.returncode == 0:
            print("  ldd:")
            for line in probe.stdout.strip().splitlines():
                print(f"    {line}")
        else:
            detail = (probe.stderr or probe.stdout).strip()
            if detail:
                print(f"  ldd_unavailable: {detail}")


if __name__ == "__main__":
    main()
