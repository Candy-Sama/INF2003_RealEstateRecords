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
