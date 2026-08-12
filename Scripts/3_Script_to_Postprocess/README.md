# Concatenate Precipitation Forcing

Combines yearly PRECIP2MOD `.425` files into one continuous multi year precipitation forcing file.

**Script**

```text
Concatenate_PRECIP2MOD_FORT425_ALL_YEARS.py
```

**Input**

```text
era5_precip_YYYY.425
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
python Concatenate_PRECIP2MOD_FORT425_ALL_YEARS.py
```

**Output**

```text
era5_precip_STARTYEAR_ENDYEAR.425
```
