"""Nearby station filtering and flat comparisons UI."""

from contextlib import closing
from typing import Any

import mysql.connector
import streamlit as st

from app import repository
from app.app_modules.database.database import get_mysql_connection
from app.app_modules.ui_feedback import show_database_error

from . import nearby_function


NEARBY_PAGE_SIZE = 100
DISTANCE_BANDS = {"≤ 300 m": 300, "≤ 500 m": 500, "≤ 1 km": 1000}
CLEAR_FILTERS = "✕ Clear filters"
CLEAR_SELECTION = "✕ Clear selection"
FLAT_TABLE_COLUMNS = {
    "flat_id": st.column_config.NumberColumn("Flat ID"),
    "flat_type": "Flat type",
    "storey_range": "Storey",
    "town": "Town",
    "block_number": "Block",
    "road_name": "Road",
    "station_count": st.column_config.NumberColumn("Stations"),
    "shared_stations": st.column_config.NumberColumn("Shared stations"),
    "nearest_m": st.column_config.NumberColumn("Nearest (m)"),
    "nearby_stations": st.column_config.TextColumn("Nearby stations", width="large"),
}


def go_to_nearby(flat_id: int, origin: str) -> None:
    """Focus a flat and ask the main tab bar to switch to Nearby stations."""
    st.session_state["nearby_focus"] = {"flat_id": int(flat_id), "origin": origin}
    st.session_state["pending_tab"] = "Nearby stations"


def clear_nearby_state() -> None:
    """Back to state 0. Runs as a callback, so it can reset widget keys."""
    st.session_state["nb_transport"] = []
    st.session_state["nb_lines"] = []
    st.session_state["nb_stations"] = []
    st.session_state["nb_band"] = None
    st.session_state["nb_clear"] = None
    st.session_state.pop("nearby_focus", None)
    st.session_state["nb_nonce"] = st.session_state.get("nb_nonce", 0) + 1


@st.fragment
def render_nearby_tab() -> None:
    try:
        with closing(get_mysql_connection()) as connection:
            render_nearby_stations(connection)
    except (mysql.connector.Error, ValueError) as error:
        show_database_error(error)


def render_nearby_stations(connection: Any) -> None:
    if not nearby_function.has_distance_column(connection):
        st.warning(nearby_function.MIGRATION_REQUIRED)
        return
    st.session_state.setdefault("nb_nonce", 0)
    focus = st.session_state.get("nearby_focus")

    title, clear_column = st.columns([3, 1], vertical_alignment="center")
    title.subheader("Nearby MRT / LRT stations")

    if not nearby_function.is_ready(connection):
        with st.spinner("`nearby` is empty, filling it now..."):
            filled = nearby_function.ensure_populated(connection)
        if filled is None:
            st.warning("There are no stations loaded. Run `python -m setup.import_data_script.import` first.")
            return
        st.success(f'Filled `nearby` with {filled["total_rows"]:,} rows in {filled["seconds"]} s.')

    filters: dict[str, Any] = {}
    clear_label = None
    if focus is None:
        options = repository.list_nearby_filter_options(connection)
        with st.container(border=True):
            transport = st.pills(
                "Transport type", options["transport_type"],
                selection_mode="multi", key="nb_transport",
            )
            lines = st.pills(
                "Line", options["line_name"], selection_mode="multi", key="nb_lines"
            )
            # Individual stations, narrowed by the transport type / line chosen above.
            station_labels = {
                item["station_code"]: f'{item["station_code"]} {item["station_name"]}'
                for item in options["stations"]
                if (not transport or item["transport_type"] in transport)
                and (not lines or item["line_name"] in lines)
            }
            st.session_state["nb_stations"] = [
                code for code in st.session_state.get("nb_stations", [])
                if code in station_labels
            ]
            chosen_stations = st.multiselect(
                "Station", list(station_labels), format_func=station_labels.get,
                key="nb_stations", placeholder="Search by code or name, e.g. NS10 or Admiralty",
            )
            band = st.pills(
                "Distance to station", list(DISTANCE_BANDS),
                selection_mode="single", key="nb_band",
            )
        filters = {
            "transport_types": transport or [],
            "lines": lines or [],
            "stations": chosen_stations,
            "max_distance_m": DISTANCE_BANDS.get(band) if band else None,
        }
        if transport or lines or chosen_stations or band:
            clear_label = CLEAR_FILTERS
    else:
        clear_label = CLEAR_SELECTION

    if clear_label:
        with clear_column:
            st.pills(
                "Clear", [clear_label], key="nb_clear",
                on_change=clear_nearby_state, label_visibility="collapsed",
            )

    station_ids: list[int] = []
    if focus is None:
        total = repository.count_nearby_flats(connection, filters)
        if clear_label:
            st.caption(f"{total:,} flat(s) near the selected stations or distance.")
        else:
            st.caption(f"All flat records · {total:,} flat(s).")
    else:
        selected = repository.search_nearby_flats(
            connection, {"flat_ids": [focus["flat_id"]]}, 1, 0
        )
        if not selected:
            st.warning("The selected flat no longer exists.")
            st.session_state.pop("nearby_focus", None)
            return
        station_ids = repository.get_flat_station_ids(connection, focus["flat_id"])
        origin = focus["origin"]
        if origin == "Manage flats":
            origin = "Flat records"
        with st.container(border=True):
            st.markdown(f"**Selected flat** · picked from {origin}")
            st.dataframe(
                selected, width="stretch", hide_index=True, column_config=FLAT_TABLE_COLUMNS
            )
            if not station_ids:
                st.info(
                    "This flat's block has no nearby stations yet. Use **Update addresses** "
                    "on the Address tab."
                )
            if origin == "Flat records" and st.button("← Back to Flat records"):
                st.session_state["pending_tab"] = origin
                st.rerun()
        total = repository.count_similar_flats(connection, focus["flat_id"], station_ids)
        st.markdown("**Flats near the same stations** · most shared stations first")

    # Back to page 1 whenever the filters or the selected flat change.
    signature = repr((
        focus["flat_id"] if focus else None,
        sorted(filters.get("transport_types", [])),
        sorted(filters.get("lines", [])),
        sorted(filters.get("stations", [])),
        filters.get("max_distance_m"),
    ))
    if st.session_state.get("nb_signature") != signature:
        st.session_state["nb_signature"] = signature
        st.session_state["nb_page"] = 1

    pages = max(1, -(-total // NEARBY_PAGE_SIZE))
    st.session_state["nb_page"] = min(st.session_state.get("nb_page", 1), pages)
    info, pager = st.columns([3, 1], vertical_alignment="center")
    with pager:
        page = st.number_input("Page", min_value=1, max_value=pages, step=1, key="nb_page")
    info.caption(f"Page {page} of {pages:,}")

    offset = (page - 1) * NEARBY_PAGE_SIZE
    if focus is None:
        rows = repository.search_nearby_flats(connection, filters, NEARBY_PAGE_SIZE, offset)
    else:
        rows = repository.search_similar_flats(
            connection, focus["flat_id"], station_ids, NEARBY_PAGE_SIZE, offset
        )
    if not rows:
        st.info("No flats to show.")
        return

    event = st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config=FLAT_TABLE_COLUMNS,
        on_select="rerun",
        selection_mode="single-row",
        key=f'nb_table_{st.session_state["nb_nonce"]}',
    )
    st.caption("Select a row to see flats near the same stations.")
    if event.selection.rows:
        picked = rows[event.selection.rows[0]]
        st.session_state["nearby_focus"] = {
            "flat_id": int(picked["flat_id"]),
            "origin": "Nearby stations",
        }
        st.session_state["nb_nonce"] += 1  # fresh table, so the old selection can't re-fire
        st.rerun(scope="fragment")
