# MySQL schema upgrade and query benchmarks

## Upgrade an existing schema

For a fresh installation, run `firstver_database.sql` and import the CSVs as described in the [README](../README.md#run-the-application). For an existing installation, point the root `.env` to the schema you intend to upgrade. Run the preflight with an account that can read the tables and their metadata.

```powershell
.\.venv\Scripts\python.exe -m setup.migrate_mysql
```

Back up the schema and pause application writes before running the migration with a MySQL account that can alter the tables and create temporary tables. MySQL commits each DDL statement independently and rebuilds tables when changing column types. If the migration stops between statements, rerun the preflight to see the remaining operations. The backup is the rollback for type conversions. [MySQL online DDL operations](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html)

```powershell
.\.venv\Scripts\python.exe -m setup.migrate_mysql --apply
.\.venv\Scripts\python.exe -m setup.migrate_mysql
```

The migration checks the transaction key, foreign keys, schema types, and existing values. It adds replacement foreign-key indexes before removing the redundant ones. On a legacy schema with a missing, nullable, or defaulted `nearby.distance_m`, it rebuilds derived station pairs before requiring an explicit distance. The default radius is 1,000 m with nearest-station fallback. Pass `--radius` or `--no-fallback` to reproduce a different existing configuration.

A fresh import preserves all 166 fractional floor areas, all 69 prices with cents, and the decimal precision of the bundled coordinates. The migration converts existing stored values. Recovering digits lost by an earlier import requires verifying the original source mapping separately.

## Index rationale

| Index | Query pattern |
| --- | --- |
| `ix_rt_agent_date_flat` | Agent equality followed by reverse date and flat-ID order for the latest transactions. Replaces the single-column agent FK index. |
| `ix_rt_date` | Date bounds, recent searches, and `MAX(transaction_date)`. |
| `ix_rt_price` | Price bounds and highest sales. A price range can still need a sort when the result is ordered by date. |
| `ix_place_town_address` | Town equality, town options, and the catalogue’s address sort. |
| `ix_place_coords` | Latitude-led range checks for the nearby builder’s bounding boxes. MySQL still computes exact spherical distances for the remaining pairs. |
| `ix_flat_type_block` | Distinct flat types and filters by flat type and block. The standalone block key still serves joins that start from a place without filtering flat type. |
| `ix_nearby_block_distance` | Block-first station joins and nearest-distance grouping. Replaces the single-column block FK index. |

The transaction primary key keeps both flat and agent IDs. It supports flat-first joins and ensures one record per agent–flat pair. The nearby primary key provides station-first access. Lookups that omit the first column of a composite index may need another access path. Aggregate sorts on computed prices and counts, geography calculations, or broad filters can still require scans, temporary tables, or filesorts. Every secondary index adds storage and work when rows are inserted or indexed values change. [MySQL multicolumn indexes](https://dev.mysql.com/doc/refman/8.0/en/multiple-column-indexes.html)

A distance-only index was tested separately. MySQL kept the station-first primary-key plan and examined the same number of rows on the station workloads, so the final schema omits that index.

## Repeat the benchmark

Use a disposable, fully migrated MySQL schema with the bundled import and nearby rows. The comparison command temporarily changes its indexes and restores the final layout. Both commands read their connection settings from the shared `.env` or process environment.

```powershell
.\.venv\Scripts\python.exe -m setup.benchmark_mysql --compare-indexes --output benchmark.json
.\.venv\Scripts\python.exe -m setup.benchmark_mysql --case agent_recent --case search_price
```

The comparison uses the same rows and decimal types through three stages. It starts with the old index layout, adds the candidates, then removes redundant indexes. Each stage refreshes statistics and measures bound application queries, including Tampines 4-room sales in 2025, station `EW2` within 500 m, monthly analytics, and the read side of the nearby builder. The defaults are five warm-ups and 30 timed runs per case. Use `--case` to select workloads or `--samples` to change the sample count.

The report includes classic `EXPLAIN` access type, selected key, row estimates and `Extra`, plus `EXPLAIN ANALYZE` iterator times, rows, and loops. Plain-query timing includes fetch time and reports the median and nearest-rank p95. Performance Schema `ROWS_EXAMINED` is included when statement history is available and readable. The report also includes approximate secondary-index size and a result checksum for each query. [MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.0/en/explain.html)

## Observed results

Local MySQL 8.0.45 on Windows, using 242,634 imported sales and 24,178 derived nearby pairs. The following queries used five warm-ups and 30 timed runs per stage. Times include fetching the query results. Both layouts used the same exact column types and query text.

| Query | Median before → final | p95 before → final | Rows examined before → final | Final plan observation |
| --- | ---: | ---: | ---: | --- |
| Recent sales by agent | 167.36 → 5.05 ms | 183.98 → 6.51 ms | 242,934 → 300 | Backward scan on `ix_rt_agent_date_flat` removes filesort. |
| Date-only search | 31.74 → 6.52 ms | 35.02 → 7.58 ms | 245,634 → 3,000 | Backward range scan on `ix_rt_date`. |
| Narrow price-only search | 24.76 → 1.41 ms | 30.67 → 1.57 ms | 243,513 → 1,172 | Range scan on `ix_rt_price`. The query still sorts by date. |
| Tampines 4-room search | 29.83 → 19.79 ms | 37.40 → 21.27 ms | 34,653 → 15,637 | Town and flat type/block indexes narrow the joins. Filesort remains. |
| Highest sales | 78.35 → 0.16 ms | 85.29 → 0.30 ms | 242,664 → 30 | Backward scan on `ix_rt_price` stops after the result limit. |
| Highest 4-room sales | 235.31 → 0.40 ms | 240.11 → 0.54 ms | 448,890 → 324 | MySQL starts with the price index and tests flat type as it scans. |
| List distinct flat types | 41.19 → 0.12 ms | 45.82 → 0.24 ms | — | `Using index for group-by` on `ix_flat_type_block`. |

Estimated secondary-index storage grew from **19.94 MiB to 28.73 MiB**. The stage containing old and new indexes used **42.11 MiB**, so dropping the redundant indexes recovered about 13.38 MiB. The station-code query still used the unique station-code lookup and the nearby primary key. The existing plan examined 1,505 rows in both layouts.

With one warm-up and three timed runs per stage, the nearby builder's SELECT fell from **7.80 s to 0.89 s**. MySQL changed from a full place scan with a hash join to range checks using the coordinate index for each station. This measurement covers the bounding-box SELECT. The fallback ranking and database writes run separately. The monthly analytics query improved from **556.45 ms to 397.45 ms** and still used temporary aggregation and filesort. Station ranking was essentially flat at **476.09 ms to 473.15 ms**.

The final run produced matching result checksums on all 17 workloads across all three layouts. The initial comparison found town-rank price-per-square-metre differences below S$0.00000004 across aggregation plans. Computing each sale's ratio at a fixed decimal scale made the final results repeatable. One full CSV import took **6.40 s** with the original indexes and **7.53 s** with the final indexes. These two import timings show the observed write cost for this run.

## Run the integration tests

For integration tests, configure `.env` for a disposable server with `CREATE DATABASE` and `DROP DATABASE` privileges. Each test uses a generated schema and removes it during cleanup.

```powershell
$env:ESTATE_MYSQL_TEST = '1'
.\.venv\Scripts\python.exe -m unittest discover -s test -v
Remove-Item Env:ESTATE_MYSQL_TEST
```
