import unittest
from decimal import Decimal

from pandas import DataFrame

from app.app_modules.analytics import analytics_sql, analytics_store
from app.app_modules.analytics.analytics_defaults import DEFAULT_CARDS
from app.app_modules.analytics.analytics_sql import QueryRejected, validate_query


class ValidatorTests(unittest.TestCase):
    def test_accepts_select_and_with(self):
        self.assertEqual(validate_query("SELECT 1;"), "SELECT 1")
        validate_query("WITH a AS (SELECT 1 AS x) SELECT x FROM a")
        validate_query("(SELECT 1 AS a) UNION (SELECT 2)")
        validate_query("SELECT ';' AS semi, 'agents' AS word, 'a -- b' AS dashes")
        validate_query("SELECT REPLACE(town, 'A', 'B') FROM place WHERE town LIKE '%AN%'")

    def test_rejects_writes_and_admin(self):
        for sql in (
            "DROP TABLE flat", "DELETE FROM flat", "UPDATE flat SET flat_type='x'",
            "INSERT INTO place VALUES (1)", "SHOW TABLES", "SET @a=1",
            "SELECT * FROM flat INTO OUTFILE '/tmp/x'", "SELECT * FROM flat FOR UPDATE",
            "SELECT SLEEP(10)", "SELECT LOAD_FILE('/etc/passwd')", "SELECT USER()",
        ):
            with self.subTest(sql=sql), self.assertRaises(QueryRejected):
                validate_query(sql)

    def test_rejects_multiple_statements_and_comments(self):
        for sql in (
            "SELECT 1; DROP TABLE flat", "SELECT 1; SELECT 2", "SELECT 1 -- x",
            "SELECT 1 # x", "SELECT /*! 1 */ 2", "SELECT 1 /* x */",
        ):
            with self.subTest(sql=sql), self.assertRaises(QueryRejected):
                validate_query(sql)

    def test_rejects_sensitive_objects(self):
        for sql in (
            "SELECT * FROM agents", "select password_hash from agents",
            "SELECT * FROM `agents`", "SELECT * FROM flat, agents",
            "SELECT * FROM estateRecordsDB.agents", "SELECT * FROM information_schema.tables",
            "SELECT * FROM mysql.user", "SELECT @@version", "SELECT @x",
        ):
            with self.subTest(sql=sql), self.assertRaises(QueryRejected):
                validate_query(sql)

    def test_rejects_bad_input(self):
        for sql in ("", "   ", None, 5, "SELECT 'unterminated", "SELECT `a b` FROM flat",
                    "SELECT " + "1," * 3000 + "1"):
            with self.subTest(sql=sql), self.assertRaises(QueryRejected):
                validate_query(sql)


class FakeCursor:
    column_names = ("a", "b")

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, query):
        self.conn.executed.append(query)

    def fetchall(self):
        return [(i, i * 2) for i in range(self.conn.rows)]


class FakeConnection:
    def __init__(self, rows):
        self.rows, self.executed, self.readonly, self.rolled_back = rows, [], None, 0

    def cursor(self):
        return FakeCursor(self)

    def start_transaction(self, readonly=None):
        self.readonly = readonly

    def rollback(self):
        self.rolled_back += 1


class RunQueryTests(unittest.TestCase):
    def test_decimal_values_are_numeric_for_charts(self):
        frame = analytics_sql._normalise(DataFrame({"price": [Decimal("650000.19"), None]}))
        self.assertEqual(frame["price"].dtype.kind, "f")
        self.assertAlmostEqual(frame["price"].iloc[0], 650000.19)

    def test_runs_read_only_wrapped_and_rolled_back(self):
        conn = FakeConnection(3)
        frame, truncated = analytics_sql.run_query(conn, "SELECT 1 AS a, 2 AS b;")
        self.assertTrue(conn.readonly)
        self.assertEqual(conn.rolled_back, 1)
        self.assertIn("max_execution_time", conn.executed[0])
        self.assertIn(f"LIMIT {analytics_sql.MAX_ROWS + 1}", conn.executed[-1])
        self.assertTrue(conn.executed[-1].startswith("SELECT * FROM (SELECT 1 AS a, 2 AS b)"))
        self.assertEqual(len(frame), 3)
        self.assertFalse(truncated)

    def test_truncates_at_row_cap(self):
        conn = FakeConnection(analytics_sql.MAX_ROWS + 1)
        frame, truncated = analytics_sql.run_query(conn, "SELECT 1")
        self.assertTrue(truncated)
        self.assertEqual(len(frame), analytics_sql.MAX_ROWS)

    def test_unsafe_sql_never_reaches_the_database(self):
        conn = FakeConnection(1)
        with self.assertRaises(QueryRejected):
            analytics_sql.run_query(conn, "DROP TABLE flat")
        self.assertEqual(conn.executed, [])


class StoreTests(unittest.TestCase):
    base = {
        "title": "Towns", "description": "d", "sql": "SELECT 1 AS a, 2 AS b",
        "display_type": "bar", "width": "half", "number_format": "auto",
        "mapping": {"x": "a", "y": "b"},
    }

    def test_valid_card(self):
        card = analytics_store.clean_card(self.base)
        self.assertEqual(card["mapping"]["x"], "a")
        self.assertFalse(card["mapping"]["horizontal"])

    def test_rejects_bad_values(self):
        bad = [
            {**self.base, "title": "  "},
            {**self.base, "title": "x" * 81},
            {**self.base, "display_type": "pie"},
            {**self.base, "width": "huge"},
            {**self.base, "mapping": {"x": {"$ne": None}, "y": "b"}},
            {**self.base, "mapping": {"x": "a"}},
            {**self.base, "mapping": {"x": "a", "y": "b", "horizontal": "yes"}},
            {**self.base, "sql": "DROP TABLE flat"},
            {**self.base, "sql": "SELECT * FROM agents"},
        ]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError):
                analytics_store.clean_card(data)

    def test_control_characters_are_stripped(self):
        card = analytics_store.clean_card({**self.base, "title": "Hi\x00 there\x07"})
        self.assertEqual(card["title"], "Hi there")

    def test_escape_markdown_neutralises_links_and_html(self):
        text = analytics_store.escape_markdown("[x](javascript:alert(1)) <img src=x> $a$ :smile:")
        for special in "[]()<>$:":
            for index, char in enumerate(text):
                if char == special:
                    self.assertEqual(text[index - 1], "\\", f"{special!r} is not escaped")

    def test_all_default_cards_are_valid(self):
        keys = set()
        for default in DEFAULT_CARDS:
            analytics_store.clean_card(default)
            keys.add(default["seed_key"])
        self.assertEqual(len(keys), len(DEFAULT_CARDS))
        self.assertEqual(len(DEFAULT_CARDS), 8)


if __name__ == "__main__":
    unittest.main()
