# Railway dataset provenance and import preparation

Verified on 27 November 2026, Singapore time. The audit compared `[P4_Group10] INF2003 Progress Report.docx`, publisher CSVs, team archives and intermediate files, the six team scripts, and the repository import files. [Comparison output and SHA-256 hashes](evidence/rail-provenance-verification.json) · [Offline replay log](evidence/rail-preparation-replay.log)

## Confirmed source files

The progress report proposed combining Dataset B coordinates with Dataset C station metadata. The files show that the implementation followed two separate paths. Dataset B supplied a station-name sample. Dataset C supplied the code-level station data and the coordinates in the final import.

| Published file | Comparison with the team files | Verified role |
| --- | --- | --- |
| Dataset B, CZTanData, version 1, `TrainStationLocation.csv` | Byte-identical to `mrt_station_locations.csv` in `raw_data.zip`. All 172 rows use `station_name,type,lat,lng`, with no station-code column. | The archived `mrt_stations_cleaned.csv` and tracked `data/samples/mrt_stations_sample.csv` agree byte for byte. All 172 rows preserve Dataset B's order, type and coordinate values. The names are uppercased and stripped of extra whitespace. [Dataset B on Kaggle](https://www.kaggle.com/datasets/cztandata/singapore-train-station-locations/versions/1) |
| Dataset C, Timothy Lim, version 3, legacy file `mrt_lrt_stations.csv` | All 203 rows and all 19 columns match `mrt_lrt_full_list.csv` in `raw_data.zip`. The files are identical after normalizing CRLF and LF. The repository's local raw railway CSV also matched the archived member byte for byte. | Confirmed source of the final import's codes, names, lines, colours, transport types, dates, address details, postal values and coordinates. The final import preserves all 203 codes in source order. [Dataset C on Kaggle](https://www.kaggle.com/datasets/lzytim/full-list-of-mrt-and-lrt-stations-in-singapore/versions/3) |
| Dataset C, version 3, `mrt_lrt_stations_2025-01-14.csv` | 211 codes, including all 203 legacy codes and eight additional codes: `NE18` and `TE23`–`TE29`. The shared station metadata and coordinates agree with the legacy file. | The legacy file is the one that matches the raw snapshot. No additional codes from the dated file appear in the bundle. Its URA planning-area field matches the bundled `Town` in only 33 of the 203 shared rows, ignoring case and whitespace. [Dataset C file listing](https://www.kaggle.com/datasets/lzytim/full-list-of-mrt-and-lrt-stations-in-singapore/versions/3) |

An exact content match identifies the source file. The earlier team download date and whether an earlier Kaggle version already contained the same legacy export remain unverified. The January 2025 date in the dataset title applies to the version with the dated file, so use the verified legacy filename and 203-code inventory when citing the imported snapshot.

### Codes, coordinates and representative records

The legacy file contains `ALPHANUMERIC_CODE`, `STATION_NAME_ENGLISH`, `LINE_ENGLISH`, `LINE_COLOR`, `TRANSPORT_TYPE`, `LATITUDE`, and `LONGITUDE`, plus Chinese labels, dates, addresses, postal codes and `X`/`Y`. The final station export preserves the key metadata text exactly. All 203 station coordinate pairs and all 203 `X`/`Y` pairs equal legacy Dataset C values rounded to **10 significant digits**. The largest latitude and longitude changes are about `4.97e-10°` and `4.99e-8°`, respectively.

Joining Dataset B to the final codes on station name, with case and whitespace normalized, plus transport type matched 199 code rows. `BP1`, `BP6`, `PTC` and `STC` did not match on that key. Zero of the 199 matched rows had an exact Dataset B coordinate pair in either the legacy Dataset C export or the final bundled rail file. This comparison identifies the source of the stored coordinates. It does not assess surveying or geocoding accuracy.

| Code and station | Line colour and type | Dataset B latitude, longitude | Dataset C legacy latitude, longitude | Final latitude, longitude |
| --- | --- | --- | --- | --- |
| NS1 and EW24, Jurong East | Red MRT and Green MRT | 1.333207, 103.742308 | 1.33315281585758, 103.742286332403 | 1.333152816, 103.7422863 |
| NE1, HarbourFront | Purple MRT | 1.265453, 103.820514 | 1.26538938374901, 103.821530157095 | 1.265389384, 103.8215302 |
| PE1, Cove | Grey LRT | 1.399534, 103.905792 | 1.39928198837342, 103.905961941214 | 1.399281988, 103.9059619 |
| TE1, Woodlands North | Brown MRT | 1.4482, 103.7851 | 1.44829245259621, 103.785692682441 | 1.448292453, 103.7856927 |

## Transformation pipeline

### HDB resale and places

| Stage | What the scripts and files establish |
| --- | --- |
| 1. Clean HDB source | The tracked cleaner renames fields, forms `full_address` from block and street, parses remaining lease to months, drops rows missing critical fields, and standardizes selected text. The archive's 242,634 cleaned rows match the raw rows after the expected date, text and field-name changes. The archived version uses first-of-month dates, consistent with the older script. The current cleaner represents the value as a monthly period. [HDB cleaner](../data/scripts/data_prep/03_clean_hdb.py) |
| 2. Locate HDB addresses | The tracked geocoder queries OneMap Address Search once per unique address, takes the first result, and checkpoints coordinates for resumption. The merge left-joins coordinates on `full_address`. The archived enriched CSV preserves every cleaned field and adds latitude and longitude. The team copy used for postal enrichment represents months as `MM/YYYY`. Compared with the archived enriched copy, the final sales file has 24,815 changed latitudes and 24,281 changed longitudes. Every changed value equals its archived value rounded to 10 significant digits. [Geocoder](../data/scripts/data_prep/06_geocode_hdb.py) · [Coordinate merge](../data/scripts/data_prep/07_merge_geo.py) · [OneMap Search API](https://www.onemap.gov.sg/apidocs/search) |
| 3. Forward postal lookup | The team-supplied `postal.py` builds block-and-street queries, caches by address, takes the first OneMap Search response's postal code, and writes `NIL` for a missing result. Its named output is `hdb_resale_enriched_with_postal_v2.csv`. An earlier archived postal file has 241,538 `NIL` rows. The v2 file has 8,639 `NIL` rows across 294 addresses. The script that wrote the earlier file is unverified. |
| 4. Reverse lookup for missing postal codes | The team-supplied `postal_cleanup.py` revisits only `NIL` rows with coordinates. It uses OneMap reverse geocoding, a 50 m buffer and `addressType=HDB`. It caches by coordinates rounded to five decimal places and uses the first returned entry with a postal code. The cleanup export fills all 8,639 previously missing rows and leaves already populated values unchanged. That export also contains `MM-YYYY` dates. The reviewed reverse-geocoding code does not reformat dates, so the exact edit that changed the separator is unverified. [OneMap API documentation](https://www.onemap.gov.sg/apidocs/) |
| 5. Assign stable HDB IDs | `blocks.py` takes categorical codes for `full_address` plus one. For this input, all 9,761 final IDs agree with the lexicographic order of distinct addresses. The offline replay reproduced `hdb_resale_enriched_block_id.csv` byte for byte. The pandas CSV round trip also reproduced the disappearance of a leading zero in 2,813 sale rows covering 97 HDB locations. The supplied `blocks_check.py` is diagnostic only. Its label says ID 1 while its address lookup uses ID 9,762, which is outside the HDB range. [Offline replay](evidence/rail-preparation-replay.log) |
| 6. Generate the HDB-only place export | `place.py` keeps one row per `full_address`, sorts by `block_id`, renames `street_name` to `road_name`, and projects the seven place columns. The replay reproduced the team's 9,761-place file byte for byte. That file is a literal prefix of the 9,964-place bundle, which then appends 203 railway places. [Offline replay](evidence/rail-preparation-replay.log) · [Bundled places](../setup/import_data_script/places_for_mysql.csv) |

### Railway rows and final import

The tracked railway cleaner projects coordinates and transport type from the raw code-level CSV, uppercases names, and deduplicates by name. Its current input would give 171 names. The archived and tracked 172-row sample matches Dataset B and includes Teck Lee. The script that created that exact sample from Dataset B was unavailable. [Tracked railway cleaner](../data/scripts/data_prep/04_clean_mrt.py) · [Tracked station sample](../data/samples/mrt_stations_sample.csv)

1. **Prepare the code-level rail file.** The team archived the legacy Dataset C CSV with CRLF line endings. A second team copy in `unused_raw_data` already omits the Chinese station and line columns, represents opening dates as day/month/year, and contains the rounded coordinates. All 203 dates represent the same dates as Dataset C. Its retained fields agree with the final rail file except for the 23 leading postal zeros that disappear in the final export.
2. **Add place columns and append the station places.** For all 203 final railway rows, `Town` is the uppercased English station name. For example, HarbourFront has `Town = HARBOURFRONT`, while the dated Dataset C export puts it in the Bukit Merah planning area. Railway `block_id` is 9,762 plus the zero-based row position. Interchanges retain separate codes and place IDs. Every linked place exactly matches the final station's block number, road, postal string, latitude, longitude, and `Town` label. The particular script or tool that formatted the intermediate rail file, added the two columns and appended the station places remains unverified. [Bundled station file](../setup/import_data_script/mrt_lrt_full_list.csv) · [Comparison output](evidence/rail-provenance-verification.json)
3. **Load MySQL.** The team-supplied historical `import.py` reads all three CSVs and links station metadata to places by `block_id`. It uses older schema names, numeric casts and multiple commits. The current repository importer is the setup path. It inserts `place` before `stations`, uses six station fields including the place foreign key, and takes station coordinates and postal values from `places_for_mysql.csv`. It reads money, floor area and place coordinates as decimals, preserves postal strings, maps HDB months to month-end dates, and commits the import in one transaction. The nearby builder then derives distances from the imported places. [Current importer](../setup/import_data_script/import.py) · [Nearby builder](../app/app_modules/nearby/nearby_function.py)

The reviewed forward and reverse postal scripts enrich HDB addresses. The station postal values come from Dataset C. All 23 altered station postal strings match the six-digit source after padding. For HDB, the cleanup file establishes the same leading-zero loss for 97 locations. Together they account for all 120 five-digit strings observed in the final places CSV. The current importer preserves those bundled strings as supplied.

## Reproduce the comparison

Obtain Dataset B's `TrainStationLocation.csv` from version 1 and Dataset C's `mrt_lrt_stations.csv` and `mrt_lrt_stations_2025-01-14.csv` from version 3. Keep the team's `raw_data.zip`, `cleaned_v2.zip`, and `used_data` folder outside the repository. The additional `unused_raw_data` rail file is optional. The report stores hashes and comparisons for these inputs, with no need to copy the team's preparation scripts or credentials into Git. [Dataset B](https://www.kaggle.com/datasets/cztandata/singapore-train-station-locations/versions/1) · [Dataset C](https://www.kaggle.com/datasets/lzytim/full-list-of-mrt-and-lrt-stations-in-singapore/versions/3)

```powershell
.\.venv\Scripts\python.exe -m docs.evidence.verify_rail_provenance `
  --raw-archive 'path/to/raw_data.zip' `
  --cleaned-archive 'path/to/cleaned_v2.zip' `
  --dataset-b 'path/to/TrainStationLocation.csv' `
  --dataset-c-legacy 'path/to/mrt_lrt_stations.csv' `
  --dataset-c-dated 'path/to/mrt_lrt_stations_2025-01-14.csv' `
  --used-data 'path/to/used_data' `
  --rail-intermediate 'path/to/unused_raw_data/mrt_lrt_full_list.csv' `
  --output 'docs/evidence/rail-provenance-verification.json'
```

The audit reads the inputs and writes the comparison JSON. Replaying `blocks.py` and `place.py` used pandas 3.1.1 and a temporary folder containing only the cleanup input and the resulting CSVs. The OneMap API and historical importer were reviewed without executing them.
