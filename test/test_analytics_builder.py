import unittest

from app.app_modules.analytics import analytics_builder as b
from app.app_modules.analytics import analytics_sql, analytics_store


def field(key, role="group", **extra):
    return {"key": key, "role": role, **extra}


TOP_TOWNS = {
    "mode": "summarise",
    "fields": [field("p.town"), field("rt.resale_price", "avg")],
    "limit": 15,
}


class CompileTests(unittest.TestCase):
    def test_joins_follow_the_chain(self):
        compiled = b.compile_spec(TOP_TOWNS)
        self.assertEqual(compiled.tables, ["rt", "f", "p"])
        self.assertIn("JOIN flat f ON f.flat_id = rt.FLAT_flat_id", compiled.sql)
        self.assertIn("JOIN place p ON p.block_id = f.block_id", compiled.sql)
        self.assertIn("GROUP BY p.town", compiled.sql)
        self.assertIn("ORDER BY avg_resale_price DESC", compiled.sql)  # top-N: biggest first
        self.assertIn("LIMIT 15", compiled.sql)

    def test_tables_between_two_picks_are_pulled_in(self):
        compiled = b.compile_spec({"mode": "summarise", "fields": [
            field("s.station_name"), field("rt.resale_price", "avg")]})
        self.assertEqual(compiled.tables, ["rt", "f", "p", "n", "s"])

    def test_station_location_and_nearby_are_separate_routes(self):
        located = b.compile_spec({"mode": "list", "fields": [
            field("s.station_name", "show"), field("sp.town", "show")]})
        self.assertEqual(located.tables, ["s", "sp"])
        self.assertIn("JOIN place sp ON sp.block_id = s.place_block_id", located.sql)
        around = b.compile_spec({"mode": "list", "fields": [
            field("p.town", "show"), field("s.station_name", "show")]})
        self.assertEqual(around.tables, ["p", "n", "s"])
        self.assertNotIn(" sp ", around.sql)

    def test_nearest_station_rule(self):
        spec = {"mode": "summarise", "fields": [
            field("calc.distance_band"), field("calc.price_per_sqm", "avg")]}
        self.assertTrue(b.compile_spec(spec).nearest_only)
        self.assertIn("ROW_NUMBER()", b.compile_spec(spec).sql)
        off = b.compile_spec({**spec, "nearest_only": False})
        self.assertFalse(off.nearest_only)
        self.assertNotIn("ROW_NUMBER()", off.sql)
        # no flats or transactions involved, so the rule doesn't apply
        stations_only = b.compile_spec({"mode": "list", "fields": [
            field("p.town", "show"), field("s.station_name", "show")]})
        self.assertFalse(stations_only.nearest_only)

    def test_date_bucket_and_filters(self):
        compiled = b.compile_spec({
            "mode": "summarise",
            "fields": [field("rt.transaction_date", "group", bucket="month"),
                       field("rt.resale_price", "avg")],
            "filters": [
                {"key": "f.flat_type", "op": "in", "values": ["3 ROOM", "4 ROOM"]},
                {"key": "rt.transaction_date", "op": "range", "min": "2020-01-01", "max": None},
                {"key": "rt.resale_price", "op": "range", "min": 300000, "max": 600000.5},
            ],
        })
        self.assertIn("DAYOFMONTH", compiled.sql)
        self.assertIn("f.flat_type IN ('3 ROOM', '4 ROOM')", compiled.sql)
        self.assertIn("rt.transaction_date >= '2020-01-01'", compiled.sql)
        self.assertIn("rt.resale_price >= 300000", compiled.sql)
        self.assertIn("rt.resale_price <= 600000.5", compiled.sql)
        self.assertIn("ORDER BY transaction_date_month ASC", compiled.sql)

    def test_number_of_records_alone_counts_transactions(self):
        compiled = b.compile_spec({"mode": "summarise",
                                   "fields": [field("calc.row_count", "count")]})
        self.assertEqual(compiled.tables, ["rt"])
        self.assertIn("COUNT(*) AS row_count", compiled.sql)

    def test_list_mode_has_a_default_limit(self):
        compiled = b.compile_spec({"mode": "list", "fields": [field("p.town", "show")]})
        self.assertIn(f"LIMIT {b.LIST_DEFAULT_LIMIT}", compiled.sql)
        self.assertNotIn("GROUP BY", compiled.sql)

    def test_every_generated_query_passes_the_sql_validator(self):
        specs = [
            TOP_TOWNS,
            {"mode": "summarise", "fields": [field("calc.row_count", "count")]},
            {"mode": "summarise", "fields": [
                field("rt.transaction_date", "group", bucket="quarter"),
                field("f.flat_type"), field("calc.price_per_sqm", "max")]},
            {"mode": "summarise", "fields": [field("sp.town"), field("s.station_code", "count")]},
        ]
        for spec in specs:
            with self.subTest(spec=spec):
                analytics_sql.validate_query(b.build_sql(spec))


class RejectTests(unittest.TestCase):
    def bad(self, **change):
        spec = {**TOP_TOWNS, **change}
        with self.assertRaises(ValueError):
            b.compile_spec(spec)

    def test_unknown_or_dangerous_columns(self):
        self.bad(fields=[field("agents.password_hash")])
        self.bad(fields=[field("p.town; DROP TABLE flat")])
        self.bad(fields=[])
        self.bad(fields="p.town")

    def test_role_must_fit_the_column(self):
        self.bad(fields=[field("p.town", "avg")])
        self.bad(fields=[field("rt.transaction_date", "sum")])

    def test_filter_values_are_validated(self):
        for values in (["x'); DROP TABLE flat; --"], ["a\\b"], [], ["ok", {"$ne": 1}]):
            with self.subTest(values=values):
                self.bad(filters=[{"key": "f.flat_type", "op": "in", "values": values}])
        self.bad(filters=[{"key": "rt.transaction_date", "op": "range",
                           "min": "2020-01-01'; DROP", "max": None}])
        self.bad(filters=[{"key": "rt.resale_price", "op": "range", "min": "1 OR 1=1", "max": None}])
        self.bad(filters=[{"key": "p.road_name", "op": "in", "values": ["X"]}])  # not filterable

    def test_apostrophes_are_escaped_not_rejected(self):
        compiled = b.compile_spec({**TOP_TOWNS, "filters": [
            {"key": "s.station_name", "op": "in", "values": ["King's Road"]}]})
        self.assertIn("'King''s Road'", compiled.sql)
        analytics_sql.validate_query(compiled.sql)

    def test_sort_and_limit(self):
        self.bad(sort={"field": "nope", "dir": "asc"})
        self.bad(sort={"field": "town; DROP", "dir": "asc"})
        self.bad(limit=10**6)
        self.bad(limit=-1)
        ok = b.compile_spec({**TOP_TOWNS, "sort": {"field": "town", "dir": "desc"}})
        self.assertIn("ORDER BY town DESC", ok.sql)

    def test_row_count_needs_summarise(self):
        with self.assertRaises(ValueError):
            b.compile_spec({"mode": "list", "fields": [field("calc.row_count", "count")]})


class DisplayTests(unittest.TestCase):
    def resolve(self, spec, choice="auto"):
        return b.resolve_display(b.compile_spec(spec), spec["mode"], choice)

    def test_auto_picks_by_shape(self):
        self.assertEqual(self.resolve(TOP_TOWNS)[0], "bar")
        kpi = {"mode": "summarise", "fields": [field("rt.resale_price", "avg")]}
        self.assertEqual(self.resolve(kpi)[0], "kpi")
        trend = {"mode": "summarise", "fields": [
            field("rt.transaction_date", "group", bucket="year"), field("rt.resale_price", "avg")]}
        self.assertEqual(self.resolve(trend)[0], "line")
        heat = {"mode": "summarise", "fields": [
            field("p.town"), field("f.flat_type"), field("calc.row_count", "count")]}
        self.assertEqual(self.resolve(heat)[0], "heatmap")
        listing = {"mode": "list", "fields": [field("p.town", "show")]}
        self.assertEqual(self.resolve(listing)[0], "table")

    def test_mapping_puts_time_on_x(self):
        spec = {"mode": "summarise", "fields": [
            field("f.flat_type"), field("rt.transaction_date", "group", bucket="month"),
            field("rt.resale_price", "avg")]}
        display, mapping = self.resolve(spec)
        self.assertEqual(display, "line")
        self.assertEqual(mapping["x"], "transaction_date_month")
        self.assertEqual(mapping["color"], "flat_type")
        self.assertEqual(mapping["y"], "avg_resale_price")

    def test_unsuitable_choices_explain_themselves(self):
        with self.assertRaises(ValueError):
            self.resolve({"mode": "list", "fields": [field("p.town", "show")]}, "bar")
        with self.assertRaises(ValueError):
            self.resolve(TOP_TOWNS, "heatmap")


class StoreIntegrationTests(unittest.TestCase):
    def card(self, **extra):
        return {"title": "Towns", "description": "", "width": "half", "number_format": "auto",
                "display_type": "bar", "mapping": {"x": "town", "y": "avg_resale_price"},
                "builder": TOP_TOWNS, **extra}

    def test_builder_cards_store_the_generated_sql(self):
        cleaned = analytics_store.clean_card(self.card(sql="DROP TABLE flat"))
        self.assertEqual(cleaned["source"], "builder")
        self.assertEqual(cleaned["sql"], b.build_sql(TOP_TOWNS))  # the supplied sql is ignored
        self.assertEqual(cleaned["builder"]["fields"][0]["key"], "p.town")

    def test_bad_builder_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            analytics_store.clean_card(self.card(builder={"mode": "summarise", "fields": [
                field("agents.password_hash")]}))

    def test_plain_sql_cards_are_sql_source(self):
        cleaned = analytics_store.clean_card({
            "title": "x", "sql": "SELECT 1 AS a, 2 AS b", "display_type": "table"})
        self.assertEqual(cleaned["source"], "sql")
        self.assertIsNone(cleaned["builder"])

    def test_describe_spec(self):
        lines = b.describe_spec(analytics_store.clean_card(self.card())["builder"])
        self.assertTrue(any("Average" in line for line in lines))
        self.assertTrue(any("nearest station" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
