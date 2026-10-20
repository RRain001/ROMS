#!/usr/bin/env python3
"""Export a separate Japanese Sea core-connected ES3K mask candidate."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"nesting"))
from es3k_core_component_filter import core_component_only_candidate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report-json",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(core_component_only_candidate(a.grid,a.output,a.report_json),
                     indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
