import unittest
from typing import Any

from repository import (
    count_flats,
    create_agent_transaction,
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

    def commit(self) -> None:
        return None

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
            ("4 ROOM", "Tampines", 300000, 600000, "2020-01-01", "2024-12-31"),
        )
        self.assertIn("FROM `resale_transaction`", connection.cursor_instance.query)

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

        update_flat(connection, 42, self.values)

        query, parameters = connection.cursor_instance.calls[0]
        self.assertIn("WHERE flat_id = %s", query)
        self.assertNotIn("created_by_agent_id", query)
        self.assertEqual(parameters[-1], 42)

    def test_own_transaction_listing_is_scoped_to_agent(self):
        connection = FakeConnection()

        list_agent_transactions(connection, agent_id=17)

        self.assertIn("WHERE rt.AGENTS_agent_id = %s", connection.cursor_instance.query)
        self.assertEqual(connection.cursor_instance.parameters, (17, 100))

    def test_create_transaction_uses_session_agent_id(self):
        connection = FakeConnection()

        create_agent_transaction(connection, 17, 42, "2024-01-02", 500000.0)

        self.assertIn(
            "(FLAT_flat_id, AGENTS_agent_id, transaction_date, resale_price)",
            connection.cursor_instance.query,
        )
        self.assertEqual(
            connection.cursor_instance.parameters,
            (42, 17, "2024-01-02", 500000.0),
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


if __name__ == "__main__":
    unittest.main()
