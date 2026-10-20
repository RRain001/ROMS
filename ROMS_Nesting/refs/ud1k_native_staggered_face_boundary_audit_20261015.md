# Current UD1K native U/V wet-face one-way boundary mapping audit — 2026-10-15

## Approved geometry stays unchanged

Original user-selected current UD1K: **290×438 RHO** exact 1/108° anchored W/S, native 15″ GEBCO 2026 bathymetry, GSHHG v2.3.7 High Level 1 and ES3K connected smoothed parent. Nothing here changes `main`, the active UD1K scope, `mask_rho`, `mask_u`, `mask_v`, the native RHO shoreline or parent bathymetry. All modifications remain Draft PR #3, not merged.

## Strict distinction: RHO receiver vs actual native face receiver

Earlier work validated **1,017 current UD1K wet RHO perimeter receivers** under coastline-aware static scalar stencils and source RHO-collocated vector diagnostics. These are *not* actual ROMS U/V-face coordinates.

[`ud1k_staggered_face_map.py`](../Data_pre/nesting/ud1k_staggered_face_map.py) now reads **actual** child `lon_u,lat_u,mask_u` (shape **290×437**) and `lon_v,lat_v,mask_v` (shape **289×438**), calculates the **unique wet C-grid perimeter** at each native face geometry, and builds *independent* source weights. It uses parent ES3K RHO locations which have confirmed both native wet U and V face support, so that the upstream vector can be collocated and angle-rotated at each child *face* coordinate. First choice is non-land-crossing bilinear all-supported parent quad, then valid three-wet triangle inside one parent quad, finally bounded wet-connected coast-visible inverse-distance fallback. This still uses **collocated ES3K RHO sources** as a staging technique rather than fully independent direct parent-U and parent-V component interpolation.

**Real native 15″ result:** [Actions #38673083639](https://github.com/RRain001/ROMS/actions/runs/38673083639), SUCCESS:

| Measure | U face | V face |
| --- | ---: | ---: |
| Native wet C-grid perimeter faces | **1010** | **1015** |
| Fully supported 4-parent-RHO bilinear | 982 | 979 |
| Local 3-wet/face-supported enclosed triangle | 12 | 14 |
| Bounded multi-wet coast-visible extrapolation | 15 | 20 |
| Bounded single-wet coast-visible extrapolation | 1 | 1 |
| Still missing face-supported RHO donors | **0** | **1** |

Logical wet-face sides, inclusive of overlapping corner cells: U south 381, north 363, east 267, west 0; V south 385, north 364, east 266, west 0. The only unresolved native V receiver is zero-based **`(eta_v=0,xi_v=30)`**, at **128.643305555556°E, 34.970101851852°N**, on the southern boundary.

**Face blocked, not silently filled.** At 2.5 median ES3K cells (**6712.595 m**), 4 nearby source ES3K wet/face-supported RHO locations all require crossing GSHHG coastline to reach this one V receiver. Do not create fictitious zero velocity, assume the V face dry, or change current domain based on this alone.

## True parent native face source review

[`ud1k_native_face_component_review.py`](../Data_pre/nesting/ud1k_native_face_component_review.py) separately checks **actual parent `lon_u,lat_u,mask_u` and `lon_v,lat_v,mask_v` source face components** under the same 2.5-cell GSHHG line-of-sight distance. [Actions #38673790216](https://github.com/RRain001/ROMS/actions/runs/38673790216) SUCCESS for the diagnostic, outcome:

- U component: 2 ES3K native wet U source faces within 6712.6 m, 1 intersects shoreline, **1 visible** at parent U `(48,262)`, ~**5360.54 m** away (only one donor, high uncertainty).
- V component: 3 ES3K native wet V source faces within 6712.6 m, **all 3 intersect shoreline**; no valid native source under that radius.
- Both components simultaneously safe? **No.** The original child V `(0,30)` remains **HOLD**. This is scientific source-support evidence, not a runtime failure of ROMS.

## Native child C-grid wet-face actual coastline crossing

A separate test [`ud1k_native_face_shoreline_topology.py`](../Data_pre/nesting/ud1k_native_face_shoreline_topology.py) checks the GSHHG L1 coastline against the straight geographic segment connecting the two adjacent wet RHO points that mathematically form every native `mask_u=1` or `mask_v=1` perimeter face.

[Real native Actions #38674485051](https://github.com/RRain001/ROMS/actions/runs/38674485051), SUCCESS:

- **U crossing (1):** face `(eta_u=23,xi_u=436)`, east side.
- **V crossings (3):** `(eta_v=0,xi_v=40)`, `(0,42)` on south side, and `(23,437)` east side.
- The **one unsupported V receiver `(0,30)` does NOT** itself cross the tested GSHHG coastline along its defining RHO-to-RHO segment.

**Critical distinction:** the four crossing faces are not automatically changed to land. These warrant local coastline-resolution and face-mask consistency review. An independent successful donor-mapping diagnostic does not prove waterway connectivity at a face if its RHO-neighbor segment intersects the coastline.

## Scope and physics still missing

- [`ud1k_vertical_flux_primitives.py`](../Data_pre/nesting/ud1k_vertical_flux_primitives.py) implements testable standard ROMS Vtransform=2/Vstretching=4 physical depths, profile remapping in physical z (explicitly counts out-of-range clamps), Hz-weighted barotropic velocity, and section normal-volume-flux primitives. This is a **pure numerical implementation**, not actual vertical-boundary forcing; no production vertical parameters or ES3K history are supplied.
- Need true time-varying ES3K `u,v,zeta,temp,salt`, correctly collocated/rotated U/V and 2D `ubar/vbar`, correct sigma levels and time axes, flux/transport matching, actual complete ROMS `bry.nc` and dynamic 1h/6h/24h/7d runs. **All NOT_RUN**.
- The last one native V face is subject to additional **read-only radius sensitivity** ([`ud1k_single_v_face_radius_sensitivity.py`](../Data_pre/nesting/ud1k_single_v_face_radius_sensitivity.py)), fixed 2.5/3.0/3.5/4.0/5.0 cells; stricter geometry and real shorelines are never bypassed, and no widened donor is promoted automatically.

**Decision:** hold `V(0,30)` rather than an unsafe fake; retain original rectangular domain while comparing independently verified coastal-source alternatives. Do not call full U/V / ROMS nesting `PASS`.
