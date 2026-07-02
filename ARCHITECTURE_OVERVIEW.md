# ROMS Workflow Architecture Overview

This document summarizes the current `/home/lhy/ROMS` architecture and the relationship between preprocessing, build, run, and case workspaces.

## Directory Relationship

```mermaid
flowchart TD
    ROOT["/home/lhy/ROMS"] --> SRC["roms_src/roms<br/>Shared ROMS source tree"]
    ROOT --> DP["Data_pre/<br/>Download + preprocessing framework"]
    ROOT --> RB["ROMS_Build/<br/>Shared build framework"]
    ROOT --> RR["ROMS_Run/<br/>Shared run framework"]
    ROOT --> PRJ["projects/<case_name>/<br/>Case workspace"]
    ROOT --> ARC["archive/<br/>Legacy materials"]
    ROOT --> CREDS["credentials/<br/>Shared credentials"]

    DP --> CASECFG["Data_pre/cases/<case_name>/config<br/>Shared case metadata"]
    PRJ --> CFG["config/"]
    PRJ --> RAW["data/"]
    PRJ --> INP["input/"]
    PRJ --> BLD["build/"]
    PRJ --> BIN["bin/"]
    PRJ --> RUN["run/"]
    PRJ --> LOG["logs/"]
    PRJ --> OUT["output/"]
    PRJ --> DOC["docs/"]
```

## Workflow Relationship

```mermaid
flowchart LR
    A["Case config<br/>projects/<case>/config<br/>Data_pre/cases/<case>/config"] --> B["Data_pre<br/>download, stage, preprocess, validate"]
    C["Offline shared datasets<br/>example: GEBCO, TPXO"] --> B
    D["Online data services<br/>example: HYCOM, ERA5"] --> B
    E["credentials/era5_key.txt"] --> B

    B --> F["projects/<case>/data<br/>raw + staged data"]
    B --> G["projects/<case>/input<br/>ROMS-ready NetCDF"]
    B --> H["projects/<case>/run<br/>generated .in files"]

    I["roms_src/roms<br/>shared source"] --> J["ROMS_Build<br/>check env, plan, build"]
    A --> J
    J --> K["projects/<case>/build<br/>build intermediates"]
    J --> L["projects/<case>/bin<br/>ROMS executable"]

    G --> M["ROMS_Run<br/>validate prereqs, launch runs"]
    H --> M
    L --> M
    A --> M

    M --> N["projects/<case>/logs<br/>stdout/stderr, run logs"]
    M --> O["projects/<case>/output<br/>ROMS history/restart/output"]
```

## Responsibility Split

- `Data_pre`: turns external or offline datasets into ROMS-ready inputs.
- `ROMS_Build`: turns shared ROMS source into a case-usable executable.
- `ROMS_Run`: turns executable + `.in` + input files into an actual model run.
- `projects/<case_name>`: stores all case-specific inputs, binaries, logs, and outputs.
- `archive/`: stores legacy projects, tools, and notes that should not stay in the active workflow.
- `credentials/`: stores shared secret files referenced by active workflows.

## Initial-Condition Note

- Scientific initial conditions belong to the ocean preprocessing chain, for example `Data_pre/scripts/ocean/create_ocean_ini_from_hycom.py`.
- `Data_pre/scripts/run_support/create_initial_nc.py` is `technical fallback only`.
- Its output `roms_ini_pilot.nc` exists to support smoke tests and file-plumbing checks before real ocean initial fields are available.
- It should not be interpreted as a scientific substitute for HYCOM- or GLORYS-derived initial conditions.

## End-to-End View

1. Define or update case configuration.
2. Use `Data_pre` to download, subset, preprocess, and validate inputs.
3. Use `ROMS_Build` to compile the ROMS executable for that case.
4. Use `ROMS_Run` to validate the run layout and launch smoke, pilot, or production runs.
5. Keep runtime products inside `projects/<case_name>/`.
