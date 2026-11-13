from typing import Any


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
                values["floor_area_sqm"],
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
                values["floor_area_sqm"],
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


def create_agent_transaction(
    connection: Any,
    agent_id: int,
    flat_id: int,
    transaction_date: Any,
    resale_price: float,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO `resale_transaction` "
            "(FLAT_flat_id, AGENTS_agent_id, transaction_date, resale_price) "
            "VALUES (%s, %s, %s, %s)",
            (flat_id, agent_id, transaction_date, resale_price),
        )
    connection.commit()


def update_agent_transaction(
    connection: Any,
    agent_id: int,
    original_flat_id: int,
    flat_id: int,
    transaction_date: Any,
    resale_price: float,
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE `resale_transaction` "
            "SET FLAT_flat_id = %s, transaction_date = %s, resale_price = %s "
            "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
            (flat_id, transaction_date, resale_price, original_flat_id, agent_id),
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
            parameters.append(value)

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
        "ORDER BY rt.transaction_date DESC LIMIT 1000"
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