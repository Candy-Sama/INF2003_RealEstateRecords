"""Check or upgrade an existing Estate Records MySQL schema in place."""

import argparse
import re
from contextlib import closing

from app.app_modules.database.database import get_mysql_connection
from app.app_modules.nearby.nearby_function import DEFAULT_RADIUS_M, populate_nearby


EXACT_COLUMNS = {
    "place": {"latitude": (18, 15), "longtitude": (18, 15)},
    "flat": {"floor_area_sqm": (7, 2)},
    "resale_transaction": {"resale_price": (12, 2)},
}
CHECKS = {
    "place": {
        "chk_place_coordinates": "latitude BETWEEN -90 AND 90 AND longtitude > -180 AND longtitude <= 180",
    },
    "flat": {
        "chk_flat_area": "floor_area_sqm > 0",
        "chk_flat_remaining_lease": "remaining_lease_months >= 0",
    },
    "resale_transaction": {"chk_resale_price": "resale_price > 0"},
    "nearby": {"chk_nearby_distance": "distance_m >= 0"},
}
INDEXES = {
    "place": {
        "ix_place_town_address": ("town", "road_name", "block_number"),
        "ix_place_coords": ("latitude", "longtitude"),
    },
    "flat": {"ix_flat_type_block": ("flat_type", "block_id")},
    "nearby": {"ix_nearby_block_distance": ("PLACE_block_id", "distance_m")},
    "resale_transaction": {
        "ix_rt_agent_date_flat": ("AGENTS_agent_id", "transaction_date", "FLAT_flat_id"),
        "ix_rt_date": ("transaction_date",),
        "ix_rt_price": ("resale_price",),
    },
}
LEGACY_INDEXES = {
    "agents": {"agent_id_UNIQUE": (0, ("agent_id",))},
    "place": {"block_id_UNIQUE": (0, ("block_id",))},
    "flat": {"transaction_id_UNIQUE": (0, ("flat_id",))},
    "stations": {"station_id_UNIQUE": (0, ("station_id",))},
    "nearby": {
        "fk_STATIONS_has_PLACE_STATIONS1_idx": (1, ("STATIONS_station_id",)),
        "fk_STATIONS_has_PLACE_PLACE1_idx": (1, ("PLACE_block_id",)),
    },
    "resale_transaction": {
        "fk_RESALE_TRANSACTION_has_AGENTS_AGENTS1_idx": (1, ("AGENTS_agent_id",)),
        "fk_RESALE_TRANSACTION_has_AGENTS_RESALE_TRANSACTION1_idx": (1, ("FLAT_flat_id",)),
    },
}
REQUIRED_KEYS = {
    "agents": {"PRIMARY": ("agent_id",), "email_UNIQUE": ("email",)},
    "place": {"PRIMARY": ("block_id",)},
    "flat": {"PRIMARY": ("flat_id",)},
    "stations": {"PRIMARY": ("station_id",), "station_code_UNIQUE": ("station_code",)},
    "nearby": {"PRIMARY": ("STATIONS_station_id", "PLACE_block_id")},
    "resale_transaction": {"PRIMARY": ("FLAT_flat_id", "AGENTS_agent_id")},
}
FOREIGN_KEYS = (
    ("flat", "block_id", "place", "block_id"),
    ("stations", "place_block_id", "place", "block_id"),
    ("nearby", "PLACE_block_id", "place", "block_id"),
    ("nearby", "STATIONS_station_id", "stations", "station_id"),
    ("resale_transaction", "FLAT_flat_id", "flat", "flat_id"),
    ("resale_transaction", "AGENTS_agent_id", "agents", "agent_id"),
)
INVALID_ROWS = {
    "place": "latitude NOT BETWEEN -90 AND 90 OR longtitude <= -180 OR longtitude > 180",
    "flat": "floor_area_sqm < 0.01 OR floor_area_sqm > 99999.99 OR remaining_lease_months < 0",
    "resale_transaction": "resale_price < 0.01 OR resale_price > 9999999999.99",
    "nearby": "distance_m < 0",
}
CREATE_RESALE_DETAIL_VIEW = """
CREATE VIEW `v_resale_detail` AS
SELECT
    rt.`FLAT_flat_id` AS `flat_id`,
    rt.`transaction_date`,
    rt.`resale_price`,
    ROUND(rt.`resale_price` / NULLIF(f.`floor_area_sqm`, 0), 2) AS `price_per_sqm`,
    f.`flat_type`,
    f.`flat_model`,
    f.`storey_range`,
    f.`floor_area_sqm`,
    f.`lease_commence_date`,
    f.`remaining_lease_months`,
    p.`block_id`,
    p.`block_number`,
    p.`road_name`,
    p.`postal`,
    p.`town`,
    p.`latitude`,
    p.`longtitude`
FROM `resale_transaction` AS rt
JOIN `flat` AS f ON f.`flat_id` = rt.`FLAT_flat_id`
JOIN `place` AS p ON p.`block_id` = f.`block_id`
""".strip()


def _read_indexes(cursor):
    cursor.execute(
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME, COLLATION, SUB_PART, "
        "INDEX_TYPE, IS_VISIBLE FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
    )
    indexes = {}
    for table, name, non_unique, column, order, prefix, kind, visible in cursor:
        indexes.setdefault((table, name), []).append(
            (non_unique, column, order, prefix, kind, visible)
        )
    return indexes


def _index_matches(entries, non_unique, columns):
    return entries == [(non_unique, column, "A", None, "BTREE", "YES") for column in columns]


def _preflight(cursor, indexes, has_distance):
    cursor.execute("SELECT @@foreign_key_checks, @@unique_checks")
    if cursor.fetchone() != (1, 1):
        raise ValueError("Enable foreign_key_checks and unique_checks before migrating.")

    cursor.execute(
        "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
    )
    engines = dict(cursor.fetchall())
    for table, keys in REQUIRED_KEYS.items():
        if engines.get(table) != "InnoDB":
            raise ValueError(f"Expected an InnoDB {table} table in the configured schema.")
        for name, columns in keys.items():
            if not _index_matches(indexes.get((table, name)), 0, columns):
                raise ValueError(f"Unexpected definition of required index {table}.{name}.")

    cursor.execute(
        "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
        "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() "
        "AND REFERENCED_TABLE_SCHEMA = DATABASE()"
    )
    references = set(cursor.fetchall())
    for table, column, parent, parent_column in FOREIGN_KEYS:
        if (table, column, parent, parent_column) not in references:
            raise ValueError(f"Missing foreign key for {table}.{column}.")
        cursor.execute(
            f"SELECT 1 FROM `{table}` AS child LEFT JOIN `{parent}` AS parent "
            f"ON child.`{column}` = parent.`{parent_column}` "
            f"WHERE parent.`{parent_column}` IS NULL LIMIT 1"
        )
        if cursor.fetchone():
            raise ValueError(f"Orphaned rows in {table}.{column}. Correct them before migrating.")

    for table, predicate in INVALID_ROWS.items():
        if table == "nearby" and not has_distance:
            continue
        cursor.execute(f"SELECT 1 FROM `{table}` WHERE {predicate} LIMIT 1")
        if cursor.fetchone():
            raise ValueError(f"Rows in {table} violate the proposed numeric bounds. Correct them before migrating.")


def _schema_operations(cursor, indexes, columns):
    cursor.execute(
        "SELECT t.TABLE_NAME, t.CONSTRAINT_NAME, c.CHECK_CLAUSE, t.ENFORCED "
        "FROM information_schema.TABLE_CONSTRAINTS AS t JOIN information_schema.CHECK_CONSTRAINTS AS c "
        "ON c.CONSTRAINT_SCHEMA = t.CONSTRAINT_SCHEMA AND c.CONSTRAINT_NAME = t.CONSTRAINT_NAME "
        "WHERE t.TABLE_SCHEMA = DATABASE() AND t.CONSTRAINT_TYPE = 'CHECK'"
    )
    checks = {(table, name): (expr, enforced) for table, name, expr, enforced in cursor}
    alters = {}
    for table, definitions in EXACT_COLUMNS.items():
        for column, (precision, scale) in definitions.items():
            current = columns.get((table, column))
            if current == ("decimal", "NO", None, precision, scale):
                continue
            legacy_type = "int" if column == "floor_area_sqm" else "float"
            if current is None or current[0] != legacy_type or current[1:3] != ("NO", None):
                raise ValueError(f"Unexpected column definition for {table}.{column}.")
            alters.setdefault(table, []).append(
                f"MODIFY COLUMN `{column}` DECIMAL({precision},{scale}) NOT NULL"
            )

    distance = columns.get(("nearby", "distance_m"))
    if distance is not None and (distance[0] != "int" or distance[2] not in (None, "0")):
        raise ValueError("Unexpected column definition for nearby.distance_m.")
    legacy_distance = distance is None or distance[1:3] != ("NO", None)
    if legacy_distance:
        alters["nearby"] = ["MODIFY COLUMN `distance_m` INT NOT NULL"]

    for table, definitions in CHECKS.items():
        for name, expression in definitions.items():
            current = checks.get((table, name))
            if current is None:
                alters.setdefault(table, []).append(f"ADD CONSTRAINT `{name}` CHECK ({expression})")
                continue
            actual = re.sub(r"[\s`()]", "", current[0]).lower()
            expected = re.sub(r"\s", "", expression).lower()
            if actual != expected or current[1] != "YES":
                raise ValueError(f"Unexpected definition of check constraint {table}.{name}.")

    additions = []
    for table, definitions in INDEXES.items():
        for name, fields in definitions.items():
            current = indexes.get((table, name))
            if current is None:
                names = ", ".join(f"`{field}`" for field in fields)
                additions.append(f"ALTER TABLE `{table}` ADD INDEX `{name}` ({names})")
            elif not _index_matches(current, 1, fields):
                raise ValueError(f"Unexpected definition of index {table}.{name}.")

    removals = []
    for table, definitions in LEGACY_INDEXES.items():
        for name, (non_unique, fields) in definitions.items():
            current = indexes.get((table, name))
            if current is not None:
                if not _index_matches(current, non_unique, fields):
                    raise ValueError(f"Unexpected definition of legacy index {table}.{name}.")
                removals.append(f"ALTER TABLE `{table}` DROP INDEX `{name}`")
    return alters, additions, removals, legacy_distance


def _needs_resale_detail_view(cursor):
    cursor.execute(
        "SELECT TABLE_TYPE FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'v_resale_detail'"
    )
    existing = cursor.fetchone()
    if existing is not None and existing[0] != "VIEW":
        raise ValueError("Expected v_resale_detail to be a view in the configured schema.")
    return existing is None


def migrate_schema(connection, *, apply=False, radius_m=DEFAULT_RADIUS_M, nearest_fallback=True):
    """Return planned or applied operations using a dedicated connection."""
    if radius_m <= 0:
        raise ValueError("radius_m must be positive.")
    if connection.in_transaction or connection.autocommit:
        raise ValueError("Migration requires a fresh connection with autocommit disabled.")

    with connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT VERSION(), CONCAT('estate-schema:', LEFT(SHA2(DATABASE(), 256), 40))")
        version, lock_name = cursor.fetchone()
        if lock_name is None or "mariadb" in version.lower() or connection.server_version < (8, 0, 18):
            raise ValueError("Select an Estate Records schema on MySQL 8.0.18 or newer.")

        cursor.execute("SELECT GET_LOCK(%s, 0)", (lock_name,))
        if cursor.fetchone()[0] != 1:
            raise ValueError("Another schema migration is running for this database.")

        try:
            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
                "NUMERIC_PRECISION, NUMERIC_SCALE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE()"
            )
            columns = {(table, name): tuple(spec) for table, name, *spec in cursor}
            indexes = _read_indexes(cursor)
            has_distance = ("nearby", "distance_m") in columns
            _preflight(cursor, indexes, has_distance)
            alters, additions, removals, rebuild_nearby = _schema_operations(cursor, indexes, columns)
            create_resale_detail_view = _needs_resale_detail_view(cursor)
            operations = []

            def execute(sql):
                operations.append(sql)
                if apply:
                    cursor.execute(sql)

            if not has_distance:
                execute("ALTER TABLE `nearby` ADD COLUMN `distance_m` INT NULL")
            for table, clauses in alters.items():
                if table != "nearby":
                    execute(f"ALTER TABLE `{table}` " + ", ".join(clauses))
            if rebuild_nearby:
                operations.append(f"Rebuild derived nearby rows at {radius_m} m (fallback={nearest_fallback})")
                if apply:
                    connection.commit()
                    populate_nearby(connection, radius_m, nearest_fallback)
            if "nearby" in alters:
                execute("ALTER TABLE `nearby` " + ", ".join(alters["nearby"]))
            for sql in additions + removals:
                execute(sql)
            if create_resale_detail_view:
                execute(CREATE_RESALE_DETAIL_VIEW)
            return operations
        finally:
            connection.rollback()
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
            cursor.fetchone()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply changes after preflight")
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M, help="legacy nearby rebuild radius in metres")
    parser.add_argument("--no-fallback", action="store_true", help="skip nearest station fallback for the legacy rebuild")
    args = parser.parse_args()
    try:
        with closing(get_mysql_connection()) as connection:
            operations = migrate_schema(
                connection, apply=args.apply, radius_m=args.radius, nearest_fallback=not args.no_fallback,
            )
    except ValueError as error:
        parser.exit(1, f"Migration preflight failed: {error}\n")
    if operations:
        print("Applied operations" if args.apply else "Pending operations (use --apply to run them)")
        for operation in operations:
            print(operation)
    else:
        print("MySQL schema is up to date.")


if __name__ == "__main__":
    main()
