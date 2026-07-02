#!/usr/bin/env python3
from pathlib import Path
import sys

CORE_DIR = Path(__file__).resolve().parents[2] / 'core'
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from entrypoint_runner import run_entrypoint


if __name__ == "__main__":
    run_entrypoint('smooth_bathymetry.py')
