# fdnpp_online_my25_uvtide_reconfig

- stage: final
- profile: online_my25_uvtide
- case: FDNPP
- status: ok

## Blocking issues

- none

## Summary

### vertical

```json
{
  "Hmin_m": 10.0,
  "N": 40,
  "Tcline_m": 200.0,
  "Vstretching": 4,
  "Vtransform": 2,
  "theta_b": 0.1,
  "theta_s": 7.0
}
```

### physics

```json
{
  "akt_bak_m2_s": 1e-06,
  "akv_bak_m2_s": 1e-05,
  "horizontal_mixing": "Smagorinsky",
  "my25_options": [
    "KANTHA_CLAYSON",
    "N2S2_HORAVG",
    "RI_SPLINES"
  ],
  "profile": "online_my25_uvtide",
  "smagorinsky_coefficient": 0.2,
  "tnu2_m2_s": 10.0,
  "ts_smagorinsky": true,
  "uv_smagorinsky": true,
  "vertical_mixing": "MY25_MIXING",
  "visc2_m2_s": 10.0
}
```

### tides

```json
{
  "ssh_tides": true,
  "uv_tides": true
}
```

### source

```json
{
  "configured_lat": 37.421,
  "configured_lon": 141.032,
  "nearest_is_water": false,
  "snap_distance_m": 929.4703931846327,
  "snapped_cell": {
    "h": 10.861332893371582,
    "is_water": true,
    "mask_rho": 1
  },
  "snapped_depth_m": 10.861332893371582,
  "snapped_eta": 95,
  "snapped_lat": 37.422222222222224,
  "snapped_lon": 141.0424,
  "snapped_xi": 29
}
```

### cpp_defs

```json
[
  "FDNPP_202501",
  "FDNPP_202501_ONLINE",
  "UV_ADV",
  "UV_COR",
  "UV_LDRAG",
  "UV_VIS2",
  "UV_SMAGORINSKY",
  "MIX_S_UV",
  "SPLINES_VDIFF",
  "SPLINES_VVISC",
  "DJ_GRADPS",
  "TS_DIF2",
  "TS_SMAGORINSKY",
  "MIX_S_TS",
  "SALINITY",
  "SOLVE3D",
  "MASKING",
  "AVERAGES",
  "DIAGNOSTICS_TS",
  "DIAGNOSTICS_UV",
  "T_PASSIVE",
  "MY25_MIXING",
  "KANTHA_CLAYSON",
  "N2S2_HORAVG",
  "RI_SPLINES",
  "BULK_FLUXES",
  "LONGWAVE_OUT",
  "SOLAR_SOURCE",
  "EMINUSP",
  "SSH_TIDES",
  "UV_TIDES",
  "ANA_BTFLUX",
  "ANA_BSFLUX",
  "ANA_SPFLUX",
  "ANA_BPFLUX"
]
```

### infile

```json
{
  "AVGNAME": "../output/avg_fdnpp_online_6h_online_my25_uvtide.nc",
  "BRYNAME": "../input/roms_bdy_fdnpp_202501_online_my25_uvtide.nc",
  "DIANAME": "../output/dia_fdnpp_online_6h_online_my25_uvtide.nc",
  "DT": "60.0d0",
  "HISNAME": "../output/his_fdnpp_online_6h_online_my25_uvtide.nc",
  "ININAME": "../input/roms_ini_fdnpp_20250101_online_my25_uvtide.nc",
  "MyAppCPP": "FDNPP_202501_ONLINE_MY25_UVTIDE",
  "N": "40",
  "NAVG": "60",
  "NDIA": "60",
  "NHIS": "60",
  "NPT": "1",
  "NTIMES": "360",
  "NtileI": "7",
  "NtileJ": "8",
  "RSTNAME": "../output/rst_fdnpp_online_6h_online_my25_uvtide.nc",
  "SSFNAME": "../input/roms_rivers_production_online_my25_uvtide.nc",
  "TCLINE": "200.0d0",
  "THETA_B": "0.1d0",
  "THETA_S": "7.0d0",
  "TIDENAME": "../input/roms_tides_fdnpp_202501_online_my25_uvtide.nc",
  "Vstretching": "4",
  "Vtransform": "2"
}
```

### files

```json
{
  "bdy": {
    "dims": {
      "dye_time": 249,
      "eta_rho": 190,
      "eta_u": 190,
      "eta_v": 189,
      "s_rho": 40,
      "salt_time": 249,
      "temp_time": 249,
      "v2d_time": 249,
      "v3d_time": 249,
      "xi_rho": 201,
      "xi_u": 200,
      "xi_v": 201,
      "zeta_time": 249
    },
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/input/roms_bdy_fdnpp_202501_online_my25_uvtide.nc"
  },
  "grid": {
    "dims": {
      "eta_psi": 189,
      "eta_rho": 190,
      "eta_u": 190,
      "eta_v": 189,
      "xi_psi": 200,
      "xi_rho": 201,
      "xi_u": 200,
      "xi_v": 201
    },
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/input/roms_grid_bathy_500m_maskclean_smoothed.nc"
  },
  "header": {
    "dims": null,
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/run/fdnpp_202501_online_my25_uvtide.h"
  },
  "infile": {
    "dims": null,
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_6h_online_my25_uvtide.in"
  },
  "ini": {
    "dims": {
      "eta_rho": 190,
      "eta_u": 190,
      "eta_v": 189,
      "ocean_time": 1,
      "s_rho": 40,
      "xi_rho": 201,
      "xi_u": 200,
      "xi_v": 201
    },
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/input/roms_ini_fdnpp_20250101_online_my25_uvtide.nc"
  },
  "river": {
    "dims": {
      "river": 1,
      "river_time": 745,
      "s_rho": 40
    },
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/input/roms_rivers_production_online_my25_uvtide.nc"
  },
  "tides": {
    "dims": {
      "eta_rho": 190,
      "tide_period": 15,
      "xi_rho": 201
    },
    "exists": true,
    "path": "/home/lhy/ROMS/projects/FDNPP/input/roms_tides_fdnpp_202501_online_my25_uvtide.nc"
  }
}
```

### build

```json
{
  "build_dir": "/home/lhy/ROMS/projects/FDNPP/build/Build_romsM",
  "executable": "/home/lhy/ROMS/projects/FDNPP/bin/romsM_fdnpp_online_my25_uvtide",
  "executable_exists": true,
  "header_name": "fdnpp_202501_online_my25_uvtide.h",
  "roms_application": "FDNPP_202501_ONLINE_MY25_UVTIDE",
  "status": "ok",
  "variant": "online_my25_uvtide"
}
```

### run_modes

```json
{
  "online_3d": {
    "binary": "/home/lhy/ROMS/projects/FDNPP/bin/romsM_fdnpp_online_my25_uvtide",
    "binary_exists": true,
    "blocking_issues": [],
    "infile": "/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_3d_online_my25_uvtide.in",
    "infile_exists": true,
    "log": "/home/lhy/ROMS/projects/FDNPP/logs/online_3d.log",
    "np": 56,
    "outputs": {
      "average": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_3d_online_my25_uvtide.nc",
      "diagnostics": "/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_online_3d_online_my25_uvtide.nc",
      "history": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_3d_online_my25_uvtide.nc",
      "restart": "/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_online_3d_online_my25_uvtide.nc"
    },
    "status": "ready"
  },
  "online_6h": {
    "binary": "/home/lhy/ROMS/projects/FDNPP/bin/romsM_fdnpp_online_my25_uvtide",
    "binary_exists": true,
    "blocking_issues": [],
    "infile": "/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_6h_online_my25_uvtide.in",
    "infile_exists": true,
    "log": "/home/lhy/ROMS/projects/FDNPP/logs/online_6h.log",
    "np": 56,
    "outputs": {
      "average": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_6h_online_my25_uvtide.nc",
      "diagnostics": "/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_online_6h_online_my25_uvtide.nc",
      "history": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_6h_online_my25_uvtide.nc",
      "restart": "/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_online_6h_online_my25_uvtide.nc"
    },
    "status": "ready"
  },
  "online_month": {
    "binary": "/home/lhy/ROMS/projects/FDNPP/bin/romsM_fdnpp_online_my25_uvtide",
    "binary_exists": true,
    "blocking_issues": [],
    "infile": "/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_month_online_my25_uvtide.in",
    "infile_exists": true,
    "log": "/home/lhy/ROMS/projects/FDNPP/logs/online_month.log",
    "np": 56,
    "outputs": {
      "average": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_month_online_my25_uvtide.nc",
      "diagnostics": "/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_online_month_online_my25_uvtide.nc",
      "history": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_month_online_my25_uvtide.nc",
      "restart": "/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_online_month_online_my25_uvtide.nc"
    },
    "status": "ready"
  }
}
```

### run_results

```json
{
  "online_3d": {
    "duration_seconds": 259200.0,
    "dye_inventory_vs_source": {
      "estimated_cumulative_source_bq": 180821917808.21915,
      "history_inventory_bq": {
        "delta": 180821917732.12582,
        "first": 0.0,
        "last": 180821917732.12582
      }
    },
    "estimated_cumulative_source_bq": 180821917808.21915,
    "log": {
      "blowup": false,
      "done": true,
      "exists": true,
      "last_model_time": "2025-01-04 00:00:00.00",
      "path": "/home/lhy/ROMS/projects/FDNPP/logs/online_3d.log",
      "records": {
        "average": 72,
        "history": 73,
        "restart": 2
      },
      "status": "done"
    },
    "outputs": {
      "average": {
        "dims": {
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 72,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_3d_online_my25_uvtide.nc"
      },
      "diagnostics": {
        "dims": {
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 72,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_online_3d_online_my25_uvtide.nc"
      },
      "history": {
        "dims": {
          "N": 40,
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 73,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "dye_inventory_bq": {
          "delta": 180821917732.12582,
          "first": 0.0,
          "last": 180821917732.12582
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_3d_online_my25_uvtide.nc",
        "stats": {
          "AKs": {
            "finite_count": 114302670,
            "max": 238.6306610107422,
            "mean": 0.04828960542287302,
            "min": 0.0
          },
          "AKt": {
            "finite_count": 114302670,
            "max": 238.6306610107422,
            "mean": 0.04828960542287302,
            "min": 0.0
          },
          "AKv": {
            "finite_count": 114302670,
            "max": 176.2513427734375,
            "mean": 0.03599939325332322,
            "min": 0.0
          },
          "dye_01": {
            "finite_count": 97808320,
            "max": 6364.41259765625,
            "mean": 0.877420732297092,
            "min": -2.209807977177289e-16
          },
          "salt": {
            "finite_count": 97808320,
            "max": 34.61275100708008,
            "mean": 34.428440180844795,
            "min": 34.02338790893555
          },
          "temp": {
            "finite_count": 97808320,
            "max": 19.558616638183594,
            "mean": 15.804670519122975,
            "min": 0.007372233550995588
          },
          "u": {
            "finite_count": 97253520,
            "max": 1.842136263847351,
            "mean": -0.009586047508027185,
            "min": -2.1614394187927246
          },
          "ubar": {
            "finite_count": 2431338,
            "max": 1.776247501373291,
            "mean": 0.00108432083262022,
            "min": -2.121619462966919
          },
          "v": {
            "finite_count": 97224320,
            "max": 2.088628053665161,
            "mean": -0.005605009306804727,
            "min": -2.1259605884552
          },
          "vbar": {
            "finite_count": 2430608,
            "max": 1.9389193058013916,
            "mean": -0.007102679102418911,
            "min": -2.0347375869750977
          },
          "zeta": {
            "finite_count": 2445208,
            "max": 1.4470019340515137,
            "mean": 0.01077523696151856,
            "min": -0.9173251986503601
          }
        }
      },
      "restart": {
        "dims": {
          "N": 40,
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 2,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_online_3d_online_my25_uvtide.nc"
      }
    }
  },
  "online_6h": {
    "duration_seconds": 21600.0,
    "dye_inventory_vs_source": {
      "estimated_cumulative_source_bq": 15068493150.684929,
      "history_inventory_bq": {
        "delta": 15068493133.136671,
        "first": 0.0,
        "last": 15068493133.136671
      }
    },
    "estimated_cumulative_source_bq": 15068493150.684929,
    "log": {
      "blowup": false,
      "done": true,
      "exists": true,
      "last_model_time": "2025-01-01 06:00:00.00",
      "path": "/home/lhy/ROMS/projects/FDNPP/logs/online_6h.log",
      "records": {
        "average": 6,
        "history": 7
      },
      "status": "done"
    },
    "outputs": {
      "average": {
        "dims": {
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 6,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_6h_online_my25_uvtide.nc"
      },
      "diagnostics": {
        "dims": {
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 6,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_online_6h_online_my25_uvtide.nc"
      },
      "history": {
        "dims": {
          "N": 40,
          "boundary": 4,
          "eta_psi": 189,
          "eta_rho": 190,
          "eta_u": 190,
          "eta_v": 189,
          "ocean_time": 7,
          "s_rho": 40,
          "s_w": 41,
          "tracer": 3,
          "xi_psi": 200,
          "xi_rho": 201,
          "xi_u": 200,
          "xi_v": 201
        },
        "dye_inventory_bq": {
          "delta": 15068493133.136671,
          "first": 0.0,
          "last": 15068493133.136671
        },
        "exists": true,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_6h_online_my25_uvtide.nc",
        "stats": {
          "AKs": {
            "finite_count": 10960530,
            "max": 238.6306610107422,
            "mean": 0.04349033974057683,
            "min": 0.0
          },
          "AKt": {
            "finite_count": 10960530,
            "max": 238.6306610107422,
            "mean": 0.04349033974057683,
            "min": 0.0
          },
          "AKv": {
            "finite_count": 10960530,
            "max": 176.2513427734375,
            "mean": 0.03280468275118224,
            "min": 0.0
          },
          "dye_01": {
            "finite_count": 9378880,
            "max": 3223.6416015625,
            "mean": 0.07821318146767778,
            "min": -2.209807977177289e-16
          },
          "salt": {
            "finite_count": 9378880,
            "max": 34.54713821411133,
            "mean": 34.41537910153643,
            "min": 34.0260009765625
          },
          "temp": {
            "finite_count": 9378880,
            "max": 18.708999633789062,
            "mean": 15.817482609274755,
            "min": 0.0075460574589669704
          },
          "u": {
            "finite_count": 9325680,
            "max": 1.824038028717041,
            "mean": -0.004422696300674449,
            "min": -1.0828837156295776
          },
          "ubar": {
            "finite_count": 233142,
            "max": 1.750993251800537,
            "mean": 0.007834061616644827,
            "min": -1.0580077171325684
          },
          "v": {
            "finite_count": 9322880,
            "max": 1.283187747001648,
            "mean": -0.025397167445120016,
            "min": -1.9407325983047485
          },
          "vbar": {
            "finite_count": 233072,
            "max": 1.2701387405395508,
            "mean": -0.03082349333386456,
            "min": -1.8638838529586792
          },
          "zeta": {
            "finite_count": 234472,
            "max": 1.4470019340515137,
            "mean": 0.26524506945520077,
            "min": -0.8301205039024353
          }
        }
      },
      "restart": {
        "dims": null,
        "exists": false,
        "path": "/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_online_6h_online_my25_uvtide.nc"
      }
    }
  }
}
```

### source_rate

```json
{
  "max_bq_s": 697615.4236428209,
  "mean_bq_s": 697615.4236428208,
  "min_bq_s": 697615.4236428209,
  "records": 745
}
```

### dye_01_initial

```json
{
  "max": 0.0,
  "min": 0.0
}
```

### smagorinsky_source_level_coefficient

```json
0.2
```
