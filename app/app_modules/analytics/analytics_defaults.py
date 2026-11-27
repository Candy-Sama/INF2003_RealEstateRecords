from __future__ import annotations

from typing import Any

_RT_FLAT = (
    "FROM resale_transaction rt "
    "JOIN flat f ON f.flat_id = rt.FLAT_flat_id "
)

MARKET_OVERVIEW_SEED_KEY = "kpi_overview"
_MARKET_OVERVIEW_TOTALS = """SELECT COUNT(*) AS transactions,
       ROUND(AVG(rt.resale_price)) AS avg_price,
       ROUND(AVG(rt.resale_price / f.floor_area_sqm)) AS avg_price_per_sqm,"""

# Keep the exact old SQL so existing seeded cards can be upgraded safely.
LEGACY_MARKET_OVERVIEW_SQL = f"""
{_MARKET_OVERVIEW_TOTALS}
       (SELECT COUNT(*) FROM resale_transaction
         WHERE transaction_date = (SELECT MAX(transaction_date) FROM resale_transaction)
       ) AS latest_month_sales
{_RT_FLAT}
""".strip()

MARKET_OVERVIEW_SQL = f"""
{_MARKET_OVERVIEW_TOTALS}
       (SELECT COUNT(*)
        FROM resale_transaction AS monthly
        CROSS JOIN (SELECT MAX(transaction_date) AS sale_date FROM resale_transaction) AS latest
        WHERE monthly.transaction_date BETWEEN
              DATE_SUB(latest.sale_date, INTERVAL (DAYOFMONTH(latest.sale_date) - 1) DAY)
              AND latest.sale_date
       ) AS latest_month_sales
{_RT_FLAT}
""".strip()

DEFAULT_CARDS: list[dict[str, Any]] = [
    {
        "seed_key": MARKET_OVERVIEW_SEED_KEY,
        "title": "Market overview",
        "description": "Headline numbers across every resale transaction.",
        "display_type": "kpi",
        "width": "full",
        "number_format": "auto",
        "mapping": {},
        "sql": MARKET_OVERVIEW_SQL,
    },
    {
        "seed_key": "price_trend",
        "title": "Average resale price over time",
        "description": "Monthly average price for 3, 4 and 5 room flats.",
        "display_type": "line",
        "width": "full",
        "number_format": "currency",
        "mapping": {"x": "sale_month", "y": "avg_price", "color": "flat_type"},
        "sql": f"""
SELECT DATE_FORMAT(rt.transaction_date, '%Y-%m-01') AS sale_month,
       f.flat_type,
       ROUND(AVG(rt.resale_price)) AS avg_price
{_RT_FLAT}
WHERE f.flat_type IN ('3 ROOM', '4 ROOM', '5 ROOM')
GROUP BY sale_month, f.flat_type
ORDER BY sale_month
""".strip(),
    },
    {
        "seed_key": "price_by_town",
        "title": "Most expensive towns",
        "description": "Top 15 towns by average resale price.",
        "display_type": "bar",
        "width": "half",
        "number_format": "currency",
        "mapping": {"x": "town", "y": "avg_price", "horizontal": True},
        "sql": f"""
SELECT p.town, ROUND(AVG(rt.resale_price)) AS avg_price
{_RT_FLAT}
JOIN place p ON p.block_id = f.block_id
GROUP BY p.town
ORDER BY avg_price DESC
LIMIT 15
""".strip(),
    },
    {
        "seed_key": "lease_vs_price",
        "title": "Price per sqm vs remaining lease",
        "description": "How value per square metre changes as the lease runs down.",
        "display_type": "scatter",
        "width": "half",
        "number_format": "currency",
        "mapping": {"x": "lease_years_left", "y": "avg_price_per_sqm"},
        "sql": f"""
SELECT FLOOR(f.remaining_lease_months / 12) AS lease_years_left,
       ROUND(AVG(rt.resale_price / f.floor_area_sqm)) AS avg_price_per_sqm,
       COUNT(*) AS sales
{_RT_FLAT}
GROUP BY lease_years_left
ORDER BY lease_years_left
""".strip(),
    },
    {
        "seed_key": "mrt_premium",
        "title": "MRT proximity premium",
        "description": (
            "Average price per sqm by distance to the nearest station. "
            "Not adjusted for town or flat type."
        ),
        "display_type": "bar",
        "width": "half",
        "number_format": "currency",
        "mapping": {"x": "distance_band", "y": "avg_price_per_sqm"},
        "sql": f"""
SELECT CASE WHEN nb.nearest_m <= 300 THEN '1) up to 300 m'
            WHEN nb.nearest_m <= 500 THEN '2) 301-500 m'
            WHEN nb.nearest_m <= 800 THEN '3) 501-800 m'
            WHEN nb.nearest_m <= 1000 THEN '4) 801-1000 m'
            ELSE '5) over 1 km' END AS distance_band,
       ROUND(AVG(rt.resale_price / f.floor_area_sqm)) AS avg_price_per_sqm,
       COUNT(*) AS sales
{_RT_FLAT}
JOIN (SELECT n.PLACE_block_id AS block_id, MIN(n.distance_m) AS nearest_m
      FROM nearby n GROUP BY n.PLACE_block_id) nb ON nb.block_id = f.block_id
GROUP BY distance_band
ORDER BY distance_band
""".strip(),
    },
    {
        "seed_key": "storey_premium",
        "title": "Storey range premium",
        "description": "Average price per sqm by storey range, for 3, 4 and 5 room flats.",
        "display_type": "line",
        "width": "half",
        "number_format": "currency",
        "mapping": {"x": "storey_range", "y": "avg_price_per_sqm", "color": "flat_type"},
        "sql": f"""
SELECT f.storey_range, f.flat_type,
       ROUND(AVG(rt.resale_price / f.floor_area_sqm)) AS avg_price_per_sqm
{_RT_FLAT}
WHERE f.flat_type IN ('3 ROOM', '4 ROOM', '5 ROOM')
GROUP BY f.storey_range, f.flat_type
ORDER BY f.storey_range
""".strip(),
    },
    {
        "seed_key": "town_year_heatmap",
        "title": "Transaction volume by town and year",
        "description": "Where and when the market has been busiest.",
        "display_type": "heatmap",
        "width": "full",
        "number_format": "integer",
        "mapping": {"x": "sale_year", "y": "town", "value": "sales"},
        "sql": f"""
SELECT p.town, YEAR(rt.transaction_date) AS sale_year, COUNT(*) AS sales
{_RT_FLAT}
JOIN place p ON p.block_id = f.block_id
GROUP BY p.town, sale_year
""".strip(),
    },
    {
        "seed_key": "price_anomalies",
        "title": "Price anomalies",
        "description": (
            "Sales more than 3 standard deviations from the average for their "
            "town and flat type. Top 100 by z-score."
        ),
        "display_type": "table",
        "width": "full",
        "number_format": "auto",
        "mapping": {},
        "sql": """
SELECT t.transaction_date, t.town, t.flat_type, t.block_number, t.road_name,
       t.floor_area_sqm, t.resale_price,
       ROUND((t.resale_price - t.avg_price) / t.sd_price, 1) AS z_score
FROM (
    SELECT rt.transaction_date, p.town, f.flat_type, p.block_number, p.road_name,
           f.floor_area_sqm, rt.resale_price,
           AVG(rt.resale_price) OVER (PARTITION BY p.town, f.flat_type) AS avg_price,
           STDDEV_SAMP(rt.resale_price) OVER (PARTITION BY p.town, f.flat_type) AS sd_price
    FROM resale_transaction rt
    JOIN flat f ON f.flat_id = rt.FLAT_flat_id
    JOIN place p ON p.block_id = f.block_id
) t
WHERE t.sd_price > 0
  AND ABS(t.resale_price - t.avg_price) > 3 * t.sd_price
ORDER BY ABS(t.resale_price - t.avg_price) / t.sd_price DESC
LIMIT 100
""".strip(),
    },
]
