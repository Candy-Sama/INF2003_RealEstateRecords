"""Resale transaction search and filter UI."""

from datetime import date
from typing import Any

import streamlit as st

from app import repository
from app.app_modules import saved_searches_store as store
from app.app_modules.table_columns import RESALE_COLUMNS


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


def filters_from_form(
    town: str,
    flat_type: str,
    minimum_price: int,
    maximum_price: int,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    return {
        "town": "" if town == "Any" else town,
        "flat_type": "" if flat_type == "Any" else flat_type,
        "min_price": minimum_price or None,
        "max_price": maximum_price or None,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }

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

def render_search(connection: Any, mongo_database: Any, agent_id: int) -> None:
    st.subheader("Search resale transactions")
    seed_filter_widgets("filter", {})

    with st.form("transaction_search_form"):
        filters = render_filter_fields(connection, "filter")
        search_submitted = st.form_submit_button("Search records", type="primary")

    auto_run_saved_search = st.session_state.pop("execute_saved_search", False)
    if search_submitted or auto_run_saved_search:
        try:
            store.validate_filter_ranges(filters)
        except ValueError as error:
            st.error(str(error))
            return
        with st.spinner("Searching resale transactions…"):
            results = repository.search_transactions(connection, filters)
        st.session_state["last_search_filters"] = filters
        st.session_state["last_search_results"] = results
        st.session_state["search_results_revision"] = st.session_state.get("search_results_revision", 0) + 1

    if "last_search_results" in st.session_state:
        results = st.session_state["last_search_results"]
        with st.container(key=f'search_results_{st.session_state.get("search_results_revision", 0)}'):
            if results:
                count = len(results)
                if count >= 1000:
                    st.caption(f"Showing the first {count:,} matching transactions.")
                else:
                    noun = "transaction" if count == 1 else "transactions"
                    st.caption(f"{count:,} matching {noun}.")
                st.dataframe(results, width="stretch", hide_index=True, column_config=RESALE_COLUMNS)
            else:
                st.info("No transactions match these filters.")
        with st.form("save_search_form"):
            search_name = st.text_input("Name this search", placeholder="e.g. 4-room flats in Tampines")
            save_submitted = st.form_submit_button("Save search", type="primary")
        if save_submitted:
            try:
                with st.spinner("Saving search…"):
                    store.create_search(
                        mongo_database,
                        agent_id,
                        search_name,
                        st.session_state["last_search_filters"],
                    )
            except ValueError as error:
                st.error(str(error))
            else:
                with st.container(key="action_success_save_search"):
                    st.success("Search saved.")
