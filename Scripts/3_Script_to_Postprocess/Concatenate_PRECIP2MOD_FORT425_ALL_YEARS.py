#!/usr/bin/env python3
"""
PRECIP2MOD
Concatenate yearly ADCIRC-Hydrology fort.425 precipitation files.

Purpose
-------
Combine yearly PRECIP2MOD precipitation files into one continuous multi-year
fort.425 forcing file.

The script:
    1. Reads the requested yearly *.425 files in chronological order.
    2. Creates one new precipitation file header spanning the complete period.
    3. Removes the yearly file header from every input file.
    4. Appends all precipitation time records and grids without changing the
       precipitation values.
    5. Confirms that grid metadata are identical between years.
    6. Confirms that timestamps are continuous and hourly across year boundaries.
    7. Writes through a temporary file before replacing the final output.

Input
-----
    era5_precip_YYYY.425

Output
------
    era5_precip_STARTYEAR_ENDYEAR.425

Example
-------
    era5_precip_2024.425
    era5_precip_2025.425

becomes:

    era5_precip_2024_2025.425

For the long-term PRECIP2MOD archive, the same script can be used for:
    START_YEAR = 1979
    END_YEAR   = 2025
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


# =============================================================================
# USER SETTINGS
# =============================================================================

# Inclusive year range to concatenate.
START_YEAR = 2024
END_YEAR = 2025

# For the final long-term forcing, change to:
# START_YEAR = 1979
# END_YEAR = 2025

# Folder containing yearly PRECIP2MOD fort.425 files.
INPUT_FOLDER = Path(
    r"D:\RESEARCH\GULF_PROJECT\PRECIP2MOD"
    r"\2_Scrip_to_convert_to_ADCIRC_Format\FORT425_YEARLY_DATA"
)

# By default, the concatenated file is written to a new folder wherever this
# script is run. Replace with an absolute path if preferred.
OUTPUT_FOLDER = Path.cwd() / "FORT425_CONCATENATED_DATA"

INPUT_FILE_PATTERN = "era5_precip_{year}.425"
OUTPUT_FILE_PATTERN = "era5_precip_{start_year}_{end_year}.425"

# Existing combined output is replaced when True.
OVERWRITE_EXISTING = True

# Expected temporal interval between fort.425 records.
EXPECTED_TIME_STEP = timedelta(hours=1)


# =============================================================================
# HEADER PARSING
# =============================================================================

MAIN_HEADER_TIME_RE = re.compile(r"\d{12}")

TIME_HEADER_RE = re.compile(
    r"^iLat=\s*(?P<nrows>\d+)"
    r"iLong=\s*(?P<ncols>\d+)"
    r"DX=\s*(?P<dx>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"DY=\s*(?P<dy>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"SWLat=\s*(?P<swlat>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"SWLon=\s*(?P<swlon>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"DT=(?P<dt>\d{12})\s*$"
)


def parse_main_header(line: str, source: Path) -> tuple[datetime, datetime]:
    """Extract the start and end timestamps from a yearly file header."""
    matches = MAIN_HEADER_TIME_RE.findall(line)

    if len(matches) < 2:
        raise ValueError(
            f"Could not find start and end timestamps in header: {source}"
        )

    start_time = datetime.strptime(matches[-2], "%Y%m%d%H%M")
    end_time = datetime.strptime(matches[-1], "%Y%m%d%H%M")

    return start_time, end_time


def parse_time_header(line: str, source: Path) -> dict:
    """Parse one fort.425 grid/time header."""
    match = TIME_HEADER_RE.match(line.strip())

    if not match:
        raise ValueError(
            "Invalid fort.425 grid/time header in:\n"
            f"  {source}\n"
            f"  {line.rstrip()}"
        )

    return {
        "n_rows": int(match.group("nrows")),
        "n_cols": int(match.group("ncols")),
        "dx": float(match.group("dx")),
        "dy": float(match.group("dy")),
        "swlat": float(match.group("swlat")),
        "swlon": float(match.group("swlon")),
        "timestamp": datetime.strptime(match.group("dt"), "%Y%m%d%H%M"),
    }


def grid_signature(header: dict) -> tuple:
    """Return the grid metadata used to confirm compatibility."""
    return (
        header["n_rows"],
        header["n_cols"],
        round(header["dx"], 10),
        round(header["dy"], 10),
        round(header["swlat"], 10),
        round(header["swlon"], 10),
    )


def build_combined_header(
    start_time: datetime,
    end_time: datetime,
) -> str:
    """Create the single main header for the concatenated forcing file."""
    return (
        "Precipitation in Oceanweather Format"
        + " " * 17
        + start_time.strftime("%Y%m%d%H%M")
        + "   "
        + end_time.strftime("%Y%m%d%H%M")
    )


# =============================================================================
# FILE HELPERS
# =============================================================================

def input_path(year: int) -> Path:
    """Return the yearly input file path."""
    return INPUT_FOLDER / INPUT_FILE_PATTERN.format(year=year)


def output_path() -> Path:
    """Return the combined output file path."""
    return OUTPUT_FOLDER / OUTPUT_FILE_PATTERN.format(
        start_year=START_YEAR,
        end_year=END_YEAR,
    )


def validate_settings() -> None:
    """Validate the requested year range and input files."""
    if START_YEAR > END_YEAR:
        raise ValueError(
            "START_YEAR must be less than or equal to END_YEAR."
        )

    missing = [
        input_path(year)
        for year in range(START_YEAR, END_YEAR + 1)
        if not input_path(year).is_file()
    ]

    if missing:
        formatted = "\n".join(f"  {path}" for path in missing)

        raise FileNotFoundError(
            "Missing yearly fort.425 input file(s):\n"
            + formatted
        )


# =============================================================================
# CONCATENATION
# =============================================================================

def get_file_period(source: Path) -> tuple[datetime, datetime]:
    """Read only the first line and return its documented time period."""
    with open(
        source,
        mode="r",
        encoding="utf-8",
    ) as file_handle:
        first_line = file_handle.readline()

    if not first_line:
        raise ValueError(f"Input file is empty: {source}")

    return parse_main_header(first_line, source)


def concatenate_files() -> Path:
    """Concatenate the requested yearly precipitation files."""
    years = list(
        range(
            START_YEAR,
            END_YEAR + 1,
        )
    )

    sources = [
        input_path(year)
        for year in years
    ]

    destination = output_path()

    if destination.exists() and not OVERWRITE_EXISTING:
        raise FileExistsError(
            "Output already exists and OVERWRITE_EXISTING is False:\n"
            f"  {destination}"
        )

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        destination.name + ".tmp"
    )

    temporary.unlink(
        missing_ok=True
    )

    # Use the yearly header dates to create the combined master header.
    first_header_start, _ = get_file_period(sources[0])
    _, last_header_end = get_file_period(sources[-1])

    common_grid_signature: tuple | None = None
    previous_timestamp: datetime | None = None
    first_actual_timestamp: datetime | None = None
    last_actual_timestamp: datetime | None = None

    total_records = 0

    try:
        with open(
            temporary,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as output:

            output.write(
                build_combined_header(
                    first_header_start,
                    last_header_end,
                )
                + "\n"
            )

            for year, source in zip(years, sources):
                print("\n" + "=" * 78)
                print(f"ADDING YEAR {year}")
                print("=" * 78)

                year_record_count = 0
                year_first_timestamp: datetime | None = None
                year_last_timestamp: datetime | None = None

                with open(
                    source,
                    mode="r",
                    encoding="utf-8",
                ) as input_file:

                    # Remove the yearly main header from the concatenated body.
                    yearly_main_header = input_file.readline()

                    if not yearly_main_header:
                        raise ValueError(
                            f"Input file is empty: {source}"
                        )

                    documented_start, documented_end = parse_main_header(
                        yearly_main_header,
                        source,
                    )

                    for line in input_file:
                        if line.startswith("iLat="):
                            header = parse_time_header(
                                line,
                                source,
                            )

                            current_signature = grid_signature(
                                header
                            )

                            if common_grid_signature is None:
                                common_grid_signature = current_signature

                            elif current_signature != common_grid_signature:
                                raise ValueError(
                                    "Grid metadata changed between yearly files.\n"
                                    f"Problem file: {source}\n"
                                    f"Expected: {common_grid_signature}\n"
                                    f"Found:    {current_signature}"
                                )

                            timestamp = header["timestamp"]

                            if year_first_timestamp is None:
                                year_first_timestamp = timestamp

                            year_last_timestamp = timestamp

                            if first_actual_timestamp is None:
                                first_actual_timestamp = timestamp

                            if previous_timestamp is not None:
                                difference = timestamp - previous_timestamp

                                if difference != EXPECTED_TIME_STEP:
                                    raise ValueError(
                                        "Precipitation timestamps are not "
                                        "continuously hourly.\n"
                                        f"Previous: {previous_timestamp}\n"
                                        f"Current : {timestamp}\n"
                                        f"File    : {source}"
                                    )

                            previous_timestamp = timestamp
                            last_actual_timestamp = timestamp

                            year_record_count += 1
                            total_records += 1

                        # Copy both time headers and precipitation values exactly.
                        output.write(line)

                if year_record_count == 0:
                    raise ValueError(
                        f"No fort.425 time records found in: {source}"
                    )

                if year_first_timestamp != documented_start:
                    raise ValueError(
                        "Yearly main-header start time does not match the "
                        "first actual time record.\n"
                        f"File header : {documented_start}\n"
                        f"First record: {year_first_timestamp}\n"
                        f"File        : {source}"
                    )

                if year_last_timestamp != documented_end:
                    raise ValueError(
                        "Yearly main-header end time does not match the "
                        "last actual time record.\n"
                        f"File header : {documented_end}\n"
                        f"Last record : {year_last_timestamp}\n"
                        f"File        : {source}"
                    )

                print(
                    f"Added {source.name}"
                )
                print(
                    f"Records : {year_record_count:,}"
                )
                print(
                    f"Start   : {year_first_timestamp}"
                )
                print(
                    f"End     : {year_last_timestamp}"
                )

        if first_actual_timestamp != first_header_start:
            raise ValueError(
                "Combined header start time does not match the "
                "first actual precipitation record."
            )

        if last_actual_timestamp != last_header_end:
            raise ValueError(
                "Combined header end time does not match the "
                "last actual precipitation record."
            )

        if destination.exists():
            destination.unlink()

        temporary.replace(
            destination
        )

    except Exception:
        temporary.unlink(
            missing_ok=True
        )
        raise

    print("\n" + "=" * 78)
    print("PRECIP2MOD CONCATENATION COMPLETED SUCCESSFULLY")
    print(f"Years         : {START_YEAR}-{END_YEAR}")
    print(f"Total records : {total_records:,}")
    print(f"Start         : {first_actual_timestamp}")
    print(f"End           : {last_actual_timestamp}")
    print(f"Output        : {destination}")
    print("=" * 78)

    return destination


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    """Run PRECIP2MOD yearly fort.425 concatenation."""
    validate_settings()

    print("=" * 78)
    print("PRECIP2MOD: CONCATENATE YEARLY FORT.425 FILES")
    print(f"Years  : {START_YEAR}-{END_YEAR}")
    print(f"Input  : {INPUT_FOLDER}")
    print(f"Output : {OUTPUT_FOLDER}")
    print("=" * 78)

    concatenate_files()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:
        print(
            "\nConcatenation cancelled by user.",
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
