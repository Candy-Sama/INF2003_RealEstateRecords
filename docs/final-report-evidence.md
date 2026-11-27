# Estate Records final technical verification

## 1. Revision and scope

| Item | Verified value |
| --- | --- |
| Repository revision | `b7385492044e7267241628d8182ab7adfa170170` |
| Verification date | 27 November 2026, Singapore time |
| Application | Estate Records, INF2003 Database Systems |
| Working tree | Clean at the start. This verification adds evidence under `docs/`. |
| Database scope | Loopback MySQL and standalone MongoDB. All application data writes, schema changes and cleanup targeted generated evidence or test namespaces. Functional fixtures used synthetic accounts and sales. No matching namespaces remained afterward. [Cleanup check](evidence/fixture-cleanup.log) |

**Evidence status.** Measured results in this file come from this revision unless marked historical. The existing setup documentation is the source for the historical results.

## 2. Testing environment

| Component | Version or configuration |
| --- | --- |
| Operating system | Windows 11, build 26200, x64 |
| Python | CPython 3.14.4, repository virtual environment |
| Streamlit | 1.67.0 |
| MySQL | 8.0.45, InnoDB, 16 KiB pages |
| MySQL connector | mysql-connector-python 9.7.0 |
| MySQL statement instrumentation | Performance Schema enabled. Current and per-thread statement history consumers enabled. |
| MongoDB | 9.0.4, local standalone |
| MongoDB client | PyMongo 4.20.2 |
| Data handling | pandas 3.1.1 and python-dotenv 1.2.4 |

Connection settings came from local configuration. The evidence contains aggregate dataset checks, synthetic fixtures, timing summaries, and query plans.

## 3. Dataset statistics and integrity

Counts combine a direct read of the three bundled CSVs with a fresh MySQL import and the default nearby builder. The raw audit records SHA-256 hashes for the three input files. [Dataset verification output](evidence/dataset-verification.json) · [Import instructions](../setup/import_data_script/ImportInstructions.md)

| Metric | Verified value | Basis |
| --- | ---: | --- |
| HDB resale transactions | 242,634 | CSV rows and loaded `resale_transaction` rows |
| Flat rows | 242,634 | One generated flat row per bundled sale. The count represents the import model and does not establish the number of physical dwellings. |
| HDB locations | 9,761 | Distinct sale `block_id` values, 1–9,761 |
| Station codes | 203 | 162 MRT and 41 LRT. There are 171 distinct English name strings. Interchange codes can share a name. |
| Total places | 9,964 | 9,761 HDB locations plus 203 station place IDs, 9,762–9,964 |
| Derived nearby relationships | 24,178 | 22,669 within the 1,000 m build radius and 1,509 nearest-station fallback rows |
| Earliest transaction month | January 2017 | Earliest stored transaction date is 31 January 2017 |
| Latest transaction month | October 2026 | Latest stored transaction date is 31 October 2026 |
| Distinct transaction months | 118 | Dates converted from monthly CSV values to calendar month-end |
| Distinct HDB towns | 26 | Sale CSV distinct towns and the imported flat-to-place join agree |

| Integrity check | Observed result |
| --- | --- |
| Identifiers and references | 9,964 unique place IDs. HDB and station ID sets are disjoint and cover all places. Zero missing place IDs, zero sale-to-place town mismatches, zero station-code/place mapping differences, and zero orphan nearby pairs. |
| Monetary values | `DECIMAL(12,2)`. The row-by-row import comparison preserved all values, including 69 sales with cents. |
| Floor areas | `DECIMAL(7,2)`. The row-by-row comparison preserved all values, including 166 fractional areas. The CSV values require at most one decimal place after insignificant zeros are removed. |
| Coordinates | `DECIMAL(18,15)`. All exported place coordinates survived import as numerically equal decimals. Bundled place coordinates require up to 15 latitude and 13 longitude decimal places. Stored scale is a representation property. Geocoding accuracy was outside this check. |
| Dates and sale-to-place mapping | All imported sales matched the corresponding CSV block ID, amount, area and month-end date in flat-ID insertion order. |
| Postal fields | Every place postal string survived import. The bundled strings include 9,844 six-digit and 120 five-digit entries. The original form of the five-digit values is unverified. |
| Nearby coverage | All 9,761 HDB locations have at least one relationship. Stored distances range from 23 to 3,516 m. The builder uses spherical distance, stores integer metres, and permits nearest-station fallback outside the radius. These distances describe geographic proximity. |

**Source provenance.** The repository identifies the Housing & Development Board resale series and describes OneMap enrichment. This audit verified the bundled snapshot and import. It did not establish byte-level equivalence to the upstream HDB export. The report should cite the verified input hashes when discussing dataset size and date range. [Repository dataset description](../README.md#datasets-and-preparation) · [HDB resale series](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view) · [SLA OneMap Search API](https://www.onemap.gov.sg/apidocs/search)

**Rail provenance remains unresolved.** The earliest rail CSV found in the available Git refs is `import/mrt_lrt_full_list.csv` at `0c908d4`. It has the same Git blob ID as the current `setup/import_data_script/mrt_lrt_full_list.csv`, `31993b046b949d15441d1faf5c2a37cf340aef1f`. The historical import instructions list the file without an upstream link. Current documentation identifies the team's `raw_data.zip` snapshot as its input, but the archive was absent from the available tracked history. Exact filename and header searches found no source that could be tied to this export. The original rail publisher, URL, snapshot date, and procedure for assigning station towns remain unverified. [Repository dataset description](../README.md#datasets-and-preparation) · [Dataset preparation notes](../setup/import_data_script/ImportInstructions.md#how-the-import-files-were-prepared)

## 4. MySQL performance

### Methodology and historical evidence

The benchmark captures parameterized application SELECTs and compares three index layouts on the same schema and rows. The baseline restores legacy indexes, the added stage keeps legacy and candidate indexes together, and the final stage removes redundant indexes while keeping the production layout. Exact numeric types and foreign keys are held constant. Each stage runs `ANALYZE TABLE`, traditional `EXPLAIN`, `EXPLAIN ANALYZE`, and timed full fetches. The script reports the median and nearest-rank p95 of the plain-query timings. It reads `ROWS_EXAMINED` from the most recent SELECT in that connection's Performance Schema statement history. Classic `EXPLAIN` row estimates and iterator counts have different meanings. [Benchmark code](../setup/benchmark_mysql.py#L89) · [MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.0/en/explain.html) · [Performance Schema statement history](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-events-statements-history-table.html)

The benchmark hashes sorted serializations of the result rows to check content and multiplicity across layouts. A matching hash does not verify ordering. The index figures sum `information_schema.TABLES.INDEX_LENGTH` across the six application tables. This is an InnoDB allocation estimate for secondary indexes. The import measurement is a separate full-load check that includes CSV parsing, seed-agent creation, insert work, and commit. [MySQL TABLES metadata](https://dev.mysql.com/doc/refman/8.0/en/information-schema-tables-table.html) · [Importer](../setup/import_data_script/import.py)

**Historical figures.** The existing benchmark notes report MySQL 8.0.45 on Windows, 242,634 sales and 24,178 derived nearby pairs, generally with five warm-ups and 30 samples per stage. The table reproduces the values recorded there. The historical raw timing and plan artifacts were absent from the available tracked history. The fresh benchmark below independently tests this revision. The comparison script is unchanged from `d10db30`, which last updated the historical notes, while some nearby and ranking SQL obtained from the repository has since changed. [Historical notes](../setup/mysql_upgrade.md#observed-results)

| Historical workload | Median before → final (ms) | p95 before → final (ms) | Rows examined before → final | Final access |
| --- | ---: | ---: | ---: | --- |
| Recent sales by agent | 167.36 → 5.05 | 183.98 → 6.51 | 242,934 → 300 | Backward `ix_rt_agent_date_flat`, no filesort |
| Date-only search | 31.74 → 6.52 | 35.02 → 7.58 | 245,634 → 3,000 | Backward `ix_rt_date` range |
| Narrow price-only search | 24.76 → 1.41 | 30.67 → 1.57 | 243,513 → 1,172 | `ix_rt_price` range with date sort |
| Tampines 4-room search | 29.83 → 19.79 | 37.40 → 21.27 | 34,653 → 15,637 | Town and flat type/block indexes with filesort |
| Highest sales | 78.35 → 0.16 | 85.29 → 0.30 | 242,664 → 30 | Backward `ix_rt_price` scan, early limit |
| Highest 4-room sales | 235.31 → 0.40 | 240.11 → 0.54 | 448,890 → 324 | Price index followed by type testing |
| Distinct flat types | 41.19 → 0.12 | 45.82 → 0.24 | Unreported | `ix_flat_type_block` for grouping |

The historical notes also record 19.94 MiB before, 42.11 MiB with both index sets, and 28.73 MiB final. One full CSV import took 6.40 s before and 7.53 s final, an increase of 1.13 s or 17.7%. The historical nearby-builder SELECT took 7.80 s before and 0.89 s final with one warm-up and three samples. Its timing excludes fallback and writes. The monthly card took 556.45 → 397.45 ms, station ranking took 476.09 → 473.15 ms, and the station-code lookup retained 1,505 examined rows. The notes report matching checksums for all 17 workloads across all layouts. [Historical notes](../setup/mysql_upgrade.md#observed-results)

### Measurements on this revision

A freshly loaded schema contained 242,634 sales and 24,178 derived nearby rows. The bundled importer assigned all sales to one synthetic agent. The evidence runner invoked the repository's `compare_indexes` with five warm-ups and 30 samples per stage for 16 workloads, then one warm-up and three samples per stage for the nearby-builder SELECT. The tables show baseline and final outcomes. Raw output also includes the added stage, parameters, returned rows, optimizer settings, per-table storage, checksums and full plans. All 17 workloads returned matching row-content checksums across all three layouts. [Regular query benchmark](evidence/mysql-benchmark.json) · [Nearby-builder benchmark](evidence/mysql-benchmark-nearby-builder.json) · [Run log](evidence/mysql-benchmark-run.log) · [Reproduction runner](evidence/run_mysql_evidence.py)

| Current workload | Median before → final (ms) | p95 before → final (ms) | Rows examined before → final | Key access change |
| --- | ---: | ---: | ---: | --- |
| Recent sales by agent | 193.530 → 6.498 | 254.422 → 7.675 | 242,934 → 300 | Legacy agent key and filesort → backward `ix_rt_agent_date_flat`, no filesort |
| Date-only search | 41.872 → 8.460 | 42.465 → 9.963 | 245,634 → 3,000 | Transaction scan → `ix_rt_date` range, no filesort |
| Narrow price-only search | 34.275 → 1.512 | 35.442 → 1.833 | 243,513 → 1,172 | Transaction scan → `ix_rt_price` range. Date sort remains. |
| Tampines 4-room search | 37.983 → 24.057 | 40.631 → 25.990 | 34,653 → 15,637 | Place scan and flat block key → `ix_place_town_address` and `ix_flat_type_block`. Filesort remains. |
| Place list | 16.951 → 6.697 | 20.288 → 7.206 | 19,928 → 9,964 | Scan and filesort → ordered `ix_place_town_address` scan |
| Distinct flat types | 49.385 → 0.083 | 50.102 → 0.229 | 242,641 → 0 | Table scan and temporary deduplication → covering skip scan on `ix_flat_type_block` |
| Highest sales | 91.990 → 0.158 | 95.559 → 0.359 | 242,664 → 30 | Transaction scan and filesort → backward `ix_rt_price`, stops at the limit |
| Highest 4-room sales | 316.961 → 0.470 | 333.056 → 0.642 | 448,890 → 324 | Flat scan and filesort → backward `ix_rt_price` and flat-type filtering |
| Town ranking | 707.480 → 670.389 | 715.664 → 680.678 | 262,359 → 19,726 | Adds ordered `ix_place_town_address` access. Latest date is optimized away. |
| Street ranking | 407.042 → 397.326 | 436.435 → 408.994 | 19,735 → 19,735 | Uses `ix_place_town_address` for place access. Filesort remains. |
| Station ranking | 483.509 → 485.411 | 486.503 → 496.787 | 11,841 → 11,841 | Same station/nearby access and temporary aggregate plan |
| EW2 within 500 m listing | 1.913 → 1.849 | 2.279 → 2.212 | 400 → 400 | Same `station_code_UNIQUE`, nearby primary key, and flat block key |
| EW2 within 500 m count | 0.375 → 0.395 | 0.541 → 0.532 | 1,353 → 1,353 | Same station-code lookup, nearby primary key, and flat block key |
| Nearest distance per block | 22.523 → 5.761 | 26.347 → 6.015 | 24,178 → 24,178 | Legacy block index → covering scan on `ix_nearby_block_distance` |
| Latest date | 23.344 → 0.099 | 24.682 → 0.203 | 242,634 → 1 | Full scan → `MAX()` optimized with the date index |
| Monthly analytics card | 549.958 → 571.959 | 557.848 → 629.357 | 354 → 354 | Flat table scan → covering `ix_flat_type_block` scan. Temporary aggregation and filesort remain. |
| Nearby-builder SELECT | 8,868.125 → 1,068.768 | 8,941.253 → 1,069.354 | 10,370 → 406 | Full place scan and hash join → per-station covering range checks using `ix_place_coords` |

These figures reproduce the historical row counts and plan direction for the main recent-sale, filter and top-sale queries. The monthly card was slower with the final layout in this run. `EXPLAIN ANALYZE` still read 242,634 flat rows and probed 220,064 matching sales in both layouts. The EW2 listing used 400 examined rows in both layouts with the current query, versus the historical 1,505. Changes to nearby and ranking SQL limit direct historical timing comparisons.

The statement-history counters and iterator metrics should be read together. The final distinct-flat-type query reports zero `ROWS_EXAMINED`, while its covering skip-scan iterator returns seven values. The final builder reports 406 `ROWS_EXAMINED`, while the range-scan iterator yields about 988 candidate rows per station across 203 loops. The legacy hash join yields about 2.02 million candidates. The statement counter is reported as captured and does not represent every iterator row or every distance calculation. [MySQL statement event fields](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-events-statements-current-table.html)

| Index layout | Secondary-index bytes | MiB |
| --- | ---: | ---: |
| Baseline | 20,905,984 | 19.94 |
| Legacy plus candidate indexes | 44,154,880 | 42.11 |
| Final | 30,130,176 | 28.73 |

The final layout adds 9,224,192 bytes, or 8.80 MiB and 44.1%, over baseline. Removing redundant indexes from the combined stage recovered 13.38 MiB. The two benchmark passes yielded the same storage totals.

| Full CSV import | Measured samples (s) | Median (s) |
| --- | --- | ---: |
| Legacy indexes | 7.140, 7.290, 7.204 | 7.204 |
| Final indexes | 8.740, 8.406, 8.413 | 8.413 |

The median increased by **1.209 s, or 16.8%**, with final indexes. Each sample used a fresh schema and the repository importer, with DDL and the nearby build outside the timed section. The three samples per layout were interleaved in the order final, legacy, legacy, final, final, legacy. This measures the observed end-to-end insertion overhead for the bundled import. Per-row insert latency and sustained write throughput were outside the experiment. [Import timing samples](evidence/mysql-import-timings.json)

## 5. MongoDB saved-search listing performance

**Measured in this verification.** The evidence runner repeats the [documented saved-search benchmark](saved-searches-mongodb.md#6-measure-the-list-before-and-after-indexing). It created three independent disposable collections, each with 20,000 synthetic searches across 200 agents and exactly 100 searches per agent. Each trial used the same collection for the baseline and indexed stage. Both stages filtered `agent_id: 42` and sorted by `created_at DESC, _id DESC`. The indexed stage added `saved_searches_agent_created_id` on `{agent_id: 1, created_at: -1, _id: -1}`. The baseline kept MongoDB's normal `_id` index. There were three ordinary warm-up reads per stage per trial, followed by 15 `explain("executionStats")` measurements and 15 separately timed full cursor reads. Neither query specified a hint. [All 90 explain results and client fetch samples](evidence/mongodb-benchmark.json) · [Reproduction runner](evidence/run_mongodb_evidence.py)

| Layout | Winning plan, root to input | Docs examined | Index keys examined | Docs returned | Explicit sort | Server execution time across 45 samples | Client fetch median |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| Before | `SORT → COLLSCAN` | 20,000 | 0 | 100 | Yes | 5 ms median, 5–8 ms range. 44 at 5 ms, one at 8 ms. | 4.460 ms |
| After | `FETCH → IXSCAN` on `saved_searches_agent_created_id` | 100 | 100 | 100 | No | 0 ms reported in all 45 samples | 0.471 ms |

Full documents matched in the same order before and after indexing in all three trials. All 90 explains agreed on the plan shape and counts for their layout. The compound index reads the contiguous set of entries for the selected agent in the required order. MongoDB then fetches those 100 full documents. The query examined 99.5% fewer documents and eliminated the explicit sorting stage on this workload. [MongoDB explain reference](https://www.mongodb.com/docs/manual/reference/explain-results/)

The server timer is reported in whole milliseconds. The 0 ms readings cannot establish a finite speedup ratio. The separate client timings include local transport and BSON decoding and describe this machine and run order. The fixture used uniform ownership, one queried agent, warmed reads, and unique dates within each agent. It did not measure tied-date ordering under load, cold-cache behavior, concurrent traffic, or write and disk costs of the compound index. The tested operation lists saved-search documents. The subsequent resale query runs in MySQL and is outside this timing.

## 6. Automated tests

| Repository test invocation | Tests discovered | Passed | Failed or errored | Skipped | unittest duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| `python -m unittest discover -s test -v` with integration flag unset | 80 | 69 | 0 | 11 | 1.258 s |
| `python -m unittest discover -s test -v` with `ESTATE_MYSQL_TEST=1` | 80 | 80 | 0 | 0 | 6.993 s |

The 11 initial skips were the opt-in tests in `MySQLSchemaTests`. Each enabled test creates and drops its own UUID-named schema. The default connection for the enabled run was `information_schema`, and each test switched to its fixture schema before loading data. Both runs succeeded. The Streamlit session test emitted the bare-mode missing `ScriptRunContext` warning and passed. Durations are unittest's reported run times. The enabled run includes the same 69 tests from the default run. [Unit log](evidence/unit-tests.log) · [MySQL-enabled log](evidence/mysql-integration-tests.log) · [MySQL test fixture](../test/test_mysql_schema.py#L25)

| Suite area | Tests | Scope |
| --- | ---: | --- |
| Analytics | 15 | SQL validation, read-only wrapper, cap, chart numeric conversion, card config, and a mocked legacy seeded-card update |
| Analytics builder | 21 | Query compilation, field and filter validation, display mapping, and stored card configuration |
| Comparable sales | 4 | Summary and bound query construction |
| MySQL integration | 11 | Schema constraints, decimal fidelity, migration, benchmark restoration, nearby and ranking behavior, comparable-sales radius, batch commit and rollback |
| Ranking | 11 | Board ordering, price calculations, and SQL regression cases |
| Repository | 14 | Access rules and bound SQL via doubles, plus batch transaction behavior |
| Password security | 3 | Verification, independent salts, malformed hashes |
| Workspace session | 1 | Mocked AppTest logout and account switch |

**Suite coverage gap.** The checked-in suite gives good coverage to SQL and Python validation, transaction atomicity, and session clearing. It lacks a live MongoDB regression suite for saved-search CRUD, owner predicates, dashboard reload persistence, and idempotent seeding and restoration. Card cleaning, default-card validity and a mocked legacy update cover parts of dashboard behavior in isolation. The dedicated functional evidence below exercises the live paths independently of the 80-test suite. [Repository tests](../test/test_repository.py) · [Analytics tests](../test/test_analytics.py) · [Workspace test](../test/test_workspace_session.py)

## 7. Functional verification

The supplemental runner executed against both real database engines and passed nine assertion groups in **3.148 s**, including fixture setup and cleanup. AppTest drove Streamlit widgets and reruns in Python. Store checks called application functions directly against MongoDB. A manual browser pass was outside this run. Static inspection is marked explicitly. [Functional output](evidence/functional-checks.log) · [Streamlit runtime output](evidence/functional-runtime.log) · [Reproduction runner](evidence/run_functional_evidence.py)

| Function | Verification method | Observed result |
| --- | --- | --- |
| Agent registration and authentication | AppTest and live MySQL | Registered two agents. Registration opened an authenticated workspace. An incorrect password and registration using the provisioned admin address were rejected. Correct login accepted uppercase email through normalization and stored the account password as a scrypt hash. |
| Relational transaction CRUD and owner restrictions | AppTest and live MySQL repository calls | Agent A created, listed, updated and deleted a sale. Agent B's owner-scoped lookup, edit and delete could not access the sale. A direct, separate MySQL connection confirmed the committed price and deletion. Agent B could see the sale through the shared market search as intended. |
| Shared flat catalogue and administrator access | AppTest and live MySQL | A normal agent could view and look up flats and had no create or edit controls. The provisioned administrator created and edited a flat. MySQL stored the updated area exactly. Static inspection found create and update flows for the shared catalogue. |
| Atomic batch insertion and rollback | Existing live MySQL integration tests | A valid two-row batch committed and was visible to a new session. In separate duplicate-key and foreign-key subtests, a valid first insert rolled back when the second row failed. The observer saw only the pre-existing sale. [Batch tests](../test/test_mysql_schema.py#L90) |
| Saved-search create, list, edit and delete | AppTest and live MongoDB | Saved the filters, confirmed the stored document, edited its name and maximum price, and deleted it as the owner. Reversed price and date bounds were rejected and the stored document remained unchanged. Agent B could not list, update or delete Agent A's saved search. |
| Saved search uses current MySQL results | AppTest with a controlled committed change in MySQL | Saved a matching search, edited its criteria, then updated the matching sale in a separate MySQL connection from S$525,000.27 to S$560,000.35. **Run saved search** restored the persisted filters, returned the new price, and matched a direct search. The MongoDB document contained the criteria and no saved result rows. |
| Analytics-card create, duplicate, edit and delete | Live MongoDB store calls | Created a custom card, duplicated its SQL and confirmed the copy title, edited the original title and width, and deleted the copy. Another agent could not list, update, duplicate or delete that card. Static inspection traced the matching dashboard controls to these store operations. |
| Dashboard persistence and default-card restoration | AppTest dashboard load, fresh AppTest login, and live MongoDB store calls | First opening Analytics created eight defaults. Repeated seeding created zero. After deleting one default, calling ordinary seeding left it absent. Explicit restore created one missing card and a second restore created zero. A fresh MongoDB client and a fresh Streamlit session loaded the edited custom card. The deleted copy stayed absent and the other default IDs were preserved. |
| Cross-agent session isolation | Existing mocked AppTest plus supplemental AppTest and live database calls | Logging out removed previous search results. A second agent started without the first agent's search state, personal listing and cards. The public market data and flat catalogue remained visible to agents. |
| Unsafe analytics SQL | Existing unit tests and supplemental live MySQL connection | The production query runner rejected write, sensitive account data, multiple-statement and comment cases. A valid aggregate ran successfully, set the 15,000 ms session timeout and ended with the transaction closed. |

## 8. Security verification

| Control | Verified evidence | Scope |
| --- | --- | --- |
| Passwords and session handling | Salted scrypt with `N=2^14, r=8, p=1`, a random 16-byte salt and constant-time digest comparison. Unit tests verified original and incorrect passwords, independent salts and malformed hashes. AppTest verified real login and logout. [Password helpers](../app/app_modules/security/security.py) · [Password tests](../test/test_security.py) | Application authentication. Deployment TLS and sign-in rate limiting were outside the review. |
| Relational ownership and query parameters | The workspace passes the authenticated agent ID to owner-specific repository calls. Update and delete use bound values and match the composite flat/agent identity. Live checks showed a foreign agent could not change the owner's record. Mocked search tests check SQL parameter binding. [Repository transaction access](../app/repository.py#L133) · [Repository tests](../test/test_repository.py) | Ownership applies to personal transaction management. Market search intentionally shares sale attributes. |
| Document ownership | Live checks confirmed agent-scoped reads and mutations for saved searches and analytics cards. Static inspection verified document IDs are paired with `agent_id` for changes, and user default metadata is keyed uniquely by agent. [Saved-search store](../app/app_modules/saved_searches_store.py) · [Analytics store](../app/app_modules/analytics/analytics_store.py#L151) | Application-level predicates tested using two synthetic agents. |
| SQL safety | Unit coverage includes writes, administration, multiple statements, comments, sensitive names and rejection before database execution. Live and static checks confirmed validation, a read-only transaction with rollback, a 15 s session limit, and a 5,000-row display cap enforced by a bounded query and truncation flag. [Validator and query runner](../app/app_modules/analytics/analytics_sql.py#L100) · [Analytics tests](../test/test_analytics.py) | The live smoke check confirmed the session setting. The unit tests cover truncation and the read-only flag. This was a representative behavior check, without adversarial coverage. |
| Database privilege boundary | Static inspection found that analytics and ordinary MySQL operations use the same connection factory. [Analytics database call](../app/workspace_pages/analytics_ui.py#L74) · [Database factory](../app/app_modules/database/database.py) | A separate restricted analytics identity and deployment grants were outside the verification. A report claim about database-enforced least privilege would require that evidence. |

## 9. Known limitations and unresolved issues

- Rail provenance still requires a publisher, download URL, release or retrieval date, and evidence tying that source to the bundled file. The 120 five-digit postal entries were preserved as supplied and their original formatting is unresolved.
- The resale snapshot ends in October 2026 and represents published sale records. The fresh import assigns every bundled sale to the synthetic seed agent, which affects how representative the agent-filter benchmark is.
- The measurements use one local machine and fixed workloads. There was no production-load, network-latency, or concurrent-writer benchmark. The MongoDB before/after experiment always applied the index second.
- The saved-search performance improvement requires provisioning `saved_searches_agent_created_id` in the target MongoDB database. Setup documents this step, and the saved-search UI simply queries the collection. Evidence database indexes are scoped to their fixtures. [Saved-search setup](saved-searches-mongodb.md#5-create-the-index-once-during-setup) · [Saved-search store](../app/app_modules/saved_searches_store.py#L30)
- The analytics dashboard caches query results for ten minutes and exposes a refresh action. The saved-search rerun uses the current MySQL results through a separate, uncached path. Dashboard configuration persistence and freshness of its SQL results are separate properties. [Analytics caching](../app/workspace_pages/analytics_ui.py#L22) · [Search execution](../app/workspace_pages/search_ui.py#L86)
- Supplemental analytics verification covered store mutations and dashboard rendering. The dashboard mutation buttons, visual layout, database restart persistence, and concurrent default-seeding behavior were outside this run.

## 10. Source-code references

| Concern | Implementation and tests |
| --- | --- |
| Schema, migration and import | [Schema DDL](../setup/firstver_database.sql) · [Migration and index lists](../setup/migrate_mysql.py#L27) · [CSV importer](../setup/import_data_script/import.py) |
| Nearby derivation | [Bounding-box query and fallback](../app/app_modules/nearby/nearby_function.py) |
| MySQL benchmark | [Workload, measurement and index orchestration](../setup/benchmark_mysql.py#L55) · [Historical benchmark](../setup/mysql_upgrade.md#observed-results) |
| Authentication and session boundaries | [Authentication UI](../app/app_modules/authentication_ui.py) · [Password hashing](../app/app_modules/security/security.py) · [Workspace routing and logout](../app/streamlit_app.py#L108) |
| Relational CRUD and atomic batches | [Repository](../app/repository.py#L133) · [Transaction UI](../app/workspace_pages/transactions_ui.py) · [Batch integration cases](../test/test_mysql_schema.py#L90) |
| Search and MongoDB ownership | [Saved-search store](../app/app_modules/saved_searches_store.py) · [Saved-search UI](../app/workspace_pages/saved_searches_ui.py) · [Live MySQL search](../app/workspace_pages/search_ui.py#L78) |
| Analytics and persistence | [Card store](../app/app_modules/analytics/analytics_store.py#L151) · [Default templates](../app/app_modules/analytics/analytics_defaults.py) · [Dashboard](../app/workspace_pages/analytics_ui.py#L114) · [SQL restrictions](../app/app_modules/analytics/analytics_sql.py#L100) |

## 11. Recommendations for the academic report

1. Tie each indexing result to a user operation, its selected access path, and a measured amount of work. Use rows examined and sort elimination to explain the change. Show MySQL's storage and import costs next to the read improvements.
2. Label the historical MySQL figures and the measurements from this revision. State the exact fixture size, timings, warm-ups and sample counts. Where optimizer behavior differs, use the new plans and checksums to explain the scope of the replication.
3. Present saved searches as MongoDB-stored criteria that trigger a live MySQL query. Use the observed changed sale price as the demonstration. Use the separately measured MongoDB work reduction to explain the listing index.
4. Show ownership and atomicity with two synthetic agents and the live duplicate-key and foreign-key rollback tests. Describe the shared flat catalogue and market search explicitly when discussing permissions.
5. Include the bundle's month range, precision checks and disjoint ID ranges. Describe nearby distances as derived values and explain the nearest-station fallback. Cite the team's rail snapshot as the known input and leave upstream attribution open until confirmed.
6. Include the two unittest summaries and the supplemental functional evidence. Recommend permanent coverage for MongoDB ownership, persistence, default-card behavior, and analytics UI interactions.
7. Describe the analytics restrictions as application validation and execution controls. Treat separation of database privileges as a future improvement unless the deployment provides independently verified grants.

### Reproducing the evidence

Run from the repository root using the provisioned project virtual environment and local database configuration. The script modules below reject non-loopback endpoints for their evidence fixtures. The MySQL test suite itself reads the configured endpoint and needs `CREATE DATABASE` and `DROP DATABASE`. Verify it points at the intended disposable test server or local instance before enabling it.

```powershell
Remove-Item Env:ESTATE_MYSQL_TEST -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s test -v

$env:ESTATE_MYSQL_TEST = '1'
$env:MYSQL_DATABASE = 'information_schema'
.\.venv\Scripts\python.exe -m unittest discover -s test -v
Remove-Item Env:ESTATE_MYSQL_TEST
Remove-Item Env:MYSQL_DATABASE

.\.venv\Scripts\python.exe -m docs.evidence.run_mongodb_evidence
.\.venv\Scripts\python.exe -m docs.evidence.run_mysql_evidence
.\.venv\Scripts\python.exe -m docs.evidence.run_functional_evidence
```

Run the benchmark modules sequentially to avoid overlapping the timed workloads. The MongoDB and MySQL modules overwrite their named JSON outputs in `docs/evidence/` on a successful rerun. The MySQL script takes several minutes. The functional runner prints assertion summaries. The captured outputs are linked alongside their results.
