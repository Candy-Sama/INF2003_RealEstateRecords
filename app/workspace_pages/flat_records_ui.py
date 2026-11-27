"""Flat record browsing and maintenance UI."""

from datetime import date
from typing import Any

import streamlit as st

from app import repository
from app.app_modules.table_columns import FLAT_RECORD_COLUMNS
from app.app_modules.ui_feedback import queue_feedback, show_feedback

from .nearby_ui import go_to_nearby


def flat_values_form(
    places: list[dict[str, Any]],
    options: dict[str, list[str]],
    prefix: str,
    initial: dict[str, Any] | None = None,
) -> dict[str, Any]:
    initial = initial or {}
    place_ids = [place["block_id"] for place in places]
    block_labels = {
        place["block_id"]: (
            f'{place["block_number"]} {place["road_name"]}, {place["town"]} '
            f'(block {place["block_id"]})'
        )
        for place in places
    }
    selected_block = initial.get("block_id")
    block_index = place_ids.index(selected_block) if selected_block in place_ids else 0

    def index_of(field: str) -> int:
        choices = options[field]
        return choices.index(initial[field]) if initial.get(field) in choices else 0

    left, right = st.columns(2)
    flat_type = left.selectbox(
        "Flat type", options["flat_type"],
        index=index_of("flat_type"), key=f"{prefix}_flat_type",
    )
    flat_model = right.selectbox(
        "Flat model", options["flat_model"],
        index=index_of("flat_model"), key=f"{prefix}_flat_model",
    )
    storey_range = left.selectbox(
        "Storey range", options["storey_range"],
        index=index_of("storey_range"), key=f"{prefix}_storey",
    )
    floor_area = right.number_input(
        "Floor area (sqm)",
        min_value=0.01,
        max_value=1000.0,
        value=float(initial.get("floor_area_sqm") or 1),
        step=0.01,
        format="%.2f",
        key=f"{prefix}_area",
    )
    block_id = st.selectbox(
        "Block / location",
        options=place_ids,
        index=block_index,
        format_func=lambda value: block_labels[value],
        key=f"{prefix}_block",
    )
    left, right = st.columns(2)
    lease_start = left.number_input(
        "Lease commencement year",
        min_value=1900,
        max_value=date.today().year,
        value=int(initial.get("lease_commence_date") or 2000),
        key=f"{prefix}_lease",
    )
    remaining_lease = right.number_input(
        "Remaining lease (months)",
        min_value=0,
        max_value=1200,
        value=int(initial.get("remaining_lease_months") or 0),
        key=f"{prefix}_remaining",
    )
    return {
        "flat_type": flat_type,
        "flat_model": flat_model,
        "storey_range": storey_range,
        "floor_area_sqm": floor_area,
        "block_id": block_id,
        "lease_commence_date": lease_start,
        "remaining_lease_months": remaining_lease,
    }


def render_flat_management(connection: Any, is_admin: bool) -> None:
    st.subheader("Flat records")
    if is_admin:
        st.caption("Administrator access: you can create and edit flat records.")
    else:
        st.caption("Flat records are read-only for agent accounts.")
    show_feedback("flat_records")
    with st.spinner("Counting flat records…"):
        total_flats = repository.count_flats(connection)
    page_size = 100
    page_count = max(1, (total_flats + page_size - 1) // page_size)
    if st.session_state.get("flat_records_page", 1) > page_count:
        st.session_state["flat_records_page"] = page_count
    details, pager = st.columns([4, 1], vertical_alignment="center")
    page = pager.number_input(
        "Page",
        min_value=1,
        max_value=page_count,
        step=1,
        key="flat_records_page",
    )
    with st.spinner("Loading flat records…"):
        flats = repository.list_flats(
            connection, limit=page_size, offset=(int(page) - 1) * page_size
        )
    st.session_state.setdefault("mf_nonce", 0)
    if flats:
        details.caption(f"{total_flats:,} flat records · Page {page:,} of {page_count:,}")
        details.markdown("Select a row to see its nearby MRT and LRT stations.")
        event = st.dataframe(
            flats, width="stretch",
            hide_index=True,
            column_config=FLAT_RECORD_COLUMNS,
            on_select="rerun",
            selection_mode="single-row",
            key=f'mf_table_{st.session_state["mf_nonce"]}',
        )
        if event.selection.rows:
            go_to_nearby(flats[event.selection.rows[0]]["flat_id"], "Flat records")
            st.session_state["mf_nonce"] += 1  # reset selection for when you come back
            st.rerun()
    else:
        st.info("No flat records are currently available.")

    if not is_admin:
        with st.form("view_flat_form"):
            flat_search_id = st.number_input(
                "Look up a flat by ID",
                min_value=1,
                step=1,
                key="view_flat_search_id",
            )
            view_submitted = st.form_submit_button("Find flat", type="primary")
        if view_submitted:
            st.session_state["view_flat_selected_id"] = int(flat_search_id)
        selected_id = st.session_state.get("view_flat_selected_id")
        if selected_id is not None:
            with st.spinner("Looking up flat…"):
                selected_flat = repository.get_flat(connection, selected_id)
            if selected_flat is None:
                st.warning("No flat record exists with that ID.")
            else:
                st.dataframe(
                    [selected_flat], width="stretch", hide_index=True,
                    column_config=FLAT_RECORD_COLUMNS,
                )
        return

    action = st.radio(
        "Flat record action",
        ["Create", "Update"],
        horizontal=True,
        label_visibility="collapsed",
        key="flat_management_action",
    )
    if action == "Create":
        with st.spinner("Loading flat form options…"):
            places = repository.list_places(connection)
            flat_options = repository.list_flat_options(connection)
        if not places:
            st.warning("Add records to the `place` table before creating a flat.")
            return
        with st.form("create_flat_form"):
            values = flat_values_form(places, flat_options, "create")
            submitted = st.form_submit_button("Create flat", type="primary")
        if submitted:
            if not all(
                values[field] for field in ("flat_type", "flat_model", "storey_range")
            ):
                st.error("Complete the flat type, model, and storey range.")
            else:
                with st.spinner("Creating flat record…"):
                    repository.create_flat(connection, values)
                queue_feedback("flat_records", "Flat record created.")
                st.rerun()
        return

    with st.form("find_edit_flat_form"):
        edit_search_id = st.number_input(
            "Flat record ID",
            min_value=1,
            step=1,
            key="edit_flat_search_id",
        )
        find_edit_submitted = st.form_submit_button("Find record")
    if find_edit_submitted:
        st.session_state["edit_flat_selected_id"] = int(edit_search_id)

    selected_id = st.session_state.get("edit_flat_selected_id")
    if selected_id is None:
        st.info("Enter a flat record ID to load its editable fields.")
        return
    with st.spinner("Looking up flat…"):
        selected_flat = repository.get_flat(connection, selected_id)
    if selected_flat is None:
        st.warning("No flat record exists with that ID.")
        return
    with st.spinner("Loading flat form options…"):
        places = repository.list_places(connection)
        flat_options = repository.list_flat_options(connection)
    if not places:
        st.warning("No place records are available.")
        return
    with st.form(f"edit_flat_form_{selected_id}"):
        values = flat_values_form(
            places, flat_options, f"edit_{selected_id}", selected_flat
        )
        submitted = st.form_submit_button("Save changes", type="primary")
    if submitted:
        if not all(
            values[field] for field in ("flat_type", "flat_model", "storey_range")
        ):
            st.error("Complete the flat type, model, and storey range.")
        else:
            with st.spinner("Saving flat record…"):
                repository.update_flat(connection, selected_id, values)
            queue_feedback("flat_records", "Flat record updated.")
            st.rerun()
