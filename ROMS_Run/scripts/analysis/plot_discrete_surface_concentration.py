#!/usr/bin/env python3
"""Create discrete-colorbar month-end tracer summary figures."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import FuncFormatter, MaxNLocator
from netCDF4 import Dataset


SCRIPT_PATH = Path(__file__).resolve()
WORKSPACE_ROOT = SCRIPT_PATH.parents[3]
for core_dir in (WORKSPACE_ROOT / "ROMS_Run" / "core", WORKSPACE_ROOT / "Data_pre" / "core"):
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))

from plot_surface_concentration import (  # type: ignore  # noqa: E402
    CONCENTRATION_CMAP,
    LAND_CMAP,
    YEAR,
    VMIN,
    choose_vmax,
    configure_style,
    default_average_path,
    lat_formatter,
    lon_formatter,
    python_datetimes,
    tracer_units,
)
from run_context import resolve_run_context  # type: ignore  # noqa: E402


VARIANT_SUFFIX = "discrete_black_edges"
N_COLOR_BINS = 12

try:
    from audit_panel_alignment import (  # type: ignore  # noqa: E402
        require_matplotlib_panel_alignment,
    )
except ImportError:  # pragma: no cover - available in the figure QA environment
    require_matplotlib_panel_alignment = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-name", required=True, help="Case name, for example FDNPP")
    parser.add_argument("--average", type=Path, default=None, help="Override average NetCDF path")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override figure output directory")
    parser.add_argument("--output-stem", default=None, help="Prefix for the new figure filenames")
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--variable", default="dye_01")
    parser.add_argument("--vmin", type=float, default=VMIN)
    parser.add_argument("--bins", type=int, default=N_COLOR_BINS)
    parser.add_argument(
        "--vmax",
        type=float,
        default=None,
        help="Log colorbar maximum; default is a case-specific power-of-ten ceiling",
    )
    return parser.parse_args()


def configure_discrete_style() -> None:
    configure_style()
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": 14,
            "axes.labelsize": 14,
            "xtick.labelsize": 10,
            "ytick.labelsize": 12,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "savefig.dpi": 600,
        }
    )


def default_output_stem(case_name: str) -> str:
    return "surface_hto" if case_name.upper() == "FDNPP" else "surface_concentration"


def log_bin_boundaries(vmin: float, vmax: float, bins: int) -> np.ndarray:
    """Match the reference figure's equal-width bins in log concentration."""
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin <= 0 or vmax <= vmin:
        raise ValueError(f"invalid logarithmic range: {vmin} to {vmax}")
    if bins < 1:
        raise ValueError(f"bins must be positive: {bins}")
    return np.geomspace(vmin, vmax, bins + 1)


def discrete_colormap(levels: np.ndarray) -> ListedColormap:
    centers = np.sqrt(levels[:-1] * levels[1:])
    fractions = (np.log10(centers) - math.log10(levels[0])) / (
        math.log10(levels[-1]) - math.log10(levels[0])
    )
    cmap = ListedColormap(CONCENTRATION_CMAP(np.clip(fractions, 0.0, 1.0)))
    cmap.set_bad("white")
    return cmap


def level_labels(levels: np.ndarray) -> list[str]:
    labels = []
    for level in levels:
        exponent = math.log10(float(level))
        rounded = round(exponent)
        if math.isclose(exponent, rounded, rel_tol=0.0, abs_tol=1e-10):
            labels.append(rf"$10^{{{rounded}}}$")
        else:
            labels.append(f"{level:.3g}")
    return labels


def draw_discrete_map(
    ax,
    lon: np.ndarray,
    lat: np.ndarray,
    mask: np.ndarray,
    concentration: np.ndarray,
    timestamp: dt.datetime,
    *,
    norm: BoundaryNorm,
    cmap: ListedColormap,
    vmin: float,
):
    # The reference renders wet values below the display floor as white.
    plotted = np.ma.masked_where(
        ~mask | ~np.isfinite(concentration) | (concentration < vmin),
        concentration,
    )
    mesh = ax.pcolormesh(
        lon,
        lat,
        plotted,
        cmap=cmap,
        norm=norm,
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
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, prune="both"))
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


def add_discrete_colorbar(figure, mesh, levels: np.ndarray):
    # Keep the legend in a reserved column, clear of all twelve maps.
    # Match the reference's 24 px bar at x=1720 on a 1880x1750 canvas.
    colorbar_axes = figure.add_axes([1720 / 1880, 240 / 1750, 24 / 1880, 1220 / 1750])
    colorbar = figure.colorbar(
        mesh,
        cax=colorbar_axes,
        boundaries=levels,
        ticks=levels,
        spacing="uniform",
        orientation="vertical",
        drawedges=True,
    )
    colorbar.set_label("Concentration [Bq/L]", fontsize=19, labelpad=12)
    colorbar.ax.set_yticklabels(level_labels(levels), fontsize=16)
    colorbar.ax.tick_params(length=5, width=0.8, color="black")
    colorbar.dividers.set_color("black")
    colorbar.dividers.set_linewidth(0.8)
    colorbar.outline.set_edgecolor("black")
    colorbar.outline.set_linewidth(0.8)
    return colorbar


def write_summary(
    average_path: Path,
    output_dir: Path,
    case_params: dict,
    *,
    case_name: str,
    output_stem: str,
    year: int,
    variable_name: str,
    requested_vmin: float,
    requested_vmax: float | None,
    bins: int,
) -> tuple[Path, Path, Path, Path]:
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
        levels = log_bin_boundaries(vmin, vmax, bins)
        norm = BoundaryNorm(levels, ncolors=len(levels) - 1, clip=True)
        cmap = discrete_colormap(levels)
        s_rho = float(dataset["s_rho"][-1]) if "s_rho" in dataset.variables else float("nan")

    figure, axes = plt.subplots(3, 4, figsize=(18, 13), sharex=True, sharey=True)
    mesh = None
    records = []
    for month, index, concentration, ax in zip(
        range(1, 13), month_indices, fields, axes.flat, strict=True
    ):
        mesh, maximum = draw_discrete_map(
            ax,
            lon,
            lat,
            mask,
            concentration,
            times[index],
            norm=norm,
            cmap=cmap,
            vmin=vmin,
        )
        row, col = divmod(month - 1, 4)
        if row == 2:
            ax.set_xlabel("Longitude")
        if col == 0:
            ax.set_ylabel("Latitude")
        records.append(
            {
                "case": case_name,
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
                "color_bins": bins,
                "discrete_boundaries": ";".join(f"{level:.12g}" for level in levels),
                "colorbar_labels": ";".join(level_labels(levels)),
                "maximum_display": maximum,
                "wet_cells_above_colorbar_max": int(
                    np.count_nonzero(mask & np.isfinite(concentration) & (concentration > vmax))
                ),
            }
        )

    figure.subplots_adjust(
        left=0.065,
        right=1690 / 1880,
        bottom=0.09,
        top=0.975,
        wspace=0.13,
        hspace=0.13,
    )
    add_discrete_colorbar(figure, mesh, levels)
    figure.canvas.draw()

    tag = f"{output_stem}_{year}_month_end_12panel_{VARIANT_SUFFIX}"
    summary_path = output_dir / f"{tag}.png"
    pdf_path = output_dir / f"{tag}.pdf"
    svg_path = output_dir / f"{tag}.svg"
    alignment_path = output_dir / f"{tag}.alignment.json"
    alignment_overlay = output_dir / f"{tag}.alignment.svg"
    if require_matplotlib_panel_alignment is None:
        raise RuntimeError(
            "the figure QA helper is unavailable; add the nature-figure scripts directory to PYTHONPATH"
        )
    require_matplotlib_panel_alignment(
        figure,
        json_out=alignment_path,
        overlay_svg=alignment_overlay,
        tolerance_pt=1.5,
        gutter_tolerance_pt=1.5,
        require_panel_labels=False,
        strict=True,
        exclude_axes=[figure.axes[-1]],
    )
    figure.savefig(summary_path, dpi=600)
    figure.savefig(pdf_path)
    figure.savefig(svg_path)
    plt.close(figure)

    manifest_path = output_dir / f"{tag}_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]) + ["figure"])
        writer.writeheader()
        for record in records:
            writer.writerow({**record, "figure": str(summary_path.resolve())})

    qa_path = output_dir / f"{tag}_qa.json"
    qa_path.write_text(
        json.dumps(
            {
                "case": case_name,
                "figure_type": "3x4 month-end surface concentration grid",
                "source": str(average_path.resolve()),
                "variable": variable_name,
                "vertical_index": -1,
                "selection": "last average record in each calendar month",
                "mask": "mask_rho > 0.5; land gray; wet cells below vmin white",
                "display_units": display_units,
                "display_conversion": conversion,
                "colorbar": {
                    "mode": "discrete logarithmic",
                    "bins": bins,
                    "boundaries": [float(level) for level in levels],
                    "labels": level_labels(levels),
                    "edge_color": "black",
                    "above_max_display": "highest color bin",
                },
                "months_with_values_above_colorbar_max": [
                    record["month"]
                    for record in records
                    if record["wet_cells_above_colorbar_max"] > 0
                ],
                "outputs": {
                    "png": str(summary_path.resolve()),
                    "pdf": str(pdf_path.resolve()),
                    "svg": str(svg_path.resolve()),
                    "alignment_report": str(alignment_path.resolve()),
                    "alignment_overlay": str(alignment_overlay.resolve()),
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary_path, pdf_path, svg_path, manifest_path


def main() -> None:
    args = parse_args()
    configure_discrete_style()
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
    output_stem = args.output_stem or default_output_stem(args.case_name)
    summary_path, pdf_path, svg_path, manifest_path = write_summary(
        average_path,
        output_dir,
        context.project_params,
        case_name=args.case_name,
        output_stem=output_stem,
        year=args.year,
        variable_name=args.variable,
        requested_vmin=args.vmin,
        requested_vmax=args.vmax,
        bins=args.bins,
    )
    print(f"Average input: {average_path}")
    print(f"Discrete summary PNG: {summary_path}")
    print(f"Discrete summary PDF: {pdf_path}")
    print(f"Discrete summary SVG: {svg_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
