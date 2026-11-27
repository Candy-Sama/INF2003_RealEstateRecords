from datetime import date
from typing import Any

from bson import ObjectId


COLLECTION = "saved_searches"
SAVED_SEARCH_SORT = [("created_at", -1), ("_id", -1)]
SAVED_SEARCH_INDEX = [("agent_id", 1), *SAVED_SEARCH_SORT]
SAVED_SEARCH_INDEX_NAME = "saved_searches_agent_created_id"


def validate_filter_ranges(filters: dict[str, Any]) -> None:
    min_price, max_price = filters.get("min_price"), filters.get("max_price")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("Minimum price cannot exceed maximum price.")
    start, end = filters.get("start_date"), filters.get("end_date")
    if start and end and date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("Start date cannot be after end date.")


def _search_fields(name: str, filters: dict[str, Any]) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("Enter a name for this saved search.")
    validate_filter_ranges(filters)
    return {"name": name, "filters": filters}


def ensure_index(database: Any) -> str:
    return database[COLLECTION].create_index(
        SAVED_SEARCH_INDEX, name=SAVED_SEARCH_INDEX_NAME
    )


def list_searches(database: Any, agent_id: int) -> list[dict[str, Any]]:
    return list(database[COLLECTION].find({"agent_id": agent_id}).sort(SAVED_SEARCH_SORT))


def create_search(database: Any, agent_id: int, name: str, filters: dict[str, Any]) -> None:
    result = database[COLLECTION].insert_one(
        {
            **_search_fields(name, filters),
            "agent_id": agent_id,
            "created_at": date.today().isoformat(),
        }
    )
    if not result.acknowledged:
        raise ValueError("The search save could not be confirmed.")


def update_search(
    database: Any, agent_id: int, search_id: ObjectId, name: str, filters: dict[str, Any]
) -> bool | None:
    result = database[COLLECTION].update_one(
        {"_id": search_id, "agent_id": agent_id},
        {"$set": _search_fields(name, filters)},
    )
    if not result.acknowledged:
        raise ValueError("The search update could not be confirmed.")
    if result.matched_count == 0:
        return None
    return result.modified_count > 0


def delete_search(database: Any, agent_id: int, search_id: ObjectId) -> bool:
    result = database[COLLECTION].delete_one({"_id": search_id, "agent_id": agent_id})
    if not result.acknowledged:
        raise ValueError("The search deletion could not be confirmed.")
    return result.deleted_count > 0