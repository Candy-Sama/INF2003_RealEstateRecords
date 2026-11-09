"""MySQL queries matching the real-estate schema shown in the project diagram."""

from typing import Any


def find_agent_by_email(connection: Any, email: str) -> dict[str, Any] | None:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT agent_id, name, email, phone_number, password_hash "
            "FROM `agents` WHERE email = %s",
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


def list_flats(connection: Any) -> list[dict[str, Any]]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT f.flat_id, f.flat_type, f.flat_model, f.storey_range, "
            "f.floor_area_sqm, f.block_id, f.lease_commence_date, "
            "f.remaining_lease_months, p.block_number, p.road_name, p.town "
            "FROM `flat` AS f JOIN `place` AS p ON p.block_id = f.block_id "
            "ORDER BY p.town, p.road_name, p.block_number, f.flat_id"
        )
        return cursor.fetchall()


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


def delete_flat(connection: Any, flat_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM `flat` WHERE flat_id = %s", (flat_id,))
    connection.commit()


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
        "SELECT rt.transacton_date, rt.resale_price, "
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
