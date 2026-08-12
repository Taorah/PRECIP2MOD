# ERA5 to ADCIRC Precipitation Forcing

Converts yearly ERA5 precipitation NetCDF files into ADCIRC Hydrology `fort.425` format.

**Script**

```text
convert_era5_precip_to_fort425.py
```

**Input**

```text
era5_precip_YYYY.nc
```

**User settings**

```text
START_YEAR
END_YEAR
INPUT_FOLDER
OUTPUT_FOLDER
```

**Run**

```bash
python convert_era5_precip_to_fort425.py
```

**Output**

```text
era5_precip_YYYY.425
```
