#!/usr/bin/env python3
"""Download and normalize staged ERA5 raw files for the active case."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

import numpy as np
import xarray as xr

from case_naming import load_case_naming, staged_atmosphere_name
from era5_action_credentials import resolve_era5_credentials

from staged_data_utils import (
    ROOT,
    candidate_first,
    config_path_to_abs,
    dewpoint_to_relative_humidity_percent,
    ensure_parent,
    get_bbox,
    get_time_window,
    load_download_config,
    normalize_longitudes,
    sort_lat_lon_depth_time,
    accumulated_to_step_amount,
    step_amount_to_rate,
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--credentials-file", default=None)
    parser.add_argument("--atm-output", default=None)
    parser.add_argument("--rad-output", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--stop", default=None)
    parser.add_argument("--trust-env-proxy", action="store_true")
    return parser.parse_args()


def build_requests(window, bbox, variables: list[str]) -> list[dict]:
    grouped: dict[tuple[int, int], dict[str, set[str]]] = defaultdict(lambda: {"day": set(), "time": set()})
    current = window.start
    while current <= window.stop:
        bucket = grouped[(current.year, current.month)]
        bucket["day"].add(f"{current.day:02d}")
        bucket["time"].add(f"{current.hour:02d}:00")
        current += timedelta(hours=1)

    requests: list[dict] = []
    for year, month in sorted(grouped):
        bucket = grouped[(year, month)]
        requests.append(
            {
                "product_type": "reanalysis",
                "variable": variables,
                "year": f"{year:04d}",
                "month": f"{month:02d}",
                "day": sorted(bucket["day"]),
                "time": sorted(bucket["time"]),
                "area": [bbox.north, bbox.west, bbox.south, bbox.east],
                "data_format": "netcdf",
                "download_format": "unarchived",
            }
        )
    return requests


def retrieve_dataset(client, dataset: str, request: dict, target: Path) -> None:
    try:
        client.retrieve(dataset, request, str(target))
        return
    except TypeError:
        pass
    legacy = dict(request)
    legacy["format"] = "netcdf"
    legacy.pop("data_format", None)
    legacy.pop("download_format", None)
    client.retrieve(dataset, legacy, str(target))


def resolve_download_artifacts(path: Path, extract_dir: Path) -> list[Path]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".nc")]
            if not members:
                raise SystemExit(f"zip download did not contain a NetCDF file: {path}")
            extracted: list[Path] = []
            for member in members:
                archive.extract(member, path=extract_dir)
                extracted.append(extract_dir / member)
            return extracted
    return [path]


def open_and_normalize_coords(paths: list[Path]) -> xr.Dataset:
    datasets: list[xr.Dataset] = []
    for path in paths:
        with xr.open_dataset(path, engine="netcdf4", decode_cf=True) as raw:
            lon_name = candidate_first(raw.coords, ("lon", "longitude", "x"))
            lat_name = candidate_first(raw.coords, ("lat", "latitude", "y"))
            time_name = candidate_first(raw.coords, ("time", "valid_time"))
            working = raw.assign_coords({lon_name: normalize_longitudes(raw[lon_name].values)})
            renamed = sort_lat_lon_depth_time(working, lon_name, lat_name, None, time_name).rename(
                {lon_name: "lon", lat_name: "lat", time_name: "time"}
            )
            datasets.append(renamed.load())
    return xr.merge(datasets, compat="override")


def normalize_atmosphere(raw: xr.Dataset, source_dataset: str) -> xr.Dataset:
    t2m = raw[candidate_first(raw.data_vars, ("t2m", "2m_temperature"))]
    d2m = raw[candidate_first(raw.data_vars, ("d2m", "2m_dewpoint_temperature"))]
    u10 = raw[candidate_first(raw.data_vars, ("u10", "10m_u_component_of_wind"))]
    v10 = raw[candidate_first(raw.data_vars, ("v10", "10m_v_component_of_wind"))]
    sp = raw[candidate_first(raw.data_vars, ("sp", "surface_pressure"))]
    tp = raw[candidate_first(raw.data_vars, ("tp", "total_precipitation"))]
    evap = raw[candidate_first(raw.data_vars, ("e", "evaporation"))]

    tair_c = t2m - 273.15
    dewpoint_c = d2m - 273.15
    qair = dewpoint_to_relative_humidity_percent(tair_c.values, dewpoint_c.values)

    times = raw["time"].values.astype("datetime64[s]")
    rain_amount = accumulated_to_step_amount(tp.values)
    rain_rate = step_amount_to_rate(rain_amount, times)

    evap_raw = evap.values
    evap_amount = accumulated_to_step_amount(np.abs(evap_raw) if np.nanmean(evap_raw) < 0.0 else evap_raw)
    evap_rate = step_amount_to_rate(evap_amount, times)
    eminusp = evap_rate - rain_rate

    ds = xr.Dataset(
        data_vars={
            "Uwind": u10.transpose("time", "lat", "lon"),
            "Vwind": v10.transpose("time", "lat", "lon"),
            "Pair": (("time", "lat", "lon"), sp.values / 100.0),
            "Tair": (("time", "lat", "lon"), tair_c.values),
            "Qair": (("time", "lat", "lon"), qair),
            "rain": (("time", "lat", "lon"), rain_rate),
            "EminusP": (("time", "lat", "lon"), eminusp),
        },
        coords={"time": raw["time"], "lat": raw["lat"], "lon": raw["lon"]},
        attrs={
            "title": f"{load_case_naming().title} staged ERA5 atmosphere subset",
            "source_dataset": source_dataset,
        },
    )
    ds["Pair"].attrs["units"] = "mbar"
    ds["Tair"].attrs["units"] = "Celsius"
    ds["Qair"].attrs["units"] = "percent"
    ds["rain"].attrs["units"] = "m s-1"
    ds["EminusP"].attrs["units"] = "m s-1"
    ds["Uwind"].attrs["units"] = u10.attrs.get("units", "m s-1")
    ds["Vwind"].attrs["units"] = v10.attrs.get("units", "m s-1")
    return ds


def normalize_radiation(raw: xr.Dataset, source_dataset: str) -> xr.Dataset:
    ssrd = raw[candidate_first(raw.data_vars, ("ssrd", "surface_solar_radiation_downwards"))]
    strd = raw[candidate_first(raw.data_vars, ("strd", "surface_thermal_radiation_downwards"))]
    strn = raw[candidate_first(raw.data_vars, ("str", "surface_net_thermal_radiation"))]

    times = raw["time"].values.astype("datetime64[s]")
    sw_flux = step_amount_to_rate(accumulated_to_step_amount(ssrd.values), times)
    lwd_flux = step_amount_to_rate(accumulated_to_step_amount(strd.values), times)
    lwn_amount = accumulated_to_step_amount(np.abs(strn.values) if np.nanmean(strn.values) < 0.0 else strn.values)
    lwn_flux = step_amount_to_rate(lwn_amount, times)

    ds = xr.Dataset(
        data_vars={
            "swrad": (("time", "lat", "lon"), sw_flux),
            "lwrad_down": (("time", "lat", "lon"), lwd_flux),
            "lwrad": (("time", "lat", "lon"), lwn_flux),
        },
        coords={"time": raw["time"], "lat": raw["lat"], "lon": raw["lon"]},
        attrs={
            "title": f"{load_case_naming().title} staged ERA5 radiation subset",
            "source_dataset": source_dataset,
        },
    )
    ds["swrad"].attrs["units"] = "W m-2"
    ds["lwrad_down"].attrs["units"] = "W m-2"
    ds["lwrad"].attrs["units"] = "W m-2"
    return ds


def main() -> None:
    args = parse_args()
    config = load_download_config(args.config)
    bbox = get_bbox(config, source="era5")
    window = get_time_window(config)
    start = datetime.fromisoformat(args.start) if args.start else window.start
    stop = datetime.fromisoformat(args.stop) if args.stop else window.stop
    if start > stop:
        raise SystemExit("start must not be later than stop")
    # CI uses CDSAPI_KEY injected by GitHub Actions Secrets; never touch
    # the historic repository credentials file. Local fallback is allowed
    # only for an explicit credential file kept OUTSIDE the Git tree.
    credentials_file = args.credentials_file
    url, key, credential_source = resolve_era5_credentials(credentials_file)
    if args.atm_output:
        atm_output = Path(args.atm_output)
    elif args.start or args.stop:
        atm_output = ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("atm", start=start, stop=stop)
    else:
        atm_output = config_path_to_abs(config, "era5_atm")
    if args.rad_output:
        rad_output = Path(args.rad_output)
    elif args.start or args.stop:
        rad_output = ROOT / "data" / "raw" / "atmosphere" / staged_atmosphere_name("rad", start=start, stop=stop)
    else:
        rad_output = config_path_to_abs(config, "era5_rad")

    if not args.trust_env_proxy:
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
            os.environ.pop(name, None)

    try:
        import cdsapi
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "cdsapi is not installed. Install it in the current Python environment before downloading ERA5."
        ) from exc

    client = cdsapi.Client(url=url, key=key, quiet=False, progress=True)
    atm_requests = build_requests(type(window)(start=start, stop=stop), bbox, list(config["era5"]["atm_variables"]))
    rad_requests = build_requests(type(window)(start=start, stop=stop), bbox, list(config["era5"]["rad_variables"]))

    with TemporaryDirectory(prefix="era5_stage_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        atm_ready: list[Path] = []
        rad_ready: list[Path] = []

        for index, request in enumerate(atm_requests):
            atm_raw = tmpdir_path / f"era5_atm_raw_{index}.nc"
            retrieve_dataset(client, config["era5"]["dataset"], request, atm_raw)
            atm_ready.extend(resolve_download_artifacts(atm_raw, tmpdir_path / f"atm_unpacked_{index}"))

        for index, request in enumerate(rad_requests):
            rad_raw = tmpdir_path / f"era5_rad_raw_{index}.nc"
            retrieve_dataset(client, config["era5"]["dataset"], request, rad_raw)
            rad_ready.extend(resolve_download_artifacts(rad_raw, tmpdir_path / f"rad_unpacked_{index}"))

        atm_src = open_and_normalize_coords(atm_ready)
        atm_ds = normalize_atmosphere(atm_src, config["era5"]["dataset"])
        ensure_parent(atm_output)
        atm_ds.to_netcdf(atm_output, engine="netcdf4")
        atm_src.close()

        rad_src = open_and_normalize_coords(rad_ready)
        rad_ds = normalize_radiation(rad_src, config["era5"]["dataset"])
        ensure_parent(rad_output)
        rad_ds.to_netcdf(rad_output, engine="netcdf4")
        rad_src.close()

    print(f"credentials_source={credential_source}")
    print(f"dataset={config['era5']['dataset']}")
    print(f"atm_output={atm_output}")
    print(f"rad_output={rad_output}")


if __name__ == "__main__":
    main()
