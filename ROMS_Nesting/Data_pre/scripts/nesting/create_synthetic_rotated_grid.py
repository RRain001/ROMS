#!/usr/bin/env python3
"""Generate ONLY a small synthetic ROMS grid for I2 rotation tests."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "nesting"))
from rotated_grid import RotatedGridSpec, write_synthetic_grid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--angle-deg", type=float, default=20.0)
    parser.add_argument("--nx", type=int, default=11)
    parser.add_argument("--ny", type=int, default=9)
    args = parser.parse_args()
    spec = RotatedGridSpec(center_lon=131.3, center_lat=37.6, width_points=args.nx,
                           height_points=args.ny, dx_m=3000.0, dy_m=3000.0,
                           angle_deg=args.angle_deg)
    results = write_synthetic_grid(Path(args.output), spec)
    print(json.dumps({"status": "SYNTHETIC_ONLY", **results}, indent=2))


if __name__ == "__main__":
    main()
