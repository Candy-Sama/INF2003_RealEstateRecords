"""Saved search management UI."""

from typing import Any

import streamlit as st

from app.app_modules import saved_searches_store as store
from app.app_modules.ui_feedback import queue_feedback, show_feedback

from .search_ui import render_filter_fields, seed_filter_widgets


def render_saved_searches(connection: Any, mongo_database: Any, agent_id: int) -> None:
    st.subheader("Saved searches")
    show_feedback("saved_searches")
    with st.spinner("Loading saved searches…"):
        saved_searches = store.list_searches(mongo_database, agent_id)
    if not saved_searches:
        st.info("You have no saved searches yet. Run a transaction search and save it.")
        return

    st.dataframe(
        [
            {
                "Name": saved["name"],
                "Town": saved["filters"].get("town") or "Any",
                "Flat type": saved["filters"].get("flat_type") or "Any",
                "Min price": saved["filters"].get("min_price") or "Any",
                "Max price": saved["filters"].get("max_price") or "Any",
                "From": saved["filters"].get("start_date") or "Any",
                "To": saved["filters"].get("end_date") or "Any",
                "Created": saved.get("created_at", ""),
            }
            for saved in saved_searches
        ],
        width="stretch",
        hide_index=True,
    )
    searches_by_id = {str(saved["_id"]): saved for saved in saved_searches}
    selection_key = "saved_search_selection"
    if st.session_state.get(selection_key) not in searches_by_id:
        st.session_state.pop(selection_key, None)
    selected_id = st.selectbox(
        "Choose a saved search",
        list(searches_by_id),
        format_func=lambda search_id: searches_by_id[search_id]["name"],
        key=selection_key,
    )
    selected = searches_by_id[selected_id]
    load_col, delete_col = st.columns(2)
    with load_col:
        if st.button("Run saved search", type="primary"):
            st.session_state["pending_search_filters"] = selected["filters"]
            st.session_state["pending_tab"] = "Search & filter"
            st.rerun()

    with delete_col:
        if st.button("Delete saved search", key="danger_delete_saved_search"):
            try:
                with st.spinner("Deleting saved search…"):
                    deleted = store.delete_search(mongo_database, agent_id, selected["_id"])
            except ValueError as error:
                st.error(str(error))
            else:
                if deleted:
                    queue_feedback("saved_searches", "Saved search deleted.")
                else:
                    queue_feedback(
                        "saved_searches", "That saved search no longer exists.", kind="warning"
                    )
                st.rerun()

    prefix = f"saved_search_edit_{selected_id}"
    seed_filter_widgets(prefix, selected["filters"])
    with st.form(f"{prefix}_form"):
        name = st.text_input("Search name", value=selected["name"], key=f"{prefix}_name")
        filters = render_filter_fields(connection, prefix)
        submitted = st.form_submit_button("Save changes", type="primary")

    if submitted:
        try:
            with st.spinner("Updating saved search…"):
                changed = store.update_search(mongo_database, agent_id, selected["_id"], name, filters)
        except ValueError as error:
            st.error(str(error))
        else:
            if changed is None:
                queue_feedback(
                    "saved_searches", "That saved search no longer exists.", kind="warning"
                )
                st.rerun()
            elif changed:
                queue_feedback("saved_searches", "Saved search updated.")
                st.rerun()
            else:
                st.info("This saved search already has those settings.")
