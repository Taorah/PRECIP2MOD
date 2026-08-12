#!/usr/bin/env python3
"""
PRECIP2MOD
ERA5 precipitation downloader: monthly retrieval -> yearly NetCDF.

Purpose
-------
Download ERA5 Mean Total Precipitation Rate for a user-defined time period,
geographic domain, and spatial resolution.

The script:
    1. Downloads one month at a time to avoid large CDS requests.
    2. Requests Mean Total Precipitation Rate at hourly intervals.
    3. Merges the 12 monthly NetCDF files into one yearly NetCDF file.
    4. Validates the expected hourly record count and temporal continuity.
    5. Skips monthly files that already exist so interrupted runs can resume.
    6. Optionally deletes monthly files after a successful yearly merge.

User-configurable parameters include:
    - Start year
    - End year
    - Geographic domain
    - Spatial resolution
    - Output directory

Required packages
-----------------
    python -m pip install "cdsapi>=0.7.7" xarray netCDF4 numpy

Output
------
    era5_precip_YYYY.nc

ERA5 Mean Total Precipitation Rate is requested as:
    mean_total_precipitation_rate

Depending on the ERA5 NetCDF encoding, the precipitation variable may appear
under different names. This script supports:

    avg_tprate
    mtpr
    mean_total_precipitation_rate

The precipitation-rate units are kg m-2 s-1.

For later conversion to precipitation intensity in mm/hr:

    mm/hr = precipitation_rate * 3600
"""

from __future__ import annotations

import calendar
import sys
import time
from pathlib import Path

import cdsapi
import numpy as np
import xarray as xr


# =============================================================================
# USER SETTINGS
# =============================================================================

# Define the inclusive year range to download.
START_YEAR = 2024
END_YEAR = 2025

# For the final long-term dataset, change to:
# START_YEAR = 1979
# END_YEAR = 2025

# By default, output is created wherever this script is run.
# Replace with an absolute path if preferred.
OUTPUT_FOLDER = Path.cwd() / "ERA5_PRECIP_YEARLY_DATA"

# Temporary monthly files are stored in this subdirectory.
MONTHLY_FOLDER_NAME = "_monthly_parts"

# Define the geographic domain:
# [North, West, South, East]
AREA = [50.0, -99.0, 5.0, -59.0]

# Define the requested grid resolution in degrees:
# [latitude_spacing, longitude_spacing]
GRID = [0.25, 0.25]

# ERA5 precipitation variable requested from CDS.
VARIABLE = "mean_total_precipitation_rate"

# Hourly timestamps requested from ERA5.
TIMES = [f"{hour:02d}:00" for hour in range(24)]

# Existing yearly files are preserved unless overwrite is enabled.
OVERWRITE_YEARLY_FILE = False

# Delete temporary monthly files after a successful yearly merge.
DELETE_MONTHLY_FILES_AFTER_MERGE = True

# Retry settings for temporary CDS or network failures.
MAX_RETRIES = 4
RETRY_WAIT_SECONDS = 60


# =============================================================================
# CDS SETTINGS
# =============================================================================

DATASET = "reanalysis-era5-single-levels"


# =============================================================================
# FILE-NAMING HELPERS
# =============================================================================

def monthly_path(monthly_folder: Path, year: int, month: int) -> Path:
    """Return the path for one monthly precipitation NetCDF file."""
    return monthly_folder / f"era5_precip_{year}_{month:02d}.nc"


def yearly_path(output_folder: Path, year: int) -> Path:
    """Return the path for one merged yearly precipitation NetCDF file."""
    return output_folder / f"era5_precip_{year}.nc"


# =============================================================================
# CDS REQUEST
# =============================================================================

def build_request(year: int, month: int) -> dict:
    """Build one monthly ERA5 precipitation request."""
    number_of_days = calendar.monthrange(year, month)[1]

    return {
        "product_type": ["reanalysis"],
        "variable": [VARIABLE],
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": [f"{day:02d}" for day in range(1, number_of_days + 1)],
        "time": TIMES,
        "area": AREA,
        "grid": GRID,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def download_month(
    client: cdsapi.Client,
    year: int,
    month: int,
    target: Path,
) -> None:
    """Download one month and skip an existing non-empty monthly file."""
    if target.is_file() and target.stat().st_size > 0:
        print(f"SKIP MONTH: {target.name} already exists.")
        return

    partial = target.with_suffix(target.suffix + ".part")
    partial.unlink(missing_ok=True)

    request = build_request(year, month)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"Downloading {year}-{month:02d} "
                f"(attempt {attempt}/{MAX_RETRIES})..."
            )

            client.retrieve(DATASET, request, str(partial))

            if not partial.is_file() or partial.stat().st_size == 0:
                raise RuntimeError("CDS returned an empty or missing file.")

            partial.replace(target)
            print(f"SAVED: {target}")
            return

        except Exception as error:
            partial.unlink(missing_ok=True)

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Failed to download {year}-{month:02d} "
                    f"after {MAX_RETRIES} attempts."
                ) from error

            print(f"WARNING: {error}")
            print(f"Retrying in {RETRY_WAIT_SECONDS} seconds...")
            time.sleep(RETRY_WAIT_SECONDS)


# =============================================================================
# NETCDF VALIDATION AND MERGE
# =============================================================================

def detect_time_name(dataset: xr.Dataset) -> str:
    """Detect the ERA5 time coordinate name."""
    for candidate in ("valid_time", "time"):
        if candidate in dataset.coords or candidate in dataset.variables:
            return candidate

    raise KeyError("Expected time coordinate 'valid_time' or 'time'.")


def detect_precip_name(dataset: xr.Dataset) -> str:
    """Detect the precipitation variable in the downloaded NetCDF file."""
    for candidate in (
        "avg_tprate",
        "mtpr",
        "mean_total_precipitation_rate",
    ):
        if candidate in dataset.data_vars:
            return candidate

    available = ", ".join(dataset.data_vars)

    raise KeyError(
        "Mean total precipitation rate was not found. "
        f"Available data variables: {available}"
    )


def coordinate_name(
    dataset: xr.Dataset,
    candidates: tuple[str, ...],
) -> str:
    """Return the first matching coordinate or variable name."""
    for candidate in candidates:
        if candidate in dataset.coords or candidate in dataset.variables:
            return candidate

    raise KeyError(f"None of these coordinates were found: {candidates}")


def validate_spatial_grid(
    dataset: xr.Dataset,
    source: Path,
) -> None:
    """Confirm that the downloaded grid matches the requested resolution."""
    latitude_name = coordinate_name(dataset, ("latitude", "lat"))
    longitude_name = coordinate_name(dataset, ("longitude", "lon"))

    lat = np.asarray(dataset[latitude_name].values, dtype=float).reshape(-1)
    lon = np.asarray(dataset[longitude_name].values, dtype=float).reshape(-1)

    if lat.size < 2 or lon.size < 2:
        raise ValueError(f"Invalid spatial coordinates in {source.name}.")

    dy = float(np.median(np.abs(np.diff(lat))))
    dx = float(np.median(np.abs(np.diff(lon))))

    if not np.isclose(dx, GRID[1], atol=1.0e-8):
        raise ValueError(
            f"Unexpected longitude spacing in {source.name}: {dx}; "
            f"expected {GRID[1]} degrees."
        )

    if not np.isclose(dy, GRID[0], atol=1.0e-8):
        raise ValueError(
            f"Unexpected latitude spacing in {source.name}: {dy}; "
            f"expected {GRID[0]} degrees."
        )


def merge_months(
    month_files: list[Path],
    output_file: Path,
    year: int,
) -> None:
    """Merge 12 monthly NetCDF files into one validated yearly file."""
    if output_file.exists() and not OVERWRITE_YEARLY_FILE:
        print(f"SKIP MERGE: {output_file.name} already exists.")
        return

    missing = [path for path in month_files if not path.is_file()]

    if missing:
        missing_text = "\n".join(str(path) for path in missing)

        raise FileNotFoundError(
            "Cannot create the yearly file because monthly files are missing:\n"
            + missing_text
        )

    print(f"Merging 12 monthly files into {output_file.name}...")

    datasets: list[xr.Dataset] = []
    temporary_output = output_file.with_suffix(output_file.suffix + ".tmp")
    temporary_output.unlink(missing_ok=True)

    combined: xr.Dataset | None = None

    try:
        for path in month_files:
            dataset = xr.open_dataset(path, engine="netcdf4")

            validate_spatial_grid(dataset, path)
            detect_precip_name(dataset)

            datasets.append(dataset)

        time_name = detect_time_name(datasets[0])

        for dataset, path in zip(datasets, month_files):
            current_time_name = detect_time_name(dataset)

            if current_time_name != time_name:
                raise ValueError(
                    f"Inconsistent time coordinate in {path.name}: "
                    f"{current_time_name!r} versus {time_name!r}."
                )

        combined = xr.concat(
            datasets,
            dim=time_name,
            data_vars="minimal",
            coords="minimal",
            compat="override",
            join="exact",
            combine_attrs="override",
        )

        combined = combined.sortby(time_name)

        # Remove duplicate timestamps, if any.
        time_values = np.asarray(combined[time_name].values)
        _, unique_indices = np.unique(time_values, return_index=True)
        unique_indices = np.sort(unique_indices)

        if unique_indices.size != time_values.size:
            duplicates = time_values.size - unique_indices.size
            print(f"WARNING: removed {duplicates} duplicate timestamp(s).")
            combined = combined.isel({time_name: unique_indices})

        # Validate the expected number of hourly records.
        expected_records = 8784 if calendar.isleap(year) else 8760
        actual_records = int(combined.sizes[time_name])

        if actual_records != expected_records:
            raise ValueError(
                f"Unexpected number of hourly records for {year}: "
                f"found {actual_records}, expected {expected_records}."
            )

        # Validate continuous hourly spacing.
        hours = (
            np.asarray(combined[time_name].values)
            .astype("datetime64[h]")
            .astype(np.int64)
        )

        differences = np.diff(hours)

        if not np.all(differences == 1):
            bad_locations = np.where(differences != 1)[0]
            first_bad = int(bad_locations[0])

            raise ValueError(
                "The merged time coordinate is not continuously hourly. "
                f"First problem occurs between indices "
                f"{first_bad} and {first_bad + 1}."
            )

        precip_name = detect_precip_name(combined)

        print(f"Precipitation variable: {precip_name}")
        print(f"Hourly records        : {actual_records}")
        print(f"First timestamp       : {combined[time_name].values[0]}")
        print(f"Last timestamp        : {combined[time_name].values[-1]}")

        combined.to_netcdf(
            temporary_output,
            engine="netcdf4",
            format="NETCDF4",
            unlimited_dims=[time_name],
        )

        if output_file.exists():
            output_file.unlink()

        temporary_output.replace(output_file)

        print(f"YEARLY FILE CREATED: {output_file}")

    finally:
        if combined is not None:
            combined.close()

        for dataset in datasets:
            dataset.close()

        temporary_output.unlink(missing_ok=True)


# =============================================================================
# YEAR PROCESSING
# =============================================================================

def process_year(
    client: cdsapi.Client,
    year: int,
) -> None:
    """Download and merge one complete year."""
    print("\n" + "=" * 78)
    print(f"PROCESSING PRECIPITATION YEAR {year}")
    print("=" * 78)

    output_file = yearly_path(OUTPUT_FOLDER, year)

    if (
        output_file.is_file()
        and output_file.stat().st_size > 0
        and not OVERWRITE_YEARLY_FILE
    ):
        print(f"SKIP YEAR: {output_file.name} already exists.")
        return

    monthly_folder = (
        OUTPUT_FOLDER
        / MONTHLY_FOLDER_NAME
        / str(year)
    )

    monthly_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    month_files = [
        monthly_path(
            monthly_folder,
            year,
            month,
        )
        for month in range(1, 13)
    ]

    for month, target in enumerate(
        month_files,
        start=1,
    ):
        download_month(
            client,
            year,
            month,
            target,
        )

    merge_months(
        month_files,
        output_file,
        year,
    )

    if (
        DELETE_MONTHLY_FILES_AFTER_MERGE
        and output_file.is_file()
    ):
        for path in month_files:
            path.unlink(
                missing_ok=True
            )

        try:
            monthly_folder.rmdir()
        except OSError:
            pass

        print(f"Deleted monthly parts for {year}.")


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    """Run the PRECIP2MOD ERA5 precipitation downloader."""
    if START_YEAR > END_YEAR:
        raise ValueError(
            "START_YEAR must be less than or equal to END_YEAR."
        )

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 78)
    print("PRECIP2MOD: ERA5 HOURLY PRECIPITATION DOWNLOADER")
    print(f"Years      : {START_YEAR}-{END_YEAR}")
    print(f"Variable   : {VARIABLE}")
    print(f"Resolution : {GRID[0]} x {GRID[1]} degrees")
    print(
        f"Area       : "
        f"N={AREA[0]}, W={AREA[1]}, "
        f"S={AREA[2]}, E={AREA[3]}"
    )
    print(f"Output     : {OUTPUT_FOLDER}")
    print("=" * 78)

    client = cdsapi.Client()

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):
        process_year(
            client,
            year,
        )

    print("\n" + "=" * 78)
    print(
        "ALL REQUESTED PRECIPITATION YEARS "
        "COMPLETED SUCCESSFULLY"
    )
    print("=" * 78)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())

    except KeyboardInterrupt:
        print(
            "\nDownload cancelled by user.",
            file=sys.stderr,
        )
        raise SystemExit(130)

    except Exception as error:
        print(
            f"\nERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)
