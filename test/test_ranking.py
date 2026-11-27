import unittest
from datetime import date

from app import repository
from app.app_modules.ranking import ranking


def town(name, psm, sales, recent=40, prior=40, recent_psm=None, prior_psm=None):
    return {"town": name, "avg_psm": psm, "sales": sales, "recent_sales": recent,
            "prior_sales": prior, "recent_psm": recent_psm if recent_psm is not None else psm,
            "prior_psm": prior_psm if prior_psm is not None else psm}


TOWNS = [
    town("BISHAN", 9000, 500, recent_psm=9900, prior_psm=9000),
    town("BEDOK", 6000, 1500, recent_psm=6000, prior_psm=6000),
    town("PUNGGOL", 7000, 900, recent_psm=7700, prior_psm=7000),
    town("TINY", 5000, 20, recent=3, prior=3, recent_psm=9999, prior_psm=1000),
]
STATIONS = [
    {"station_name": "Bishan", "station_code": "NS17", "sales": 400, "avg_psm": 9500},
    {"station_name": "Bedok", "station_code": "EW5", "sales": 900, "avg_psm": 6200},
]
STREETS = [{"town": "BISHAN", "road_name": "BISHAN ST 12", "sales": 80, "avg_price": 1100000}]
SALES = [{"block_number": "1", "road_name": "THE PINNACLE", "town": "TANJONG PAGAR",
          "flat_type": "5 ROOM", "transaction_date": date(2024, 3, 31), "resale_price": 1500000}]


def boards():
    return {b["id"]: b for b in ranking.build_boards(TOWNS, STATIONS, STREETS, SALES)}


class BoardTests(unittest.TestCase):
    def test_orders(self):
        b = boards()
        self.assertEqual([r["name"] for r in b["towns_priciest"]["rows"]][:2], ["BISHAN", "PUNGGOL"])
        self.assertEqual(b["towns_affordable"]["rows"][0]["name"], "TINY")
        self.assertEqual(b["towns_busiest"]["rows"][0]["name"], "BEDOK")
        self.assertEqual(b["stations_busiest"]["rows"][0]["name"], "Bedok (EW5)")
        self.assertEqual([r["rank"] for r in b["towns_priciest"]["rows"]], [1, 2, 3, 4])

    def test_rising_needs_enough_sales_in_both_windows(self):
        rows = boards()["towns_rising"]["rows"]
        self.assertNotIn("TINY", [r["name"] for r in rows])
        self.assertEqual(rows[0]["name"], "BISHAN")
        self.assertAlmostEqual(rows[0]["value"], 10.0, places=1)

    def test_prices_are_shown_in_thousands(self):
        self.assertEqual(boards()["streets_priciest"]["rows"][0]["value"], 1100)
        sale = boards()["sales_highest"]["rows"][0]
        self.assertEqual(sale["value"], 1500)
        self.assertEqual(sale["extra"], "5 Room, Mar 2024")

    def test_empty_inputs_give_empty_boards(self):
        built = ranking.build_boards([], [], [], [])
        self.assertTrue(all(b["rows"] == [] for b in built))
        self.assertEqual(ranking.leaders(built), [])

    def test_boards_are_capped(self):
        many = [town(f"T{i}", 1000 + i, 100 + i) for i in range(30)]
        built = {b["id"]: b for b in ranking.build_boards(many, [], [], [])}
        self.assertEqual(len(built["towns_priciest"]["rows"]), ranking.BOARD_SIZE)

    def test_leaders(self):
        names = [item["name"] for item in ranking.leaders(list(boards().values()))]
        self.assertEqual(names, ["BISHAN", "BEDOK", "BISHAN", "Bishan (NS17)"])


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, query, parameters):
        self.log.append((query, parameters))

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self):
        self.log = []

    def cursor(self, **_):
        return FakeCursor(self.log)


class RankingQueryTests(unittest.TestCase):
    def test_flat_type_is_bound_not_interpolated(self):
        evil = "4 ROOM' OR 1=1 --"
        for call, expected in (
            (lambda c: repository.rank_towns(c, evil), (evil,)),
            (lambda c: repository.rank_stations(c, evil), (500, evil, 200)),
            (lambda c: repository.rank_streets(c, evil), (evil, 30, 10)),
            (lambda c: repository.top_sales(c, evil), (evil, 10)),
        ):
            connection = FakeConnection()
            call(connection)
            query, parameters = connection.log[0]
            self.assertNotIn("OR 1=1", query)
            self.assertEqual(parameters, expected)

    def test_no_flat_type_adds_no_condition(self):
        connection = FakeConnection()
        repository.rank_towns(connection, None)
        query, parameters = connection.log[0]
        self.assertNotIn("f.flat_type = %s", query)
        self.assertEqual(parameters, ())


if __name__ == "__main__":
    unittest.main()
