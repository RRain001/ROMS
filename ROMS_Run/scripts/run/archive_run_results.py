#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from run_context import parse_cli, resolve_binary_path, resolve_run_context  # type: ignore  # noqa: E402


def main() -> None:
    base = parse_cli(sys.argv[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-name", default=base.case_name)
    parser.add_argument("--case-root", default=base.case_root)
    parser.add_argument("--config", default=base.config)
    parser.add_argument("--mode", default=base.mode)
    parser.add_argument("--name", default=None, help="Optional archive suffix")
    args = parser.parse_args()

    context = resolve_run_context(
        case_name=args.case_name,
        case_root=args.case_root,
        config_path=args.config,
        mode=args.mode,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.name}" if args.name else ""
    archive_dir = context.paths.logs_dir / "archive" / f"{stamp}_{context.mode.name}{suffix}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    if context.mode.log_file.exists():
        dst = archive_dir / context.mode.log_file.name
        shutil.copy2(context.mode.log_file, dst)
        copied.append(dst)
    if context.mode.infile.exists():
        dst = archive_dir / context.mode.infile.name
        shutil.copy2(context.mode.infile, dst)
        copied.append(dst)

    summary = archive_dir / "summary.txt"
    binary = resolve_binary_path(context)
    output_listing = sorted(path.name for path in context.paths.output_dir.glob("*.nc"))
    summary.write_text(
        "\n".join(
            [
                f"case: {context.case_name}",
                f"mode: {context.mode.name}",
                f"infile: {context.mode.infile}",
                f"binary: {binary or 'missing'}",
                f"log_file: {context.mode.log_file}",
                f"outputs: {', '.join(output_listing) if output_listing else 'none'}",
            ]
        )
        + "\n"
    )
    copied.append(summary)
    print(f"archive: {archive_dir}")
    for path in copied:
        print(f"- {path}")


if __name__ == "__main__":
    main()
