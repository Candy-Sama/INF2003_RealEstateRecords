# Edit and index Saved searches

This walkthrough adds editing to **Saved searches** and measures the MongoDB query that lists an agent’s searches. MongoDB stores each search’s name and nested filters. **Run saved search** restores those filters and executes the normal MySQL resale query against current data.

Start from the repo root with the app’s `.venv`, `.env`, and local databases set up. Use a disposable database for the benchmark and verification steps. [App setup](../README.md#run-the-application)

## 1. Keep the existing document format

An existing `saved_searches` document has this shape. MongoDB generates `_id` when the app inserts a document.

```json
{
  "agent_id": 7,
  "name": "Tampines 4-room resale",
  "filters": {
    "town": "TAMPINES",
    "flat_type": "4 ROOM",
    "min_price": null,
    "max_price": 700000,
    "start_date": "2025-01-01",
    "end_date": null
  },
  "created_at": "2026-11-27"
}
```

Keep `created_at` as a `YYYY-MM-DD` string so existing and new documents sort together. Sort by `created_at` and then `_id`, both descending, to give searches created on the same date a consistent order. The edit updates the name and filters. The app represents unrestricted town and flat type as empty strings and unspecified limits as `null`.

## 2. Put MongoDB operations in one module

Create `app/app_modules/saved_searches_store.py`. The listing uses the signed-in agent ID, and each update or delete matches both the search ID and that agent ID. A successfully matched update can have `modified_count == 0` when the submitted values equal the stored values.

```python
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
```

The filter validation assumes values produced by the app’s typed widgets. The reusable filters contain money bounds as integers and transaction dates as ISO strings. Add type checks at the boundary if another feature starts accepting raw filter values from an external API.

## 3. Reuse the search form and validation

In `app/workspace_pages/search_ui.py`, add this import beside the other app imports.

```python
from app.app_modules import saved_searches_store as store
```

Replace the `apply_saved_search_filters` function with the block below. Leave the existing `filters_from_form` in place. Both the regular form and the edit form can then use the same widget defaults. The edit form uses separate keys for each saved search.

```python
def seed_filter_widgets(
    prefix: str, filters: dict[str, Any], *, replace: bool = False
) -> None:
    values = {
        "town": filters.get("town") or "Any",
        "flat_type": filters.get("flat_type") or "Any",
        "min_price": filters.get("min_price") or 0,
        "max_price": filters.get("max_price") or 0,
        "start_date": date.fromisoformat(filters["start_date"]) if filters.get("start_date") else None,
        "end_date": date.fromisoformat(filters["end_date"]) if filters.get("end_date") else None,
    }
    for name, value in values.items():
        key = f"{prefix}_{name}"
        if replace:
            st.session_state[key] = value
        else:
            st.session_state.setdefault(key, value)


def apply_saved_search_filters(filters: dict[str, Any]) -> None:
    seed_filter_widgets("filter", filters, replace=True)
    st.session_state["execute_saved_search"] = True
```

Add the shared field renderer after `filters_from_form`. Including the saved option in each dropdown preserves the original filter if that value has disappeared from MySQL’s current choices. A search for a removed value can then correctly show zero matches.

```python
def render_filter_fields(connection: Any, prefix: str) -> dict[str, Any]:
    town_key, type_key = f"{prefix}_town", f"{prefix}_flat_type"
    towns = list(dict.fromkeys([
        "Any", *filter(None, repository.list_towns(connection)), st.session_state[town_key],
    ]))
    flat_types = list(dict.fromkeys([
        "Any", *filter(None, repository.list_flat_types(connection)), st.session_state[type_key],
    ]))

    left, right = st.columns(2)
    town = left.selectbox("Town", towns, key=town_key)
    flat_type = right.selectbox("Flat type", flat_types, key=type_key)
    left, right = st.columns(2)
    min_price = left.number_input(
        "Minimum price (0 = no minimum)", min_value=0, max_value=20_000_000,
        step=10_000, key=f"{prefix}_min_price",
    )
    max_price = right.number_input(
        "Maximum price (0 = no maximum)", min_value=0, max_value=20_000_000,
        step=10_000, key=f"{prefix}_max_price",
    )
    left, right = st.columns(2)
    start = left.date_input("Transaction from", value=None, key=f"{prefix}_start_date")
    end = right.date_input("Transaction to", value=None, key=f"{prefix}_end_date")
    return filters_from_form(town, flat_type, min_price, max_price, start, end)
```

Inside `render_search`, replace the setup and field definitions between the page heading and `auto_run_saved_search` with this block.

```python
    seed_filter_widgets("filter", {})
    with st.form("transaction_search_form"):
        filters = render_filter_fields(connection, "filter")
        search_submitted = st.form_submit_button("Search records", type="primary")
```

Inside `if search_submitted or auto_run_saved_search`, replace the existing call to `filters_from_form` and the price check with this block. Keep the MySQL query and assignments immediately below it.

```python
        try:
            store.validate_filter_ranges(filters)
        except ValueError as error:
            st.error(str(error))
            return
```

Finally, replace the body under `if save_submitted:` with the following. Using `last_search_filters` saves the criteria that produced the displayed results, even if the user has typed other values into the search form.

```python
            try:
                store.create_search(
                    mongo_database, agent_id, search_name, st.session_state["last_search_filters"]
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Search saved.")
```

## 4. Add the edit form to Saved searches

Replace `app/workspace_pages/saved_searches_ui.py` with the example below. It uses the shared feedback functions for messages that need to survive the rerun.

```python
from typing import Any

import streamlit as st

from app.app_modules import saved_searches_store as store
from app.app_modules.ui_feedback import queue_feedback, show_feedback
from .search_ui import render_filter_fields, seed_filter_widgets


def render_saved_searches(connection: Any, mongo_database: Any, agent_id: int) -> None:
    st.subheader("Saved searches")
    show_feedback("saved_searches")
    saved_searches = store.list_searches(mongo_database, agent_id)
    if not saved_searches:
        st.info("You have no saved searches yet. Run a transaction search and save it.")
        return

    rows = []
    for saved in saved_searches:
        filters = saved["filters"]
        rows.append({
            "Name": saved["name"],
            "Town": filters.get("town") or "Any",
            "Flat type": filters.get("flat_type") or "Any",
            "Min price": filters.get("min_price") or "Any",
            "Max price": filters.get("max_price") or "Any",
            "From": filters.get("start_date") or "Any",
            "To": filters.get("end_date") or "Any",
            "Created": saved["created_at"],
        })
    st.dataframe(rows, width="stretch", hide_index=True)

    searches_by_id = {str(saved["_id"]): saved for saved in saved_searches}
    selection_key = "saved_search_selection"
    if st.session_state.get(selection_key) not in searches_by_id:
        st.session_state.pop(selection_key, None)
    selected_id = st.selectbox(
        "Choose a saved search", list(searches_by_id),
        format_func=lambda value: searches_by_id[value]["name"], key=selection_key,
    )
    selected = searches_by_id[selected_id]

    if st.button("Run saved search", type="primary"):
        st.session_state["pending_search_filters"] = selected["filters"]
        st.session_state["pending_tab"] = "Search & filter"
        st.rerun()

    prefix = f"saved_search_edit_{selected_id}"
    seed_filter_widgets(prefix, selected["filters"])
    with st.form(f"{prefix}_form"):
        name = st.text_input("Search name", value=selected["name"], key=f"{prefix}_name")
        filters = render_filter_fields(connection, prefix)
        save = st.form_submit_button("Save changes")

    if save:
        try:
            updated = store.update_search(mongo_database, agent_id, selected["_id"], name, filters)
        except ValueError as error:
            st.error(str(error))
        else:
            if updated is None:
                queue_feedback("saved_searches", "That saved search is no longer available.", kind="warning")
            elif updated:
                queue_feedback("saved_searches", "Saved search updated.")
            else:
                queue_feedback("saved_searches", "No changes to save.", kind="info")
            st.rerun()

    if st.button("Delete saved search"):
        try:
            deleted = store.delete_search(mongo_database, agent_id, selected["_id"])
        except ValueError as error:
            st.error(str(error))
        else:
            if deleted:
                queue_feedback("saved_searches", "Saved search deleted.")
            else:
                queue_feedback("saved_searches", "That saved search is no longer available.", kind="warning")
            st.rerun()
```

In `app/streamlit_app.py`, update the call inside the **Saved searches** branch so the edit form can load MySQL town and flat-type choices.

```python
render_saved_searches(connection, mongo_database, agent["agent_id"])
```

The existing navigation reads `pending_search_filters` and calls `apply_saved_search_filters` before rendering the Search page. That restores the widgets and triggers `repository.search_transactions`. [Workspace routing](../app/streamlit_app.py) · [MySQL search query](../app/repository.py)

## 5. Create the index once during setup

Run this from the repo root using the database configured in `.env`. Add it to your project setup instructions once implemented. An account running this setup step needs permission to create indexes.

```powershell
@'
from app.app_modules.database.database import get_mongodb_client, get_mongodb_database_name
from app.app_modules.saved_searches_store import ensure_index

with get_mongodb_client() as client:
    print(ensure_index(client[get_mongodb_database_name()]))
'@ | .\.venv\Scripts\python.exe -
```

The index starts with the equality filter (`agent_id`) and then follows the list’s sort (`created_at`, `_id`). An agent’s records can be read in list order from one part of the index. The `_id` index MongoDB creates automatically supports lookups by identifier. [MongoDB compound indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)

## 6. Measure the list before and after indexing

Use a disposable local MongoDB setup as configured in `.env`. Run the following from the repo root. The script creates a uniquely named temporary collection, inserts 20,000 synthetic saved searches spread evenly among 200 agents, and drops that temporary collection in `finally`. Both runs use the same filter, sort, and documents. The output shows the plans MongoDB chooses. [MongoDB explain command](https://www.mongodb.com/docs/manual/reference/command/explain/)

```powershell
@'
from datetime import date, timedelta
from uuid import uuid4

from app.app_modules.database.database import get_mongodb_client, get_mongodb_database_name
from app.app_modules.saved_searches_store import (
    SAVED_SEARCH_INDEX, SAVED_SEARCH_INDEX_NAME, SAVED_SEARCH_SORT,
)


def stages(node):
    if isinstance(node, dict):
        if "stage" in node:
            yield node["stage"]
        for child in node.values():
            yield from stages(child)
    elif isinstance(node, list):
        for child in node:
            yield from stages(child)


def measure(database, searches, label):
    owner = {"agent_id": 42}
    result = database.command({
        "explain": {"find": searches.name, "filter": owner, "sort": dict(SAVED_SEARCH_SORT)},
        "verbosity": "executionStats",
    })
    stats = result["executionStats"]
    print(label, {
        "planStages": list(stages(result["queryPlanner"]["winningPlan"])),
        "nReturned": stats["nReturned"],
        "totalKeysExamined": stats["totalKeysExamined"],
        "totalDocsExamined": stats["totalDocsExamined"],
        "executionTimeMillis": stats["executionTimeMillis"],
    })
    return [doc["_id"] for doc in searches.find(owner).sort(SAVED_SEARCH_SORT)]


with get_mongodb_client() as client:
    database = client[get_mongodb_database_name()]
    searches = database[f"tmp_saved_search_bench_{uuid4().hex}"]
    try:
        searches.insert_many([
            {
                "agent_id": agent,
                "name": f"Benchmark {number}",
                "filters": {"town": "TAMPINES", "flat_type": "4 ROOM"},
                "created_at": (date(2026, 1, 1) + timedelta(days=number)).isoformat(),
            }
            for agent in range(1, 201)
            for number in range(100)
        ])
        before = measure(database, searches, "before")
        searches.create_index(SAVED_SEARCH_INDEX, name=SAVED_SEARCH_INDEX_NAME)
        after = measure(database, searches, "after")
        assert len(before) == 100 and before == after
    finally:
        searches.drop()
'@ | .\.venv\Scripts\python.exe -
```

Record the returned documents, examined documents and keys, and the actual plan stages. Expect 100 results in both runs. Typically the first plan scans the collection and sorts the matches, and the second uses the index and fetches the matching documents. Check the reported plan and use the measured counts in the report. Millisecond readings can be noisy on a local fixture. [MongoDB explain result fields](https://www.mongodb.com/docs/manual/reference/explain-results/)

## 7. Verify and demonstrate the feature

1. Start the app with `.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py`. Sign in as agent A, search for **TAMPINES**, **4 ROOM**, and save the result criteria as **Tampines 4-room resale**.
2. Open **Saved searches**. Edit the name, maximum price and start date. Reload the page and check that those values are still displayed. Open any pre-existing saved search to check the edit form loads its filters too.
3. Try a minimum price above the maximum and a start date after the end date. Each attempt should show a validation message. Reload the saved search to verify its stored values survived both attempts.
4. Click **Run saved search**. Check the Search widgets match the stored values and compare the results with a manually run search using the same filters.
5. Sign in as agent B on the same browser and verify agent A’s search and last run are absent. Sign back in as agent A, delete the search, and check that the list updates with a deletion confirmation.
6. Run `.\.venv\Scripts\python.exe -m unittest discover -s test -v`. Run the MongoDB benchmark above for live index evidence.
7. For the video, show one saved document, edit a filter, and rerun it. Then show the measured MongoDB listing plan alongside the existing MySQL query-plan evidence. MongoDB’s numbers describe listing documents and MySQL’s numbers describe retrieving market data. Compare how each index serves its own workload, and discuss the additional storage and write cost of indexing. [Existing MySQL benchmarks](../setup/mysql_upgrade.md#observed-results)
