#!/usr/bin/env python3
"""Create month-end surface passive-tracer concentration maps for a ROMS case."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, LogNorm
from matplotlib.ticker import FuncFormatter, LogFormatterMathtext
from netCDF4 import Dataset, num2date


SCRIPT_PATH = Path(__file__).resolve()
WORKSPACE_ROOT = SCRIPT_PATH.parents[3]
for core_dir in (WORKSPACE_ROOT / "ROMS_Run" / "core", WORKSPACE_ROOT / "Data_pre" / "core"):
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))

from run_context import resolve_run_context  # type: ignore  # noqa: E402


YEAR = 2025
TRACER_NAME = "dye_01"
VMIN = 1.0e-11
LAND_COLOR = (180 / 255, 180 / 255, 180 / 255)
COLOR_STOPS = [
    (0.00, (20 / 255, 32 / 255, 120 / 255)),
    (0.20, (35 / 255, 110 / 255, 210 / 255)),
    (0.40, (38 / 255, 190 / 255, 225 / 255)),
    (0.60, (95 / 255, 220 / 255, 140 / 255)),
    (0.78, (245 / 255, 220 / 255, 70 / 255)),
    (0.90, (245 / 255, 120 / 255, 40 / 255)),
    (1.00, (175 / 255, 0 / 255, 20 / 255)),
]
CONCENTRATION_CMAP = LinearSegmentedColormap.from_list(
    "fdnpp_reference_concentration", COLOR_STOPS
)
CONCENTRATION_CMAP.set_bad("white")
LAND_CMAP = ListedColormap([LAND_COLOR])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-name", required=True, help="Case name, for example LAHAGUE")
    parser.add_argument("--average", type=Path, default=None, help="Override average NetCDF path")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override figure output directory")
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--variable", default=TRACER_NAME)
    parser.add_argument("--vmin", type=float, default=VMIN)
    parser.add_argument(
        "--vmax",
        type=float,
        default=None,
        help="Log colorbar maximum; default is a case-specific power-of-ten ceiling",
    )
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 12,
            "axes.labelsize": 13,
            "axes.titlesize": 15,
            "axes.titleweight": "bold",
            "axes.linewidth": 1.0,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )


def python_datetimes(time_variable) -> list[dt.datetime]:
    converted = num2date(
        time_variable[:],
        time_variable.units,
        calendar=getattr(time_variable, "calendar", "standard"),
        only_use_cftime_datetimes=False,
    )
    return [
        dt.datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
        )
        for value in converted
    ]


def lon_formatter(value: float, _position: int) -> str:
    suffix = "E" if value >= 0 else "W"
    return f"{abs(value):.1f}\N{DEGREE SIGN}{suffix}"


def lat_formatter(value: float, _position: int) -> str:
    suffix = "N" if value >= 0 else "S"
    return f"{abs(value):.1f}\N{DEGREE SIGN}{suffix}"


def tracer_units(case_params: dict, variable) -> tuple[str, str, float, str]:
    """Return metadata units, authoritative units, conversion, and display units."""
    metadata_units = str(getattr(variable, "units", "unknown"))
    tracer_cfg = case_params.get("passive_tracer", {})
    authoritative_units = str(tracer_cfg.get("unit") or metadata_units)
    compact = authoritative_units.lower().replace(" ", "")
    if "bq/l" in compact or "bql-1" in compact:
        return metadata_units, authoritative_units, 1.0, "Bq/L"
    if "bq" in compact and ("m-3" in compact or "meter-3" in compact):
        return metadata_units, authoritative_units, 1.0e-3, "Bq/L"
    return metadata_units, authoritative_units, 1.0, authoritative_units


def choose_vmax(fields: list[np.ndarray], vmin: float) -> float:
    values = np.concatenate([field[np.isfinite(field)] for field in fields])
    positive = values[values > 0]
    if positive.size == 0:
        return max(1.0, vmin * 10.0)
    maximum = float(np.max(positive))
    ceiling = 10.0 ** math.ceil(math.log10(maximum))
    return max(10.0, ceiling, vmin * 10.0)


def colorbar_ticks(vmax: float, vmin: float) -> list[float]:
    upper_exponent = max(-10, math.floor(math.log10(vmax)))
    ticks = [
        10.0**exponent
        for exponent in range(-11, upper_exponent + 1, 2)
        if vmin <= 10.0**exponent <= vmax
    ]
    if not ticks or not math.isclose(ticks[-1], vmax):
        ticks.append(vmax)
    return ticks


def draw_concentration_map(
    ax,
    lon: np.ndarray,
    lat: np.ndarray,
    mask: np.ndarray,
    concentration: np.ndarray,
    timestamp: dt.datetime,
    *,
    vmin: float,
    vmax: float,
):
    plotted = np.ma.masked_invalid(
        np.where(mask, np.maximum(concentration, vmin), np.nan)
    )
    mesh = ax.pcolormesh(
        lon,
        lat,
        plotted,
        cmap=CONCENTRATION_CMAP,
        norm=LogNorm(vmin=vmin, vmax=vmax, clip=True),
        shading="auto",
        rasterized=True,
    )
    land = np.ma.masked_where(mask, np.ones(mask.shape))
    ax.pcolormesh(
        lon,
        lat,
        land,
        cmap=LAND_CMAP,
        vmin=0,
        vmax=1,
        shading="auto",
        rasterized=True,
    )
    ax.set_facecolor("white")
    ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
    ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))
    ax.xaxis.set_major_formatter(FuncFormatter(lon_formatter))
    ax.yaxis.set_major_formatter(FuncFormatter(lat_formatter))
    maximum = float(np.nanmax(np.where(mask, concentration, np.nan)))
    ax.text(
        0.5,
        0.955,
        f"{timestamp:%Y-%m-%d}",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=15,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.875,
        f"Max: {maximum:.3g} Bq/L" if np.isfinite(maximum) else "Max: n/a",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=13,
    )
    return mesh, maximum


def add_colorbar(figure, mesh, axes, *, vmin: float, vmax: float):
    colorbar = figure.colorbar(
        mesh,
        ax=axes,
        orientation="vertical",
        fraction=0.035,
        pad=0.025,
        ticks=colorbar_ticks(vmax, vmin),
        format=LogFormatterMathtext(10),
    )
    colorbar.set_label("Concentration [Bq/L]", fontsize=14)
    colorbar.ax.tick_params(labelsize=11)
    return colorbar


def default_average_path(case_root: Path, case_params: dict) -> Path:
    case_cfg = case_params.get("case", {})
    slug = str(case_cfg.get("slug") or case_cfg.get("name", case_root.name)).lower()
    source = str(case_params.get("ocean", {}).get("default_source", "glorys12v1"))
    filename = f"avg_{slug}_online_continuous_my25_uvtide_{source}.nc"
    return case_root / "output" / filename


def write_products(
    average_path: Path,
    output_dir: Path,
    case_params: dict,
    *,
    year: int,
    variable_name: str,
    requested_vmin: float,
    requested_vmax: float | None,
) -> tuple[Path, Path]:
    monthly_dir = output_dir / "concentration_month_end"
    monthly_dir.mkdir(parents=True, exist_ok=True)

    with Dataset(average_path) as dataset:
        lon = np.asarray(dataset["lon_rho"][:])
        lat = np.asarray(dataset["lat_rho"][:])
        mask = np.asarray(dataset["mask_rho"][:]) > 0.5
        times = python_datetimes(dataset["ocean_time"])
        variable = dataset[variable_name]
        metadata_units, authoritative_units, conversion, display_units = tracer_units(
            case_params, variable
        )
        month_indices = [
            max(
                index
                for index, timestamp in enumerate(times)
                if timestamp.year == year and timestamp.month == month
            )
            for month in range(1, 13)
        ]
        fields: list[np.ndarray] = []
        for index in month_indices:
            raw = np.ma.asarray(variable[index, -1, :, :]).filled(np.nan).astype(float)
            raw[~mask] = np.nan
            fields.append(raw * conversion)
        vmin = requested_vmin
        vmax = requested_vmax or choose_vmax(fields, vmin)
        if vmax <= vmin:
            raise ValueError(f"vmax must be greater than vmin; got {vmax} <= {vmin}")
        s_rho = float(dataset["s_rho"][-1]) if "s_rho" in dataset.variables else float("nan")

    records = []
    for month, index, concentration in zip(
        range(1, 13), month_indices, fields, strict=True
    ):
        figure, ax = plt.subplots(figsize=(8.3, 6.5))
        mesh, maximum = draw_concentration_map(
            ax,
            lon,
            lat,
            mask,
            concentration,
            times[index],
            vmin=vmin,
            vmax=vmax,
        )
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        add_colorbar(figure, mesh, ax, vmin=vmin, vmax=vmax)
        figure.tight_layout()
        output_path = monthly_dir / f"surface_concentration_{year}_{month:02d}_month_end.png"
        figure.savefig(output_path)
        plt.close(figure)
        records.append(
            {
                "month": f"{year}-{month:02d}",
                "average_record": index,
                "average_time_utc": times[index].isoformat(sep=" "),
                "vertical_index": -1,
                "s_rho": s_rho,
                "metadata_units": metadata_units,
                "authoritative_input_units": authoritative_units,
                "display_units": display_units,
                "display_conversion": conversion,
                "colorbar_min": vmin,
                "colorbar_max": vmax,
                "maximum_display": maximum,
                "figure": str(output_path.resolve()),
            }
        )

    summary_path = output_dir / f"surface_concentration_{year}_month_end_12panel.png"
    figure, axes = plt.subplots(3, 4, figsize=(18, 13), sharex=True, sharey=True)
    mesh = None
    for month, index, concentration, ax in zip(
        range(1, 13), month_indices, fields, axes.flat, strict=True
    ):
        mesh, _ = draw_concentration_map(
            ax,
            lon,
            lat,
            mask,
            concentration,
            times[index],
            vmin=vmin,
            vmax=vmax,
        )
        row, col = divmod(month - 1, 4)
        if row == 2:
            ax.set_xlabel("Longitude")
        if col == 0:
            ax.set_ylabel("Latitude")
    add_colorbar(figure, mesh, list(axes.flat), vmin=vmin, vmax=vmax)
    figure.subplots_adjust(
        left=0.06,
        right=0.9,
        bottom=0.07,
        top=0.985,
        wspace=0.08,
        hspace=0.08,
    )
    figure.savefig(summary_path)
    plt.close(figure)

    manifest_path = output_dir / f"surface_concentration_{year}_month_end_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    return summary_path, manifest_path


def main() -> None:
    args = parse_args()
    configure_style()
    context = resolve_run_context(
        case_name=args.case_name,
        mode="online_continuous_my25_uvtide",
    )
    average_path = (
        args.average.expanduser().resolve()
        if args.average is not None
        else default_average_path(context.case_root, context.project_params)
    )
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else context.case_root / "analysis" / "figures" / "v2_continuous"
    )
    if not average_path.exists():
        raise SystemExit(f"average NetCDF does not exist: {average_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path, manifest_path = write_products(
        average_path,
        output_dir,
        context.project_params,
        year=args.year,
        variable_name=args.variable,
        requested_vmin=args.vmin,
        requested_vmax=args.vmax,
    )
    print(f"Average input: {average_path}")
    print(f"Summary figure: {summary_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
