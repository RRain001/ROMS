#!/usr/bin/env python3
from pathlib import Path
import sys

CORE_DIR = Path('/home/lhy/ROMS/Data_pre/core')
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from entrypoint_runner import run_entrypoint


if __name__ == "__main__":
    run_entrypoint('stage_source_discharge.py')
