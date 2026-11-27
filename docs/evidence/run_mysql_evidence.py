"""Reproduce the MySQL evidence using UUID-named schemas on a loopback server.

Run from the repository root with python -m docs.evidence.run_mysql_evidence.
"""

import csv
import hashlib
import json
import os
from calendar import monthrange
from collections import Counter
from contextlib import closing, contextmanager
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

from app.app_modules.database.database import get_mysql_connection
from app.app_modules.nearby.nearby_function import populate_nearby
from setup.benchmark_mysql import _restore_legacy_indexes, compare_indexes, workload


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[1]
INPUTS = ROOT / "setup" / "import_data_script"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
import_csv = import_module("setup.import_data_script.import").main


def write_json(name, payload):
    (EVIDENCE / name).write_text(json.dumps(payload, default=str, indent=2) + "\n", encoding="utf-8")


@contextmanager
def disposable_schema():
    if os.getenv("MYSQL_HOST", "localhost").lower() not in LOOPBACK:
        raise ValueError("Use a loopback MySQL server for evidence.")
    key = "MYSQL_DATABASE"
    original = os.environ.get(key)
    os.environ[key] = "information_schema"
    schema = "estate_evidence_" + uuid4().hex
    try:
        with closing(get_mysql_connection()) as control, control.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{schema}`")
            try:
                ddl = (ROOT / "setup" / "firstver_database.sql").read_text(encoding="utf-8")
                cursor.execute(ddl.replace("`estateRecordsDB`", f"`{schema}`"), map_results=True)
                while cursor.nextset():
                    pass
                control.commit()
                os.environ[key] = schema
                yield schema
            finally:
                control.rollback()
                cursor.execute(f"DROP DATABASE `{schema}`")
    finally:
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


def read_csv(name):
    with (INPUTS / name).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def dataset_evidence(connection, cursor):
    sale_file = "hdb_resale_enriched_block_id.csv"
    place_file = "places_for_mysql.csv"
    station_file = "mrt_lrt_full_list.csv"
    sales, places, stations = map(read_csv, (sale_file, place_file, station_file))
    sale_blocks = {int(row["block_id"]) for row in sales}
    station_blocks = {int(row["block_id"]) for row in stations}
    places_by_id = {int(row["block_id"]): row for row in places}
    station_codes = [row["ALPHANUMERIC_CODE"] for row in stations]
    prices = [Decimal(row["resale_price"]) for row in sales]
    areas = [Decimal(row["floor_area_sqm"]) for row in sales]
    months = sorted({tuple(map(int, row["transaction_date"].split("-")[::-1])) for row in sales})
    cursor.execute("SELECT flat_id, block_id, floor_area_sqm, resale_price, transaction_date "
                   "FROM flat JOIN resale_transaction ON flat_id = FLAT_flat_id ORDER BY flat_id")
    sale_mismatches = 0
    for (flat_id, block_id, area, price, month_end), source, source_area, source_price in zip(
        cursor, sales, areas, prices, strict=True,
    ):
        sale_mismatches += (
            flat_id <= 0 or block_id != int(source["block_id"]) or
            area != source_area or price != source_price or
            month_end.strftime("%m-%Y") != source["transaction_date"] or
            month_end.day != monthrange(month_end.year, month_end.month)[1]
        )
    cursor.execute("SELECT block_id, postal, latitude, longtitude FROM place")
    place_mismatches = 0
    for block_id, postal, lat, lon in cursor:
        source = places_by_id[block_id]
        place_mismatches += (postal, lat, lon) != (
            source["postal"], Decimal(source["latitude"]), Decimal(source["longitude"]),
        )
    cursor.execute("SELECT station_code, place_block_id FROM stations")
    loaded_station_pairs = set(cursor.fetchall())
    expected_station_pairs = {(row["ALPHANUMERIC_CODE"], int(row["block_id"])) for row in stations}
    cursor.execute("SELECT VERSION(), @@innodb_page_size")
    version, page_size = cursor.fetchone()
    cursor.execute("SELECT NAME, ENABLED FROM performance_schema.setup_consumers "
                   "WHERE NAME IN ('events_statements_current','events_statements_history')")
    performance_consumers = dict(cursor.fetchall())
    counts = {}
    for table in ("agents", "place", "flat", "stations", "resale_transaction", "nearby"):
        cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
        counts[table] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT town) FROM place JOIN flat USING (block_id)")
    imported_hdb_towns = cursor.fetchone()[0]
    cursor.execute("SELECT STATIONS_station_id, COUNT(*), MIN(distance_m), MAX(distance_m) "
                   "FROM nearby GROUP BY STATIONS_station_id")
    station_distances = cursor.fetchall()
    cursor.execute("SELECT COUNT(DISTINCT n.PLACE_block_id), MIN(n.distance_m), MAX(n.distance_m), "
                   "SUM(n.distance_m > 1000), SUM(n.distance_m = 0) FROM nearby n "
                   "WHERE EXISTS (SELECT 1 FROM flat f WHERE f.block_id = n.PLACE_block_id)")
    covered, minimum, maximum, over, zero = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM nearby n "
                   "LEFT JOIN stations s ON n.STATIONS_station_id = s.station_id "
                   "LEFT JOIN place p ON n.PLACE_block_id = p.block_id "
                   "WHERE s.station_id IS NULL OR p.block_id IS NULL")
    orphan_nearby = cursor.fetchone()[0]
    connection.rollback()
    return {
        "mysql_version": version, "innodb_page_size_bytes": page_size,
        "performance_schema_consumers": performance_consumers,
        "sha256": {name: hashlib.sha256((INPUTS / name).read_bytes()).hexdigest()
                   for name in (sale_file, place_file, station_file)},
        "csv": {
            "resale_rows": len(sales), "hdb_location_ids": len(sale_blocks),
            "hdb_ids_min_max": [min(sale_blocks), max(sale_blocks)],
            "distinct_station_codes": len(set(station_codes)), "station_rows": len(stations),
            "station_transport_types": Counter(row["TRANSPORT_TYPE"] for row in stations),
            "distinct_station_names": len({row["STATION_NAME_ENGLISH"] for row in stations}),
            "station_location_ids": len(station_blocks),
            "station_ids_min_max": [min(station_blocks), max(station_blocks)],
            "place_rows": len(places), "distinct_place_ids": len(places_by_id),
            "ids_shared_by_hdb_and_stations": len(sale_blocks & station_blocks),
            "unreferenced_place_ids": len(set(places_by_id) - (sale_blocks | station_blocks)),
            "missing_place_ids": len((sale_blocks | station_blocks) - set(places_by_id)),
            "hdb_towns": sorted({row["town"] for row in sales}),
            "hdb_town_join_mismatches": sum(
                places_by_id[int(row["block_id"])]["town"] != row["town"] for row in sales
            ),
            "transaction_months_min_max": [f"{year}-{month:02}" for year, month in (months[0], months[-1])],
            "distinct_transaction_months": len(months),
            "fractional_floor_areas": sum(area != area.to_integral_value() for area in areas),
            "nonzero_price_cents": sum(price != price.to_integral_value() for price in prices),
            "max_price_scale": max(-price.normalize().as_tuple().exponent for price in prices),
            "max_area_scale": max(-area.normalize().as_tuple().exponent for area in areas),
            "max_place_coordinate_scale": {
                key: max(-Decimal(row[key]).normalize().as_tuple().exponent for row in places)
                for key in ("latitude", "longitude")
            },
            "place_postal_length_histogram": Counter(len(row["postal"]) for row in places),
        },
        "mysql_imported_rows": counts, "mysql_hdb_towns": imported_hdb_towns,
        "sale_precision_or_link_mismatches": sale_mismatches,
        "place_postal_or_coordinate_mismatches": place_mismatches,
        "station_code_place_pair_differences": len(loaded_station_pairs ^ expected_station_pairs),
        "nearby": {
            "station_ids_with_pairs": len(station_distances), "covered_hdb_locations": covered,
            "hdb_distance_min_max_m": [minimum, maximum], "hdb_stored_distance_over_1000_m": over,
            "hdb_zero_m_pairs": zero, "orphan_pairs": orphan_nearby,
        },
    }


def timed_import():
    started = perf_counter()
    import_csv()
    return round(perf_counter() - started, 6)


def main():
    # Generated administrator credentials are confined to these fixtures.
    os.environ["FLAT_RECORD_ADMIN_EMAIL"] = "evidence-admin@example.invalid"
    os.environ["FLAT_RECORD_ADMIN_PASSWORD"] = uuid4().hex
    imports = {"before": [], "final": []}
    with disposable_schema():
        imports["final"].append(timed_import())
        with closing(get_mysql_connection()) as connection:
            nearby = populate_nearby(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT agent_id FROM agents")
                (agent_id,), = cursor.fetchall()
                dataset = dataset_evidence(connection, cursor)
            dataset["nearby_build"] = nearby
            write_json("dataset-verification.json", dataset)
            print("Dataset checked and nearby populated.", flush=True)
            queries = workload(agent_id)
            nearby_query = {"nearby_build_select": queries.pop("nearby_build_select")}
            write_json("mysql-benchmark.json", compare_indexes(connection, queries, warmups=5, samples=30))
            print("Regular MySQL query benchmark finished.", flush=True)
            write_json("mysql-benchmark-nearby-builder.json",
                       compare_indexes(connection, nearby_query, warmups=1, samples=3))
            print("Nearby-builder read benchmark finished.", flush=True)

    for layout in ("before", "before", "final", "final", "before"):
        with disposable_schema():
            if layout == "before":
                with closing(get_mysql_connection()) as connection:
                    _restore_legacy_indexes(connection)
            imports[layout].append(timed_import())
            print(f"Import timing recorded for {layout}.", flush=True)

    write_json("mysql-import-timings.json", {
        "method": "Complete repository CSV import function, excluding DDL and nearby derivation",
        "order": ["final", "before", "before", "final", "final", "before"],
        "samples_s": imports, "median_s": {key: median(values) for key, values in imports.items()},
    })


if __name__ == "__main__":
    main()
