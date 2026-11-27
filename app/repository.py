import re
import statistics
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict


def find_agent_by_email(connection: Any, email: str) -> dict[str, Any] | None:
    with connection.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(
            "SELECT agent_id, name, email, phone_number, password_hash "
            "FROM `agents` WHERE email = %s LIMIT 1",
            (email,),
        )
        return cursor.fetchone()


def create_agent(
    connection: Any,
    name: str,
    email: str,
    phone_number: str,
    password_hash: str,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO `agents` (name, email, phone_number, password_hash) "
            "VALUES (%s, %s, %s, %s)",
            (name, email, phone_number, password_hash),
        )
        agent_id = int(cursor.lastrowid)
    connection.commit()
    return agent_id


def list_places(connection: Any) -> list[dict[str, Any]]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT block_id, block_number, road_name, town "
            "FROM `place` ORDER BY town, road_name, block_number"
        )
        return cursor.fetchall()


def count_flats(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM `flat`")
        return int(cursor.fetchone()[0])


def list_flats(
    connection: Any, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT f.flat_id, f.flat_type, f.flat_model, f.storey_range, "
            "f.floor_area_sqm, f.block_id, f.lease_commence_date, "
            "f.remaining_lease_months, p.block_number, p.road_name, p.town "
            "FROM `flat` AS f JOIN `place` AS p ON p.block_id = f.block_id "
            "ORDER BY f.flat_id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        return cursor.fetchall()


def get_flat(connection: Any, flat_id: int) -> dict[str, Any] | None:
    with connection.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(
            "SELECT f.flat_id, f.flat_type, f.flat_model, f.storey_range, "
            "f.floor_area_sqm, f.block_id, f.lease_commence_date, "
            "f.remaining_lease_months, p.block_number, p.road_name, p.town "
            "FROM `flat` AS f JOIN `place` AS p ON p.block_id = f.block_id "
            "WHERE f.flat_id = %s",
            (flat_id,),
        )
        return cursor.fetchone()


def list_flat_types(connection: Any) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT flat_type FROM `flat` ORDER BY flat_type")
        return [row[0] for row in cursor.fetchall()]


def list_towns(connection: Any) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT town FROM `place` ORDER BY town")
        return [row[0] for row in cursor.fetchall()]


def create_flat(connection: Any, values: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO `flat` "
            "(flat_type, flat_model, storey_range, floor_area_sqm, block_id, "
            "lease_commence_date, remaining_lease_months) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                values["flat_type"],
                values["flat_model"],
                values["storey_range"],
                Decimal(str(values["floor_area_sqm"])),
                values["block_id"],
                values["lease_commence_date"],
                values["remaining_lease_months"],
            ),
        )
    connection.commit()


def update_flat(connection: Any, flat_id: int, values: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE `flat` SET flat_type = %s, flat_model = %s, "
            "storey_range = %s, floor_area_sqm = %s, block_id = %s, "
            "lease_commence_date = %s, remaining_lease_months = %s "
            "WHERE flat_id = %s",
            (
                values["flat_type"],
                values["flat_model"],
                values["storey_range"],
                Decimal(str(values["floor_area_sqm"])),
                values["block_id"],
                values["lease_commence_date"],
                values["remaining_lease_months"],
                flat_id,
            ),
        )
    connection.commit()


def list_agent_transactions(
    connection: Any, agent_id: int, limit: int = 100
) -> list[dict[str, Any]]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT rt.FLAT_flat_id AS flat_id, rt.transaction_date, "
            "rt.resale_price, f.flat_type, f.flat_model, p.block_number, "
            "p.road_name, p.town "
            "FROM `resale_transaction` AS rt "
            "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
            "JOIN `place` AS p ON p.block_id = f.block_id "
            "WHERE rt.AGENTS_agent_id = %s "
            "ORDER BY rt.transaction_date DESC, rt.FLAT_flat_id DESC LIMIT %s",
            (agent_id, limit),
        )
        return cursor.fetchall()


def get_agent_transaction(
    connection: Any, agent_id: int, flat_id: int
) -> dict[str, Any] | None:
    with connection.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(
            "SELECT rt.FLAT_flat_id AS flat_id, rt.transaction_date, "
            "rt.resale_price, f.flat_type, f.flat_model, p.block_number, "
            "p.road_name, p.town "
            "FROM `resale_transaction` AS rt "
            "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
            "JOIN `place` AS p ON p.block_id = f.block_id "
            "WHERE rt.AGENTS_agent_id = %s AND rt.FLAT_flat_id = %s",
            (agent_id, flat_id),
        )
        return cursor.fetchone()


class PlannedTransaction(TypedDict):
    flat_id: int
    transaction_date: date
    resale_price: int | float | Decimal


_INSERT_AGENT_TRANSACTION = (
    "INSERT INTO `resale_transaction` "
    "(FLAT_flat_id, AGENTS_agent_id, transaction_date, resale_price) "
    "VALUES (%s, %s, %s, %s)"
)


def create_agent_transaction(
    connection: Any,
    agent_id: int,
    flat_id: int,
    transaction_date: Any,
    resale_price: int | float | Decimal,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            _INSERT_AGENT_TRANSACTION,
            (flat_id, agent_id, transaction_date, Decimal(str(resale_price))),
        )
    connection.commit()


def _draft_insert_parameters(
    draft: PlannedTransaction, agent_id: int, number: int
) -> tuple[int, int, date, Decimal]:
    flat_id = draft.get("flat_id")
    if type(flat_id) is not int or not 1 <= flat_id <= 2_147_483_647:
        raise ValueError(f"Draft {number} needs a valid positive flat ID.")

    transaction_date = draft.get("transaction_date")
    if type(transaction_date) is not date or transaction_date.year < 1000:
        raise ValueError(f"Draft {number} needs a valid transaction date.")

    price_error = (
        f"Draft {number} needs a positive resale price up to S$9,999,999,999.99 "
        "with at most two decimal places."
    )
    try:
        price = Decimal(str(draft.get("resale_price")))
    except InvalidOperation as error:
        raise ValueError(price_error) from error
    if (
        not price.is_finite()
        or not Decimal("0.01") <= price <= Decimal("9999999999.99")
        or price != price.quantize(Decimal("0.01"))
    ):
        raise ValueError(price_error)

    return flat_id, agent_id, transaction_date, price


def create_agent_transactions_batch(
    connection: Any, agent_id: int, items: Sequence[PlannedTransaction]
) -> int:
    """Insert the entire batch on a dedicated connection and return the committed count."""
    if not items:
        raise ValueError("Add at least one draft before committing.")

    connection.start_transaction()
    try:
        with connection.cursor() as cursor:
            for number, draft in enumerate(items, start=1):
                parameters = _draft_insert_parameters(draft, agent_id, number)
                cursor.execute(_INSERT_AGENT_TRANSACTION, parameters)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return len(items)


def update_agent_transaction(
    connection: Any,
    agent_id: int,
    original_flat_id: int,
    flat_id: int,
    transaction_date: Any,
    resale_price: int | float | Decimal,
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE `resale_transaction` "
            "SET FLAT_flat_id = %s, transaction_date = %s, resale_price = %s "
            "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
            (flat_id, transaction_date, Decimal(str(resale_price)), original_flat_id, agent_id),
        )
        updated = cursor.rowcount > 0
        if not updated:
            cursor.execute(
                "SELECT FLAT_flat_id FROM `resale_transaction` "
                "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
                (original_flat_id, agent_id),
            )
            updated = cursor.fetchone() is not None
    connection.commit()
    return updated


def delete_agent_transaction(
    connection: Any, agent_id: int, flat_id: int
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM `resale_transaction` "
            "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
            (flat_id, agent_id),
        )
        deleted = cursor.rowcount > 0
    connection.commit()
    return deleted


def search_transactions(connection: Any, filters: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    parameters: list[Any] = []
    for key, column in (
        ("flat_type", "f.flat_type"),
        ("town", "p.town"),
    ):
        value = filters.get(key)
        if value:
            conditions.append(f"{column} = %s")
            parameters.append(value)

    for key, operator in (("min_price", ">="), ("max_price", "<=")):
        value = filters.get(key)
        if value is not None:
            conditions.append(f"rt.resale_price {operator} %s")
            parameters.append(Decimal(str(value)))

    for key, operator in (("start_date", ">="), ("end_date", "<=")):
        value = filters.get(key)
        if value:
            conditions.append(f"rt.transaction_date {operator} %s")
            parameters.append(value)

    query = (
        "SELECT rt.transaction_date, rt.resale_price, "
        "f.flat_id, f.flat_type, f.flat_model, f.storey_range, "
        "f.floor_area_sqm, f.remaining_lease_months, "
        "p.block_number, p.road_name, p.town, p.postal "
        "FROM `resale_transaction` AS rt "
        "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
        "JOIN `place` AS p ON p.block_id = f.block_id "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY rt.transaction_date DESC, rt.FLAT_flat_id DESC, rt.AGENTS_agent_id DESC LIMIT 1000"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, tuple(parameters))
        return cursor.fetchall()


def list_flat_options(connection: Any) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    with connection.cursor(buffered=True) as cursor:
        # Column names are fixed constants, never user input.
        for column in ("flat_type", "flat_model", "storey_range"):
            cursor.execute(
                f"SELECT DISTINCT `{column}` FROM `flat` ORDER BY `{column}`"
            )
            options[column] = [row[0] for row in cursor.fetchall()]
    return options


# address & nearby
_FLAT_COLUMNS = (
    "f.flat_id, f.flat_type, f.storey_range, p.town, p.block_number, p.road_name"
)
_STATION_LABEL = (
    "GROUP_CONCAT(CONCAT(s.station_code, ' ', s.station_name, ' (', n.distance_m, ' m)') "
    "ORDER BY n.distance_m, s.station_code SEPARATOR ', ')"
)


def list_address_stations(connection: Any) -> list[dict[str, Any]]:
    """Every row of `place`, with its nearby stations (blank if it has none)."""
    query = (
        "SELECT p.block_id, p.block_number, p.road_name, p.postal, p.town, "
        "COUNT(s.station_id) AS station_count, MIN(n.distance_m) AS nearest_m, "
        f"{_STATION_LABEL} AS nearby_stations "
        "FROM `place` AS p "
        "LEFT JOIN `nearby` AS n ON n.PLACE_block_id = p.block_id "
        "LEFT JOIN `stations` AS s ON s.station_id = n.STATIONS_station_id "
        "GROUP BY p.block_id, p.block_number, p.road_name, p.postal, p.town "
        "ORDER BY p.town, p.road_name, p.block_number"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def list_nearby_filter_options(connection: Any) -> dict[str, Any]:
    """Distinct station values used by the Nearby stations filter pills."""
    queries = {
        "transport_type": "SELECT DISTINCT transport_type FROM `stations` ORDER BY transport_type",
        "line_name": "SELECT DISTINCT line_name FROM `stations` ORDER BY line_name",
    }
    options: dict[str, Any] = {}
    with connection.cursor(buffered=True) as cursor:
        for key, query in queries.items():
            cursor.execute(query)
            options[key] = [row[0] for row in cursor.fetchall()]
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT station_code, station_name, line_name, transport_type FROM `stations`"
        )
        stations = cursor.fetchall()

    def natural(row: dict[str, Any]) -> tuple[str, int]:
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", row["station_code"])
        return (match.group(1), int(match.group(2))) if match else (row["station_code"], 0)

    options["stations"] = sorted(stations, key=natural)  # NS1, NS2 ... NS10
    return options


def _has_station_filter(filters: dict[str, Any]) -> bool:
    return bool(
        filters.get("transport_types")
        or filters.get("lines")
        or filters.get("stations")
        or filters.get("max_distance_m") is not None
    )


def _nearby_where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    conditions = ["1 = 1"]
    parameters: list[Any] = []
    # Column names are fixed constants; only the values are user input.
    for key, column in (
        ("flat_ids", "f.flat_id"),
        ("transport_types", "s.transport_type"),
        ("lines", "s.line_name"),
        ("stations", "s.station_code"),
    ):
        values = filters.get(key) or []
        if values:
            conditions.append(f"{column} IN ({', '.join(['%s'] * len(values))})")
            parameters.extend(values)
    if filters.get("max_distance_m") is not None:
        conditions.append("n.distance_m <= %s")
        parameters.append(int(filters["max_distance_m"]))
    return " AND ".join(conditions), parameters


def _nearby_joins(filters: dict[str, Any]) -> str:
    # With no station filter every flat is kept, even one with no nearby station.
    join = "JOIN" if _has_station_filter(filters) else "LEFT JOIN"
    return (
        "FROM `flat` AS f JOIN `place` AS p ON p.block_id = f.block_id "
        f"{join} `nearby` AS n ON n.PLACE_block_id = p.block_id "
        f"{join} `stations` AS s ON s.station_id = n.STATIONS_station_id "
    )


def count_nearby_flats(connection: Any, filters: dict[str, Any]) -> int:
    where, parameters = _nearby_where(filters)
    if _has_station_filter(filters):
        query = f"SELECT COUNT(DISTINCT f.flat_id) {_nearby_joins(filters)} WHERE {where}"
    else:
        query = (
            "SELECT COUNT(*) FROM `flat` AS f "
            f"JOIN `place` AS p ON p.block_id = f.block_id WHERE {where}"
        )
    with connection.cursor(buffered=True) as cursor:
        cursor.execute(query, tuple(parameters))
        return int(cursor.fetchone()[0])


def search_nearby_flats(
    connection: Any, filters: dict[str, Any], limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """One row per flat with its nearby stations collapsed into one column.

    Station filters (type, line, distance) also limit which stations are listed.
    """
    where, parameters = _nearby_where(filters)
    query = (
        f"SELECT {_FLAT_COLUMNS}, COUNT(s.station_id) AS station_count, "
        f"MIN(n.distance_m) AS nearest_m, {_STATION_LABEL} AS nearby_stations "
        f"{_nearby_joins(filters)} WHERE {where} "
        f"GROUP BY {_FLAT_COLUMNS} ORDER BY f.flat_id LIMIT %s OFFSET %s"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, tuple(parameters) + (int(limit), int(offset)))
        return cursor.fetchall()


def get_flat_station_ids(connection: Any, flat_id: int) -> list[int]:
    with connection.cursor(buffered=True) as cursor:
        cursor.execute(
            "SELECT DISTINCT n.STATIONS_station_id FROM `flat` AS f "
            "JOIN `nearby` AS n ON n.PLACE_block_id = f.block_id "
            "WHERE f.flat_id = %s",
            (flat_id,),
        )
        return [row[0] for row in cursor.fetchall()]


def count_similar_flats(connection: Any, flat_id: int, station_ids: list[int]) -> int:
    """Other flats whose block shares at least one nearby station."""
    if not station_ids:
        return 0
    marks = ", ".join(["%s"] * len(station_ids))
    with connection.cursor(buffered=True) as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM `flat` AS f WHERE f.flat_id <> %s AND f.block_id IN "
            f"(SELECT n.PLACE_block_id FROM `nearby` AS n WHERE n.STATIONS_station_id IN ({marks}))",
            (flat_id, *station_ids),
        )
        return int(cursor.fetchone()[0])


def search_similar_flats(
    connection: Any,
    flat_id: int,
    station_ids: list[int],
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Flats sharing nearby stations with `flat_id`, most shared stations first."""
    if not station_ids:
        return []
    marks = ", ".join(["%s"] * len(station_ids))
    query = (
        f"SELECT {_FLAT_COLUMNS}, COUNT(s.station_id) AS station_count, "
        f"CAST(SUM(n.STATIONS_station_id IN ({marks})) AS UNSIGNED) AS shared_stations, "
        f"MIN(n.distance_m) AS nearest_m, {_STATION_LABEL} AS nearby_stations "
        "FROM `flat` AS f JOIN `place` AS p ON p.block_id = f.block_id "
        "JOIN `nearby` AS n ON n.PLACE_block_id = p.block_id "
        "JOIN `stations` AS s ON s.station_id = n.STATIONS_station_id "
        "WHERE f.flat_id <> %s AND f.block_id IN "
        f"(SELECT n2.PLACE_block_id FROM `nearby` AS n2 WHERE n2.STATIONS_station_id IN ({marks})) "
        f"GROUP BY {_FLAT_COLUMNS} "
        "ORDER BY shared_stations DESC, nearest_m, f.flat_id LIMIT %s OFFSET %s"
    )
    parameters = (*station_ids, flat_id, *station_ids, int(limit), int(offset))
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, parameters)
        return cursor.fetchall()

#rankings
RANKING_RADIUS_M = 500
RANKING_MIN_STATION_SALES = 200
RANKING_MIN_STREET_SALES = 30
RANKING_BOARD_SIZE = 10
# Use the same precision per sale in streaming and temporary-table aggregations.
_PRICE_PER_SQM = "CAST(rt.resale_price / f.floor_area_sqm AS DECIMAL(20,6))"


def _flat_type_filter(flat_type: str | None) -> tuple[str, list[Any]]:
    return (" AND f.flat_type = %s", [flat_type]) if flat_type else ("", [])


def latest_transaction_date(connection: Any):
    with connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT MAX(transaction_date) FROM `resale_transaction`")
        row = cursor.fetchone()
        return row[0] if row else None


def rank_towns(connection: Any, flat_type: str | None = None) -> list[dict[str, Any]]:
    """Per-town averages plus the latest 12 months against the 12 before.

    Windows are measured back from the most recent transaction in the data.
    """
    extra, parameters = _flat_type_filter(flat_type)
    recent = "rt.transaction_date > DATE_SUB(m.latest, INTERVAL 12 MONTH)"
    prior = (
        "rt.transaction_date > DATE_SUB(m.latest, INTERVAL 24 MONTH) "
        "AND rt.transaction_date <= DATE_SUB(m.latest, INTERVAL 12 MONTH)"
    )
    query = (
        "SELECT p.town, COUNT(*) AS sales, "
        f"AVG({_PRICE_PER_SQM}) AS avg_psm, "
        "AVG(rt.resale_price) AS avg_price, "
        f"SUM(CASE WHEN {recent} THEN 1 ELSE 0 END) AS recent_sales, "
        f"AVG(CASE WHEN {recent} THEN {_PRICE_PER_SQM} END) AS recent_psm, "
        f"SUM(CASE WHEN {prior} THEN 1 ELSE 0 END) AS prior_sales, "
        f"AVG(CASE WHEN {prior} THEN {_PRICE_PER_SQM} END) AS prior_psm "
        "FROM `resale_transaction` AS rt "
        "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
        "JOIN `place` AS p ON p.block_id = f.block_id "
        "CROSS JOIN (SELECT MAX(transaction_date) AS latest FROM `resale_transaction`) AS m "
        f"WHERE 1 = 1{extra} GROUP BY p.town"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, tuple(parameters))
        return cursor.fetchall()


def rank_stations(
    connection: Any,
    flat_type: str | None = None,
    radius_m: int = RANKING_RADIUS_M,
    min_sales: int = RANKING_MIN_STATION_SALES,
) -> list[dict[str, Any]]:
    """Sales within `radius_m` of each station. Interchanges are merged by name."""
    extra, parameters = _flat_type_filter(flat_type)
    query = (
        "SELECT ns.station_name, MIN(ns.station_code) AS station_code, COUNT(*) AS sales, "
        f"AVG({_PRICE_PER_SQM}) AS avg_psm "
        "FROM `resale_transaction` AS rt "
        "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
        "JOIN (SELECT n.PLACE_block_id AS block_id, s.station_name, "
        "MIN(s.station_code) AS station_code "
        "FROM `nearby` AS n JOIN `stations` AS s ON s.station_id = n.STATIONS_station_id "
        "WHERE n.distance_m <= %s GROUP BY n.PLACE_block_id, s.station_name) AS ns "
        "ON ns.block_id = f.block_id "
        f"WHERE 1 = 1{extra} "
        "GROUP BY ns.station_name HAVING COUNT(*) >= %s"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, (int(radius_m), *parameters, int(min_sales)))
        return cursor.fetchall()


def rank_streets(
    connection: Any,
    flat_type: str | None = None,
    min_sales: int = RANKING_MIN_STREET_SALES,
    limit: int = RANKING_BOARD_SIZE,
) -> list[dict[str, Any]]:
    extra, parameters = _flat_type_filter(flat_type)
    query = (
        "SELECT p.town, p.road_name, COUNT(*) AS sales, AVG(rt.resale_price) AS avg_price "
        "FROM `resale_transaction` AS rt "
        "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
        "JOIN `place` AS p ON p.block_id = f.block_id "
        f"WHERE 1 = 1{extra} GROUP BY p.town, p.road_name "
        "HAVING COUNT(*) >= %s ORDER BY avg_price DESC LIMIT %s"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, (*parameters, int(min_sales), int(limit)))
        return cursor.fetchall()


def top_sales(
    connection: Any, flat_type: str | None = None, limit: int = RANKING_BOARD_SIZE
) -> list[dict[str, Any]]:
    extra, parameters = _flat_type_filter(flat_type)
    query = (
        "SELECT rt.transaction_date, p.town, p.block_number, p.road_name, "
        "f.flat_type, f.floor_area_sqm, rt.resale_price "
        "FROM `resale_transaction` AS rt "
        "JOIN `flat` AS f ON f.flat_id = rt.FLAT_flat_id "
        "JOIN `place` AS p ON p.block_id = f.block_id "
        f"WHERE 1 = 1{extra} "
        "ORDER BY rt.resale_price DESC, rt.FLAT_flat_id DESC, rt.AGENTS_agent_id DESC LIMIT %s"
    )
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, (*parameters, int(limit)))
        return cursor.fetchall()

COMPARABLE_ROW_CAP = 2000
SMALL_SAMPLE_THRESHOLD = 5
SIMILAR_SIZE_TOLERANCE_SQM = Decimal("10.0")
CATCHMENT_RADII_M: dict[str, int] = {
    "300 m": 300,
    "500 m": 500,
    "1,000 m": 1000,
}

def get_reference_flat_profile(connection: Any, flat_id: int) -> dict[str, Any] | None:
    """Return reference flat details, address, and price per sqm if a sale exists."""
    with connection.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(
            "SELECT f.flat_id, f.flat_type, f.flat_model, f.storey_range, "
            "f.floor_area_sqm, f.block_id, f.lease_commence_date, "
            "f.remaining_lease_months, p.block_number, p.road_name, p.postal, p.town, "
            "rt.transaction_date, rt.resale_price, "
            "CASE WHEN f.floor_area_sqm > 0 AND rt.resale_price IS NOT NULL "
            "THEN ROUND(rt.resale_price / f.floor_area_sqm, 2) ELSE NULL END AS price_per_sqm "
            "FROM `flat` AS f "
            "JOIN `place` AS p ON p.block_id = f.block_id "
            "LEFT JOIN `resale_transaction` AS rt ON rt.FLAT_flat_id = f.flat_id "
            "WHERE f.flat_id = %s "
            "ORDER BY rt.transaction_date DESC LIMIT 1",
            (flat_id,),
        )
        return cursor.fetchone()


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * (pct / 100.0)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    frac = pos - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * frac)


def summarize_comparable_sales(
    rows: list[dict[str, Any]],
    reference_psm: float | Decimal | None = None,
) -> dict[str, Any]:
    """Compute sample count, medians, 25th-75th percentiles, and ref % diff."""
    prices: list[float] = []
    psms: list[float] = []
    for row in rows:
        price_val = row.get("resale_price")
        area_val = row.get("floor_area_sqm")
        psm_val = row.get("price_per_sqm")
        if price_val is not None:
            prices.append(float(price_val))
        if psm_val is not None:
            psms.append(float(psm_val))
        elif price_val is not None and area_val is not None and float(area_val) > 0:
            psms.append(float(price_val) / float(area_val))

    sample_count = len(rows)
    median_price = float(statistics.median(prices)) if prices else None
    median_psm = float(statistics.median(psms)) if psms else None
    price_p25 = _percentile(prices, 25)
    price_p75 = _percentile(prices, 75)
    psm_p25 = _percentile(psms, 25)
    psm_p75 = _percentile(psms, 75)

    ref_psm_float = float(reference_psm) if reference_psm is not None else None
    diff_pct = None
    if ref_psm_float is not None and median_psm is not None and median_psm > 0:
        diff_pct = ((ref_psm_float - median_psm) / median_psm) * 100.0

    return {
        "sample_count": sample_count,
        "is_small_sample": 0 < sample_count < SMALL_SAMPLE_THRESHOLD,
        "median_price": median_price,
        "median_psm": median_psm,
        "price_p25": price_p25,
        "price_p75": price_p75,
        "psm_p25": psm_p25,
        "psm_p75": psm_p75,
        "reference_psm": ref_psm_float,
        "diff_vs_median_pct": diff_pct,
    }


def _period_cutoff_date(latest_sale_date: date | None, months: int) -> date:
    anchor = latest_sale_date or date.today()
    return anchor - timedelta(days=int(months) * 30)


def build_comparable_sales_query(
    reference: dict[str, Any],
    station_ids: list[int],
    options: dict[str, Any],
    cutoff_date: date,
    row_cap: int = COMPARABLE_ROW_CAP,
) -> tuple[str, tuple[Any, ...]]:
    """Build parameterized SQL against `v_resale_detail` for comparable sales."""
    catchment = options.get("catchment", "500 m")
    similar_size = bool(options.get("similar_size", True))
    ref_flat_id = int(reference["flat_id"])
    ref_flat_type = reference["flat_type"]

    conditions = ["v.flat_type = %s", "v.flat_id <> %s", "v.transaction_date >= %s"]
    parameters: list[Any] = [ref_flat_type, ref_flat_id, cutoff_date]
    nearest_expr = (
        "(SELECT MIN(n_min.distance_m) FROM `nearby` AS n_min "
        "WHERE n_min.PLACE_block_id = v.block_id)"
    )

    if catchment == "Same block":
        conditions.append("v.block_id = %s")
        parameters.append(int(reference["block_id"]))
    elif catchment == "Same town":
        conditions.append("v.town = %s")
        parameters.append(reference["town"])
    elif station_ids:
        radius_m = CATCHMENT_RADII_M.get(catchment, 500)
        marks = ", ".join(["%s"] * len(station_ids))
        conditions.append(
            "EXISTS (SELECT 1 FROM `nearby` AS n_ref "
            "JOIN `nearby` AS n_sale "
            "ON n_sale.STATIONS_station_id = n_ref.STATIONS_station_id "
            "WHERE n_ref.PLACE_block_id = %s AND n_ref.distance_m <= %s "
            f"AND n_ref.STATIONS_station_id IN ({marks}) "
            "AND n_sale.PLACE_block_id = v.block_id AND n_sale.distance_m <= %s)"
        )
        parameters.extend((int(reference["block_id"]), radius_m, *station_ids, radius_m))
    else:
        conditions.append("1 = 0")

    if similar_size and reference.get("floor_area_sqm") is not None:
        ref_area = Decimal(str(reference["floor_area_sqm"]))
        conditions.append("v.floor_area_sqm BETWEEN %s AND %s")
        parameters.append(ref_area - SIMILAR_SIZE_TOLERANCE_SQM)
        parameters.append(ref_area + SIMILAR_SIZE_TOLERANCE_SQM)

    query = (
        "SELECT DISTINCT v.flat_id, v.transaction_date, v.resale_price, "
        "v.price_per_sqm, v.flat_type, v.flat_model, v.storey_range, "
        "v.floor_area_sqm, v.lease_commence_date, v.remaining_lease_months, "
        "v.block_id, v.block_number, v.road_name, v.postal, v.town, "
        f"{nearest_expr} AS nearest_station_m "
        "FROM `v_resale_detail` AS v "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY v.transaction_date DESC, v.flat_id DESC "
        "LIMIT %s"
    )
    parameters.append(int(row_cap) + 1)
    return query, tuple(parameters)


def search_comparable_sales(
    connection: Any,
    reference: dict[str, Any],
    station_ids: list[int],
    options: dict[str, Any],
    row_cap: int = COMPARABLE_ROW_CAP,
) -> tuple[list[dict[str, Any]], bool, date]:
    """Return (rows, truncated, cutoff_date) for comparable sales."""
    months = int(options.get("months", 12))
    latest_date = latest_transaction_date(connection)
    cutoff_date = _period_cutoff_date(latest_date, months)

    if catchment_needs_stations(options.get("catchment", "500 m")) and not station_ids:
        return [], False, cutoff_date

    query, parameters = build_comparable_sales_query(
        reference, station_ids, options, cutoff_date, row_cap=row_cap
    )
    with connection.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(query, parameters)
        fetched = cursor.fetchall()

    truncated = len(fetched) > row_cap
    return fetched[:row_cap], truncated, cutoff_date


def catchment_needs_stations(catchment: str) -> bool:
    return catchment not in ("Same block", "Same town")
