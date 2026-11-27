"""Opt-in MySQL tests. Each test creates and drops its own temporary schema."""

import os
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import mysql.connector
from mysql.connector import errorcode

from app import repository
from app.app_modules.analytics.analytics_defaults import MARKET_OVERVIEW_SQL
from app.app_modules.analytics.analytics_sql import run_query
from app.app_modules.database.database import get_mysql_connection
from app.app_modules.nearby.nearby_function import coverage
from setup.benchmark_mysql import _restore_legacy_indexes, compare_indexes, workload
from setup.migrate_mysql import migrate_schema


@unittest.skipUnless(os.getenv("ESTATE_MYSQL_TEST") == "1", "set ESTATE_MYSQL_TEST=1 for MySQL integration tests")
class MySQLSchemaTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_mysql_connection()
        self.addCleanup(self.connection.close)
        self.schema = "estate_test_" + uuid4().hex
        self.execute(f"CREATE DATABASE `{self.schema}`")
        self.addCleanup(self.drop_schema)
        ddl_path = Path(__file__).resolve().parents[1] / "setup" / "firstver_database.sql"
        ddl = ddl_path.read_text(encoding="utf-8").replace("`estateRecordsDB`", f"`{self.schema}`")
        with self.connection.cursor() as cursor:
            cursor.execute(ddl, map_results=True)
            while cursor.nextset():
                pass
        self.connection.commit()

    def drop_schema(self):
        self.connection.rollback()
        self.execute(f"DROP DATABASE `{self.schema}`")

    def execute(self, sql, parameters=()):
        with self.connection.cursor(buffered=True) as cursor:
            cursor.execute(sql, parameters)
            return cursor.fetchall() if cursor.with_rows else []

    def load_fixture(self, *, area=Decimal("60.30")):
        self.execute(
            "INSERT INTO place VALUES (%s, '1', 'TEST ROAD', '010101', %s, %s, 'TEST'), "
            "(2, '2', 'TEST ROAD', '020202', 1.35, 103.801, 'TEST')",
            (1, Decimal("1.350000000000123"), Decimal("103.800000000000012")),
        )
        self.execute("INSERT INTO stations VALUES (1, 'EW1', 'Test', 'Line', 'Green', 'MRT', 1)")
        self.execute("INSERT INTO flat VALUES (1, '4 ROOM', 'Model', '01 TO 03', %s, 2, 1982, 780)", (area,))
        self.execute(
            "INSERT INTO agents VALUES (1, 'One', 'one@example.com', '0', 'fixture'), "
            "(2, 'Two', 'two@example.com', '0', 'fixture')"
        )
        self.connection.commit()

    def assert_mysql_error(self, number, sql):
        with self.assertRaises(mysql.connector.Error) as context:
            self.execute(sql)
        self.assertEqual(context.exception.errno, number)
        self.connection.rollback()

    def load_batch_fixture(self, transaction_date):
        self.load_fixture()
        self.execute(
            "INSERT INTO flat VALUES "
            "(2, '4 ROOM', 'Model', '01 TO 03', 80.20, 2, 1982, 780), "
            "(3, '4 ROOM', 'Model', '01 TO 03', 80.50, 2, 1982, 780)"
        )
        self.connection.commit()
        repository.create_agent_transaction(self.connection, 1, 1, transaction_date, Decimal("500000.19"))

    def committed_transactions(self):
        # Read from a separate session to verify committed state.
        with closing(get_mysql_connection()) as observer:
            observer.database = self.schema
            with observer.cursor() as cursor:
                cursor.execute(
                    "SELECT FLAT_flat_id, AGENTS_agent_id, transaction_date, resale_price "
                    "FROM resale_transaction ORDER BY FLAT_flat_id, AGENTS_agent_id"
                )
                return cursor.fetchall()

    def test_transaction_batch_commit_is_visible_to_a_new_session(self):
        saved_on = date(2027, 1, 15)
        self.load_batch_fixture(saved_on)
        items: list[repository.PlannedTransaction] = [
            {"flat_id": 2, "transaction_date": saved_on, "resale_price": Decimal("520000.23")},
            {"flat_id": 3, "transaction_date": saved_on, "resale_price": Decimal("550000.47")},
        ]

        self.assertEqual(repository.create_agent_transactions_batch(self.connection, 1, items), 2)
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(self.committed_transactions(), [
            (1, 1, saved_on, Decimal("500000.19")),
            (2, 1, saved_on, Decimal("520000.23")),
            (3, 1, saved_on, Decimal("550000.47")),
        ])

    def test_transaction_batch_rolls_back_a_valid_first_row_when_the_next_row_fails(self):
        saved_on = date(2027, 1, 15)
        self.load_batch_fixture(saved_on)

        for invalid_flat_id, errno in ((1, errorcode.ER_DUP_ENTRY), (99, errorcode.ER_NO_REFERENCED_ROW_2)):
            with self.subTest(errno=errno):
                items: list[repository.PlannedTransaction] = [
                    {"flat_id": 2, "transaction_date": saved_on, "resale_price": Decimal("520000.23")},
                    {"flat_id": invalid_flat_id, "transaction_date": saved_on, "resale_price": Decimal("550000.47")},
                ]
                with self.assertRaises(mysql.connector.IntegrityError) as raised:
                    repository.create_agent_transactions_batch(self.connection, 1, items)

                self.assertEqual(raised.exception.errno, errno)
                self.assertFalse(self.connection.in_transaction)
                self.assertEqual(self.committed_transactions(), [(1, 1, saved_on, Decimal("500000.19"))])

    def test_exact_types_and_owner_key(self):
        self.assertEqual(migrate_schema(self.connection), [])
        self.load_fixture()
        saved_on = date(2025, 1, 31)
        repository.create_agent_transaction(self.connection, 1, 1, saved_on, 650000.19)
        repository.create_agent_transaction(self.connection, 2, 1, saved_on, Decimal("650000.21"))
        self.assertEqual(repository.get_flat(self.connection, 1)["floor_area_sqm"], Decimal("60.30"))
        self.assertEqual(repository.get_agent_transaction(self.connection, 1, 1)["resale_price"], Decimal("650000.19"))
        self.assertEqual(self.execute("SELECT latitude, longtitude FROM place WHERE block_id = 1"), [
            (Decimal("1.350000000000123"), Decimal("103.800000000000012")),
        ])
        results = repository.search_transactions(
            self.connection, {"min_price": Decimal("650000.20"), "max_price": Decimal("650000.21")},
        )
        self.assertEqual([row["resale_price"] for row in results], [Decimal("650000.21")])
        self.connection.rollback()
        frame, truncated = run_query(self.connection, "SELECT AVG(resale_price) AS avg_price FROM resale_transaction")
        self.assertFalse(truncated)
        self.assertAlmostEqual(frame["avg_price"].iloc[0], 650000.2)
        self.assert_mysql_error(1062, "INSERT INTO resale_transaction VALUES (1, 1, '2025-02-28', 650001)")
        self.assert_mysql_error(1452, "INSERT INTO resale_transaction VALUES (99, 1, '2025-02-28', 650001)")
        self.assert_mysql_error(1452, "INSERT INTO resale_transaction VALUES (1, 99, '2025-02-28', 650001)")
        self.assert_mysql_error(1451, "DELETE FROM flat WHERE flat_id = 1")

    def test_numeric_checks_and_real_zero_distance(self):
        self.load_fixture()
        self.assert_mysql_error(3819, "UPDATE flat SET floor_area_sqm = 0")
        self.assert_mysql_error(3819, "UPDATE flat SET remaining_lease_months = -1")
        self.assert_mysql_error(3819, "UPDATE place SET longtitude = -180 WHERE block_id = 1")
        self.assert_mysql_error(3819, "INSERT INTO resale_transaction VALUES (1, 1, '2025-01-31', -1)")
        self.assert_mysql_error(3819, "INSERT INTO nearby VALUES (1, 1, -1)")
        self.execute("INSERT INTO nearby VALUES (1, 1, 0)")
        self.assertEqual(self.execute("SELECT distance_m FROM nearby"), [(0,)])

    def test_market_overview_counts_all_sales_in_the_latest_calendar_month(self):
        self.load_fixture()
        frame, _ = run_query(self.connection, MARKET_OVERVIEW_SQL)
        self.assertEqual(frame["latest_month_sales"].iloc[0], 0)

        self.execute("INSERT INTO flat VALUES (2, '4 ROOM', 'Model', '01 TO 03', 80.20, 2, 1982, 780)")
        self.execute(
            "INSERT INTO resale_transaction VALUES (1, 1, '2025-12-31', 400000), "
            "(1, 2, '2026-01-01', 450000), (2, 1, '2026-01-20', 500000)"
        )
        self.connection.commit()

        frame, truncated = run_query(self.connection, MARKET_OVERVIEW_SQL)
        self.assertFalse(truncated)
        self.assertEqual(frame["transactions"].iloc[0], 3)
        self.assertEqual(frame["latest_month_sales"].iloc[0], 2)

    def test_defaulted_legacy_distances_are_rebuilt(self):
        self.load_fixture()
        self.execute("ALTER TABLE nearby ALTER COLUMN distance_m SET DEFAULT 0")
        self.execute("INSERT INTO nearby (STATIONS_station_id, PLACE_block_id) VALUES (1, 2)")
        self.connection.commit()
        self.assertTrue(migrate_schema(self.connection, apply=True))
        self.assertEqual(migrate_schema(self.connection), [])
        rows = self.execute("SELECT PLACE_block_id, distance_m FROM nearby ORDER BY PLACE_block_id")
        self.assertEqual(rows[0], (1, 0))
        self.assertEqual(rows[1][0], 2)
        self.assertTrue(100 <= rows[1][1] <= 120)

    def test_benchmark_compares_and_restores_index_layouts(self):
        self.load_fixture()
        repository.create_agent_transaction(self.connection, 1, 1, date(2025, 1, 31), Decimal("650000.19"))
        queries = workload(1)
        selected = {name: queries[name] for name in ("top_sales", "rank_towns")}
        report = compare_indexes(self.connection, selected, warmups=0, samples=1)
        self.assertEqual(set(report["stages"]), {"before", "added", "final"})
        self.assertTrue(report["comparison"]["top_sales"]["same_rows"])
        self.assertTrue(report["comparison"]["rank_towns"]["same_rows"])
        final = report["stages"]["final"]["queries"]["top_sales"]
        self.assertEqual(final["rows_returned"], 1)
        self.assertTrue(final["explain"] and final["explain_analyze"])
        self.assertEqual(migrate_schema(self.connection), [])

    def test_market_rankings_preserve_sale_weights_periods_and_interchanges(self):
        self.load_fixture(area=Decimal("100.00"))
        self.execute("INSERT INTO flat VALUES (2, '3 ROOM', 'Model', '01 TO 03', 50.00, 1, 1982, 780)")
        self.execute("INSERT INTO stations VALUES (2, 'NS1', 'Test', 'Line', 'Red', 'MRT', 1)")
        self.execute("INSERT INTO nearby VALUES (1, 1, 150), (1, 2, 500), (2, 2, 499)")
        self.execute(
            "INSERT INTO resale_transaction VALUES (1, 1, '2025-01-31', 400000), "
            "(1, 2, '2024-01-31', 500000), (2, 1, '2024-12-31', 300000)"
        )
        self.connection.commit()

        with patch.multiple(repository, RANKING_MIN_STATION_SALES=1, RANKING_MIN_STREET_SALES=1):
            towns, stations, streets = repository.rank_market(self.connection)
            filtered_towns, filtered_stations, filtered_streets = repository.rank_market(self.connection, "4 ROOM")
            self.assertEqual(repository.rank_market(self.connection, "2 ROOM"), ([], [], []))

        self.assertEqual(towns, [{
            "town": "TEST", "sales": 3, "avg_psm": Decimal("5000"), "avg_price": Decimal("400000"),
            "recent_sales": 2, "recent_psm": Decimal("5000"), "prior_sales": 1, "prior_psm": Decimal("5000"),
        }])
        self.assertEqual(stations, [{
            "station_name": "Test", "station_code": "EW1", "sales": 3, "avg_psm": Decimal("5000"),
        }])
        self.assertEqual(streets, [{"town": "TEST", "road_name": "TEST ROAD", "sales": 3, "avg_price": Decimal("400000")}])
        self.assertEqual(filtered_towns, repository.rank_towns(self.connection, "4 ROOM"))
        self.assertEqual(filtered_stations, repository.rank_stations(self.connection, "4 ROOM", min_sales=1))
        self.assertEqual(filtered_streets, repository.rank_streets(self.connection, "4 ROOM", min_sales=1))
        self.assertEqual(filtered_towns[0]["recent_psm"], Decimal("4000"))
        self.assertEqual(filtered_towns[0]["prior_psm"], Decimal("5000"))

    def test_nearby_listing_filters_stations_and_paginates_by_flat(self):
        self.load_fixture()
        self.execute(
            "INSERT INTO place VALUES "
            "(3, '3', 'TEST ROAD', '030303', 1.35, 103.802, 'TEST'), "
            "(4, '4', 'TEST ROAD', '040404', 1.35, 103.803, 'TEST'), "
            "(5, '5', 'TEST ROAD', '050505', 1.35, 103.804, 'TEST')"
        )
        self.execute(
            "INSERT INTO stations VALUES (2, 'EW2', 'Second', 'Line', 'Green', 'LRT', 1), "
            "(3, 'EW3', 'Third', 'Line', 'Green', 'MRT', 1), "
            "(4, 'EW4', 'Fourth', 'Line', 'Green', 'MRT', 1)"
        )
        self.execute(
            "INSERT INTO flat VALUES "
            "(2, '4 ROOM', 'Model', '01 TO 03', 95.00, 4, 1982, 780), "
            "(3, '4 ROOM', 'Model', '01 TO 03', 95.00, 3, 1982, 780), "
            "(4, '4 ROOM', 'Model', '01 TO 03', 95.00, 2, 1982, 780), "
            "(5, '4 ROOM', 'Model', '01 TO 03', 95.00, 5, 1982, 780)"
        )
        self.execute(
            "INSERT INTO nearby VALUES (1, 2, 250), (2, 2, 25), (3, 2, 50), (4, 2, 350), "
            "(1, 3, 500), (4, 3, 501), (1, 5, 501), (2, 5, 25), (3, 5, 50)"
        )
        self.connection.commit()

        page = repository.list_flats(self.connection, limit=2, offset=2)
        self.assertEqual([(row["flat_id"], row["block_number"]) for row in page], [(3, "3"), (2, "4")])
        address_coverage = coverage(self.connection)
        self.assertEqual((address_coverage["places_missing"], address_coverage["flats_missing"]), (2, 1))

        self.assertEqual(repository.count_nearby_flats(self.connection, {}), 5)
        first_page = repository.search_nearby_flats(self.connection, {}, limit=2)
        self.assertEqual([row["flat_id"] for row in first_page], [1, 2])
        self.assertEqual(first_page[0]["station_count"], 4)
        self.assertEqual(first_page[0]["nearest_m"], 25)
        self.assertEqual(first_page[1]["station_count"], 0)
        self.assertIsNone(first_page[1]["nearest_m"])
        self.assertIsNone(first_page[1]["nearby_stations"])

        filters = {"transport_types": ["MRT"], "stations": ["EW1", "EW2", "EW4"], "max_distance_m": 500}
        self.assertEqual(repository.count_nearby_flats(self.connection, filters), 3)
        rows = repository.search_nearby_flats(self.connection, filters)
        self.assertEqual(
            [(row["flat_id"], row["station_count"], row["nearest_m"], row["nearby_stations"]) for row in rows],
            [
                (1, 2, 250, "EW1 Test (250 m), EW4 Fourth (350 m)"),
                (3, 1, 500, "EW1 Test (500 m)"),
                (4, 2, 250, "EW1 Test (250 m), EW4 Fourth (350 m)"),
            ],
        )
        second_page = repository.search_nearby_flats(self.connection, filters, limit=2, offset=2)
        self.assertEqual(second_page, rows[2:])

        broad_filters = {"transport_types": ["MRT"], "max_distance_m": 500}
        self.assertEqual(repository.count_nearby_flats(self.connection, broad_filters), 4)
        broad_page = repository.search_nearby_flats(self.connection, broad_filters, limit=2, offset=2)
        self.assertEqual(
            [(row["flat_id"], row["station_count"], row["nearest_m"]) for row in broad_page],
            [(4, 3, 50), (5, 1, 50)],
        )

        station_ids = repository.get_flat_station_ids(self.connection, 3)
        self.assertEqual(repository.count_similar_flats(self.connection, 3, station_ids), 3)
        similar = repository.search_similar_flats(self.connection, 3, station_ids, limit=2, offset=1)
        self.assertEqual(
            [(row["flat_id"], row["station_count"], row["shared_stations"], row["nearest_m"]) for row in similar],
            [(4, 4, 2, 25), (5, 3, 1, 25)],
        )
        self.assertEqual(similar[0]["nearby_stations"], first_page[0]["nearby_stations"])

        # Make the filter broad enough to use the ordered scan, with flats sharing a block.
        self.execute(
            "INSERT INTO flat VALUES " + ", ".join(
                f"({flat_id}, '4 ROOM', 'Model', '01 TO 03', 95.00, 2, 1982, 780)"
                for flat_id in range(6, 26)
            )
        )
        count = repository.count_nearby_flats(self.connection, broad_filters)
        self.assertEqual(count, 24)
        ordered_page = repository.search_nearby_flats(
            self.connection, broad_filters, limit=1, offset=2, matching_flat_count=count,
        )
        self.assertEqual(ordered_page, broad_page[:1])

    def test_station_comparables_require_both_flats_within_the_radius(self):
        self.load_fixture(area=Decimal("95.00"))
        self.execute(
            "INSERT INTO place VALUES "
            "(3, '3', 'TEST ROAD', '030303', 1.35, 103.802, 'TEST'), "
            "(4, '4', 'TEST ROAD', '040404', 1.35, 103.803, 'TEST'), "
            "(5, '5', 'TEST ROAD', '050505', 1.35, 103.804, 'TEST')"
        )
        self.execute(
            "INSERT INTO stations VALUES (2, 'EW2', 'Second', 'Line', 'Green', 'MRT', 1), "
            "(3, 'EW3', 'Third', 'Line', 'Green', 'MRT', 1)"
        )
        self.execute(
            "INSERT INTO flat VALUES "
            "(2, '4 ROOM', 'Model', '01 TO 03', 95.00, 3, 1982, 780), "
            "(3, '4 ROOM', 'Model', '01 TO 03', 95.00, 4, 1982, 780), "
            "(4, '4 ROOM', 'Model', '01 TO 03', 95.00, 5, 1982, 780)"
        )
        self.execute(
            "INSERT INTO nearby VALUES (1, 2, 450), (2, 2, 500), (3, 2, 501), "
            "(1, 3, 500), (2, 3, 300), (1, 4, 501), (3, 5, 100)"
        )
        self.execute(
            "INSERT INTO resale_transaction VALUES (1, 1, '2025-01-31', 500000), "
            "(2, 1, '2025-01-31', 510000), (3, 1, '2025-01-31', 520000), "
            "(4, 1, '2025-01-31', 530000)"
        )
        self.connection.commit()

        reference = repository.get_reference_flat_profile(self.connection, 1)
        stations = repository.get_flat_station_ids(self.connection, 1)
        rows, truncated, _ = repository.search_comparable_sales(self.connection, reference, stations, {})
        self.assertFalse(truncated)
        self.assertEqual([row["flat_id"] for row in rows], [2])

        rows, _, _ = repository.search_comparable_sales(
            self.connection, reference, stations, {"catchment": "300 m"},
        )
        self.assertEqual(rows, [])

    def test_legacy_migration_is_repeatable_and_preserves_records(self):
        fresh_view_definition = self.execute("SHOW CREATE VIEW v_resale_detail")[0][1]
        _restore_legacy_indexes(self.connection)
        for ddl in (
            "DROP VIEW v_resale_detail",
            "ALTER TABLE place DROP CHECK chk_place_coordinates, MODIFY latitude FLOAT NOT NULL, MODIFY longtitude FLOAT NOT NULL",
            "ALTER TABLE flat DROP CHECK chk_flat_area, DROP CHECK chk_flat_remaining_lease, MODIFY floor_area_sqm INT NOT NULL",
            "ALTER TABLE resale_transaction DROP CHECK chk_resale_price, MODIFY resale_price FLOAT NOT NULL",
            "ALTER TABLE nearby DROP CHECK chk_nearby_distance, DROP COLUMN distance_m",
        ):
            self.execute(ddl)
        self.load_fixture(area=60)
        self.execute("INSERT INTO resale_transaction VALUES (1, 1, '2025-01-31', 0)")
        self.execute("INSERT INTO nearby VALUES (1, 2)")
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "resale_transaction violate"):
            migrate_schema(self.connection, apply=True)
        self.execute("UPDATE resale_transaction SET resale_price = 650001")
        self.connection.commit()

        operations = migrate_schema(self.connection)
        self.assertIn("ALTER TABLE `nearby` ADD COLUMN `distance_m` INT NULL", operations)
        self.assertTrue(any(operation.startswith("CREATE VIEW `v_resale_detail`") for operation in operations))
        self.assertEqual(self.execute("SHOW COLUMNS FROM nearby LIKE 'distance_m'"), [])
        self.assertEqual(self.execute("SHOW FULL TABLES LIKE 'v_resale_detail'"), [])
        self.connection.rollback()
        self.assertEqual(migrate_schema(self.connection, apply=True), operations)
        self.assertEqual(migrate_schema(self.connection, apply=True), [])
        self.assertEqual(self.execute("SHOW CREATE VIEW v_resale_detail")[0][1], fresh_view_definition)
        self.assertEqual(self.execute("SELECT resale_price FROM resale_transaction"), [(Decimal("650001.00"),)])
        self.assertEqual(self.execute("SELECT flat_id, resale_price, price_per_sqm, town FROM v_resale_detail"), [
            (1, Decimal("650001.00"), Decimal("10833.35"), "TEST"),
        ])
        rows = self.execute("SELECT PLACE_block_id, distance_m FROM nearby ORDER BY PLACE_block_id")
        self.assertEqual(rows[0], (1, 0))
        self.assertEqual(rows[1][0], 2)
        self.assertTrue(100 <= rows[1][1] <= 120)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
