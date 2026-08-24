#!/usr/bin/env python3
"""Merge adjacent ROMS forcing files while removing the shared boundary record."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from roms_preprocessing_utils import ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _is_time_dimension(ds: Dataset, name: str) -> bool:
    lowered = name.lower()
    if lowered.endswith("_time") or lowered == "time":
        return True
    variable = ds.variables.get(name)
    units = str(getattr(variable, "units", "")) if variable is not None else ""
    return " since " in units.lower() and variable is not None and len(variable.dimensions) == 1


def _time_dimensions(ds: Dataset) -> list[str]:
    return [name for name in ds.dimensions if _is_time_dimension(ds, name) and name in ds.variables]


def _value_key(value: object) -> tuple[str, float | str]:
    try:
        return ("number", round(float(value), 9))
    except (TypeError, ValueError):
        return ("text", str(value))


def _merge_indices(datasets: list[Dataset], dimension: str) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]:
    merged_values: list[object] = []
    source_indices: list[list[int]] = [[] for _ in datasets]
    source_positions: list[list[int]] = [[] for _ in datasets]
    seen: set[tuple[str, float | str]] = set()
    for source_index, ds in enumerate(datasets):
        values = np.asarray(ds.variables[dimension][:])
        for local_index, value in enumerate(values):
            key = _value_key(value)
            if key in seen:
                continue
            seen.add(key)
            source_indices[source_index].append(local_index)
            source_positions[source_index].append(len(merged_values))
            merged_values.append(value)
    if not merged_values:
        return np.asarray([], dtype=float), [np.asarray(item, dtype=int) for item in source_indices], [np.asarray(item, dtype=int) for item in source_positions]
    return np.asarray(merged_values), [np.asarray(item, dtype=int) for item in source_indices], [np.asarray(item, dtype=int) for item in source_positions]


def _copy_attributes(source: object, target: object) -> None:
    for name in source.ncattrs():
        if name == "_FillValue":
            continue
        setattr(target, name, getattr(source, name))


def _create_variable(ds: Dataset, source: object, dimensions: tuple[str, ...]):
    fill_value = getattr(source, "_FillValue", None)
    kwargs = {"zlib": True, "complevel": 1}
    if fill_value is not None:
        kwargs["fill_value"] = fill_value
    try:
        target = ds.createVariable(source.name, source.datatype, dimensions, **kwargs)
    except (TypeError, ValueError):
        target = ds.createVariable(source.name, source.datatype, dimensions)
    _copy_attributes(source, target)
    return target


def merge_files(inputs: list[Path], output: Path) -> None:
    if len(inputs) < 2:
        raise ValueError("at least two input forcing files are required")
    if any(not path.exists() for path in inputs):
        missing = ", ".join(str(path) for path in inputs if not path.exists())
        raise FileNotFoundError(missing)

    with ExitStackDatasets(inputs) as datasets:
        first = datasets[0]
        time_dims = _time_dimensions(first)
        if not time_dims:
            raise ValueError(f"no time dimensions found in {inputs[0]}")
        for ds in datasets[1:]:
            if set(ds.dimensions) != set(first.dimensions):
                raise ValueError("all forcing files must have the same dimensions")
            if set(ds.variables) != set(first.variables):
                raise ValueError("all forcing files must have the same variables")
        merged = {}
        for dimension in time_dims:
            merged[dimension] = _merge_indices(datasets, dimension)

        output.parent.mkdir(parents=True, exist_ok=True)
        with Dataset(output, "w", format="NETCDF4") as target:
            for name, dimension in first.dimensions.items():
                if name in merged:
                    target.createDimension(name, len(merged[name][0]))
                else:
                    target.createDimension(name, len(dimension))
            _copy_attributes(first, target)
            target.merged_from = ",".join(str(path) for path in inputs)
            target.merge_policy = "concatenate in input order and remove duplicate coordinate records"

            for name, source_var in first.variables.items():
                target_var = _create_variable(target, source_var, source_var.dimensions)
                time_axes = [
                    (axis, dimension)
                    for axis, dimension in enumerate(source_var.dimensions)
                    if dimension in merged
                ]
                if not time_axes:
                    target_var[:] = source_var[:]
                    continue
                for source_index, ds in enumerate(datasets):
                    selections = {dimension: merged[dimension][1][source_index] for _, dimension in time_axes}
                    if any(indices.size == 0 for indices in selections.values()):
                        continue
                    data = np.asarray(ds.variables[name][:])
                    for axis, dimension in reversed(time_axes):
                        data = np.take(data, selections[dimension], axis=axis)
                    destination = []
                    for axis, dimension in enumerate(source_var.dimensions):
                        if dimension in merged:
                            positions = merged[dimension][2][source_index]
                            destination.append(slice(int(positions[0]), int(positions[-1]) + 1))
                        else:
                            destination.append(slice(None))
                    target_var[tuple(destination)] = data


class ExitStackDatasets(list[Dataset]):
    """Small context manager keeping the merge implementation dependency-free."""

    def __init__(self, paths: list[Path]):
        super().__init__([Dataset(path) for path in paths])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        for dataset in self:
            dataset.close()
        return False


def main() -> None:
    args = parse_args()
    inputs = [Path(item) for item in args.inputs]
    output = Path(args.output)
    merge_files(inputs, output)
    print(f"inputs={','.join(str(path) for path in inputs)}")
    print(f"output={output}")


if __name__ == "__main__":
    main()
