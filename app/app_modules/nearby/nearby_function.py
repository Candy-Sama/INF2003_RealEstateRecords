"""Populate the `nearby` table (station <-> block distances) with pure SQL.

MySQL's ST_Distance_Sphere does the great-circle distance, so the
whole job is a couple of INSERT ... SELECT statements. No streamlit dependency.

Run standalone (uses the same .env settings as the app):

    python -m app.app_modules.nearby.nearby_function
    python -m app.app_modules.nearby.nearby_function --radius 800

Requires MySQL 8.0+ (window functions are used for the nearest-station fallback).
Note: `place` stores longitude in a column spelled `longtitude`, and MySQL's
POINT() takes (longitude, latitude) -- in that order.
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from app.app_modules.database.database import get_mysql_connection

DEFAULT_RADIUS_M = 1000
MIGRATION_REQUIRED = (
    "The nearby.distance_m column is missing. Run `python -m setup.migrate_mysql --apply`."
)

# Roughly 110 km per degree; deliberately a little generous so the bounding-box
# pre-filter never throws away a pair the exact distance check would keep.
_METRES_PER_DEGREE = 110_000


def has_distance_column(connection: Any) -> bool:
    with connection.cursor(buffered=True) as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'nearby' "
            "AND COLUMN_NAME = 'distance_m'"
        )
        return cursor.fetchone()[0] > 0


def is_ready(connection: Any) -> bool:
    """True when `distance_m` exists and `nearby` has rows."""
    if not has_distance_column(connection):
        return False
    with connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM `nearby`)")
        return bool(cursor.fetchone()[0])


# Every block paired with every station, bounding-box pre-filtered, then exact
# distance. The derived table lets us filter on the computed alias.
_WITHIN_RADIUS_SELECT = """
SELECT d.station_id, d.block_id, d.distance_m
FROM (
    SELECT s.station_id,
           p.block_id,
           ROUND(ST_Distance_Sphere(
               POINT(p.longtitude, p.latitude),
               POINT(sp.longtitude, sp.latitude)
           )) AS distance_m
    FROM `stations` AS s
    JOIN `place` AS sp ON sp.block_id = s.place_block_id
    JOIN `place` AS p
      ON p.latitude   BETWEEN sp.latitude   - %(deg)s AND sp.latitude   + %(deg)s
     AND p.longtitude BETWEEN sp.longtitude - %(deg)s AND sp.longtitude + %(deg)s
    /*MISSING_JOIN*/
) AS d
WHERE d.distance_m <= %(radius)s
"""

# Blocks with nothing inside the radius still get their single closest station.
_NEAREST_FALLBACK_SQL = """
INSERT INTO `nearby` (STATIONS_station_id, PLACE_block_id, distance_m)
SELECT r.station_id, r.block_id, r.distance_m
FROM (
    SELECT s.station_id,
           p.block_id,
           ROUND(ST_Distance_Sphere(
               POINT(p.longtitude, p.latitude),
               POINT(sp.longtitude, sp.latitude)
           )) AS distance_m,
           ROW_NUMBER() OVER (
               PARTITION BY p.block_id
               ORDER BY ST_Distance_Sphere(
                   POINT(p.longtitude, p.latitude),
                   POINT(sp.longtitude, sp.latitude)
               ), s.station_id
           ) AS rn
    FROM `tmp_missing_blocks` AS m
    JOIN `place` AS p ON p.block_id = m.block_id
    CROSS JOIN `stations` AS s
    JOIN `place` AS sp ON sp.block_id = s.place_block_id
) AS r
WHERE r.rn = 1
"""


_MISSING_JOIN = "JOIN `tmp_missing_blocks` AS m ON m.block_id = p.block_id"


def _collect_missing_blocks(cursor: Any) -> None:
    """Temp table of place rows that have no `nearby` row yet."""
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS `tmp_missing_blocks`")
    cursor.execute(
        "CREATE TEMPORARY TABLE `tmp_missing_blocks` (block_id INT NOT NULL PRIMARY KEY) "
        "AS SELECT p.block_id FROM `place` AS p "
        "WHERE NOT EXISTS (SELECT 1 FROM `nearby` AS n WHERE n.PLACE_block_id = p.block_id)"
    )


def coverage(connection: Any) -> dict[str, Any]:
    """How complete `nearby` is. Used by the Address tab's check."""
    has_column = has_distance_column(connection)
    with connection.cursor(buffered=True) as cursor:
        cursor.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM `place`), "
            "(SELECT COUNT(*) FROM `stations`), "
            "(SELECT COUNT(*) FROM `place` p WHERE NOT EXISTS "
            "  (SELECT 1 FROM `nearby` n WHERE n.PLACE_block_id = p.block_id)), "
            "(SELECT COUNT(*) FROM `flat` f WHERE NOT EXISTS "
            "  (SELECT 1 FROM `nearby` n WHERE n.PLACE_block_id = f.block_id))"
        )
        places, stations, places_missing, flats_missing = cursor.fetchone()
    return {
        "has_column": has_column,
        "places_total": int(places),
        "stations_total": int(stations),
        "places_missing": int(places_missing),
        "places_with_nearby": int(places) - int(places_missing),
        "flats_missing": int(flats_missing),
    }


def populate_nearby(
    connection: Any,
    radius_m: int = DEFAULT_RADIUS_M,
    nearest_fallback: bool = True,
    only_missing: bool = False,
) -> dict[str, Any]:
    """Fill `nearby`.

    only_missing=False: wipe and rebuild everything (safe to rerun).
    only_missing=True:  keep existing rows and only add places with no row yet.
    """
    if radius_m <= 0:
        raise ValueError("radius_m must be positive.")
    if not has_distance_column(connection):
        raise ValueError(MIGRATION_REQUIRED)

    started = time.time()
    degrees = radius_m / _METRES_PER_DEGREE

    try:
        with connection.cursor() as cursor:
            if only_missing:
                _collect_missing_blocks(cursor)
                within_sql = _WITHIN_RADIUS_SELECT.replace("/*MISSING_JOIN*/", _MISSING_JOIN)
            else:
                cursor.execute("DELETE FROM `nearby`")
                within_sql = _WITHIN_RADIUS_SELECT.replace("/*MISSING_JOIN*/", "")
            cursor.execute(
                "INSERT INTO `nearby` (STATIONS_station_id, PLACE_block_id, distance_m) " + within_sql,
                {"deg": degrees, "radius": radius_m},
            )
            within_radius = cursor.rowcount

            fallback_rows = 0
            if nearest_fallback:
                _collect_missing_blocks(cursor)
                cursor.execute(_NEAREST_FALLBACK_SQL)
                fallback_rows = cursor.rowcount
            cursor.execute("DROP TEMPORARY TABLE IF EXISTS `tmp_missing_blocks`")
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return {
        "radius_m": radius_m,
        "within_radius_rows": within_radius,
        "fallback_rows": fallback_rows,
        "total_rows": within_radius + fallback_rows,
        "seconds": round(time.time() - started, 2),
    }


def update_missing(connection: Any, radius_m: int = DEFAULT_RADIUS_M) -> dict[str, Any]:
    """Add `nearby` rows only for places that have none (the 'Update addresses' action)."""
    return populate_nearby(connection, radius_m, True, only_missing=True)


def ensure_populated(connection: Any, radius_m: int = DEFAULT_RADIUS_M) -> dict[str, Any] | None:
    """Fill `nearby` automatically if it is empty.

    Called when the Address and Nearby stations tabs open. Returns the populate
    result when it ran, or None when there was nothing to do (already filled,
    or no stations loaded to measure against).
    """
    if is_ready(connection):
        return None
    info = coverage(connection)
    if not info["has_column"]:
        raise ValueError(MIGRATION_REQUIRED)
    if info["stations_total"] == 0:
        return None
    return update_missing(connection, radius_m)


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate the nearby table.")
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M, help="radius in metres")
    parser.add_argument(
        "--no-fallback", action="store_true", help="skip the nearest-station fallback"
    )
    parser.add_argument(
        "--only-missing", action="store_true", help="keep existing rows, fill gaps only"
    )
    args = parser.parse_args()

    connection = get_mysql_connection()
    try:
        result = populate_nearby(
            connection, args.radius, not args.no_fallback, args.only_missing
        )
    finally:
        connection.close()

    print(
        f"nearby rebuilt: {result['within_radius_rows']} rows within {result['radius_m']} m, "
        f"{result['fallback_rows']} fallback rows, {result['seconds']} s."
    )


if __name__ == "__main__":
    main()
