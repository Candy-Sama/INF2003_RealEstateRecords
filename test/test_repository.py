import unittest
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from mysql.connector import IntegrityError, errorcode

from app.repository import (
    PlannedTransaction,
    count_flats,
    create_agent_transaction,
    create_agent_transactions_batch,
    delete_agent_transaction,
    list_agent_transactions,
    list_flats,
    search_transactions,
    update_agent_transaction,
    update_flat,
)


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.parameters: tuple[Any, ...] = ()
        self.rowcount = 1
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> None:
        self.query = query
        self.parameters = parameters
        self.calls.append((query, parameters))

    def fetchall(self) -> list[dict[str, Any]]:
        return [{"flat_id": 1}]

    def fetchone(self) -> tuple[int]:
        return (1,)


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.transaction_calls: list[str] = []

    def start_transaction(self) -> None:
        self.transaction_calls.append("start")

    def commit(self) -> None:
        self.transaction_calls.append("commit")

    def rollback(self) -> None:
        self.transaction_calls.append("rollback")

    def cursor(
        self, dictionary: bool = False, buffered: bool = False
    ) -> FakeCursor:
        return self.cursor_instance


class TransactionSearchTests(unittest.TestCase):
    def test_filters_are_bound_as_parameters(self):
        connection = FakeConnection()
        filters = {
            "town": "Tampines",
            "flat_type": "4 ROOM",
            "min_price": 300000,
            "max_price": 600000,
            "start_date": "2020-01-01",
            "end_date": "2024-12-31",
        }

        results = search_transactions(connection, filters)

        self.assertEqual(results, [{"flat_id": 1}])
        self.assertEqual(
            connection.cursor_instance.parameters,
            ("4 ROOM", "Tampines", Decimal("300000"), Decimal("600000"), "2020-01-01", "2024-12-31"),
        )
        self.assertIn("FROM `resale_transaction`", connection.cursor_instance.query)

    def test_decimal_price_bounds_and_stable_date_order(self):
        connection = FakeConnection()
        search_transactions(connection, {"min_price": 650000.19, "max_price": Decimal("700001.01")})
        query, parameters = connection.cursor_instance.calls[0]
        self.assertEqual(parameters, (Decimal("650000.19"), Decimal("700001.01")))
        self.assertIn("ORDER BY rt.transaction_date DESC, rt.FLAT_flat_id DESC, rt.AGENTS_agent_id DESC", query)

    def test_user_values_are_not_interpolated_into_sql(self):
        connection = FakeConnection()
        filters = {"town": "X' OR 1=1 --"}

        search_transactions(connection, filters)

        self.assertNotIn("X' OR 1=1 --", connection.cursor_instance.query)
        self.assertEqual(connection.cursor_instance.parameters, ("X' OR 1=1 --",))


class FlatAndTransactionAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.values = {
            "flat_type": "4 ROOM",
            "flat_model": "NEW GENERATION",
            "storey_range": "07 TO 09",
            "floor_area_sqm": 98,
            "block_id": 2137,
            "lease_commence_date": 1977,
            "remaining_lease_months": 684,
        }

    def test_flat_listing_is_public_and_limited(self):
        connection = FakeConnection()

        list_flats(connection, limit=100)

        self.assertIn("LIMIT %s", connection.cursor_instance.query)
        self.assertNotIn("created_by_agent_id", connection.cursor_instance.query)
        self.assertEqual(connection.cursor_instance.parameters, (100, 0))

    def test_flat_count_supports_pagination_without_loading_records(self):
        connection = FakeConnection()

        self.assertEqual(count_flats(connection), 1)

        self.assertEqual(connection.cursor_instance.query, "SELECT COUNT(*) FROM `flat`")

    def test_flat_update_has_no_owner_dependency(self):
        connection = FakeConnection()

        update_flat(connection, 42, {**self.values, "floor_area_sqm": 60.3})

        query, parameters = connection.cursor_instance.calls[0]
        self.assertIn("WHERE flat_id = %s", query)
        self.assertNotIn("created_by_agent_id", query)
        self.assertEqual(parameters[3], Decimal("60.3"))
        self.assertEqual(parameters[-1], 42)

    def test_own_transaction_listing_is_scoped_to_agent(self):
        connection = FakeConnection()

        list_agent_transactions(connection, agent_id=17)

        self.assertIn("WHERE rt.AGENTS_agent_id = %s", connection.cursor_instance.query)
        self.assertEqual(connection.cursor_instance.parameters, (17, 100))

    def test_create_transaction_uses_session_agent_id(self):
        connection = FakeConnection()

        create_agent_transaction(connection, 17, 42, "2024-01-02", 500000.19)

        self.assertIn(
            "(FLAT_flat_id, AGENTS_agent_id, transaction_date, resale_price)",
            connection.cursor_instance.query,
        )
        self.assertEqual(
            connection.cursor_instance.parameters,
            (42, 17, "2024-01-02", Decimal("500000.19")),
        )

    def test_transaction_update_is_owner_scoped(self):
        connection = FakeConnection()

        updated = update_agent_transaction(
            connection, 17, 42, 42, "2024-01-02", 500000.0
        )

        self.assertTrue(updated)
        query, parameters = connection.cursor_instance.calls[0]
        self.assertIn(
            "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s", query
        )
        self.assertEqual(parameters[-2:], (42, 17))

    def test_transaction_delete_is_owner_scoped(self):
        connection = FakeConnection()

        self.assertTrue(delete_agent_transaction(connection, 17, 42))

        self.assertIn(
            "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
            connection.cursor_instance.query,
        )
        self.assertEqual(connection.cursor_instance.parameters, (42, 17))


class TransactionBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = FakeConnection()
        self.transaction_date = date(2027, 1, 15)
        self.items: list[PlannedTransaction] = [
            {"flat_id": 42, "transaction_date": self.transaction_date, "resale_price": 500000.19},
            {"flat_id": 43, "transaction_date": self.transaction_date, "resale_price": Decimal("600000.21")},
        ]

    def test_all_rows_commit_in_one_transaction(self):
        count = create_agent_transactions_batch(self.connection, 17, self.items)

        self.assertEqual(count, 2)
        self.assertEqual(self.connection.transaction_calls, ["start", "commit"])
        calls = self.connection.cursor_instance.calls
        self.assertEqual([parameters for _, parameters in calls], [
            (42, 17, self.transaction_date, Decimal("500000.19")),
            (43, 17, self.transaction_date, Decimal("600000.21")),
        ])
        for query, _ in calls:
            self.assertIn("VALUES (%s, %s, %s, %s)", query)

    def test_database_error_on_second_insert_rolls_back(self):
        error = IntegrityError("Duplicate agent and flat", errno=errorcode.ER_DUP_ENTRY)
        with patch.object(self.connection.cursor_instance, "execute", side_effect=[None, error]) as insert:
            with self.assertRaises(IntegrityError) as raised:
                create_agent_transactions_batch(self.connection, 17, self.items)

        self.assertIs(raised.exception, error)
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(self.connection.transaction_calls, ["start", "rollback"])

    def test_invalid_second_draft_rolls_back_the_first_insert(self):
        self.items[1]["resale_price"] = Decimal("0.00")

        with self.assertRaisesRegex(ValueError, "Draft 2 needs a positive resale price"):
            create_agent_transactions_batch(self.connection, 17, self.items)

        self.assertEqual(len(self.connection.cursor_instance.calls), 1)
        self.assertEqual(self.connection.transaction_calls, ["start", "rollback"])

    def test_empty_batch_does_not_start_a_transaction(self):
        with self.assertRaisesRegex(ValueError, "Add at least one draft"):
            create_agent_transactions_batch(self.connection, 17, [])

        self.assertEqual(self.connection.transaction_calls, [])
        self.assertEqual(self.connection.cursor_instance.calls, [])


if __name__ == "__main__":
    unittest.main()
