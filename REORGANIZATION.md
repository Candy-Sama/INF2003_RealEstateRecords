# Reorganization and dependency log

Reviewed on 27 November 2026 for the INF2003 grading checkout.

| Issue found | Change |
| --- | --- |
| The relocated Streamlit app, feature modules, and five test modules still imported files by their old top-level names. The old `app/app.py` filename also shadowed the `app` package during Streamlit execution. | Updated imports to match the `app` package and renamed the entry point to `app/streamlit_app.py`. The Nearby utility and seed importer now have documented module commands. |
| The moved database module looked beside itself for `.env`. The seed importer used separate hard-coded credentials and resolved the CSVs from the current directory. | The app and importer share the root `.env` configuration. The importer locates the bundled CSVs beside itself. |
| The importer assumed the demo agent’s ID was `1`, disabled foreign-key checks, and could leave partially committed seed data. | The importer uses the configured administrator’s actual ID, keeps foreign keys enabled, and commits the whole seed in one transaction. It rejects a repeat import into a populated schema. It hashes the supplied password when provisioning a new administrator. |
| The schema script dropped existing data and omitted the distance column used by nearby and analytics queries. | The setup SQL creates missing tables and includes `nearby.distance_m` for fresh installs. The distance utility retains support for adding the column to an older schema. |
| The requirements file omitted the direct Altair dependency and allowed Streamlit versions older than the UI calls. Several listed data libraries were unused. | Declared Altair explicitly, updated the Streamlit and MySQL Connector minimums for the documented Python environment, and kept the packages used by the app and preparation scripts. [Streamlit release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2025) · [MySQL Connector/Python releases](https://pypi.org/project/mysql-connector-python/#history) |
| The preparation scripts resolved inputs from the working directory, the ignore rule targeted the old script location, and the geocoder embedded a OneMap token. | Anchored paths under `data/`, updated the ignore rule, and made the geocoder load `ONEMAP_API_TOKEN` from the environment or root `.env`. An authentication failure now stops the geocoder. |
| The setup documentation pointed to the former layout and described only part of the application. | Rebuilt the README as the grading user manual with database design, bundled datasets, configuration, a walkthrough, and test commands. Updated the linked import guide. |

## Verification

- A fresh requirements install succeeded on Windows with Python 3.14.4. `pip check` found no broken requirements, and all 54 unit tests passed.
- All three bundled CSV files matched their pre-move Git blobs. Every flat and station input `block_id` had a matching `place` row.
- On disposable MySQL 8.0.45, the importer loaded 9,964 places, 203 station codes, 242,634 flats, and 242,634 resale transactions. The checks verified month-end dates, ownership by the generated administrator ID, repeat-import rejection, and preservation of rows when the schema script ran again. A fixture with an invalid station foreign key confirmed that earlier inserts were rolled back.
- The nearby builder generated 22,671 in-radius rows and 1,507 nearest-station fallback rows, covering all 9,964 places.
- Streamlit AppTest ran against disposable MySQL and MongoDB 9.0.4. It verified administrator login, a filtered MySQL search, MongoDB saved search creation, rename, replay, and deletion, plus rendering of the other workspace pages and persistence of eight default analytics cards.
- The documented MySQL client command loaded the schema, and the documented Streamlit command started a local server that responded to its health check.
- Fixture checks verified root `.env` discovery, shell override precedence, and the data preparation paths from a different working directory. The optional geocoder’s missing-token behavior was checked locally. A live OneMap call remains unverified.

The previous embedded credential values remain in earlier Git history.
