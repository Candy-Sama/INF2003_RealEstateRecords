"""Load the bundled demonstration data into a fresh Estate Records schema."""

import os
import time
from contextlib import closing
from decimal import Decimal
from getpass import getpass
from pathlib import Path

import pandas as pd

from app.app_modules.database.database import (
    get_flat_record_admin_email,
    get_mysql_connection,
)
from app.app_modules.security.security import hash_password


CSV_DIR = Path(__file__).resolve().parent
BATCH_SIZE = 10_000
FLAT_COLUMNS = [
    "flat_type", "flat_model", "storey_range", "floor_area_sqm", "block_id",
    "lease_commence_date", "remaining_lease_months",
]


def get_seed_agent_id(cursor):
    email = get_flat_record_admin_email()
    if not email:
        raise ValueError("Set FLAT_RECORD_ADMIN_EMAIL before importing the dataset.")

    cursor.execute("SELECT agent_id FROM agents WHERE email = %s", (email,))
    existing = cursor.fetchone()
    if existing:
        return existing[0]

    password = os.getenv("FLAT_RECORD_ADMIN_PASSWORD")
    if password is None:
        password = getpass("Choose a password for the demo administrator: ")
    if len(password) < 8:
        raise ValueError("Choose a demo administrator password of at least 8 characters.")

    cursor.execute(
        "INSERT INTO agents (name, email, phone_number, password_hash) "
        "VALUES (%s, %s, %s, %s)",
        ("Admin", email, "0000000000", hash_password(password)),
    )
    return cursor.lastrowid


def main():
    started = time.perf_counter()
    places = pd.read_csv(
        CSV_DIR / "places_for_mysql.csv",
        dtype={"postal": str},
        converters={"latitude": Decimal, "longitude": Decimal},
    )
    stations = pd.read_csv(CSV_DIR / "mrt_lrt_full_list.csv")
    hdb = pd.read_csv(
        CSV_DIR / "hdb_resale_enriched_block_id.csv",
        converters={"floor_area_sqm": Decimal, "resale_price": Decimal},
    )
    transaction_dates = (
        pd.to_datetime(hdb["transaction_date"], format="%m-%Y") + pd.offsets.MonthEnd(0)
    ).dt.date

    with closing(get_mysql_connection()) as connection, connection.cursor() as cursor:
        try:
            connection.start_transaction(isolation_level="REPEATABLE READ")
            cursor.execute("SELECT @@foreign_key_checks, @@unique_checks")
            if cursor.fetchone() != (1, 1):
                raise ValueError("Enable foreign_key_checks and unique_checks before importing.")
            cursor.execute("SELECT block_id FROM place LIMIT 1 FOR UPDATE")
            if cursor.fetchone():
                raise ValueError("The import requires a fresh schema with an empty place table.")

            agent_id = get_seed_agent_id(cursor)
            place_columns = [
                "block_id", "block_number", "road_name", "postal", "latitude",
                "longitude", "town",
            ]
            cursor.executemany(
                "INSERT INTO place (block_id, block_number, road_name, postal, "
                "latitude, longtitude, town) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                list(places[place_columns].itertuples(index=False, name=None)),
            )

            station_columns = [
                "ALPHANUMERIC_CODE", "STATION_NAME_ENGLISH", "LINE_ENGLISH",
                "LINE_COLOR", "TRANSPORT_TYPE", "block_id",
            ]
            cursor.executemany(
                "INSERT INTO stations (station_code, station_name, line_name, "
                "line_color, transport_type, place_block_id) VALUES (%s, %s, %s, %s, %s, %s)",
                list(stations[station_columns].itertuples(index=False, name=None)),
            )

            flat_query = (
                "INSERT INTO flat (flat_type, flat_model, storey_range, floor_area_sqm, "
                "block_id, lease_commence_date, remaining_lease_months) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)"
            )
            flats = hdb[FLAT_COLUMNS]
            for offset in range(0, len(flats), BATCH_SIZE):
                batch = flats.iloc[offset : offset + BATCH_SIZE]
                cursor.executemany(flat_query, list(batch.itertuples(index=False, name=None)))

            # In the empty schema, generated flat IDs follow the CSV insertion order.
            cursor.execute("SELECT flat_id FROM flat ORDER BY flat_id")
            flat_ids = [row[0] for row in cursor.fetchall()]
            if len(flat_ids) != len(hdb):
                raise ValueError("The number of generated flat IDs differs from the resale CSV.")

            resale_query = (
                "INSERT INTO resale_transaction (FLAT_flat_id, AGENTS_agent_id, "
                "transaction_date, resale_price) VALUES (%s, %s, %s, %s)"
            )
            for offset in range(0, len(hdb), BATCH_SIZE):
                end = offset + BATCH_SIZE
                batch = [
                    (flat_id, agent_id, month_end, price)
                    for flat_id, month_end, price in zip(
                        flat_ids[offset:end],
                        transaction_dates.iloc[offset:end],
                        hdb["resale_price"].iloc[offset:end],
                        strict=True,
                    )
                ]
                cursor.executemany(resale_query, batch)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    print(
        f"Imported {len(places):,} places, {len(stations):,} station codes, "
        f"{len(flats):,} flats, and {len(hdb):,} resale transactions "
        f"in {time.perf_counter() - started:.2f} seconds."
    )


if __name__ == "__main__":
    main()
