"""Resale transaction search and filter UI."""

from datetime import date
from typing import Any

import streamlit as st

from app import repository


def apply_saved_search_filters(filters: dict[str, Any]) -> None:
    """Restore saved values before Streamlit creates the search widgets."""
    st.session_state["filter_town"] = filters.get("town") or "Any"
    st.session_state["filter_flat_type"] = filters.get("flat_type") or "Any"
    st.session_state["filter_min_price"] = filters.get("min_price") or 0
    st.session_state["filter_max_price"] = filters.get("max_price") or 0
    st.session_state["filter_start_date"] = (
        date.fromisoformat(filters["start_date"])
        if filters.get("start_date")
        else None
    )
    st.session_state["filter_end_date"] = (
        date.fromisoformat(filters["end_date"])
        if filters.get("end_date")
        else None
    )
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


def render_search(connection: Any, mongo_database: Any, agent_id: int) -> None:
    st.subheader("Search resale transactions")
    towns = ["Any", *[town for town in repository.list_towns(connection) if town]]
    flat_types = ["Any", *[value for value in repository.list_flat_types(connection) if value]]

    st.session_state.setdefault("filter_town", "Any")
    st.session_state.setdefault("filter_flat_type", "Any")
    st.session_state.setdefault("filter_min_price", 0)
    st.session_state.setdefault("filter_max_price", 0)
    st.session_state.setdefault("filter_start_date", None)
    st.session_state.setdefault("filter_end_date", None)
    if st.session_state["filter_town"] not in towns:
        st.session_state["filter_town"] = "Any"
    if st.session_state["filter_flat_type"] not in flat_types:
        st.session_state["filter_flat_type"] = "Any"

    with st.form("transaction_search_form"):
        left, right = st.columns(2)
        town = left.selectbox("Town", towns, key="filter_town")
        flat_type = right.selectbox("Flat type", flat_types, key="filter_flat_type")
        left, right = st.columns(2)
        minimum_price = left.number_input(
            "Minimum price (0 = no minimum)",
            min_value=0,
            max_value=20_000_000,
            step=10_000,
            key="filter_min_price",
        )
        maximum_price = right.number_input(
            "Maximum price (0 = no maximum)",
            min_value=0,
            max_value=20_000_000,
            step=10_000,
            key="filter_max_price",
        )
        left, right = st.columns(2)
        start_date = left.date_input("Transaction from", value=None, key="filter_start_date")
        end_date = right.date_input("Transaction to", value=None, key="filter_end_date")
        search_submitted = st.form_submit_button("Search records", type="primary")

    auto_run_saved_search = st.session_state.pop("execute_saved_search", False)
    if search_submitted or auto_run_saved_search:
        filters = filters_from_form(
            town, flat_type, minimum_price, maximum_price, start_date, end_date
        )
        if filters["min_price"] and filters["max_price"]:
            if filters["min_price"] > filters["max_price"]:
                st.error("Minimum price cannot exceed maximum price.")
                return
        results = repository.search_transactions(connection, filters)
        st.session_state["last_search_filters"] = filters
        st.session_state["last_search_results"] = results

    if "last_search_results" in st.session_state:
        results = st.session_state["last_search_results"]
        st.caption(f'{len(results)} matching transaction(s), up to 1,000 shown.')
        st.dataframe(results, width="stretch", hide_index=True)
        with st.form("save_search_form"):
            search_name = st.text_input("Name this search", placeholder="e.g. 4-room flats in Tampines")
            save_submitted = st.form_submit_button("Save search")
        if save_submitted:
            if not search_name.strip():
                st.error("Enter a name for this saved search.")
            else:
                collection = mongo_database["saved_searches"]
                collection.insert_one(
                    {
                        "agent_id": agent_id,
                        "name": search_name.strip(),
                        "filters": st.session_state["last_search_filters"],
                        "created_at": date.today().isoformat(),
                    }
                )
                st.success("Search saved to MongoDB.")
