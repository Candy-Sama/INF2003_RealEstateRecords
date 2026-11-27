"""Opt-in MySQL tests. Each test creates and drops its own temporary schema."""

import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import mysql.connector

from app import repository
from app.app_modules.analytics.analytics_sql import run_query
from app.app_modules.database.database import get_mysql_connection
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

    def test_legacy_migration_is_repeatable_and_preserves_records(self):
        _restore_legacy_indexes(self.connection)
        for ddl in (
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
        self.assertEqual(self.execute("SHOW COLUMNS FROM nearby LIKE 'distance_m'"), [])
        self.connection.rollback()
        self.assertEqual(migrate_schema(self.connection, apply=True), operations)
        self.assertEqual(migrate_schema(self.connection, apply=True), [])
        self.assertEqual(self.execute("SELECT resale_price FROM resale_transaction"), [(Decimal("650001.00"),)])
        rows = self.execute("SELECT PLACE_block_id, distance_m FROM nearby ORDER BY PLACE_block_id")
        self.assertEqual(rows[0], (1, 0))
        self.assertEqual(rows[1][0], 2)
        self.assertTrue(100 <= rows[1][1] <= 120)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
