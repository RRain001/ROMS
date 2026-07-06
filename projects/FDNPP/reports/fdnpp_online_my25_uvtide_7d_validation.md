# fdnpp_online_my25_uvtide_7d_validation

- completed: True
- roms_done: True
- blowup: False
- nan_in_log: False
- history_records: 169
- average_records: 168
- restart_records: 2
- recommend_online_month: True

## Blocking issues

- none

## Interpretation

- AKv/AKt/AKs maxima above 100 m2/s: AKv=True, AKt=True, AKs=True
- flow reaches 2 m/s scale: True (order 2.338 m/s)
- min temp near freezing: True (min 0.006933 C)
- dye negative roundoff only: False (min -6.385604e-02)
- dye max near source: True (distance 0.0 m)
- source is surface-only and dye max in upper layers: source_surface_only=True, max_vertical_index=39
- inventory delta / cumulative source = 0.999990
- approximate open-boundary loss Bq = 4.402547e+06

## paths

```json
{
  "average": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_7d_online_my25_uvtide.nc",
  "diagnostics": "/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_online_7d_online_my25_uvtide.nc",
  "grid": "/home/lhy/ROMS/projects/FDNPP/input/roms_grid_bathy_500m_maskclean_smoothed.nc",
  "history": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_7d_online_my25_uvtide.nc",
  "log": "/home/lhy/ROMS/projects/FDNPP/logs/online_7d.log",
  "restart": "/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_online_7d_online_my25_uvtide.nc",
  "river": "/home/lhy/ROMS/projects/FDNPP/input/roms_rivers_production_online_my25_uvtide.nc"
}
```

## run

```json
{
  "blowup": false,
  "completed": true,
  "done_line": "ROMS: DONE... Sunday - July 5, 2026 -  9:24:42 PM",
  "error_in_log": false,
  "nan_in_log": false,
  "records": {
    "average": 168,
    "history": 169,
    "restart": 2
  },
  "roms_done": true
}
```

## source

```json
{
  "configured_lat": 37.421,
  "configured_lon": 141.032,
  "max_rate_bq_s": 697615.4236428209,
  "mean_rate_bq_s": 697615.4236428208,
  "min_rate_bq_s": 697615.4236428209,
  "placement_rule": "configured source on land; snapped to nearest mask_rho=1 rho cell",
  "snapped_depth_m": 10.861332893371582,
  "snapped_eta": 95,
  "snapped_lat": 37.422222222222224,
  "snapped_lon": 141.0424,
  "snapped_xi": 29,
  "surface_only": true,
  "vertical_nonzero_levels": 1,
  "vertical_sum": 1.0
}
```

## history

```json
{
  "extrema": {
    "AKs": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 56409.6875867444,
        "eta_index": 129,
        "grid_type": "rho",
        "h_m": 254.05078125,
        "lat": 37.57333333333334,
        "lon": 141.65279999999998,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.625,
        "time_index": 3,
        "time_iso": "2025-01-01T03:00:00",
        "value": 238.6306610107422,
        "vertical_index": 15,
        "xi_index": 138
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 47014.40225711109,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 44.74568557739258,
        "lat": 37.0,
        "lon": 141.0144,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -1.0,
        "time_index": 0,
        "time_iso": "2025-01-01T00:00:00",
        "value": 0.0,
        "vertical_index": 0,
        "xi_index": 24
      }
    },
    "AKt": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 56409.6875867444,
        "eta_index": 129,
        "grid_type": "rho",
        "h_m": 254.05078125,
        "lat": 37.57333333333334,
        "lon": 141.65279999999998,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.625,
        "time_index": 3,
        "time_iso": "2025-01-01T03:00:00",
        "value": 238.6306610107422,
        "vertical_index": 15,
        "xi_index": 138
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 47014.40225711109,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 44.74568557739258,
        "lat": 37.0,
        "lon": 141.0144,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -1.0,
        "time_index": 0,
        "time_iso": "2025-01-01T00:00:00",
        "value": 0.0,
        "vertical_index": 0,
        "xi_index": 24
      }
    },
    "AKv": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 56409.6875867444,
        "eta_index": 129,
        "grid_type": "rho",
        "h_m": 254.05078125,
        "lat": 37.57333333333334,
        "lon": 141.65279999999998,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.625,
        "time_index": 3,
        "time_iso": "2025-01-01T03:00:00",
        "value": 176.2513427734375,
        "vertical_index": 15,
        "xi_index": 138
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 47014.40225711109,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 44.74568557739258,
        "lat": 37.0,
        "lon": 141.0144,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -1.0,
        "time_index": 0,
        "time_iso": "2025-01-01T00:00:00",
        "value": 0.0,
        "vertical_index": 0,
        "xi_index": 24
      }
    },
    "dye_01": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 0.0,
        "eta_index": 95,
        "grid_type": "rho",
        "h_m": 10.861332893371582,
        "lat": 37.422222222222224,
        "lon": 141.0424,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": true,
        "open_boundary_sides": [],
        "s_coordinate": -0.0125,
        "time_index": 97,
        "time_iso": "2025-01-05T01:00:00",
        "value": 9487.935546875,
        "vertical_index": 39,
        "xi_index": 29
      },
      "min": {
        "boundary_sides": [],
        "distance_to_source_m": 35822.86491645031,
        "eta_index": 30,
        "grid_type": "rho",
        "h_m": 128.72842407226562,
        "lat": 37.13333333333333,
        "lon": 141.2216,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.9375,
        "time_index": 160,
        "time_iso": "2025-01-07T16:00:00",
        "value": -0.06385604292154312,
        "vertical_index": 2,
        "xi_index": 61
      }
    },
    "omega": {
      "max": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 92622.83097810333,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 1155.1956787109375,
        "lat": 37.0,
        "lon": 141.944,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.925,
        "time_index": 165,
        "time_iso": "2025-01-07T21:00:00",
        "value": 0.07489854097366333,
        "vertical_index": 3,
        "xi_index": 190
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 88383.75704419918,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 969.15625,
        "lat": 37.0,
        "lon": 141.888,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.9750000000000001,
        "time_index": 55,
        "time_iso": "2025-01-03T07:00:00",
        "value": -0.06816014647483826,
        "vertical_index": 1,
        "xi_index": 180
      }
    },
    "rho": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 47120.082299354646,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.84,
        "lon": 140.9528,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.7125,
        "time_index": 151,
        "time_iso": "2025-01-07T07:00:00",
        "value": 29.443050384521484,
        "vertical_index": 11,
        "xi_index": 13
      },
      "min": {
        "boundary_sides": [
          "east"
        ],
        "distance_to_source_m": 86108.86608807054,
        "eta_index": 63,
        "grid_type": "rho",
        "h_m": 794.7535400390625,
        "lat": 37.28,
        "lon": 142.0,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "east"
        ],
        "s_coordinate": -0.0625,
        "time_index": 64,
        "time_iso": "2025-01-03T16:00:00",
        "value": 26.029521942138672,
        "vertical_index": 37,
        "xi_index": 200
      }
    },
    "salt": {
      "max": {
        "boundary_sides": [
          "east"
        ],
        "distance_to_source_m": 93799.08720627788,
        "eta_index": 178,
        "grid_type": "rho",
        "h_m": 496.2657775878906,
        "lat": 37.791111111111114,
        "lon": 142.0,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "east"
        ],
        "s_coordinate": -0.5875,
        "time_index": 64,
        "time_iso": "2025-01-03T16:00:00",
        "value": 34.61275100708008,
        "vertical_index": 16,
        "xi_index": 200
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 82397.35550770441,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 370.3934631347656,
        "lat": 37.84,
        "lon": 141.8152,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.9875,
        "time_index": 8,
        "time_iso": "2025-01-01T08:00:00",
        "value": 34.02338790893555,
        "vertical_index": 0,
        "xi_index": 167
      }
    },
    "temp": {
      "max": {
        "boundary_sides": [
          "east"
        ],
        "distance_to_source_m": 86108.86608807054,
        "eta_index": 63,
        "grid_type": "rho",
        "h_m": 794.7535400390625,
        "lat": 37.28,
        "lon": 142.0,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "east"
        ],
        "s_coordinate": -0.0625,
        "time_index": 64,
        "time_iso": "2025-01-03T16:00:00",
        "value": 19.558616638183594,
        "vertical_index": 37,
        "xi_index": 200
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 47120.082299354646,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.84,
        "lon": 140.9528,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.7125,
        "time_index": 151,
        "time_iso": "2025-01-07T07:00:00",
        "value": 0.006932535208761692,
        "vertical_index": 11,
        "xi_index": 13
      }
    },
    "u": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46151.33233835228,
        "eta_index": 188,
        "grid_type": "u",
        "h_m": 13.337443351745605,
        "lat": 37.83555555555556,
        "lon": 140.9948,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.0125,
        "time_index": 157,
        "time_iso": "2025-01-07T13:00:00",
        "value": 2.3380706310272217,
        "vertical_index": 39,
        "xi_index": 20
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46460.65833097625,
        "eta_index": 189,
        "grid_type": "u",
        "h_m": 24.181941032409668,
        "lat": 37.84,
        "lon": 141.05079999999998,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.3875,
        "time_index": 10,
        "time_iso": "2025-01-01T10:00:00",
        "value": -2.1614394187927246,
        "vertical_index": 24,
        "xi_index": 30
      }
    },
    "ubar": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46643.499564694066,
        "eta_index": 189,
        "grid_type": "u",
        "h_m": 13.881741046905518,
        "lat": 37.84,
        "lon": 140.9948,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 157,
        "time_iso": "2025-01-07T13:00:00",
        "value": 2.2661478519439697,
        "vertical_index": null,
        "xi_index": 20
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46460.65833097625,
        "eta_index": 189,
        "grid_type": "u",
        "h_m": 24.181941032409668,
        "lat": 37.84,
        "lon": 141.05079999999998,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 10,
        "time_iso": "2025-01-01T10:00:00",
        "value": -2.121619462966919,
        "vertical_index": null,
        "xi_index": 30
      }
    },
    "v": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46207.66951673842,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 22.420555114746094,
        "lat": 37.83777777777778,
        "lon": 141.0424,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.3125,
        "time_index": 11,
        "time_iso": "2025-01-01T11:00:00",
        "value": 2.088628053665161,
        "vertical_index": 27,
        "xi_index": 29
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46210.3010072276,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 21.5214262008667,
        "lat": 37.83777777777778,
        "lon": 141.0368,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.9875,
        "time_index": 17,
        "time_iso": "2025-01-01T17:00:00",
        "value": -2.1259605884552,
        "vertical_index": 0,
        "xi_index": 28
      }
    },
    "vbar": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46207.66951673842,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 22.420555114746094,
        "lat": 37.83777777777778,
        "lon": 141.0424,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 11,
        "time_iso": "2025-01-01T11:00:00",
        "value": 1.9389193058013916,
        "vertical_index": null,
        "xi_index": 29
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46231.347538841175,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 25.673171997070312,
        "lat": 37.83777777777778,
        "lon": 141.0592,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 56,
        "time_iso": "2025-01-03T08:00:00",
        "value": -2.0347375869750977,
        "vertical_index": null,
        "xi_index": 32
      }
    },
    "w": {
      "max": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 92622.83097810333,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 1155.1956787109375,
        "lat": 37.0,
        "lon": 141.944,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.925,
        "time_index": 165,
        "time_iso": "2025-01-07T21:00:00",
        "value": 0.0759853795170784,
        "vertical_index": 3,
        "xi_index": 190
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 88383.75704419918,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 969.15625,
        "lat": 37.0,
        "lon": 141.888,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.9750000000000001,
        "time_index": 55,
        "time_iso": "2025-01-03T07:00:00",
        "value": -0.07392970472574234,
        "vertical_index": 1,
        "xi_index": 180
      }
    },
    "zeta": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 39784.521575272534,
        "eta_index": 175,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.77777777777778,
        "lon": 140.992,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": null,
        "time_index": 1,
        "time_iso": "2025-01-01T01:00:00",
        "value": 1.4470019340515137,
        "vertical_index": null,
        "xi_index": 20
      },
      "min": {
        "boundary_sides": [],
        "distance_to_source_m": 44750.58308175442,
        "eta_index": 185,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.82222222222222,
        "lon": 140.9864,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": null,
        "time_index": 22,
        "time_iso": "2025-01-01T22:00:00",
        "value": -0.9173251986503601,
        "vertical_index": null,
        "xi_index": 19
      }
    }
  },
  "label": "history",
  "path": "/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_online_7d_online_my25_uvtide.nc"
}
```

## average

```json
{
  "extrema": {
    "AKs": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 82846.01875592176,
        "eta_index": 2,
        "grid_type": "rho",
        "h_m": 752.7930908203125,
        "lat": 37.00888888888889,
        "lon": 141.8208,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.275,
        "time_index": 48,
        "time_iso": "2025-01-03T00:30:00",
        "value": 34.99448776245117,
        "vertical_index": 29,
        "xi_index": 168
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 47014.40225711109,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 44.74568557739258,
        "lat": 37.0,
        "lon": 141.0144,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -1.0,
        "time_index": 0,
        "time_iso": "2025-01-01T00:30:00",
        "value": 0.0,
        "vertical_index": 0,
        "xi_index": 24
      }
    },
    "AKt": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 82846.01875592176,
        "eta_index": 2,
        "grid_type": "rho",
        "h_m": 752.7930908203125,
        "lat": 37.00888888888889,
        "lon": 141.8208,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.275,
        "time_index": 48,
        "time_iso": "2025-01-03T00:30:00",
        "value": 34.99448776245117,
        "vertical_index": 29,
        "xi_index": 168
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 47014.40225711109,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 44.74568557739258,
        "lat": 37.0,
        "lon": 141.0144,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -1.0,
        "time_index": 0,
        "time_iso": "2025-01-01T00:30:00",
        "value": 0.0,
        "vertical_index": 0,
        "xi_index": 24
      }
    },
    "AKv": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 82846.01875592176,
        "eta_index": 2,
        "grid_type": "rho",
        "h_m": 752.7930908203125,
        "lat": 37.00888888888889,
        "lon": 141.8208,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.275,
        "time_index": 48,
        "time_iso": "2025-01-03T00:30:00",
        "value": 26.426847457885742,
        "vertical_index": 29,
        "xi_index": 168
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 47014.40225711109,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 44.74568557739258,
        "lat": 37.0,
        "lon": 141.0144,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -1.0,
        "time_index": 0,
        "time_iso": "2025-01-01T00:30:00",
        "value": 0.0,
        "vertical_index": 0,
        "xi_index": 24
      }
    },
    "dye_01": {
      "max": {
        "boundary_sides": [],
        "distance_to_source_m": 0.0,
        "eta_index": 95,
        "grid_type": "rho",
        "h_m": 10.861332893371582,
        "lat": 37.422222222222224,
        "lon": 141.0424,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": true,
        "open_boundary_sides": [],
        "s_coordinate": -0.0125,
        "time_index": 97,
        "time_iso": "2025-01-05T01:30:00",
        "value": 9457.7451171875,
        "vertical_index": 39,
        "xi_index": 29
      },
      "min": {
        "boundary_sides": [],
        "distance_to_source_m": 35822.86491645031,
        "eta_index": 30,
        "grid_type": "rho",
        "h_m": 128.72842407226562,
        "lat": 37.13333333333333,
        "lon": 141.2216,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": -0.9375,
        "time_index": 159,
        "time_iso": "2025-01-07T15:30:00",
        "value": -0.05293960124254227,
        "vertical_index": 2,
        "xi_index": 61
      }
    },
    "omega": {
      "max": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 92622.83097810333,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 1155.1956787109375,
        "lat": 37.0,
        "lon": 141.944,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.925,
        "time_index": 165,
        "time_iso": "2025-01-07T21:30:00",
        "value": 0.07526012510061264,
        "vertical_index": 3,
        "xi_index": 190
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 88383.75704419918,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 969.15625,
        "lat": 37.0,
        "lon": 141.888,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.9750000000000001,
        "time_index": 55,
        "time_iso": "2025-01-03T07:30:00",
        "value": -0.06951674073934555,
        "vertical_index": 1,
        "xi_index": 180
      }
    },
    "rho": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 47120.082299354646,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.84,
        "lon": 140.9528,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.23750000000000002,
        "time_index": 4,
        "time_iso": "2025-01-01T04:30:00",
        "value": 29.442941665649414,
        "vertical_index": 30,
        "xi_index": 13
      },
      "min": {
        "boundary_sides": [
          "east"
        ],
        "distance_to_source_m": 86108.86608807054,
        "eta_index": 63,
        "grid_type": "rho",
        "h_m": 794.7535400390625,
        "lat": 37.28,
        "lon": 142.0,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "east"
        ],
        "s_coordinate": -0.08750000000000001,
        "time_index": 63,
        "time_iso": "2025-01-03T15:30:00",
        "value": 26.029556274414062,
        "vertical_index": 36,
        "xi_index": 200
      }
    },
    "salt": {
      "max": {
        "boundary_sides": [
          "east"
        ],
        "distance_to_source_m": 93799.08720627788,
        "eta_index": 178,
        "grid_type": "rho",
        "h_m": 496.2657775878906,
        "lat": 37.791111111111114,
        "lon": 142.0,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "east"
        ],
        "s_coordinate": -0.5875,
        "time_index": 63,
        "time_iso": "2025-01-03T15:30:00",
        "value": 34.61268615722656,
        "vertical_index": 16,
        "xi_index": 200
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 82397.35550770441,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 370.3934631347656,
        "lat": 37.84,
        "lon": 141.8152,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.9875,
        "time_index": 7,
        "time_iso": "2025-01-01T07:30:00",
        "value": 34.02348709106445,
        "vertical_index": 0,
        "xi_index": 167
      }
    },
    "temp": {
      "max": {
        "boundary_sides": [
          "east"
        ],
        "distance_to_source_m": 86108.86608807054,
        "eta_index": 63,
        "grid_type": "rho",
        "h_m": 794.7535400390625,
        "lat": 37.28,
        "lon": 142.0,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "east"
        ],
        "s_coordinate": -0.08750000000000001,
        "time_index": 63,
        "time_iso": "2025-01-03T15:30:00",
        "value": 19.558414459228516,
        "vertical_index": 36,
        "xi_index": 200
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 47120.082299354646,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.84,
        "lon": 140.9528,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.23750000000000002,
        "time_index": 4,
        "time_iso": "2025-01-01T04:30:00",
        "value": 0.007548291236162186,
        "vertical_index": 30,
        "xi_index": 13
      }
    },
    "u": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46151.33233835228,
        "eta_index": 188,
        "grid_type": "u",
        "h_m": 13.337443351745605,
        "lat": 37.83555555555556,
        "lon": 140.9948,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.0125,
        "time_index": 156,
        "time_iso": "2025-01-07T12:30:00",
        "value": 2.3479225635528564,
        "vertical_index": 39,
        "xi_index": 20
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46460.65833097625,
        "eta_index": 189,
        "grid_type": "u",
        "h_m": 24.181941032409668,
        "lat": 37.84,
        "lon": 141.05079999999998,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.1875,
        "time_index": 34,
        "time_iso": "2025-01-02T10:30:00",
        "value": -2.0096428394317627,
        "vertical_index": 32,
        "xi_index": 30
      }
    },
    "ubar": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46198.735416112606,
        "eta_index": 188,
        "grid_type": "u",
        "h_m": 12.931921482086182,
        "lat": 37.83555555555556,
        "lon": 140.98919999999998,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 156,
        "time_iso": "2025-01-07T12:30:00",
        "value": 2.2737221717834473,
        "vertical_index": null,
        "xi_index": 19
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46460.65833097625,
        "eta_index": 189,
        "grid_type": "u",
        "h_m": 24.181941032409668,
        "lat": 37.84,
        "lon": 141.05079999999998,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 34,
        "time_iso": "2025-01-02T10:30:00",
        "value": -1.9794118404388428,
        "vertical_index": null,
        "xi_index": 30
      }
    },
    "v": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46207.66951673842,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 22.420555114746094,
        "lat": 37.83777777777778,
        "lon": 141.0424,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.2625,
        "time_index": 10,
        "time_iso": "2025-01-01T10:30:00",
        "value": 1.9928122758865356,
        "vertical_index": 29,
        "xi_index": 29
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46210.3010072276,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 21.5214262008667,
        "lat": 37.83777777777778,
        "lon": 141.0368,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": -0.9875,
        "time_index": 17,
        "time_iso": "2025-01-01T17:30:00",
        "value": -2.1084229946136475,
        "vertical_index": 0,
        "xi_index": 28
      }
    },
    "vbar": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46207.66951673842,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 22.420555114746094,
        "lat": 37.83777777777778,
        "lon": 141.0424,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 10,
        "time_iso": "2025-01-01T10:30:00",
        "value": 1.9495368003845215,
        "vertical_index": null,
        "xi_index": 29
      },
      "min": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 46210.3010072276,
        "eta_index": 188,
        "grid_type": "v",
        "h_m": 21.5214262008667,
        "lat": 37.83777777777778,
        "lon": 141.0368,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 17,
        "time_iso": "2025-01-01T17:30:00",
        "value": -2.0089974403381348,
        "vertical_index": null,
        "xi_index": 28
      }
    },
    "w": {
      "max": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 92622.83097810333,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 1155.1956787109375,
        "lat": 37.0,
        "lon": 141.944,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.925,
        "time_index": 165,
        "time_iso": "2025-01-07T21:30:00",
        "value": 0.07634355872869492,
        "vertical_index": 3,
        "xi_index": 190
      },
      "min": {
        "boundary_sides": [
          "south"
        ],
        "distance_to_source_m": 88383.75704419918,
        "eta_index": 0,
        "grid_type": "rho",
        "h_m": 969.15625,
        "lat": 37.0,
        "lon": 141.888,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "south"
        ],
        "s_coordinate": -0.9750000000000001,
        "time_index": 55,
        "time_iso": "2025-01-03T07:30:00",
        "value": -0.07541292160749435,
        "vertical_index": 1,
        "xi_index": 180
      }
    },
    "zeta": {
      "max": {
        "boundary_sides": [
          "north"
        ],
        "distance_to_source_m": 47040.01781532243,
        "eta_index": 189,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.84,
        "lon": 140.95839999999998,
        "mask_rho_like": 1,
        "near_boundary": true,
        "near_open_boundary": true,
        "near_source_within_5km": false,
        "open_boundary_sides": [
          "north"
        ],
        "s_coordinate": null,
        "time_index": 3,
        "time_iso": "2025-01-01T03:30:00",
        "value": 0.6727716326713562,
        "vertical_index": null,
        "xi_index": 14
      },
      "min": {
        "boundary_sides": [],
        "distance_to_source_m": 44750.58308175442,
        "eta_index": 185,
        "grid_type": "rho",
        "h_m": 10.0,
        "lat": 37.82222222222222,
        "lon": 140.9864,
        "mask_rho_like": 1,
        "near_boundary": false,
        "near_open_boundary": false,
        "near_source_within_5km": false,
        "open_boundary_sides": [],
        "s_coordinate": null,
        "time_index": 22,
        "time_iso": "2025-01-01T22:30:00",
        "value": -0.9209019541740417,
        "vertical_index": null,
        "xi_index": 19
      }
    }
  },
  "label": "average",
  "path": "/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_online_7d_online_my25_uvtide.nc"
}
```

## inventory

```json
{
  "cumulative_source_bq": 421917808219.1781,
  "delta_bq": 421913754201.44946,
  "first_bq": 0.0,
  "last_bq": 421913754201.44946,
  "source_rate_bq_s": 697615.4236428209
}
```

## open_boundary_export_estimate

```json
{
  "east_bq": 0.0,
  "north_bq": 4402524.273780699,
  "note": "Approximate outward dye export integrated from hourly-averaged Huon/Hvom times boundary-adjacent dye concentration.",
  "south_bq": 22.645339951419647,
  "total_bq": 4402546.919120651
}
```

## interpretation

```json
{
  "akv_akt_aks": {
    "AKs_max_gt_100": true,
    "AKs_max_location": {
      "boundary_sides": [],
      "distance_to_source_m": 56409.6875867444,
      "eta_index": 129,
      "grid_type": "rho",
      "h_m": 254.05078125,
      "lat": 37.57333333333334,
      "lon": 141.65279999999998,
      "mask_rho_like": 1,
      "near_boundary": false,
      "near_open_boundary": false,
      "near_source_within_5km": false,
      "open_boundary_sides": [],
      "s_coordinate": -0.625,
      "time_index": 3,
      "time_iso": "2025-01-01T03:00:00",
      "value": 238.6306610107422,
      "vertical_index": 15,
      "xi_index": 138
    },
    "AKt_max_gt_100": true,
    "AKt_max_location": {
      "boundary_sides": [],
      "distance_to_source_m": 56409.6875867444,
      "eta_index": 129,
      "grid_type": "rho",
      "h_m": 254.05078125,
      "lat": 37.57333333333334,
      "lon": 141.65279999999998,
      "mask_rho_like": 1,
      "near_boundary": false,
      "near_open_boundary": false,
      "near_source_within_5km": false,
      "open_boundary_sides": [],
      "s_coordinate": -0.625,
      "time_index": 3,
      "time_iso": "2025-01-01T03:00:00",
      "value": 238.6306610107422,
      "vertical_index": 15,
      "xi_index": 138
    },
    "AKv_max_gt_100": true,
    "AKv_max_location": {
      "boundary_sides": [],
      "distance_to_source_m": 56409.6875867444,
      "eta_index": 129,
      "grid_type": "rho",
      "h_m": 254.05078125,
      "lat": 37.57333333333334,
      "lon": 141.65279999999998,
      "mask_rho_like": 1,
      "near_boundary": false,
      "near_open_boundary": false,
      "near_source_within_5km": false,
      "open_boundary_sides": [],
      "s_coordinate": -0.625,
      "time_index": 3,
      "time_iso": "2025-01-01T03:00:00",
      "value": 176.2513427734375,
      "vertical_index": 15,
      "xi_index": 138
    }
  },
  "dye": {
    "max_distance_to_source_m": 0.0,
    "max_in_upper_quarter": true,
    "max_near_source": true,
    "max_vertical_index": 39,
    "min_value": -0.06385604292154312,
    "negative_roundoff_only": false,
    "surface_source_profile": true
  },
  "flow_scale": {
    "reaches_2m_s_scale": true,
    "u_v_speed_order_m_s": 2.3380706310272217
  },
  "inventory": {
    "approx_open_boundary_loss_bq": 4402546.919120651,
    "cumulative_source_bq": 421917808219.1781,
    "inventory_delta_bq": 421913754201.44946,
    "inventory_over_source": 0.9999903914514873
  },
  "temp_low": {
    "min_temp_c": 0.006932535208761692,
    "near_freezing": true
  }
}
```
