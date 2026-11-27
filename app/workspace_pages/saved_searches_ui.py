"""Saved search management UI."""

from typing import Any

import streamlit as st


def render_saved_searches(mongo_database: Any, agent_id: int) -> None:
    st.subheader("Saved searches")
    collection = mongo_database["saved_searches"]
    saved_searches = list(
        collection.find({"agent_id": agent_id}).sort("created_at", -1)
    )
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
                "Created": saved.get("created_at", ""),
            }
            for saved in saved_searches
        ],
        width="stretch",
        hide_index=True,
    )
    saved_ids = [str(saved["_id"]) for saved in saved_searches]
    selected_id = st.selectbox(
        "Choose a saved search",
        saved_ids,
        format_func=lambda value: next(
            saved["name"] for saved in saved_searches if str(saved["_id"]) == value
        ),
    )
    selected = next(saved for saved in saved_searches if str(saved["_id"]) == selected_id)
    load_col, rename_col, delete_col = st.columns(3)

    with load_col:
        if st.button("Run saved search", type="primary"):
            st.session_state["pending_search_filters"] = selected["filters"]
            st.session_state["pending_tab"] = "Search & filter"
            st.rerun()

    with rename_col:
        with st.form("rename_saved_search_form"):
            new_name = st.text_input("Rename", value=selected["name"])
            rename_submitted = st.form_submit_button("Update name")
        if rename_submitted:
            if not new_name.strip():
                st.error("Enter a name for this saved search.")
            else:
                collection.update_one(
                    {"_id": selected["_id"], "agent_id": agent_id},
                    {"$set": {"name": new_name.strip()}},
                )
                st.success("Saved search renamed.")
                st.rerun()

    with delete_col:
        if st.button("Delete saved search"):
            collection.delete_one({"_id": selected["_id"], "agent_id": agent_id})
            st.success("Saved search deleted.")
            st.rerun()
