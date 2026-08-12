#!/usr/bin/env python3
"""
PRECIP2MOD
ERA5 precipitation -> ADCIRC-Hydrology fort.425 converter.

Purpose
-------
Convert yearly ERA5 precipitation NetCDF files produced by PRECIP2MOD into
the structured precipitation format used by the ADCIRC-Hydrology fort.425
workflow.

The script:
    1. Reads one yearly ERA5 precipitation NetCDF file at a time.
    2. Detects the precipitation variable automatically.
    3. Reads the original ERA5 timestamps and geographic grid.
    4. Reorders the grid south-to-north and west-to-east.
    5. Converts precipitation rate from kg m-2 s-1 to mm/hr.
    6. Sets negative precipitation values to zero.
    7. Writes one precipitation grid for every ERA5 timestamp.
    8. Writes eight precipitation values per output line.
    9. Creates one yearly *.425 file for each requested year.

Supported precipitation variable names
--------------------------------------
    avg_tprate
    mtpr
    mean_total_precipitation_rate

Input
-----
    era5_precip_YYYY.nc

Output
------
    era5_precip_YYYY.425

Required packages
-----------------
    python -m pip install numpy netCDF4

Important
---------
The input precipitation rate is expected in kg m-2 s-1.

For liquid-water precipitation:

    1 kg m-2 = 1 mm

Therefore:

    mm/hr = precipitation_rate * 3600
"""

from __future__ import annotations

import sys
import time as walltime
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence, TextIO

import numpy as np
from netCDF4 import Dataset, num2date


# =============================================================================
# USER SETTINGS
# =============================================================================

# Inclusive year range to convert.
START_YEAR = 2024
END_YEAR = 2025

# Folder containing:
#     era5_precip_2024.nc
#     era5_precip_2025.nc
#
# Change this path if your yearly NetCDF files are stored elsewhere.
INPUT_FOLDER = Path(
    r"D:\RESEARCH\GULF_PROJECT\PRECIP2MOD"
    r"\1.Script_to_download\ERA5_PRECIP_YEARLY_DATA"
)

# Folder where yearly fort.425-format files will be created.
# Change this path as desired.
OUTPUT_FOLDER = Path.cwd() / "FORT425_YEARLY_DATA"

INPUT_FILE_PATTERN = "era5_precip_{year}.nc"
OUTPUT_FILE_PATTERN = "era5_precip_{year}.425"

# Convert kg m-2 s-1 to mm/hr.
PRECIP_RATE_SCALE = 3600.0

# Negative precipitation values are physically invalid and may occur as
# very small numerical artifacts. They are set to zero.
CLIP_NEGATIVE_TO_ZERO = True

# If a masked or non-finite precipitation value is encountered, write zero.
MISSING_VALUE_REPLACEMENT = 0.0

# Number of values written per line in the precipitation field.
VALUES_PER_LINE = 8

# Five decimal places follow the reference fort.425 precipitation workflow.
VALUE_DECIMALS = 5

# Existing yearly output files are replaced when True.
OVERWRITE_EXISTING = True

# Print progress every N timesteps.
PROGRESS_INTERVAL = 100

# If False, a missing requested input year stops the run.
# If True, missing yearly files are skipped.
SKIP_MISSING_FILES = False


# =============================================================================
# NETCDF NAME ALIASES
# =============================================================================

TIME_NAMES = ("valid_time", "time")
LATITUDE_NAMES = ("latitude", "lat")
LONGITUDE_NAMES = ("longitude", "lon")

PRECIPITATION_NAMES = (
    "avg_tprate",
    "mtpr",
    "mean_total_precipitation_rate",
)


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def find_variable_name(
    dataset: Dataset,
    candidates: Sequence[str],
) -> str:
    """Return the first candidate variable present in the NetCDF file."""
    for name in candidates:
        if name in dataset.variables:
            return name

    raise KeyError(
        "None of the expected variables were found: "
        + ", ".join(candidates)
    )


def as_python_datetime(value: object) -> datetime:
    """Convert a netCDF4/cftime datetime-like value to Python datetime."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    required = (
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
    )

    if all(hasattr(value, attr) for attr in required):
        second_float = float(getattr(value, "second"))
        second = int(second_float)

        microsecond = int(
            round(
                (second_float - second)
                * 1_000_000
            )
        )

        microsecond += int(
            getattr(
                value,
                "microsecond",
                0,
            )
            or 0
        )

        if microsecond >= 1_000_000:
            second += microsecond // 1_000_000
            microsecond %= 1_000_000

        base = datetime(
            int(getattr(value, "year")),
            int(getattr(value, "month")),
            int(getattr(value, "day")),
            int(getattr(value, "hour")),
            int(getattr(value, "minute")),
            0,
            microsecond,
        )

        return base + timedelta(
            seconds=second
        )

    raise TypeError(
        f"Cannot convert time value to datetime: {value!r}"
    )


def decode_time_variable(
    time_variable,
) -> list[datetime]:
    """Decode an ERA5 time coordinate from its NetCDF metadata."""
    raw = np.asarray(
        time_variable[:],
        dtype=np.float64,
    ).reshape(-1)

    if raw.size == 0:
        raise ValueError(
            "The NetCDF time variable is empty."
        )

    units = getattr(
        time_variable,
        "units",
        None,
    )

    calendar_name = getattr(
        time_variable,
        "calendar",
        "standard",
    )

    if units:
        decoded = num2date(
            raw,
            units=units,
            calendar=calendar_name,
        )

        return [
            as_python_datetime(value)
            for value in np.atleast_1d(decoded)
        ]

    # Fallback for ERA5 valid_time when a units attribute is absent.
    magnitude = float(
        np.nanmedian(
            np.abs(raw)
        )
    )

    if magnitude >= 10_000_000:
        origin = datetime(
            1970,
            1,
            1,
        )

        return [
            origin
            + timedelta(
                seconds=float(value)
            )
            for value in raw
        ]

    origin = datetime(
        1900,
        1,
        1,
    )

    return [
        origin
        + timedelta(
            hours=float(value)
        )
        for value in raw
    ]


def validate_year_range() -> None:
    """Validate the requested inclusive year range."""
    if START_YEAR > END_YEAR:
        raise ValueError(
            "START_YEAR must be less than or equal to END_YEAR."
        )


def validate_regular_coordinate(
    values: np.ndarray,
    name: str,
) -> float:
    """
    Confirm that a coordinate is regularly spaced.

    Returns the positive grid spacing.
    """
    values = np.asarray(
        values,
        dtype=np.float64,
    ).reshape(-1)

    if values.size < 2:
        raise ValueError(
            f"{name} must contain at least two points."
        )

    if not np.all(
        np.isfinite(values)
    ):
        raise ValueError(
            f"{name} contains non-finite values."
        )

    differences = np.diff(values)

    spacing = float(
        np.median(
            np.abs(differences)
        )
    )

    tolerance = max(
        1.0e-10,
        spacing * 1.0e-6,
    )

    if (
        spacing <= 0.0
        or not np.allclose(
            np.abs(differences),
            spacing,
            rtol=1.0e-6,
            atol=tolerance,
        )
    ):
        raise ValueError(
            f"{name} is not regularly spaced."
        )

    return spacing


def validate_hourly_time(
    timestamps: list[datetime],
) -> None:
    """Confirm that timestamps are strictly continuous at one-hour intervals."""
    if not timestamps:
        raise ValueError(
            "No timestamps were found."
        )

    for index in range(
        1,
        len(timestamps),
    ):
        difference = (
            timestamps[index]
            - timestamps[index - 1]
        ).total_seconds()

        if abs(
            difference - 3600.0
        ) > 1.0e-6:
            raise ValueError(
                "Time coordinate is not continuously hourly. "
                f"Problem between {timestamps[index - 1]} "
                f"and {timestamps[index]}."
            )


# =============================================================================
# GRID HANDLING
# =============================================================================

def read_grid(
    dataset: Dataset,
    latitude_name: str,
    longitude_name: str,
) -> dict:
    """
    Read the source grid and create south-to-north / west-to-east ordering.
    """
    latitude_raw = np.asarray(
        dataset.variables[latitude_name][:],
        dtype=np.float64,
    ).reshape(-1)

    longitude_raw = np.asarray(
        dataset.variables[longitude_name][:],
        dtype=np.float64,
    ).reshape(-1)

    latitude_order = np.argsort(
        latitude_raw
    )

    longitude_order = np.argsort(
        longitude_raw
    )

    latitude = latitude_raw[
        latitude_order
    ]

    longitude = longitude_raw[
        longitude_order
    ]

    dy = validate_regular_coordinate(
        latitude,
        "latitude",
    )

    dx = validate_regular_coordinate(
        longitude,
        "longitude",
    )

    return {
        "latitude": latitude,
        "longitude": longitude,
        "latitude_order": latitude_order,
        "longitude_order": longitude_order,
        "n_rows": int(
            latitude.size
        ),
        "n_cols": int(
            longitude.size
        ),
        "dy": dy,
        "dx": dx,
        "swlat": float(
            latitude[0]
        ),
        "swlon": float(
            longitude[0]
        ),
    }


def read_time_slice(
    variable,
    time_index: int,
    time_dimension: str,
    latitude_dimension: str,
    longitude_dimension: str,
    latitude_order: np.ndarray,
    longitude_order: np.ndarray,
) -> np.ndarray:
    """
    Read one precipitation timestep and return [latitude, longitude].

    Dimension names are used rather than assuming a fixed NetCDF dimension
    order. Extra dimensions are allowed only when their size is one.
    """
    dimensions = list(
        variable.dimensions
    )

    if time_dimension not in dimensions:
        raise ValueError(
            f"Variable {variable.name!r} does not use "
            f"time dimension {time_dimension!r}. "
            f"Dimensions are {dimensions}."
        )

    if (
        latitude_dimension not in dimensions
        or longitude_dimension not in dimensions
    ):
        raise ValueError(
            f"Variable {variable.name!r} must contain "
            f"{latitude_dimension!r} and {longitude_dimension!r}. "
            f"Dimensions are {dimensions}."
        )

    indexer: list[object] = [
        slice(None)
    ] * variable.ndim

    time_axis = dimensions.index(
        time_dimension
    )

    indexer[
        time_axis
    ] = int(
        time_index
    )

    array = np.ma.asarray(
        variable[
            tuple(indexer)
        ]
    )

    remaining_dimensions = [
        dimension
        for axis, dimension in enumerate(dimensions)
        if axis != time_axis
    ]

    # Remove extra singleton dimensions if present.
    for axis in range(
        len(remaining_dimensions) - 1,
        -1,
        -1,
    ):
        dimension = remaining_dimensions[
            axis
        ]

        if dimension in (
            latitude_dimension,
            longitude_dimension,
        ):
            continue

        if array.shape[axis] != 1:
            raise ValueError(
                f"Variable {variable.name!r} has unsupported "
                f"non-singleton dimension {dimension!r} "
                f"with size {array.shape[axis]}."
            )

        array = np.ma.squeeze(
            array,
            axis=axis,
        )

        remaining_dimensions.pop(
            axis
        )

    if set(
        remaining_dimensions
    ) != {
        latitude_dimension,
        longitude_dimension,
    }:
        raise ValueError(
            f"Could not reduce variable {variable.name!r} "
            f"to latitude/longitude. Remaining dimensions are "
            f"{remaining_dimensions}."
        )

    latitude_axis = remaining_dimensions.index(
        latitude_dimension
    )

    longitude_axis = remaining_dimensions.index(
        longitude_dimension
    )

    array = np.ma.transpose(
        array,
        axes=(
            latitude_axis,
            longitude_axis,
        ),
    )

    array = array[
        latitude_order,
        :,
    ]

    array = array[
        :,
        longitude_order,
    ]

    field = np.ma.filled(
        array,
        fill_value=MISSING_VALUE_REPLACEMENT,
    ).astype(
        np.float64,
        copy=False,
    )

    invalid = ~np.isfinite(
        field
    )

    if np.any(
        invalid
    ):
        field[
            invalid
        ] = MISSING_VALUE_REPLACEMENT

    return field


# =============================================================================
# PRECIPITATION CONVERSION
# =============================================================================

def convert_to_mm_per_hour(
    field: np.ndarray,
) -> np.ndarray:
    """
    Convert ERA5 precipitation rate from kg m-2 s-1 to mm/hr.
    """
    output = np.asarray(
        field,
        dtype=np.float64,
    ) * PRECIP_RATE_SCALE

    if CLIP_NEGATIVE_TO_ZERO:
        output = np.maximum(
            output,
            0.0,
        )

    return output


# =============================================================================
# FORT.425 WRITING
# =============================================================================

def write_file_header(
    file_handle: TextIO,
    start_time: datetime,
    end_time: datetime,
) -> None:
    """Write the main precipitation file header."""
    header = (
        "Precipitation in Oceanweather Format"
        + " " * 17
        + start_time.strftime(
            "%Y%m%d%H%M"
        )
        + "   "
        + end_time.strftime(
            "%Y%m%d%H%M"
        )
    )

    file_handle.write(
        header + "\n"
    )


def write_time_header(
    file_handle: TextIO,
    grid: dict,
    timestamp: datetime,
) -> None:
    """Write one OWI-style precipitation grid/time header."""
    header = (
        f"iLat={grid['n_rows']:4d}"
        f"iLong={grid['n_cols']:4d}"
        f"DX={grid['dx']:6.4f}"
        f"DY={grid['dy']:6.4f}"
        f"SWLat={grid['swlat']:8.4f}"
        f"SWLon={grid['swlon']:8.4f}"
        f"DT={timestamp:%Y%m%d%H%M}"
    )

    file_handle.write(
        header + "\n"
    )


def write_precipitation_field(
    file_handle: TextIO,
    field: np.ndarray,
) -> None:
    """
    Write one precipitation grid.

    The array is already ordered south-to-north and west-to-east.
    Values are flattened row by row and written eight values per line.
    """
    values = np.asarray(
        field,
        dtype=np.float64,
    ).reshape(
        -1,
        order="C",
    )

    value_format = (
        f" {{value:9.{VALUE_DECIMALS}f}}"
    )

    for start in range(
        0,
        values.size,
        VALUES_PER_LINE,
    ):
        chunk = values[
            start:
            start + VALUES_PER_LINE
        ]

        line = "".join(
            value_format.format(
                value=float(value)
            )
            for value in chunk
        )

        file_handle.write(
            line + "\n"
        )


# =============================================================================
# YEAR PROCESSING
# =============================================================================

def input_path(
    year: int,
) -> Path:
    """Return one yearly NetCDF input path."""
    return (
        INPUT_FOLDER
        / INPUT_FILE_PATTERN.format(
            year=year
        )
    )


def output_path(
    year: int,
) -> Path:
    """Return one yearly fort.425-format output path."""
    return (
        OUTPUT_FOLDER
        / OUTPUT_FILE_PATTERN.format(
            year=year
        )
    )


def process_year(
    year: int,
    source: Path,
) -> Path:
    """Convert one yearly ERA5 precipitation file."""
    started = walltime.perf_counter()

    destination = output_path(
        year
    )

    if (
        destination.exists()
        and not OVERWRITE_EXISTING
    ):
        raise FileExistsError(
            "Output already exists and "
            f"OVERWRITE_EXISTING is False: {destination}"
        )

    temporary = destination.with_name(
        destination.name
        + ".tmp"
    )

    temporary.unlink(
        missing_ok=True
    )

    try:
        with Dataset(
            source,
            mode="r",
        ) as dataset:

            time_name = find_variable_name(
                dataset,
                TIME_NAMES,
            )

            latitude_name = find_variable_name(
                dataset,
                LATITUDE_NAMES,
            )

            longitude_name = find_variable_name(
                dataset,
                LONGITUDE_NAMES,
            )

            precipitation_name = find_variable_name(
                dataset,
                PRECIPITATION_NAMES,
            )

            time_variable = dataset.variables[
                time_name
            ]

            if len(
                time_variable.dimensions
            ) != 1:
                raise ValueError(
                    f"Time variable {time_name!r} must be "
                    "one-dimensional."
                )

            time_dimension = (
                time_variable.dimensions[0]
            )

            latitude_dimension = (
                dataset.variables[
                    latitude_name
                ].dimensions[0]
            )

            longitude_dimension = (
                dataset.variables[
                    longitude_name
                ].dimensions[0]
            )

            timestamps = decode_time_variable(
                time_variable
            )

            time_order = np.argsort(
                np.asarray(
                    timestamps,
                    dtype="datetime64[us]",
                )
            )

            sorted_timestamps = [
                timestamps[
                    int(index)
                ]
                for index in time_order
            ]

            if any(
                sorted_timestamps[index]
                <= sorted_timestamps[index - 1]
                for index in range(
                    1,
                    len(sorted_timestamps),
                )
            ):
                raise ValueError(
                    "Time coordinate contains duplicate "
                    "or non-increasing values."
                )

            validate_hourly_time(
                sorted_timestamps
            )

            grid = read_grid(
                dataset,
                latitude_name,
                longitude_name,
            )

            precipitation_variable = (
                dataset.variables[
                    precipitation_name
                ]
            )

            input_units = getattr(
                precipitation_variable,
                "units",
                "not specified",
            )

            print(
                f"Input              : {source}"
            )
            print(
                f"Precipitation var  : {precipitation_name}"
            )
            print(
                f"Input units        : {input_units}"
            )
            print(
                f"Grid               : "
                f"{grid['n_rows']} rows x "
                f"{grid['n_cols']} columns"
            )
            print(
                f"DX / DY            : "
                f"{grid['dx']} / {grid['dy']} degrees"
            )
            print(
                f"Southwest          : "
                f"{grid['swlon']}, {grid['swlat']}"
            )
            print(
                f"Timesteps          : {len(sorted_timestamps)}"
            )
            print(
                f"Start              : {sorted_timestamps[0]}"
            )
            print(
                f"End                : {sorted_timestamps[-1]}"
            )
            print(
                "Output units       : mm/hr"
            )

            overall_min = np.inf
            overall_max = -np.inf

            with open(
                temporary,
                mode="w",
                encoding="utf-8",
                newline="\n",
            ) as output:

                write_file_header(
                    output,
                    sorted_timestamps[0],
                    sorted_timestamps[-1],
                )

                total = len(
                    time_order
                )

                for output_index, source_index_value in enumerate(
                    time_order,
                    start=1,
                ):
                    source_index = int(
                        source_index_value
                    )

                    timestamp = timestamps[
                        source_index
                    ]

                    field = read_time_slice(
                        precipitation_variable,
                        source_index,
                        time_dimension,
                        latitude_dimension,
                        longitude_dimension,
                        grid["latitude_order"],
                        grid["longitude_order"],
                    )

                    field = convert_to_mm_per_hour(
                        field
                    )

                    field_min = float(
                        np.min(field)
                    )

                    field_max = float(
                        np.max(field)
                    )

                    overall_min = min(
                        overall_min,
                        field_min,
                    )

                    overall_max = max(
                        overall_max,
                        field_max,
                    )

                    write_time_header(
                        output,
                        grid,
                        timestamp,
                    )

                    write_precipitation_field(
                        output,
                        field,
                    )

                    if (
                        output_index == 1
                        or output_index == total
                        or output_index % PROGRESS_INTERVAL == 0
                    ):
                        print(
                            f"  Wrote timestep "
                            f"{output_index:,} of {total:,} "
                            f"({timestamp:%Y-%m-%d %H:%M})"
                        )

        if destination.exists():
            destination.unlink()

        temporary.replace(
            destination
        )

        elapsed = (
            walltime.perf_counter()
            - started
        )

        print(
            f"Precipitation range : "
            f"{overall_min:.5f} to "
            f"{overall_max:.5f} mm/hr"
        )

        print(
            f"Finished {year} in "
            f"{elapsed / 60.0:.2f} minutes."
        )

        print(
            f"Output             : {destination}"
        )

        return destination

    except Exception:
        temporary.unlink(
            missing_ok=True
        )
        raise


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    """Run yearly PRECIP2MOD fort.425 conversion."""
    validate_year_range()

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 78)
    print(
        "PRECIP2MOD: ERA5 PRECIPITATION -> FORT.425"
    )
    print(
        f"Years  : {START_YEAR}-{END_YEAR}"
    )
    print(
        f"Input  : {INPUT_FOLDER}"
    )
    print(
        f"Output : {OUTPUT_FOLDER}"
    )
    print("=" * 78)

    processed = 0
    skipped = 0

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):
        print(
            "\n"
            + "=" * 78
        )
        print(
            f"PROCESSING YEAR {year}"
        )
        print(
            "=" * 78
        )

        source = input_path(
            year
        )

        if not source.is_file():
            message = (
                f"Input file not found: {source}"
            )

            if SKIP_MISSING_FILES:
                print(
                    "WARNING: "
                    + message
                )

                skipped += 1
                continue

            raise FileNotFoundError(
                message
            )

        process_year(
            year,
            source,
        )

        processed += 1

    print(
        "\n"
        + "=" * 78
    )

    print(
        "PRECIP2MOD FORT.425 CONVERSION "
        "COMPLETED SUCCESSFULLY"
    )

    print(
        f"Processed: {processed}; "
        f"skipped: {skipped}"
    )

    print(
        "=" * 78
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:
        print(
            "\nConversion cancelled by user.",
            file=sys.stderr,
        )

        raise SystemExit(
            130
        )

    except Exception as error:
        print(
            f"\nERROR: {error}",
            file=sys.stderr,
        )

        raise SystemExit(
            1
        )
