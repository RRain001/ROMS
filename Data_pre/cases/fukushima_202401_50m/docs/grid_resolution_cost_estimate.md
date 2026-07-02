# Fukushima Domain Grid Resolution Cost Estimate

Generated: 2026-06-25

Remote script:

- `/home/lhy/ROMS/projects/fukushima_202401_50m/preprocessing/estimate_grid_cost.py`

Configuration:

- domain: 140E-142E, 36N-38N
- vertical levels: `N=21`

## Result

| Resolution | Approx. `xi_rho x eta_rho` | Horizontal cells | Sigma cells | One float32 3D variable per output record | Five core 3D variables per output record |
| --- | ---: | ---: | ---: | ---: | ---: |
| 50 m | 3557 x 4453 | 15,839,321 | 332,625,741 | 1.24 GiB | 6.20 GiB |
| 250 m | 712 x 891 | 634,392 | 13,322,232 | 0.05 GiB | 0.25 GiB |
| 500 m | 356 x 446 | 158,776 | 3,334,296 | 0.01 GiB | 0.06 GiB |

## Interpretation

The 50 m full-domain grid is technically possible only as a later high-cost production or nested experiment. It is not the right next step while bathymetry, land mask, ocean boundary fields, atmospheric forcing, tide forcing and source discharge are still unresolved.

For the next scientifically useful implementation:

1. Keep `N=21`.
2. Continue using 500 m for workflow validation.
3. Move to 250 m only after real bathymetry and external forcing are ready.
4. Reserve 50 m for a smaller nested source-region domain or a final sensitivity case.
