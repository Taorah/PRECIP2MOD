# PRECIP2MOD

## Precipitation Forcing Toolkit for Coastal and Hydrologic Models

PRECIP2MOD is an open source workflow for downloading ERA5 precipitation data and converting it into precipitation forcing files for coastal and hydrologic models.

**Current supported format:**

* ADCIRC Hydrology precipitation forcing (`*.425` / `fort.425`)

---

# Overview

PRECIP2MOD automates the workflow:

```text
ERA5 Precipitation Download
          ↓
Yearly NetCDF Files (.nc)
          ↓
Convert ERA5 Precipitation → fort.425 Format
          ↓
Yearly .425 Files
          ↓
Optional Multi Year Concatenation
          ↓
Continuous Precipitation Forcing
```

The workflow is designed so that users can define the study period, geographic domain, spatial resolution, and output locations required for their application.

The configuration included in the repository serves as an example implementation and can be modified for different study regions and simulation periods.

---

# Workflow Flexibility

PRECIP2MOD is designed so that the primary workflow parameters can be modified directly within each script.

| Workflow Step                  | User Configurable Parameters                                                  |
| :----------------------------- | :---------------------------------------------------------------------------- |
| **ERA5 Download**              | Start year, end year, geographic domain, spatial resolution, output directory |
| **ERA5 → fort.425 Conversion** | Input directory, output directory, years to process                           |
| **Concatenate Files**          | Start year, end year, input directory, output directory                       |

Throughout this README, user configurable parameters are identified within each workflow step.

---

# Repository Structure

```text
PRECIP2MOD
│
├── README.md
│
└── Scripts
    │
    ├── 1_Script_to_Download_ERA5
    │   └── Download_ERA5_Precip_Hourly_Monthly_to_Yearly.py
    │
    ├── 2_Script_to_Convert_to_ADCIRC
    │   └── convert_era5_precip_to_fort425.py
    │
    └── 3_Script_to_Postprocess
        └── Concatenate_PRECIP2MOD_FORT425_ALL_YEARS.py
```

---

# Software Requirements

| Software | Purpose                                                   |
| -------- | --------------------------------------------------------- |
| Python   | Download, convert, and post process precipitation forcing |

Required Python packages can be installed using:

```bash
python -m pip install "cdsapi>=0.7.7" xarray netCDF4 numpy
```

---

# Step 1 — Download ERA5 Precipitation

PRECIP2MOD downloads:

```text
Mean Total Precipitation Rate
```

from the Copernicus Climate Data Store.

The ERA5 variable requested is:

```text
mean_total_precipitation_rate
```
Depending on the NetCDF encoding, the precipitation variable may appear as:

```text
avg_tprate
mtpr
mean_total_precipitation_rate
```

The precipitation rate is provided in:

```text
kg m-2 s-1
```

---

## Configure CDS API

Create an account with the Copernicus Climate Data Store and accept the ERA5 licence agreement.

Install the CDS API:

```bash
python -m pip install cdsapi
```

Configure the CDS API credentials according to the Copernicus Climate Data Store instructions.

---

## Why are downloads split by month?

Large ERA5 requests may exceed Copernicus Climate Data Store request limits.

To avoid this problem, PRECIP2MOD downloads precipitation data one month at a time.

After all 12 months for a year have been downloaded, the script automatically merges the monthly NetCDF files into one yearly NetCDF file.

Existing monthly files are skipped, allowing interrupted downloads to resume without repeating successfully completed months.

---

## Download ERA5 Data

Script:

```text
Scripts/1_Script_to_Download_ERA5/Download_ERA5_Precip_Hourly_Monthly_to_Yearly.py
```

### User Configurable Parameters

Users may specify:

* Start year
* End year
* Geographic domain
* Spatial resolution
* Output directory

Example:

```python
START_YEAR = 2024
END_YEAR = 2025
```

Define the geographic domain using:

```python
AREA = [50.0, -99.0, 5.0, -59.0]
```

where:

```text
AREA = [North, West, South, East]
```

Define the requested spatial resolution using:

```python
GRID = [0.25, 0.25]
```

where:

```text
GRID = [latitude_spacing, longitude_spacing]
```

The values included in the script are example settings and may be modified for other study regions.

Run:

```bash
python Download_ERA5_Precip_Hourly_Monthly_to_Yearly.py
```

Output:

```text
era5_precip_2024.nc
era5_precip_2025.nc
```

More generally:

```text
era5_precip_YYYY.nc
```

---

# Step 2 — Convert ERA5 Precipitation to ADCIRC fort.425 Format

The yearly ERA5 precipitation NetCDF files are converted into ADCIRC Hydrology precipitation forcing files.

Script:

```text
Scripts/2_Script_to_Convert_to_ADCIRC/convert_era5_precip_to_fort425.py
```

### User Configurable Parameters

Users may specify:

* Start year
* End year
* Input directory
* Output directory

Input:

```text
era5_precip_YYYY.nc
```

Output:

```text
era5_precip_YYYY.425
```

Run:

```bash
python convert_era5_precip_to_fort425.py
```

ERA5 precipitation rate is converted from `kg m-2 s-1` to `mm/hr` before the precipitation forcing file is written.

---

# fort.425 Format

Each yearly output begins with a precipitation forcing header:

```text
Precipitation in Oceanweather Format
```

Each precipitation timestep contains a structured grid header with:

```text
iLat
iLong
DX
DY
SWLat
SWLon
DT
```

followed by the precipitation field.

Example:

```text
Precipitation in Oceanweather Format                 STARTTIME   ENDTIME

iLat=...iLong=...DX=...DY=...SWLat=...SWLon=...DT=YYYYMMDDHHMM
precipitation values
precipitation values
precipitation values

iLat=...iLong=...DX=...DY=...SWLat=...SWLon=...DT=YYYYMMDDHHMM
precipitation values
precipitation values
precipitation values
```

---

# Step 3 — Concatenate Yearly fort.425 Files

PRECIP2MOD can optionally combine multiple yearly precipitation forcing files into one continuous forcing record.

Script:

```text
Scripts/3_Script_to_Postprocess/Concatenate_PRECIP2MOD_FORT425_ALL_YEARS.py
```

### User Configurable Parameters

Users may specify:

* Start year
* End year
* Input directory
* Output directory

Example input:

```text
era5_precip_2024.425
era5_precip_2025.425
```

Run:

```bash
python Concatenate_PRECIP2MOD_FORT425_ALL_YEARS.py
```

Output:

```text
era5_precip_2024_2025.425
```

More generally:

```text
era5_precip_STARTYEAR_ENDYEAR.425
```

---

# ADCIRC Hydrology Usage

The yearly or concatenated precipitation forcing file can be used as the precipitation input required by an ADCIRC Hydrology simulation.

For example:

```text
era5_precip_2024_2025.425
```

may be copied, renamed, or linked as:

```text
fort.425
```

within the ADCIRC simulation directory.

The exact precipitation configuration should follow the requirements of the ADCIRC Hydrology version and model setup being used.

---

# Example Application

The scripts included in this repository contain an example PRECIP2MOD configuration using:

* Atmospheric dataset: ERA5
* Precipitation variable: Mean Total Precipitation Rate
* Temporal resolution: Hourly
* Spatial resolution: 0.25 degrees
* Example period: 2024 to 2025
* Example geographic domain:

  * North: 50°
  * West: 99°W
  * South: 5°
  * East: 59°W

These values are provided as an example application only.

Users may adapt the workflow to different:

* Geographic regions
* Spatial resolutions
* Simulation periods
* Output directories
* Project specific requirements

For example, a longer precipitation record can be generated by changing:

```python
START_YEAR = 1979
END_YEAR = 2025
```

---

# Troubleshooting

## CDS Licence Error

If the CDS returns an error indicating that the required licence has not been accepted, sign in to the Copernicus Climate Data Store and accept the licence agreement for the ERA5 single level dataset.

---

## CDS Request Too Large

If the CDS returns an error such as:

```text
cost limits exceeded
Your request is too large, please reduce your selection
```

retain the monthly download workflow rather than requesting large multi year datasets in a single request.

---

## Missing Python Packages

Example:

```text
ModuleNotFoundError: No module named 'numpy'
```

Install the required packages:

```bash
python -m pip install "cdsapi>=0.7.7" xarray netCDF4 numpy
```

---

## Missing Yearly NetCDF File

The conversion script expects yearly input files named:

```text
era5_precip_YYYY.nc
```

Verify the input directory, requested year range, and input filenames.

---

## Missing Precipitation Variable

The workflow currently recognizes:

```text
avg_tprate
mtpr
mean_total_precipitation_rate
```

If the ERA5 NetCDF file uses a different variable name, inspect the NetCDF variables and update the supported precipitation variable names in the script.

---



# Acknowledgements

PRECIP2MOD was developed using:

* Copernicus Climate Change Service (C3S)
* ERA5 Reanalysis Dataset
* ADCIRC Modeling System
* ADCIRC Hydrology precipitation forcing framework

Louisiana State University
Louisiana State University Coastal Ecosystem Design Studio

Special thanks to the ADCIRC community and developers whose documentation and tools contributed to this workflow.

---

# Contributors

### Dr. Peter Bacopoulos

Louisiana State University: Coastal Ecosystem Design Studio (CEDS)
Louisiana State University: Department of Civil and Environmental Engineering

Project conception, precipitation forcing workflow guidance, and scientific direction.

### Taofiq Yusuf

Department of Civil and Environmental Engineering
Louisiana State University

Repository development, workflow automation, Python implementation, documentation, testing, validation, and maintenance.

### Dr. Matthew Brand

Department of Civil and Environmental Engineering
Louisiana State University

Project oversight and scientific guidance.

---

# Citation

If you use PRECIP2MOD in your research, please cite:

Yusuf, T., Bacopoulos, P., and Brand, M. (2026). **PRECIP2MOD: A workflow for downloading ERA5 precipitation data and generating ADCIRC Hydrology precipitation forcing files.** GitHub repository: https://github.com/Taorah/PRECIP2MOD

Please also cite:

* Copernicus Climate Change Service (C3S) ERA5 Reanalysis Dataset
* ADCIRC Modeling System publications relevant to your application
* ADCIRC Hydrology publications relevant to your application

---

# Contact

Repository Maintainer:

Taofiq Yusuf
Louisiana State University
Email: [tyusuf1@lsu.edu](mailto:tyusuf1@lsu.edu)
