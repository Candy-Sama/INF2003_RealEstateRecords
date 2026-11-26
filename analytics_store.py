from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import analytics_builder
import analytics_sql
from analytics_defaults import DEFAULT_CARDS

COLLECTION = "analytics_cards"
META_COLLECTION = "analytics_meta"

DISPLAY_TYPES = ("table", "kpi", "bar", "line", "area", "scatter", "heatmap")
WIDTHS = ("half", "full")
NUMBER_FORMATS = ("auto", "currency", "integer", "percent")
MAPPING_KEYS = ("x", "y", "color", "value")
REQUIRED_ROLES = {
    "table": (),
    "kpi": (),
    "bar": ("x", "y"),
    "line": ("x", "y"),
    "area": ("x", "y"),
    "scatter": ("x", "y"),
    "heatmap": ("x", "y", "value"),
}
MAX_TITLE = 80
MAX_DESCRIPTION = 300
MAX_COLUMN_NAME = 128

# text helpers
def clean_text(value: Any, max_len: int, *, label: str = "Text") -> str:
    """Strip control characters and enforce a length limit."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    text = "".join(ch for ch in value if ch.isprintable() or ch == "\n").strip()
    if len(text) > max_len:
        raise ValueError(f"{label} must be at most {max_len} characters.")
    return text


def escape_markdown(text: Any) -> str:
    """Make user text safe to show through st.markdown / st.caption / st.error.

    Streamlit already refuses raw HTML in markdown; this also neutralises links,
    images, emphasis, LaTeX ($) and emoji shortcodes (:x:) inside user text.
    """
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$&:])", r"\\\1", str(text))


# validation
def clean_card(data: dict[str, Any]) -> dict[str, Any]:
    """Validate user input and return only the fields we store."""
    if not isinstance(data, dict):
        raise ValueError("Invalid card.")

    title = clean_text(data.get("title"), MAX_TITLE, label="Title").replace("\n", " ")
    if not title:
        raise ValueError("Give the card a title.")
    description = clean_text(data.get("description") or "", MAX_DESCRIPTION, label="Description")
    # A card made in the visual builder always stores the SQL the builder generates,
    # so the saved settings and the saved query can never disagree.
    raw_builder = data.get("builder")
    if raw_builder is not None:
        builder_spec = analytics_builder.clean_spec(raw_builder)
        sql = analytics_sql.validate_query(analytics_builder.build_sql(builder_spec))
        source = "builder"
    else:
        builder_spec = None
        sql = analytics_sql.validate_query(data.get("sql"))
        source = "sql"

    display_type = data.get("display_type")
    if display_type not in DISPLAY_TYPES:
        raise ValueError("Choose a display type.")
    width = data.get("width", "half")
    if width not in WIDTHS:
        raise ValueError("Card width must be half or full.")
    number_format = data.get("number_format", "auto")
    if number_format not in NUMBER_FORMATS:
        raise ValueError("Unknown number format.")

    raw_mapping = data.get("mapping") or {}
    if not isinstance(raw_mapping, dict):
        raise ValueError("Invalid column mapping.")
    mapping: dict[str, Any] = {}
    for key in MAPPING_KEYS:
        value = raw_mapping.get(key)
        if value in (None, ""):
            mapping[key] = None
        elif isinstance(value, str) and len(value) <= MAX_COLUMN_NAME and value.isprintable():
            mapping[key] = value
        else:
            raise ValueError(f"Invalid column for '{key}'.")
    horizontal = raw_mapping.get("horizontal", False)
    if not isinstance(horizontal, bool):
        raise ValueError("Invalid orientation.")
    mapping["horizontal"] = horizontal

    for role in REQUIRED_ROLES[display_type]:
        if not mapping.get(role):
            raise ValueError(f"Choose a column for '{role}'.")

    return {
        "title": title,
        "description": description,
        "sql": sql,
        "display_type": display_type,
        "width": width,
        "number_format": number_format,
        "mapping": mapping,
        "source": source,
        "builder": builder_spec,
    }

# crud
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _object_id(card_id: Any):
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        return ObjectId(str(card_id))
    except (InvalidId, TypeError):
        raise ValueError("Unknown card.") from None


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "sql": doc.get("sql", ""),
        "display_type": doc.get("display_type", "table"),
        "width": doc.get("width", "half"),
        "number_format": doc.get("number_format", "auto"),
        "mapping": doc.get("mapping") or {},
        "source": doc.get("source", "sql"),
        "builder": doc.get("builder"),
        "seed_key": doc.get("seed_key"),
    }


def ensure_indexes(db: Any) -> None:
    cards = db[COLLECTION]
    cards.create_index([("agent_id", 1), ("position", 1)])
    cards.create_index(
        [("agent_id", 1), ("seed_key", 1)],
        unique=True,
        partialFilterExpression={"seed_key": {"$type": "string"}},
    )
    db[META_COLLECTION].create_index("agent_id", unique=True)


def list_cards(db: Any, agent_id: int) -> list[dict[str, Any]]:
    cursor = db[COLLECTION].find({"agent_id": int(agent_id)}).sort(
        [("position", 1), ("_id", 1)]
    )
    return [_public(doc) for doc in cursor]


def _next_position(db: Any, agent_id: int) -> int:
    last = db[COLLECTION].find_one({"agent_id": int(agent_id)}, sort=[("position", -1)])
    return int(last.get("position", 0)) + 1 if last else 0


def create_card(db: Any, agent_id: int, data: dict[str, Any]) -> str:
    card = clean_card(data)
    now = _now()
    doc = {
        **card,
        "agent_id": int(agent_id),
        "position": _next_position(db, agent_id),
        "created_at": now,
        "updated_at": now,
    }
    return str(db[COLLECTION].insert_one(doc).inserted_id)


def update_card(db: Any, agent_id: int, card_id: str, data: dict[str, Any]) -> None:
    card = clean_card(data)
    result = db[COLLECTION].update_one(
        {"_id": _object_id(card_id), "agent_id": int(agent_id)},
        {"$set": {**card, "updated_at": _now()}},
    )
    if result.matched_count == 0:
        raise ValueError("That card no longer exists.")


def delete_card(db: Any, agent_id: int, card_id: str) -> bool:
    result = db[COLLECTION].delete_one(
        {"_id": _object_id(card_id), "agent_id": int(agent_id)}
    )
    return result.deleted_count > 0


def duplicate_card(db: Any, agent_id: int, card_id: str) -> str:
    doc = db[COLLECTION].find_one({"_id": _object_id(card_id), "agent_id": int(agent_id)})
    if doc is None:
        raise ValueError("That card no longer exists.")
    copy = _public(doc)
    copy["title"] = f"Copy of {copy['title']}"[:MAX_TITLE]
    if copy["source"] != "builder":
        copy["builder"] = None
    return create_card(db, agent_id, copy)  # no seed_key, so it is an ordinary card


# defaults
def _insert_missing_defaults(db: Any, agent_id: int) -> int:
    base = _next_position(db, agent_id)
    added = 0
    now = _now()
    for offset, default in enumerate(DEFAULT_CARDS):
        card = clean_card(default)
        result = db[COLLECTION].update_one(
            {"agent_id": int(agent_id), "seed_key": default["seed_key"]},
            {"$setOnInsert": {
                **card,
                "position": base + offset,
                "created_at": now,
                "updated_at": now,
            }},
            upsert=True,
        )
        if result.upserted_id is not None:
            added += 1
    return added


def seed_defaults(db: Any, agent_id: int) -> int:
    """Give a new agent their copies of the default cards, once."""
    meta = db[META_COLLECTION]
    if meta.find_one({"agent_id": int(agent_id)}):
        return 0
    added = _insert_missing_defaults(db, agent_id)
    meta.update_one(
        {"agent_id": int(agent_id)}, {"$set": {"seeded_at": _now()}}, upsert=True
    )
    return added


def restore_defaults(db: Any, agent_id: int) -> int:
    """Re-add any default card the agent has deleted. Returns how many were added."""
    return _insert_missing_defaults(db, agent_id)