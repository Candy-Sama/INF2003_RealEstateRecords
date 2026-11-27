from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

MAX_FIELDS = 12
MAX_FILTERS = 8
MAX_LIMIT = 5000
LIST_DEFAULT_LIMIT = 1000
MAX_FILTER_VALUES = 50

DISPLAY_CHOICES = ("auto", "table", "kpi", "bar", "line", "area", "scatter", "heatmap")
MODES = ("summarise", "list")
BUCKETS = ("month", "year", "quarter", "day")

# The chain of tables, in join order.
ORDER = ("rt", "f", "p", "n", "s", "sp")
TABLES = {
    "rt": ("resale_transaction", "Resale transactions"),
    "f": ("flat", "Flats"),
    "p": ("place", "Address of the flat"),
    "n": ("nearby", "Nearby (distance from the address to a station)"),
    "s": ("stations", "Stations"),
    "sp": ("place", "Station location (the station's own address)"),
}
UI_TABLES = (*ORDER, "calc")
TABLE_LABELS = {**{alias: label for alias, (_, label) in TABLES.items()},
                "calc": "Calculated fields"}

# (column, label, kind, is_key)
_PLACE_COLUMNS = (
    ("block_id", "Block ID", "id", True),
    ("town", "Town", "text", False),
    ("road_name", "Road name", "text", False),
    ("block_number", "Block number", "text", False),
    ("postal", "Postal code", "text", False),
    ("latitude", "Latitude", "number", False),
    ("longtitude", "Longitude", "number", False),
)
_COLUMNS: dict[str, tuple[tuple[str, str, str, bool], ...]] = {
    "rt": (
        ("FLAT_flat_id", "Flat ID", "id", True),
        ("AGENTS_agent_id", "Agent ID", "id", True),
        ("transaction_date", "Transaction date", "date", False),
        ("resale_price", "Resale price", "number", False),
    ),
    "f": (
        ("flat_id", "Flat ID", "id", True),
        ("flat_type", "Flat type", "text", False),
        ("flat_model", "Flat model", "text", False),
        ("storey_range", "Storey range", "text", False),
        ("floor_area_sqm", "Floor area (sqm)", "number", False),
        ("lease_commence_date", "Lease commencement year", "number", False),
        ("remaining_lease_months", "Remaining lease (months)", "number", False),
        ("block_id", "Block ID (link to address)", "id", False),
    ),
    "p": _PLACE_COLUMNS,
    "n": (
        ("STATIONS_station_id", "Station ID", "id", True),
        ("PLACE_block_id", "Block ID", "id", True),
        ("distance_m", "Distance to station (m)", "number", False),
    ),
    "s": (
        ("station_id", "Station ID", "id", True),
        ("station_code", "Station code", "text", False),
        ("station_name", "Station name", "text", False),
        ("line_name", "Line", "text", False),
        ("line_color", "Line colour", "text", False),
        ("transport_type", "Transport type (MRT / LRT)", "text", False),
        ("place_block_id", "Station location block ID", "id", False),
    ),
    "sp": _PLACE_COLUMNS,
}

_ROLES_BY_KIND = {
    "text": ("group", "count_distinct", "count"),
    "number": ("avg", "sum", "min", "max", "group", "count"),
    "date": ("group", "min", "max", "count"),
    "id": ("count_distinct", "count", "group"),
    "count": ("count",),
}
ROLE_LABELS = {
    "group": "Group by", "avg": "Average", "sum": "Total (sum)", "min": "Minimum",
    "max": "Maximum", "count": "Count", "count_distinct": "Count distinct",
    "show": "Show",
}
_ROLE_PREFIX = {"avg": "avg_", "sum": "total_", "min": "min_", "max": "max_",
                "count": "count_", "count_distinct": "distinct_"}
BUCKET_LABELS = {"month": "by month", "year": "by year", "quarter": "by quarter", "day": "by day"}

_BUCKET_SQL = {
    "day": "{e}",
    "month": "DATE_SUB({e}, INTERVAL (DAYOFMONTH({e}) - 1) DAY)",
    "quarter": "DATE_ADD(MAKEDATE(YEAR({e}), 1), INTERVAL (QUARTER({e}) - 1) QUARTER)",
    "year": "MAKEDATE(YEAR({e}), 1)",
}

_DISTANCE_BAND = (
    "CASE WHEN n.distance_m <= 300 THEN '1) up to 300 m' "
    "WHEN n.distance_m <= 500 THEN '2) 301-500 m' "
    "WHEN n.distance_m <= 800 THEN '3) 501-800 m' "
    "WHEN n.distance_m <= 1000 THEN '4) 801-1000 m' "
    "ELSE '5) over 1 km' END"
)
# (name, label, kind, expression, tables needed, help)
_CALCULATED = (
    ("row_count", "Number of records", "count", "*", (),
     "Counts rows of the joined data: transactions if you picked a transaction field."),
    ("price_per_sqm", "Price per sqm", "number",
     "(rt.resale_price / f.floor_area_sqm)", ("rt", "f"), None),
    ("lease_years_left", "Remaining lease (years)", "number",
     "FLOOR(f.remaining_lease_months / 12)", ("f",), None),
    ("flat_age", "Flat age at sale (years)", "number",
     "(YEAR(rt.transaction_date) - f.lease_commence_date)", ("rt", "f"), None),
    ("distance_band", "Distance band to station", "text", _DISTANCE_BAND, ("n",),
     "Up to 300 m, 301-500 m, 501-800 m, 801-1000 m, over 1 km."),
)

# Fields that can be filtered, and where to look up the choices
_FILTER_SOURCES = {
    "p.town": ("place", "town"), "sp.town": ("place", "town"),
    "f.flat_type": ("flat", "flat_type"), "f.flat_model": ("flat", "flat_model"),
    "f.storey_range": ("flat", "storey_range"),
    "s.station_name": ("stations", "station_name"), "s.station_code": ("stations", "station_code"),
    "s.line_name": ("stations", "line_name"), "s.transport_type": ("stations", "transport_type"),
}
_NUMBER_FILTERS = {
    "rt.resale_price", "f.floor_area_sqm", "f.lease_commence_date",
    "f.remaining_lease_months", "n.distance_m",
    "calc.price_per_sqm", "calc.lease_years_left", "calc.flat_age",
}
_DATE_FILTERS = {"rt.transaction_date"}

_SAFE_TEXT = re.compile(r"^[\w /&'().,\-]{1,80}$")


@dataclass(frozen=True)
class FieldDef:
    key: str
    table: str         
    column: str
    label: str
    kind: str           
    is_key: bool
    expr: str
    requires: tuple[str, ...]
    alias_base: str
    help: str | None = None

    @property
    def roles(self) -> tuple[str, ...]:
        return _ROLES_BY_KIND[self.kind]

    @property
    def filter_kind(self) -> str | None:
        if self.key in _FILTER_SOURCES:
            return "text"
        if self.key in _NUMBER_FILTERS:
            return "number"
        if self.key in _DATE_FILTERS:
            return "date"
        return None


def _build_fields() -> dict[str, FieldDef]:
    fields: dict[str, FieldDef] = {}
    for alias in ORDER:
        for column, label, kind, is_key in _COLUMNS[alias]:
            key = f"{alias}.{column}"
            shown = f"Station location: {label}" if alias == "sp" else label
            base = column.replace("longtitude", "longitude")
            if alias == "sp":
                base = f"station_loc_{base}"
            fields[key] = FieldDef(key, alias, column, shown, kind, is_key,
                                   f"{alias}.{column}", (alias,), base)
    for name, label, kind, expr, requires, help_text in _CALCULATED:
        key = f"calc.{name}"
        fields[key] = FieldDef(key, "calc", name, label, kind, False, expr,
                               requires, name, help_text)
    return fields


FIELDS = _build_fields()


def fields_for_table(alias: str) -> list[FieldDef]:
    return [f for f in FIELDS.values() if f.table == alias]


def filterable_keys() -> list[str]:
    return [key for key, f in FIELDS.items() if f.filter_kind]


def filter_source(key: str) -> tuple[str, str]:
    """(table, column) for a text filter's choices. Constants only, never user input."""
    return _FILTER_SOURCES[key]


def is_safe_text(value: Any) -> bool:
    return isinstance(value, str) and bool(_SAFE_TEXT.match(value))


def default_role(field: FieldDef) -> str:
    return {"text": "group", "number": "avg", "date": "group",
            "id": "count_distinct", "count": "count"}[field.kind]


# filter validation
def _literal_text(value: Any) -> str:
    if not is_safe_text(value):
        raise ValueError(f"The value {str(value)[:30]!r} can't be used in a filter.")
    return "'" + value.replace("'", "''") + "'"


def _number(value: Any) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Filter numbers must be finite numbers.")
    return int(value) if float(value).is_integer() else round(float(value), 6)


def _iso_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError("Filter dates must look like YYYY-MM-DD.") from None


def clean_spec(spec: Any) -> dict[str, Any]:
    """Validate builder settings and return a normalised copy. Raises ValueError."""
    if not isinstance(spec, dict):
        raise ValueError("Invalid builder settings.")
    mode = spec.get("mode", "summarise")
    if mode not in MODES:
        raise ValueError("Unknown mode.")

    raw_fields = spec.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError("Tick at least one column.")
    if len(raw_fields) > MAX_FIELDS:
        raise ValueError(f"Choose at most {MAX_FIELDS} columns.")
    fields, seen = [], set()
    for item in raw_fields:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            raise ValueError("Invalid column choice.")
        definition = FIELDS.get(item["key"])
        if definition is None:
            raise ValueError("Unknown column.")
        if mode == "list":
            if definition.kind == "count":
                raise ValueError("'Number of records' only works in Summarise mode.")
            role = "show"
        else:
            role = item.get("role")
            if role not in definition.roles:
                raise ValueError(f"'{definition.label}' can't be used as '{role}'.")
        bucket = None
        if mode == "summarise" and role == "group" and definition.kind == "date":
            bucket = item.get("bucket") or "month"
            if bucket not in BUCKETS:
                raise ValueError("Unknown date grouping.")
        signature = (item["key"], role, bucket)
        if signature in seen:
            raise ValueError(f"'{definition.label}' is chosen twice.")
        seen.add(signature)
        fields.append({"key": item["key"], "role": role, "bucket": bucket})

    raw_filters = spec.get("filters") or []
    if not isinstance(raw_filters, list) or len(raw_filters) > MAX_FILTERS:
        raise ValueError(f"Use at most {MAX_FILTERS} filters.")
    filters = []
    for item in raw_filters:
        if not isinstance(item, dict):
            raise ValueError("Invalid filter.")
        definition = FIELDS.get(item.get("key")) if isinstance(item.get("key"), str) else None
        if definition is None or definition.filter_kind is None:
            raise ValueError("That column can't be filtered.")
        kind = definition.filter_kind
        if kind == "text":
            values = item.get("values")
            if not isinstance(values, list) or not 1 <= len(values) <= MAX_FILTER_VALUES:
                raise ValueError(f"Choose 1 to {MAX_FILTER_VALUES} values for '{definition.label}'.")
            for value in values:
                _literal_text(value)  # validates
            filters.append({"key": definition.key, "op": "in", "values": list(values)})
        else:
            low, high = item.get("min"), item.get("max")
            if low is None and high is None:
                raise ValueError(f"Give '{definition.label}' a minimum or a maximum.")
            convert = _number if kind == "number" else _iso_date
            filters.append({
                "key": definition.key, "op": "range",
                "min": None if low is None else convert(low),
                "max": None if high is None else convert(high),
            })

    sort = spec.get("sort") or {}
    if not isinstance(sort, dict):
        raise ValueError("Invalid sort.")
    sort_field = sort.get("field")
    if sort_field is not None and not (isinstance(sort_field, str)
                                       and re.fullmatch(r"[a-z0-9_]{1,80}", sort_field)):
        raise ValueError("Invalid sort column.")
    direction = sort.get("dir", "asc")
    if direction not in ("asc", "desc"):
        raise ValueError("Invalid sort direction.")

    limit = spec.get("limit", 0)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= MAX_LIMIT:
        raise ValueError(f"The row limit must be between 0 and {MAX_LIMIT}.")
    nearest_only = spec.get("nearest_only", True)
    if not isinstance(nearest_only, bool):
        raise ValueError("Invalid station setting.")
    choice = spec.get("display_choice", "auto")
    if choice not in DISPLAY_CHOICES:
        raise ValueError("Unknown display type.")

    return {
        "mode": mode, "fields": fields, "filters": filters,
        "sort": {"field": sort_field, "dir": direction},
        "limit": limit, "nearest_only": nearest_only, "display_choice": choice,
    }


# --------------------------------------------------------------------------
# SQL generation
# --------------------------------------------------------------------------
@dataclass
class Compiled:
    sql: str
    outputs: list[dict[str, Any]]   # alias, label, kind (text/date/number/measure/raw), role
    tables: list[str]
    nearest_only: bool              # whether the nearest-station rule was applied


_NEAREST = (
    "(SELECT x.PLACE_block_id, x.STATIONS_station_id, x.distance_m "
    "FROM (SELECT n1.PLACE_block_id, n1.STATIONS_station_id, n1.distance_m, "
    "ROW_NUMBER() OVER (PARTITION BY n1.PLACE_block_id "
    "ORDER BY n1.distance_m, n1.STATIONS_station_id) AS rn FROM nearby n1) x "
    "WHERE x.rn = 1) n"
)
_JOIN_ON = {
    "f": "JOIN flat f ON f.flat_id = rt.FLAT_flat_id",
    "p": "JOIN place p ON p.block_id = f.block_id",
    "n": "JOIN {nearby} ON n.PLACE_block_id = p.block_id",
    "s": "JOIN stations s ON s.station_id = n.STATIONS_station_id",
    "sp": "JOIN place sp ON sp.block_id = s.place_block_id",
}
_ROOT = {"rt": "resale_transaction rt", "f": "flat f", "p": "place p",
         "n": "{nearby}", "s": "stations s", "sp": "place sp"}


def _alias(base: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", base.lower()).strip("_") or "col"
    candidate, count = base, 2
    while candidate in taken:
        candidate, count = f"{base}_{count}", count + 1
    taken.add(candidate)
    return candidate


def nearest_rule_applies(tables: list[str]) -> bool:
    """The nearest-station switch matters when flats/transactions meet nearby stations."""
    return "n" in tables and ("rt" in tables or "f" in tables)


def compile_spec(spec: Any) -> Compiled:
    spec = clean_spec(spec)
    summarise = spec["mode"] == "summarise"

    used: set[str] = set()
    for item in (*spec["fields"], *spec["filters"]):
        used.update(FIELDS[item["key"]].requires)
    if not used:
        used = {"rt"}  # only "Number of records" was chosen: count transactions
    indexes = sorted(ORDER.index(alias) for alias in used)
    tables = list(ORDER[indexes[0] : indexes[-1] + 1])
    nearest = spec["nearest_only"] and nearest_rule_applies(tables)
    nearby_sql = _NEAREST if nearest else "nearby n"

    selects: list[str] = []
    group_exprs: list[str] = []
    outputs: list[dict[str, Any]] = []
    taken: set[str] = set()
    for item in spec["fields"]:
        definition = FIELDS[item["key"]]
        role, expr = item["role"], definition.expr
        if not summarise:
            alias = _alias(definition.alias_base, taken)
            selects.append(f"{expr} AS {alias}")
            outputs.append({"alias": alias, "label": definition.label,
                            "kind": "raw", "role": "show"})
        elif role == "group":
            if item["bucket"]:
                expr = _BUCKET_SQL[item["bucket"]].format(e=expr)
                alias = _alias(f"{definition.alias_base}_{item['bucket']}", taken)
                label = f"{definition.label} ({BUCKET_LABELS[item['bucket']]})"
            else:
                alias = _alias(definition.alias_base, taken)
                label = definition.label
            kind = "date" if definition.kind == "date" else (
                "number" if definition.kind == "number" else "text")
            selects.append(f"{expr} AS {alias}")
            group_exprs.append(expr)
            outputs.append({"alias": alias, "label": label, "kind": kind, "role": "group"})
        else:
            if definition.kind == "count":
                measure = "COUNT(*)"
            elif role == "avg":
                measure = f"ROUND(AVG({expr}), 2)"
            elif role == "sum":
                measure = f"ROUND(SUM({expr}), 2)"
            elif role == "min":
                measure = f"MIN({expr})"
            elif role == "max":
                measure = f"MAX({expr})"
            elif role == "count_distinct":
                measure = f"COUNT(DISTINCT {expr})"
            else:
                measure = f"COUNT({expr})"
            alias = _alias(
                definition.alias_base if definition.kind == "count"
                else f"{_ROLE_PREFIX[role]}{definition.alias_base}", taken)
            selects.append(f"{measure} AS {alias}")
            date_extreme = definition.kind == "date" and role in ("min", "max")
            outputs.append({"alias": alias,
                            "label": definition.label if definition.kind == "count"
                            else f"{ROLE_LABELS[role]} of {definition.label.lower()}",
                            "kind": "date" if date_extreme else "measure", "role": role})

    conditions: list[str] = []
    for item in spec["filters"]:
        definition = FIELDS[item["key"]]
        if item["op"] == "in":
            values = ", ".join(_literal_text(v) for v in item["values"])
            conditions.append(f"{definition.expr} IN ({values})")
        else:
            literal = (_number if definition.filter_kind == "number" else None)
            for bound, symbol in ((item["min"], ">="), (item["max"], "<=")):
                if bound is None:
                    continue
                text = str(literal(bound)) if literal else f"'{_iso_date(bound)}'"
                conditions.append(f"{definition.expr} {symbol} {text}")

    order_sql = ""
    sort = spec["sort"]
    by_alias = {o["alias"]: o for o in outputs}
    if sort["field"]:
        if sort["field"] not in by_alias:
            raise ValueError("The sort column isn't part of the result.")
        order_sql = f"{sort['field']} {sort['dir'].upper()}"
    elif summarise:
        measures = [o for o in outputs if o["kind"] == "measure"]
        groups = [o for o in outputs if o["role"] == "group"]
        dated = [o for o in groups if o["kind"] == "date"]
        if spec["limit"] and measures:
            order_sql = f"{measures[0]['alias']} DESC"   # "top N" means biggest first
        elif dated or groups:
            order_sql = f"{(dated or groups)[0]['alias']} ASC"

    limit = spec["limit"] or (0 if summarise else LIST_DEFAULT_LIMIT)

    lines = ["SELECT " + ",\n       ".join(selects)]
    lines.append("FROM " + _ROOT[tables[0]].format(nearby=nearby_sql))
    for alias in tables[1:]:
        lines.append(_JOIN_ON[alias].format(nearby=nearby_sql))
    if conditions:
        lines.append("WHERE " + "\n  AND ".join(conditions))
    if summarise and group_exprs:
        lines.append("GROUP BY " + ", ".join(group_exprs))
    if order_sql:
        lines.append("ORDER BY " + order_sql)
    if limit:
        lines.append(f"LIMIT {limit}")
    return Compiled("\n".join(lines), outputs, tables, nearest)


def build_sql(spec: Any) -> str:
    return compile_spec(spec).sql


# display
def _split(compiled: Compiled):
    groups = [o for o in compiled.outputs if o["role"] == "group"]
    measures = [o for o in compiled.outputs if o["kind"] == "measure"]
    return groups, measures


def suggest_display(compiled: Compiled, mode: str) -> str:
    if mode == "list":
        return "table"
    groups, measures = _split(compiled)
    if not measures:
        return "table"
    if not groups:
        return "kpi"
    if len(groups) == 1:
        return "line" if groups[0]["kind"] in ("date", "number") else "bar"
    if len(groups) == 2:
        if any(g["kind"] == "date" for g in groups):
            return "line"
        return "heatmap" if len(measures) == 1 else "bar"
    return "table"


def resolve_display(
    compiled: Compiled, mode: str, choice: str, horizontal: bool = False
) -> tuple[str, dict[str, Any]]:
    """Pick the display type and column mapping. Raises ValueError with a friendly message."""
    display = suggest_display(compiled, mode) if choice == "auto" else choice
    mapping: dict[str, Any] = {"x": None, "y": None, "color": None, "value": None,
                               "horizontal": False}
    if display in ("table", "kpi"):
        if display == "kpi" and mode == "list":
            raise ValueError("KPI numbers need Summarise mode.")
        return display, mapping

    groups, measures = _split(compiled)
    if mode == "list" or not measures:
        raise ValueError(f"A {display} chart needs at least one 'Group by' column and one number "
                         "to summarise. Use Summarise mode, or choose Table.")
    if not groups:
        raise ValueError(f"A {display} chart needs a 'Group by' column.")
    ordered = sorted(groups, key=lambda g: g["kind"] != "date")  # time goes on x
    if display == "heatmap":
        if len(groups) < 2:
            raise ValueError("A heatmap needs two 'Group by' columns.")
        mapping.update(x=ordered[0]["alias"], y=ordered[1]["alias"], value=measures[0]["alias"])
        return display, mapping
    mapping.update(x=ordered[0]["alias"], y=measures[0]["alias"])
    if len(ordered) > 1:
        mapping["color"] = ordered[1]["alias"]
    mapping["horizontal"] = bool(horizontal and display == "bar")
    return display, mapping


# --------------------------------------------------------------------------
# Plain-language summary (shown in a card's details)
# --------------------------------------------------------------------------
def describe_spec(spec: dict[str, Any]) -> list[str]:
    lines = ["Mode: " + ("Summarise (groups and totals)" if spec.get("mode") == "summarise"
                         else "List rows")]
    for item in spec.get("fields", []):
        definition = FIELDS.get(item.get("key"))
        if definition is None:
            continue
        role = ROLE_LABELS.get(item.get("role"), "")
        bucket = f" {BUCKET_LABELS[item['bucket']]}" if item.get("bucket") else ""
        table = TABLE_LABELS.get(definition.table, "")
        lines.append(f"{definition.label} · {role}{bucket} · from {table}")
    for item in spec.get("filters", []):
        definition = FIELDS.get(item.get("key"))
        if definition is None:
            continue
        if item.get("op") == "in":
            lines.append(f"Filter: {definition.label} is one of {', '.join(item['values'])}")
        else:
            low, high = item.get("min"), item.get("max")
            lines.append(f"Filter: {definition.label} from {'any' if low is None else low} "
                         f"to {'any' if high is None else high}")
    sort = spec.get("sort") or {}
    if sort.get("field"):
        lines.append(f"Sorted by {sort['field']} ({'descending' if sort.get('dir') == 'desc' else 'ascending'})")
    if spec.get("limit"):
        lines.append(f"Limited to {spec['limit']} rows")
    lines.append("Stations: " + ("nearest station only" if spec.get("nearest_only", True)
                                 else "every nearby station"))
    return lines
