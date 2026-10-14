# I1 MATLAB source inventory and Python-port contracts

Reference repository: [f-shake/my_roms_tools](https://github.com/f-shake/my_roms_tools), `main` at **`7b94657341d25ea7d975093c71780b267a36a6f4`** (read snapshot 2026-10-14). The original ROMS repository has 17 historical `.m` files under `archive/legacy_tools/Ocean-Data-Download`, primarily downloads, **not** nesting-grid tools. Never treat these as contact-grid references.

Status: **I1 preliminary inventory**. Relevant MATLAB function headers were read, but a complete line-by-line port, license audit and numerical MATLAB golden-result comparison have NOT been completed. Existing Python tests are synthetic analytical contracts only.

| Source MATLAB in `f-shake/my_roms_tools` | Observed semantics | Python role / status |
| --- | --- | --- |
| `rutgers/grid/rotate_spherical.m` | Spherical logically rectangular rotated grid; uses local Mercator construction and multiple geometry stages; outputs ROMS C-grid coordinates, `pm/pn`, `angle`, orthogonality | `Data_pre/nesting/rotated_grid.py`: **new conformal LCC-based synthetic prototype**, **not yet algorithmically equivalent** to Mercator implementation |
| `rutgers/grid/rotate_grid.m` | Rotated subdomain from donor ROMS grid centered at `Xc/Yc`, `theta` degrees relative to East; generates NetCDF | Compare orientation and stagger locations; donor bathymetry transfer not yet implemented |
| `rutgers/grid/grid_rotated.m` | Rotated grid from existing grid; scattered interpolation over spherical non-plaid donor coordinates | Referenced for future GEBCO + GSHHG interpolation |
| `rutgers/grid/grid_metrics.m` | `pm/pn/dndx/dmde`, great-circle vs Cartesian distance switch | Independent copy of approved WGS84 `grid_metrics.py` from ROMS PR #2; MATLAB numerical golden comparison NOT RUN |
| `rutgers/grid/coarse2fine.m` | PSI-index bounds and odd refinement factor 1,3,5,...; includes exterior contact points | **Inapplicable as direct ES3K(rotated)→UD1K(unrotated) geometry producer**. Audit index/halo conventions, do not force contact |
| `rutgers/grid/contact.m`, `c_contact.m` | Simultaneous-model nesting contact mapping and NetCDF schema including `nLweights=4`, `nQweights=9` | Interface reference only for possible future native nesting; current baseline is standalone offline one-way |
| `rutgers/grid/check_nest_masks.m` | Diagnose wet/dry mask at contact boundaries | Adapt wet coastal boundary checks in the offline remapping chain |
| `mtools/create_roms_child_init.m` | Transfers parent `temp/salt/u/v/ubar/vbar` to child initial NetCDF, handles vertical dimensions | Planned separate `create_child_ini_bry.py`; verify stagger + sigma, avoid unqualified depth-index copying |
| `mtools/parentchild_bathy.m` | Averages child bathymetry to parent using child cell area and matches child's perimeter to parent depth | Only use geographic overlap + physical boundary principles; algorithm's parent cell index loops **cannot** be copied to differently oriented grids |

**Notation and test contract:** `xi` is first horizontal ROMS direction, `eta` second, `angle` measured counterclockwise from true geographic East in **radians** in NetCDF (MATLAB inputs use degrees). ROMS C-grid shape: `rho:ny×nx`, `u:ny×(nx−1)`, `v:(ny−1)×nx`, `psi:(ny−1)×(nx−1)`. Python arrays row `eta`, column `xi`; MATLAB/Fortran transposition and 0/1 indexing require independent tests. For vectors: `u_grid=Ueast*cos(angle)+Vnorth*sin(angle)`, `v_grid=−Ueast*sin(angle)+Vnorth*cos(angle)`; must interpolate components at physical stagger positions before applying in production.

**Licenses:** sampled `rotate_spherical.m`, `rotate_grid.m`, `grid_metrics.m` and `coarse2fine.m` headers identify ROMS/TOMS Group MIT/X-style licensing. Confirm the other files' headers and repository license **before directly copying**. The current LCC code was independently developed and does not reproduce the original program line-by-line.

**I2 risk:** for Japan Sea-scale ES3K, a conformal projection does not guarantee physical 3 km spacing everywhere. Before real grid generation, recover Kim 2020's exact rotated corners/projection and independently quantify WGS84 scale/angle errors; synthetic ROT tests cannot replace this or an actual compiled ROMS integration.

## 2026-10-15 focused methodological audit

See [nesting_reference_audit_20261015.md](nesting_reference_audit_20261015.md) for the frozen-source comparison of `coarse2fine.m`, `rotate_grid.m`, `contact.m`, `grid_connections.m`, `write_contact.m`, `check_refine.m`, `refined_gridvar.m`, `parentchild_mask.m`, `create_roms_child_init.m`, `create_roms_child_clm.m`, and `rotate_uv.m`.

For independent, differently oriented ES3K → UD1K:
- Retain separate grids and one-way offline ROMS water-dynamics runs; the upstream odd-integer PSI-index refinement/Fortran contact is a **reference**, not the selected execution path.
- Implement read-only, physically located donor/receiver and C-grid wet-contact diagnostics. Do not mirror the reference script's on-disk child-mask rewriting or mean-angle velocity rotation.
- Treat the 27 initial missing all-wet-parent quadrilateral stencils as **diagnostic**, not physical failure or permission to fill across land. A fixed 16 nearest-centroid search can produce false negatives for warped quads; use geometrically complete search before final classification.
- Preserve the later distinct work of full vector rotation, sigma z-remap, tide/time alignment, normal boundary transport and two-way *tritium* Bq flux accounting.
- This is a targeted methodological review, not a claim of line-by-line MATLAB golden output equivalence or resolved GPL/individual-file license questions.
