#!/usr/bin/env python3
"""Audit/register an archived test grid, then use the existing .in generator."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'core'))
from external_test_case import prepare

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-name',required=True)
    p.add_argument('--source-grid',required=True,type=Path)
    a=p.parse_args()
    r=prepare(a.case_name,a.source_grid)
    print(json.dumps({k:r[k] for k in ['status','active_grid','active_sha256','rho_shape','wet_rho','rx0','rx1','orthogonality_max_deg']},indent=2))
