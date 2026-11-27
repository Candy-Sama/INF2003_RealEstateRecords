# Import the demonstration dataset

Use the [README setup instructions](../../README.md#run-the-application) to install dependencies, create a root `.env`, and execute the [MySQL schema](../firstver_database.sql). The SQL creates missing tables and retains existing tables and data when run again.

From the repository root, run the importer and the station-distance builder.

```powershell
.\.venv\Scripts\python.exe -m setup.import_data_script.import
.\.venv\Scripts\python.exe -m app.app_modules.nearby.nearby_function
```

The importer resolves all three CSV paths beside `import.py`. It creates the agent configured by `FLAT_RECORD_ADMIN_EMAIL` if that agent is missing. Enter a password of at least eight characters when prompted, or set `FLAT_RECORD_ADMIN_PASSWORD` in the process environment for an unattended run. If the agent already exists, the importer uses the existing agent ID and password.

The import requires an empty `place` table and keeps foreign-key checks active. It loads places before stations and flats, then links each transaction to its new flat and the configured agent. It commits all changes together. A failed import rolls back and can be retried after the cause is corrected.

| MySQL table | Expected seeded rows |
| --- | ---: |
| `place` | 9,964 |
| `stations` | 203 |
| `flat` | 242,634 |
| `resale_transaction` | 242,634 |

The distance builder populates `nearby` after the CSV import. It rebuilds the distance rows by default. Pass `--only-missing` to fill gaps while retaining existing rows.

The MySQL account in `.env` needs read and write privileges in `estateRecordsDB` and `CREATE TEMPORARY TABLES` for the distance builder. Run the [MySQL migration](../mysql_upgrade.md#upgrade-an-existing-schema) before using an older schema. The main application creates its MongoDB collections and analytics indexes on first use, so the configured MongoDB account needs read and write access to the chosen database.

## How the import files were prepared

1. The team cleaned the HDB transaction CSV, formed a `full_address` for each sale, and merged OneMap coordinates by address. The repository's `03_clean_hdb.py`, `06_geocode_hdb.py`, and `07_merge_geo.py` cover this stage.
2. The team's postal enrichment looked up the block number and street in OneMap Address Search. A reverse geocoding pass used the available coordinates and a 50 m buffer to try to fill missing HDB postal codes. The scripts cached repeated lookups by address or coordinates. [OneMap API documentation](https://www.onemap.gov.sg/apidocs/)
3. The team's block assignment created IDs from the sorted unique HDB `full_address` values. Its place export retained one HDB location per address and renamed `street_name` to `road_name` for the MySQL schema. The team's original place export contains the 9,761 HDB locations.
4. The bundled station export contains one record per station code from the team's raw rail snapshot, including separate codes at interchanges. Its place IDs continue after the HDB IDs in station-file order. The final places CSV includes both the HDB and station locations. The original rail publisher and the procedure for assigning station towns remain unverified.

The bundled HDB sale and station CSVs match the team's final exports byte for byte. The bundled places CSV covers 9,761 HDB locations and 203 additional station locations. HDB place IDs run from 1 through 9,761 and station place IDs run from 9,762 through 9,964. The two ID ranges are disjoint and together cover every row in `places_for_mysql.csv`. All sales and stations reference an existing place. The bundled snapshots are the inputs for the documented setup and grading demo.
