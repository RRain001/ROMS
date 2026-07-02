#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from build_context import parse_cli, probe_shell_command, resolve_build_context  # type: ignore  # noqa: E402


def main() -> None:
    args = parse_cli(sys.argv[1:])
    context = resolve_build_context(
        case_name=args.case_name,
        case_root=args.case_root,
        config_path=args.config,
        variant=args.variant,
    )
    checks: list[tuple[str, bool, str]] = []
    checks.append(("roms_src", context.roms_src.exists(), str(context.roms_src)))
    checks.append(("header", context.variant.header_path.exists(), str(context.variant.header_path)))
    checks.append(("header_dir", context.variant.header_dir.exists(), str(context.variant.header_dir)))
    checks.append(("analytical_dir", context.variant.analytical_dir.exists(), str(context.variant.analytical_dir)))
    if context.netcdf_root is not None:
        checks.append(("netcdf_root", context.netcdf_root.exists(), str(context.netcdf_root)))
    if context.hdf5_root is not None:
        checks.append(("hdf5_root", context.hdf5_root.exists(), str(context.hdf5_root)))
    if context.mpi_root is not None:
        checks.append(("mpi_root", context.mpi_root.exists(), str(context.mpi_root)))
    if context.oneapi_setvars is not None:
        checks.append(("oneapi_setvars", context.oneapi_setvars.exists(), str(context.oneapi_setvars)))
    if context.my_local_paths is not None:
        checks.append(("my_local_paths", context.my_local_paths.exists(), str(context.my_local_paths)))
    fort = context.compiler.get("fort")
    if fort:
        checks.append((f"compiler:{fort}", shutil.which(str(fort)) is not None, shutil.which(str(fort)) or "not on current PATH"))
        probe = probe_shell_command(context, f"command -v {fort}")
        checks.append((f"compiler:{fort}:shell_probe", probe.returncode == 0, (probe.stdout or probe.stderr).strip() or "not found via shell probe"))
    if context.compiler.get("use_mpif90", True):
        probe = probe_shell_command(context, "command -v mpif90")
        checks.append(("mpif90:shell_probe", probe.returncode == 0, (probe.stdout or probe.stderr).strip() or "not found via shell probe"))

    failed = False
    print(f"case: {context.case_name}")
    print(f"variant: {context.variant.name}")
    for label, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        print(f"[{status}] {label}: {detail}")
        if not ok:
            failed = True
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
