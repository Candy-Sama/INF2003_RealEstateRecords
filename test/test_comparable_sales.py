import unittest
from datetime import date
from decimal import Decimal
from typing import Any

from app.repository import (
    COMPARABLE_ROW_CAP,
    build_comparable_sales_query,
    summarize_comparable_sales,
)


class ComparableSalesSummaryTests(unittest.TestCase):
    def test_empty_rows_returns_nones_and_zero_count(self):
        summary = summarize_comparable_sales([], reference_psm=6500)
        self.assertEqual(summary["sample_count"], 0)
        self.assertFalse(summary["is_small_sample"])
        self.assertIsNone(summary["median_price"])
        self.assertIsNone(summary["median_psm"])
        self.assertIsNone(summary["price_p25"])
        self.assertIsNone(summary["price_p75"])
        self.assertIsNone(summary["diff_vs_median_pct"])

    def test_medians_percentiles_small_sample_and_diff_pct(self):
        rows = [
            {"resale_price": Decimal("500000"), "floor_area_sqm": Decimal("100"), "price_per_sqm": Decimal("5000")},
            {"resale_price": Decimal("600000"), "floor_area_sqm": Decimal("100"), "price_per_sqm": Decimal("6000")},
            {"resale_price": Decimal("700000"), "floor_area_sqm": Decimal("100"), "price_per_sqm": Decimal("7000")},
            {"resale_price": Decimal("800000"), "floor_area_sqm": Decimal("100"), "price_per_sqm": Decimal("8000")},
        ]
        summary = summarize_comparable_sales(rows, reference_psm=Decimal("7150"))

        self.assertEqual(summary["sample_count"], 4)
        self.assertTrue(summary["is_small_sample"])
        self.assertAlmostEqual(summary["median_price"], 650000.0)
        self.assertAlmostEqual(summary["median_psm"], 6500.0)
        self.assertAlmostEqual(summary["price_p25"], 575000.0)
        self.assertAlmostEqual(summary["price_p75"], 725000.0)
        self.assertAlmostEqual(summary["psm_p25"], 5750.0)
        self.assertAlmostEqual(summary["psm_p75"], 7250.0)
        self.assertAlmostEqual(summary["diff_vs_median_pct"], 10.0)


class ComparableSalesQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference: dict[str, Any] = {
            "flat_id": 10,
            "flat_type": "4 ROOM",
            "floor_area_sqm": Decimal("95.00"),
            "block_id": 200,
            "town": "ANG MO KIO",
        }
        self.cutoff = date(2025, 11, 1)

    def test_station_catchment_binds_both_distances_in_sql_order(self):
        query, params = build_comparable_sales_query(
            self.reference,
            station_ids=[3, 7],
            options={"catchment": "500 m", "similar_size": True},
            cutoff_date=self.cutoff,
        )
        self.assertIn("FROM `v_resale_detail` AS v", query)
        self.assertIn(
            "WHERE v.flat_type = %s AND v.flat_id <> %s AND v.transaction_date >= %s "
            "AND EXISTS (SELECT 1 FROM `nearby` AS n_ref JOIN `nearby` AS n_sale "
            "ON n_sale.STATIONS_station_id = n_ref.STATIONS_station_id "
            "WHERE n_ref.PLACE_block_id = %s AND n_ref.distance_m <= %s "
            "AND n_ref.STATIONS_station_id IN (%s, %s) "
            "AND n_sale.PLACE_block_id = v.block_id AND n_sale.distance_m <= %s)",
            query,
        )
        self.assertIn("v.floor_area_sqm BETWEEN %s AND %s", query)
        self.assertEqual(
            params,
            (
                "4 ROOM",
                10,
                self.cutoff,
                200,
                500,
                3,
                7,
                500,
                Decimal("85.0"),
                Decimal("105.0"),
                COMPARABLE_ROW_CAP + 1,
            ),
        )

    def test_same_town_without_similar_size_avoids_string_interpolation(self):
        query, params = build_comparable_sales_query(
            {**self.reference, "town": "BEDOK' OR 1=1 --"},
            station_ids=[],
            options={"catchment": "Same town", "similar_size": False},
            cutoff_date=self.cutoff,
        )
        self.assertNotIn("BEDOK' OR 1=1 --", query)
        self.assertIn("v.town = %s", query)
        self.assertNotIn("v.floor_area_sqm BETWEEN", query)
        self.assertEqual(params, ("4 ROOM", 10, self.cutoff, "BEDOK' OR 1=1 --", COMPARABLE_ROW_CAP + 1))


if __name__ == "__main__":
    unittest.main()
