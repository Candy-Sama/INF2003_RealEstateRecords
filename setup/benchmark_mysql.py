"""Measure Estate Records queries and optionally compare index layouts on a disposable schema."""

import argparse
import hashlib
import json
from contextlib import closing
from datetime import date
from decimal import Decimal
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter

import mysql.connector

from app import repository
from app.app_modules.analytics.analytics_defaults import DEFAULT_CARDS
from app.app_modules.analytics.analytics_sql import bounded_select
from app.app_modules.database.database import get_flat_record_admin_email, get_mysql_connection
from app.app_modules.nearby import nearby_function
from setup.migrate_mysql import INDEXES, LEGACY_INDEXES, migrate_schema


TABLES = "agents, place, flat, stations, nearby, resale_transaction"


class QueryCapture:
    """Capture the repository's bound SELECT without running it."""

    def cursor(self, **_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, parameters=()):
        self.query = sql, parameters

    def fetchall(self):
        return []

    def fetchone(self):
        return (0,)


def _capture(query, *args):
    connection = QueryCapture()
    query(connection, *args)
    return connection.query


def workload(agent_id):
    dates = {"start_date": date(2025, 1, 1), "end_date": date(2025, 12, 31)}
    prices = {"min_price": Decimal("600000.00"), "max_price": Decimal("900000.00")}
    monthly = next(card["sql"] for card in DEFAULT_CARDS if card["seed_key"] == "price_trend")
    radius = nearby_function.DEFAULT_RADIUS_M
    nearby_filter = {"stations": ["EW2"], "max_distance_m": 500}
    return {
        "agent_recent": _capture(repository.list_agent_transactions, agent_id),
        "search_town_type": _capture(repository.search_transactions, {
            **dates, **prices, "town": "TAMPINES", "flat_type": "4 ROOM",
        }),
        "search_date": _capture(repository.search_transactions, dates),
        "search_price": _capture(repository.search_transactions, {
            "min_price": Decimal("1400000.00"), "max_price": Decimal("1600000.00"),
        }),
        "place_list": _capture(repository.list_places),
        "flat_types": _capture(repository.list_flat_types),
        "top_sales": _capture(repository.top_sales),
        "top_sales_4room": _capture(repository.top_sales, "4 ROOM"),
        "rank_towns": _capture(repository.rank_towns),
        "rank_streets": _capture(repository.rank_streets),
        "rank_stations": _capture(repository.rank_stations),
        "nearby_ew2": _capture(repository.search_nearby_flats, nearby_filter),
        "nearby_count_ew2": _capture(repository.count_nearby_flats, nearby_filter),
        "nearest_by_block": ("SELECT PLACE_block_id, MIN(distance_m) FROM nearby GROUP BY PLACE_block_id", ()),
        "latest_date": _capture(repository.latest_transaction_date),
        "monthly_card": (bounded_select(monthly), ()),
        "nearby_build_select": (
            nearby_function._WITHIN_RADIUS_SELECT.replace("/*MISSING_JOIN*/", "").strip(),
            {"deg": radius / nearby_function._METRES_PER_DEGREE, "radius": radius},
        ),
    }


def _rows_examined(cursor):
    try:
        cursor.execute(
            "SELECT h.ROWS_EXAMINED FROM performance_schema.events_statements_history AS h "
            "JOIN performance_schema.threads AS t ON t.THREAD_ID = h.THREAD_ID "
            "WHERE t.PROCESSLIST_ID = CONNECTION_ID() AND h.EVENT_NAME = 'statement/sql/select' "
            "ORDER BY h.EVENT_ID DESC LIMIT 1"
        )
        row = cursor.fetchone()
    except mysql.connector.Error:
        return None
    return row[0] if row else None


def _measure(cursor, sql, parameters, warmups, samples):
    cursor.execute("EXPLAIN FORMAT=TRADITIONAL " + sql, parameters)
    columns = cursor.column_names
    explain = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    cursor.execute("EXPLAIN ANALYZE " + sql, parameters)
    analyze = "\n".join(row[0] for row in cursor.fetchall())

    for _ in range(warmups):
        cursor.execute(sql, parameters)
        cursor.fetchall()
    elapsed = []
    for _ in range(samples):
        started = perf_counter()
        cursor.execute(sql, parameters)
        rows = cursor.fetchall()
        elapsed.append((perf_counter() - started) * 1000)
    examined = _rows_examined(cursor)
    # Aggregate queries may return the same rows in a different physical order.
    result = "\n".join(sorted(json.dumps(row, default=str) for row in rows))
    return {
        "sql": sql,
        "parameters": parameters,
        "explain": explain,
        "explain_analyze": analyze,
        "rows_examined": examined,
        "rows_returned": len(rows),
        "result_sha256": hashlib.sha256(result.encode()).hexdigest(),
        "median_ms": round(median(elapsed), 3),
        "p95_ms": round(sorted(elapsed)[ceil(0.95 * len(elapsed)) - 1], 3),
    }


def measure_workload(connection, queries, *, warmups, samples, refresh_stats=False):
    with connection.cursor(buffered=True) as cursor:
        if refresh_stats:
            cursor.execute(f"ANALYZE TABLE {TABLES}")
            errors = [row[3] for row in cursor.fetchall() if row[2] == "error"]
            if errors:
                raise ValueError("Could not refresh benchmark statistics. " + " ".join(errors))
        cursor.execute("SELECT VERSION(), DATABASE(), @@optimizer_switch")
        version, schema, optimizer = cursor.fetchone()
        cursor.execute("SET SESSION information_schema_stats_expiry = 0")
        cursor.execute(
            "SELECT TABLE_NAME, INDEX_LENGTH FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
            "('agents', 'place', 'flat', 'stations', 'nearby', 'resale_transaction')"
        )
        index_bytes = dict(cursor.fetchall())
        results = {name: _measure(cursor, *query, warmups, samples) for name, query in queries.items()}
    connection.rollback()
    return {
        "mysql": version, "schema": schema, "optimizer_switch": optimizer,
        "warmups": warmups, "samples": samples, "index_bytes": index_bytes, "queries": results,
    }


def _restore_legacy_indexes(connection):
    with connection.cursor() as cursor:
        for table, indexes in LEGACY_INDEXES.items():
            for name, (non_unique, columns) in indexes.items():
                kind = "INDEX" if non_unique else "UNIQUE INDEX"
                fields = ", ".join(f"`{column}`" for column in columns)
                cursor.execute(f"ALTER TABLE `{table}` ADD {kind} `{name}` ({fields})")
        for table, indexes in INDEXES.items():
            for name in indexes:
                cursor.execute(f"ALTER TABLE `{table}` DROP INDEX `{name}`")


def compare_indexes(connection, queries, *, warmups, samples):
    if migrate_schema(connection):
        raise ValueError("Index comparison requires a fully migrated disposable schema.")
    stages = {}
    try:
        _restore_legacy_indexes(connection)
        stages["before"] = measure_workload(connection, queries, warmups=warmups, samples=samples, refresh_stats=True)

        for statement in migrate_schema(connection):
            if " ADD INDEX " in statement:
                with connection.cursor() as cursor:
                    cursor.execute(statement)
        stages["added"] = measure_workload(connection, queries, warmups=warmups, samples=samples, refresh_stats=True)

        migrate_schema(connection, apply=True)
        stages["final"] = measure_workload(connection, queries, warmups=warmups, samples=samples, refresh_stats=True)
    finally:
        connection.rollback()
        migrate_schema(connection, apply=True)

    baseline = stages["before"]["queries"]
    final = stages["final"]["queries"]
    comparison = {
        name: {
            "same_rows": all(
                item["result_sha256"] == stages[stage]["queries"][name]["result_sha256"]
                for stage in ("added", "final")
            ),
            "median_change_ms": round(final[name]["median_ms"] - item["median_ms"], 3),
        }
        for name, item in baseline.items()
    }
    return {"stages": stages, "comparison": comparison}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-indexes", action="store_true", help="cycle index layouts on a disposable schema")
    parser.add_argument("--refresh-stats", action="store_true", help="run ANALYZE TABLE before a single measurement")
    parser.add_argument("--case", action="append", choices=workload(0), help="query to run, repeat to select several")
    parser.add_argument("--agent-id", type=int, help="agent for the transaction list (default is configured demo agent)")
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, help="write the JSON report to this path")
    args = parser.parse_args()
    if args.warmups < 0 or args.samples < 1:
        parser.error("use zero or more warmups and at least one sample")

    with closing(get_mysql_connection()) as connection:
        agent_id = args.agent_id
        if agent_id is None and (not args.case or "agent_recent" in args.case):
            with connection.cursor() as cursor:
                cursor.execute("SELECT agent_id FROM agents WHERE email = %s", (get_flat_record_admin_email(),))
                agent = cursor.fetchone()
            connection.rollback()
            if agent is None:
                parser.error("seed the configured administrator or pass --agent-id")
            agent_id = agent[0]
        queries = workload(agent_id)
        if args.case:
            queries = {name: queries[name] for name in args.case}
        if args.compare_indexes:
            report = compare_indexes(connection, queries, warmups=args.warmups, samples=args.samples)
        else:
            report = measure_workload(
                connection, queries, warmups=args.warmups, samples=args.samples, refresh_stats=args.refresh_stats,
            )
    output = json.dumps(report, default=str, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
