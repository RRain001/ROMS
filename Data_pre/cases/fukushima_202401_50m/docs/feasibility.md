# Feasibility Notes

## Grid Scales

The domain is 140E-142E and 36N-38N. At the representative latitude 37N:

| Resolution | Lm | Mm | rho points | 3D cells with N=21 |
| --- | ---: | ---: | ---: | ---: |
| 50 m target | 3557 | 4453 | 15,855,345 | 332,962,245 |
| 250 m intermediate | 712 | 891 | 637,602 | 13,389,642 |
| 500 m pilot | 356 | 446 | 160,384 | 3,368,064 |
| 1000 m smoke test | 178 | 223 | 40,500 | 850,500 |

The first implementable project should use 500 m or 1000 m until the full data chain is validated.

## Time Settings

Pilot defaults:

- `DT = 60 s`
- `NDTFAST = 20`
- January 2024 has 31 days.
- `NTIMES = 44640`
- hourly output gives `NHIS = NAVG = 60`

These are draft values. They need a CFL check after bathymetry, max current, vertical coordinates and forcing are finalized.

## Source Conversion

Annual source:

- `22 TBq/year = 2.2e13 Bq/year`
- 2024 is a leap year: 366 days.
- Constant rate: `695709.371 Bq/s`.
- January inventory under constant release: `1.863e12 Bq`.

ROMS river/source forcing usually needs concentration, not only activity flux:

```text
activity flux [Bq/s] = discharge [m3/s] * concentration [Bq/m3]
```

The project currently computes the activity flux. A source discharge or effective mixing volume must be chosen before writing a physically meaningful `river_dye_01` concentration.

