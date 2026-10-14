#!/usr/bin/env python3
"""I8 source-level compatibility audit; never reports ROMS physics PASS.

Usage: python scripts/audit_thyng_offline.py --verify-upstream --expect-gap --output DIR
All GitHub upstream bytes are pinned to a commit AND independently checked by Git blob hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "roms_src" / "roms" / "ROMS"
MANIFEST = ROOT / "refs" / "thyng_offline_upstream.json"
LOCAL_IMPORTANT = [
    "Nonlinear/main3d_offline.F",
    "Nonlinear/set_massflux.F",
    "Nonlinear/set_zeta.F",
    "Nonlinear/ini_fields.F",
    "Nonlinear/set_data.F",
    "Nonlinear/set_depth.F",
    "Nonlinear/step3d_t.F",
    "Utility/get_2dfld.F",
    "Utility/get_3dfld.F",
    "Drivers/nl_roms.h",
    "Nonlinear/CMakeLists.txt",
    "External/varinfo.yaml",
    "Include/globaldefs.h",
]
SYMBOLS = {
    "OFFLINE_TPASSIVE": r"\bOFFLINE_TPASSIVE\b",
    "set_massflux_avg": r"\bset_massflux_avg\b",
    "set_avg_zeta": r"\bset_avg_zeta\b",
    "main3d_offline": r"\bmain3d_offline\b",
    "AKSCLIMATOLOGY": r"\bAKSCLIMATOLOGY\b",
}
UPSTREAM_PROBES = {
    "ROMS/Nonlinear/main3d_offline.F": ("OFFLINE_TPASSIVE", "set_massflux_avg", "set_avg_zeta", "step3d_t"),
    "ROMS/Nonlinear/set_massflux.F": ("set_massflux_avg", "Huon", "Hvom"),
    "ROMS/Nonlinear/set_zeta.F": ("set_avg_zeta",),
    "ROMS/External/varinfo-offline.dat": ("'zeta'", "'Huon'"),
}

def git_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()

def read_upstream(commit: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/kthyng/COAWST-ROMS-OIL/{commit}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "ROMS-nesting-I8-pinned-audit"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read()

def audit(verify_upstream: bool) -> dict:
    data = json.loads(MANIFEST.read_text())
    pinned = data["upstream_commit"]
    expected = data["files"]
    base = {}
    for relative in LOCAL_IMPORTANT:
        p = SOURCE / relative
        exists = p.is_file()
        content = p.read_bytes() if exists else b""
        base[relative] = {
            "present": exists,
            "local_git_blob_sha": git_sha(content) if exists else None,
            "bytes": len(content),
        }
    symbol_hits = {}
    # Scope to original Fortran/CPP source; don't accidentally count docs or this audit script.
    for symbol, rx in SYMBOLS.items():
        matchfiles = []
        for relative, stat in base.items():
            if stat["present"]:
                src = (SOURCE / relative).read_text(errors="replace")
                lines = [i + 1 for i, line in enumerate(src.splitlines()) if re.search(rx, line, re.IGNORECASE)]
                if lines:
                    matchfiles.append({"file": relative, "lines": lines[:16]})
        symbol_hits[symbol] = matchfiles
    evidence = {}
    for relative, upstream_sha in expected.items():
        local_rel = relative.removeprefix("ROMS/")
        local = base.get(local_rel)
        if local is None:
            p = SOURCE / local_rel
            content = p.read_bytes() if p.is_file() else b""
            local = {"present": p.is_file(), "local_git_blob_sha": git_sha(content) if p.is_file() else None}
        item = {
            "upstream_sha": upstream_sha, "local_present": local["present"],
            "local_sha": local["local_git_blob_sha"],
            "identical_bytes": local["local_git_blob_sha"] == upstream_sha,
        }
        if verify_upstream:
            raw = read_upstream(pinned, relative)
            actual = git_sha(raw)
            if actual != upstream_sha:
                raise RuntimeError(f"UPSTREAM_INTEGRITY_FAIL {relative}: actual {actual} != pinned {upstream_sha}")
            item["upstream_verified"] = True
            probes = UPSTREAM_PROBES.get(relative, ())
            missing = [probe for probe in probes if probe not in raw.decode("utf-8", "replace")]
            if missing:
                raise RuntimeError(f"UPSTREAM_CONTRACT_FAIL {relative}: missing {missing}")
            item["upstream_bytes"] = len(raw)
        else:
            item["upstream_verified"] = False
        evidence[relative] = item
    gaps = []
    if not base["Nonlinear/main3d_offline.F"]["present"]:
        gaps.append("MISSING_NONLINEAR_MAIN3D_OFFLINE")
    if not base["External/varinfo.yaml"]["present"]:
        gaps.append("MISSING_MODERN_VARINFO")
    if not any(x["file"] == "Nonlinear/set_massflux.F" for x in symbol_hits["set_massflux_avg"]):
        gaps.append("MISSING_SET_MASSFLUX_AVG")
    if not any(x["file"] == "Nonlinear/set_zeta.F" for x in symbol_hits["set_avg_zeta"]):
        gaps.append("MISSING_SET_AVG_ZETA")
    if not symbol_hits["OFFLINE_TPASSIVE"]:
        gaps.append("NO_OFFLINE_TPASSIVE_IN_SCANNED_PATHS")
    if not symbol_hits["AKSCLIMATOLOGY"]:
        gaps.append("NO_AKSCLIMATOLOGY_IN_SCANNED_PATHS")
    if not base["Drivers/nl_roms.h"]["present"]:
        gaps.append("NO_MODERN_DRIVER")
    # A present source symbol is not equivalent to a compiled and validated offline model.
    return {
        "schema_version": 1,
        "status": "BLOCKED_PORT_REQUIRED" if gaps else "SOURCE_SYMBOLS_PRESENT_UNVERIFIED",
        "physics_validation": "NOT_RUN",
        "upstream_commit": pinned,
        "model_codebase": "ROMS_Nesting/roms_src/roms (copied ROMS 4.3)",
        "upstream_checked_online": verify_upstream,
        "local_files": base,
        "upstream_files": evidence,
        "symbols": symbol_hits,
        "blocking_gaps": gaps,
        "next_actions": [
            "Map nonlinear driver call-chain and build system to new offline main3d routine.",
            "Design version-aware set_avg_zeta and time-averaged Huon/Hvom; do NOT overwrite modern set_massflux.",
            "Map offline climatology read into modern YAML varinfo and new get_2dfld/get_3dfld.",
            "Port salinity diffusivity Aks input and match step3d_t/online schemes.",
            "Compile synthetic single-grid offline ROMS with explicit CPP echo; then test physics.",
            "Only after single-grid offline equivalence address conservative inter-grid tracer fluxes.",
        ],
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--verify-upstream", action="store_true")
    p.add_argument("--expect-gap", action="store_true", help="Fail if old code unexpectedly appears ready, or gap contract changes.")
    p.add_argument("--output", type=Path, default=ROOT / "projects" / "JAPAN_SEA" / "reports" / "thyng_i8")
    args = p.parse_args()
    out = audit(args.verify_upstream)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "compatibility.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# Thyng 2021 → ROMS 4.3 I8 source compatibility report",
        "", "**Status: " + out["status"] + "**; physical ROMS offline tests: **NOT_RUN**.",
        "",
        f"Pinned upstream commit: \`{out['upstream_commit']}\`.",
        f"Upstream integrity checked: {args.verify_upstream}.",
        "", "## Verified source gap list", "",
    ]
    lines.extend("- " + x for x in out["blocking_gaps"])
    lines.extend(["", "## Key upstream/local source comparison", "",
                  "| Upstream file | Upstream SHA | Local file | Byte-identical |",
                  "| --- | --- | --- | --- |"])
    for name, entry in out["upstream_files"].items():
        lines.append(f"| \`{name}\` | \`{entry['upstream_sha'][:12]}\` | {'present' if entry['local_present'] else 'MISSING'} | {entry['identical_bytes']} |")
    lines.extend(["", "## Work required", ""])
    lines.extend("- " + x for x in out["next_actions"])
    (args.output / "compatibility.md").write_text("\n".join(lines) + "\n")
    print(f"I8 source audit: {out['status']} ({len(out['blocking_gaps'])} gaps); physical validation NOT_RUN")
    for gap in out["blocking_gaps"]:
        print("  " + gap)
    if args.expect_gap:
        required = {"MISSING_NONLINEAR_MAIN3D_OFFLINE"}
        resolved = {"MISSING_SET_AVG_ZETA", "MISSING_SET_MASSFLUX_AVG"}
        if not required.issubset(out["blocking_gaps"]) or resolved.intersection(out["blocking_gaps"]):
            print("I8 expected remaining offline driver gap and both native zeta/flux adapters", file=sys.stderr)
            return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
