#!/usr/bin/env python3
"""Repair spherical ROMS metrics in a new file; never overwrite an existing file."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from grid_metrics import compute_grid_metrics, METRIC_NAMES, METHOD


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stats(values: np.ndarray) -> dict:
    values = np.asarray(np.ma.filled(values, np.nan), dtype=float)
    finite = values[np.isfinite(values)]
    return {"min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
            "mean": float(finite.mean()) if finite.size else None,
            "nonfinite_count": int(values.size - finite.size)}


def equal(a, b) -> bool:
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and (np.array_equal(a, b, equal_nan=True)
                                   if a.dtype.kind in "fc" and b.dtype.kind in "fc"
                                   else np.array_equal(a, b))


def verify_unchanged(source: Path, repaired: Path) -> list[str]:
    """Check raw values (including fill/packed data), metadata and storage layout."""
    checked = []
    def compare(a, b, prefix=""):
        if set(a.dimensions) != set(b.dimensions) or set(a.variables) != set(b.variables) or set(a.groups) != set(b.groups):
            raise ValueError("unexpected dimension/variable/group changes")
        for name, dim in a.dimensions.items():
            if len(dim) != len(b.dimensions[name]) or dim.isunlimited() != b.dimensions[name].isunlimited():
                raise ValueError(f"dimension changed: {prefix}{name}")
        allowed = {"grid_metrics_repair"} if not prefix else set()
        if set(a.ncattrs()) - allowed != set(b.ncattrs()) - allowed:
            raise ValueError("unexpected global metadata changes")
        for name in set(a.ncattrs()) - allowed:
            if not equal(a.getncattr(name), b.getncattr(name)):
                raise ValueError(f"global attribute changed: {name}")
        for name, var in a.variables.items():
            other = b.variables[name]
            if var.dtype != other.dtype or var.dimensions != other.dimensions or var.ncattrs() != other.ncattrs():
                raise ValueError(f"variable schema changed: {prefix}{name}")
            if var.filters() != other.filters() or var.chunking() != other.chunking() or var.endian() != other.endian():
                raise ValueError(f"variable storage changed: {prefix}{name}")
            for attr in var.ncattrs():
                if not equal(var.getncattr(attr), other.getncattr(attr)):
                    raise ValueError(f"variable attribute changed: {prefix}{name}:{attr}")
            if not prefix and name in METRIC_NAMES:
                continue
            var.set_auto_maskandscale(False)
            other.set_auto_maskandscale(False)
            if not equal(var[:], other[:]):
                raise ValueError(f"non-target data changed: {prefix}{name}")
            checked.append(prefix + name)
        for name in a.groups:
            compare(a.groups[name], b.groups[name], prefix + name + "/")
    with Dataset(source) as a, Dataset(repaired) as b:
        if a.data_model != b.data_model:
            raise ValueError("NetCDF format changed")
        compare(a, b)
    return checked


def repair(input_path: Path, output_path: Path, *, dry_run=False, report_path: Path | None = None) -> dict:
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    report_path = Path(report_path).resolve() if report_path else Path(str(output_path) + ".audit.json")
    if input_path == output_path or output_path.exists():
        raise ValueError("output must be a new file, distinct from input (in-place repair is forbidden)")
    if report_path in (input_path, output_path) or report_path.exists():
        raise ValueError("audit report must also be a new, distinct file")
    before_hash = sha256(input_path)
    with Dataset(input_path) as ds:
        spherical = ds.variables.get("spherical")
        if spherical is None or str(np.asarray(spherical[:]).item()).lower() not in ("1", "t", "true", "b't'"):
            raise ValueError("repair requires spherical=T/1; Cartesian metrics cannot be inferred from lon/lat")
        dims = ds.variables["lon_rho"].dimensions
        if dims != ("eta_rho", "xi_rho") or ds.variables["lat_rho"].dimensions != dims:
            raise ValueError("expected lon/lat dimensions (eta_rho, xi_rho)")
        metrics = compute_grid_metrics(ds.variables["lon_rho"][:], ds.variables["lat_rho"][:])
        old = {}
        for name in METRIC_NAMES:
            var = ds.variables[name]
            if var.dimensions != dims or var.dtype.kind != "f" or any(a in var.ncattrs() for a in ("scale_factor", "add_offset")):
                raise ValueError(f"unsupported metric schema: {name}; require unpacked floating RHO fields")
            old[name] = np.ma.filled(var[:], np.nan)
        report = {"input": str(input_path), "output": str(output_path), "method": METHOD,
                  "dry_run": dry_run, "input_sha256": before_hash, "output_sha256": None,
                  "fields": {}, "unchanged_variables": []}
        for name, values in metrics.items():
            cast = values.astype(ds.variables[name].dtype)
            delta = np.abs(cast - old[name])
            finite = delta[np.isfinite(delta)]
            report["fields"][name] = {"before": stats(old[name]), "after": stats(cast),
                "max_abs_change": float(finite.max()) if finite.size else None,
                "p95_abs_change": float(np.percentile(finite, 95)) if finite.size else None}
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(suffix=".nc", dir=output_path.parent)
        os.close(handle)
        tmp = Path(tmp)
        try:
            shutil.copyfile(input_path, tmp)  # preserves every encoding and non-target byte payload
            with Dataset(tmp, "r+") as ds:
                for name, values in metrics.items():
                    ds.variables[name][:] = values
                ds.grid_metrics_repair = json.dumps({"utc": datetime.now(timezone.utc).isoformat(),
                    "method": METHOD, "source_sha256": before_hash,
                    "auxiliary_coordinates": "x/y and xl/el preserved; not geodesic lengths"})
            report["unchanged_variables"] = verify_unchanged(input_path, tmp)
            with Dataset(tmp) as ds:
                for name, values in metrics.items():
                    if not equal(ds.variables[name][:], values.astype(ds.variables[name].dtype)):
                        raise ValueError(f"metric write verification failed: {name}")
            if sha256(input_path) != before_hash:
                raise ValueError("source changed during repair")
            report["output_sha256"] = sha256(tmp)
            # Atomic create without clobbering even if another process creates output.
            os.link(tmp, output_path)
        finally:
            tmp.unlink(missing_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="default: OUTPUT.audit.json (must not exist)")
    parser.add_argument("--dry-run", action="store_true", help="write audit only; output SHA256 is null")
    args = parser.parse_args()
    try:
        report = repair(args.input, args.output, dry_run=args.dry_run, report_path=args.report)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"repair failed: {exc}\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
