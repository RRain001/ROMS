"""Register a read-only source grid and prepare one isolated external-forcing case.

No ROMS source edits, online nesting, downloads or hydrodynamic launches.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from case_context import export_case_context, resolve_case_context
from roms_preprocessing_utils import VerticalConfig, compute_rx0_rx1, derive_staggered_masks


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def audit_grid(source: Path, params: dict, spec: dict) -> dict:
    fingerprint = sha256(source)
    if fingerprint != spec['source_sha256']:
        raise ValueError('source grid SHA256 does not match the archived provenance')
    from pyproj import Geod
    v = params['vertical']
    vertical = VerticalConfig(N=v['N'], theta_s=v['theta_s'], theta_b=v['theta_b'],
                             Tcline=v['Tcline_m'], Hmin_m=v['Hmin_m'],
                             Vtransform=v['Vtransform'], Vstretching=v['Vstretching'])
    with Dataset(source) as ds:
        if str(getattr(ds, 'synthetic_test_only', '')).upper() != 'FALSE':
            raise ValueError('grid must be explicitly labelled as real, not synthetic')
        if str(getattr(ds, 'actual_bathymetry_interpolated', '')).upper() != 'TRUE':
            raise ValueError('grid lacks real bathymetry provenance')
        fields = {}
        for name in ('h', 'lon_rho', 'lat_rho', 'lon_u', 'lat_u', 'lon_v', 'lat_v',
                     'lon_psi', 'lat_psi', 'pm', 'pn', 'dndx', 'dmde', 'f', 'angle',
                     'mask_rho', 'mask_u', 'mask_v', 'mask_psi'):
            a = np.ma.asarray(ds[name][:])
            if np.ma.getmaskarray(a).any() or not np.isfinite(a).all():
                raise ValueError(f'masked/nonfinite grid field {name}')
            fields[name] = np.asarray(a)
        h, mask = fields['h'], fields['mask_rho']
        nj, ni = h.shape
        if list(h.shape) != spec['rho_shape'] or not np.isin(mask, [0, 1]).all():
            raise ValueError('unexpected RHO dimensions or nonbinary mask')
        for name in ('h', 'lat_rho', 'lon_rho', 'pm', 'pn', 'dndx', 'dmde', 'f', 'angle'):
            if fields[name].shape != (nj, ni):
                raise ValueError(f'invalid RHO shape {name}')
        for loc, shape in [('u', (nj, ni-1)), ('v', (nj-1, ni)), ('psi', (nj-1, ni-1))]:
            for prefix in ('lon_', 'lat_', 'mask_'):
                if fields[prefix+loc].shape != shape:
                    raise ValueError(f'invalid C-grid shape {prefix+loc}')
        for name, expected in zip(('mask_u', 'mask_v', 'mask_psi'), derive_staggered_masks(mask)):
            if not np.array_equal(fields[name], expected):
                raise ValueError(f'native {name} disagrees with RHO wet neighbours')
        wet = mask == 1
        if int(wet.sum()) != spec['wet_rho_points'] or np.min(h[wet]) < vertical.Hmin_m:
            raise ValueError('wet count or minimum wet depth changed')
        if not ((fields['pm'] > 0).all() and (fields['pn'] > 0).all()):
            raise ValueError('nonpositive metric')
        lon, lat = fields['lon_rho'], fields['lat_rho']
        geod = Geod(ellps='WGS84')
        ax, _, dx = geod.inv(lon[:, :-1], lat[:, :-1], lon[:, 1:], lat[:, 1:])
        ay, _, dy = geod.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
        orth = np.rad2deg(np.arcsin(np.clip(np.abs(np.cos(np.deg2rad(ax[:-1]-ay[:, :-1]))), 0, 1)))
        if min(dx.min(), dy.min()) <= 0 or orth.max() > spec['max_orthogonality_deg']:
            raise ValueError('geometry spacing or orthogonality gate failed')
        corners = json.loads(ds.geometry_input_json)['user_corners_lat_lon']
        errors = {name:float(geod.inv(lon[j,i],lat[j,i],corners[name][1],corners[name][0])[2])
                  for name,(j,i) in {'W':(0,0),'S':(0,-1),'N':(-1,0),'E':(-1,-1)}.items()}
        if max(errors.values()) > 0.01:
            raise ValueError('grid no longer matches archived corners')
        expected_angle = np.deg2rad(90-ax)
        angle_error = np.max(np.abs(np.arctan2(np.sin(fields['angle'][:,:-1]-expected_angle),
                                             np.cos(fields['angle'][:,:-1]-expected_angle))))
        if angle_error > 1e-8 or not np.allclose(fields['f'],2*7.2921159e-5*np.sin(np.deg2rad(lat)),rtol=1e-10):
            raise ValueError('angle/Coriolis mismatch')
        rx0, rx1 = compute_rx0_rx1(h, mask, vertical)
        if rx0 > spec['max_rx0'] or rx1 > spec['max_rx1']:
            raise ValueError('41-layer stiffness gate failed')
        boundaries = {}
        for side,sel in [('west',np.s_[:,0]),('east',np.s_[:,-1]),('south',np.s_[0,:]),('north',np.s_[-1,:])]:
            wh=h[sel][wet[sel]]
            boundaries[side]={'wet_rho':int(wh.size),'depth_min_m':float(wh.min()) if wh.size else None,
                              'depth_max_m':float(wh.max()) if wh.size else None}
        spacing_claim = str(ds.angular_spacing_claim)
    # Existing wet-domain implementation, independently re-evaluated on the recovered file.
    nesting = Path(__file__).resolve().parents[1]/'nesting'
    sys.path.insert(0,str(nesting))
    from es3k_wet_domain_audit import audit_grid as wet_audit
    wet_report = wet_audit(source)
    if wet_report['wet_connected_component_count_4_neighbor'] != 1:
        raise ValueError('active test domain must be one connected wet component')
    if not all(wet_report['strait_window_connected_to_core'].values()):
        raise ValueError('a strait proxy window lost connectivity')
    return dict(status='STATIC_TEST_GRID_ADMISSION_PASS_NOT_PHYSICAL_ACCEPTANCE',
                source=str(source.resolve()),sha256=fingerprint,rho_shape=[nj,ni],
                wet_rho=int(wet.sum()),rx0=rx0,rx1=rx1,orthogonality_max_deg=float(orth.max()),
                corner_error_m=errors,angle_error_rad=float(angle_error),
                dx_range_m=[float(dx.min()),float(dx.max())],dy_range_m=[float(dy.min()),float(dy.max())],
                wet_depth_range_m=[float(h[wet].min()),float(h[wet].max())],
                boundaries=boundaries,wet_domain_audit=wet_report,
                angular_spacing_claim=spacing_claim,
                scientific_limitations=['archived smoothed candidate admitted for local tests only',
                  'nominal angular resolution is a local metric equivalent, not an exact rotated 1/36-degree system',
                  'historical smoothing can alter depth by ~1943m; no new smoothing performed',
                  'strait windows are proxies; shoreline not exhaustively revalidated',
                  'hydrodynamics and parent-child transport NOT_RUN'])


def copy_unchanged(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        raise ValueError('source and destination must differ')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != sha256(source):
            raise FileExistsError(f'refuse to replace existing artifact: {target}')
    else:
        shutil.copy2(source,target)
    if sha256(source) != sha256(target):
        raise ValueError('copy checksum mismatch')


def prepare(case_name: str, source: Path) -> dict:
    ctx=export_case_context(resolve_case_context(case_name))
    params=json.loads((ctx.config_dir/'project_parameters.json').read_text())
    spec=json.loads((ctx.config_dir/'external_test_config.json').read_text())
    report=audit_grid(source,params,spec['grid'])
    active=ctx.case_root/params['paths']['active_grid']
    copy_unchanged(source,active)
    report.update(active_grid=str(active),active_sha256=sha256(active),archive=spec['grid']['archive'],
                  purpose='TEST_ONLY_NOT_GRID_DESIGN_APPROVAL')
    logs=ctx.case_root/'logs/external_test';logs.mkdir(parents=True,exist_ok=True)
    (logs/'active_grid_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    template=ctx.case_dir/'templates'/spec['header_template']
    copy_unchanged(template,ctx.case_root/'run'/spec['header_template'])
    entry=Path(__file__).resolve().parents[1]/'scripts'/'run_support'/'create_pilot_infile.py'
    # Existing public single-grid entry point is the only .in generator.
    for mode in spec['modes']:
        cmd=[sys.executable,str(entry),'--case-name',case_name,'--mode',mode,
             '--forcing-mode','external','--ocean-source','glorys12v1','--grid',str(active),
             '--start-time',spec['test_start'],'--stop-time',spec['test_stop'],
             '--dt-seconds',str(spec['dt_seconds'])]
        for key,value in spec['forcing_paths'].items():
            cmd += ['--'+key.replace('_','-')+'-path',value]
        p=subprocess.run(cmd,text=True,capture_output=True)
        (logs/(mode+'_generation.log')).write_text(p.stdout+p.stderr)
        if p.returncode:
            raise RuntimeError(f'existing infile generator failed for {mode}: {p.stdout}{p.stderr}')
    return report
