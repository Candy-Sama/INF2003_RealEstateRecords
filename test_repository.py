import unittest
from typing import Any

from repository import search_transactions


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.parameters: tuple[Any, ...] = ()

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[Any, ...]) -> None:
        self.query = query
        self.parameters = parameters

    def fetchall(self) -> list[dict[str, Any]]:
        return [{"flat_id": 1}]


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self, dictionary: bool = False) -> FakeCursor:
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


if __name__ == "__main__":
    unittest.main()
