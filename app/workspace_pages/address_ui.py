"""Address and station coverage UI."""

from contextlib import closing
from typing import Any

import mysql.connector
import streamlit as st

from app import repository
from app.app_modules.database.database import get_mysql_connection
from app.app_modules.nearby import nearby_function
from app.app_modules.ui_feedback import show_database_error


@st.fragment
def render_address_tab() -> None:
    # A fragment reruns on its own, so it opens its own connection.
    try:
        with closing(get_mysql_connection()) as connection:
            render_addresses(connection)
    except (mysql.connector.Error, ValueError) as error:
        show_database_error(error)


def render_addresses(connection: Any) -> None:
    if not nearby_function.has_distance_column(connection):
        st.warning(nearby_function.MIGRATION_REQUIRED)
        return
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center",
    ):
        st.subheader("Addresses & nearby stations", width="content")
        update_clicked = st.button("Update addresses", key="update_addresses")

    if update_clicked:
        with st.spinner("Computing station distances for addresses without any..."):
            result = nearby_function.update_missing(connection)
        st.success(
            f'Added {result["total_rows"]:,} nearby rows '
            f'({result["within_radius_rows"]:,} within {result["radius_m"]} m, '
            f'{result["fallback_rows"]:,} nearest-station fallbacks) in {result["seconds"]} s.'
        )

    # Runs whenever this tab is opened: fill `nearby` if it is empty, then check it.
    if not update_clicked and not nearby_function.is_ready(connection):
        with st.spinner("`nearby` is empty, filling it now..."):
            filled = nearby_function.ensure_populated(connection)
        if filled:
            st.success(
                f'`nearby` was empty, so it was filled automatically: '
                f'{filled["total_rows"]:,} rows in {filled["seconds"]} s.'
            )
    with st.spinner("Checking station coverage…"):
        check = nearby_function.coverage(connection)
    if check["stations_total"] == 0:
        st.warning(
            "The `stations` table is empty. From the repository root, run "
            "`python -m setup.import_data_script.import` to load a fresh demo schema."
        )
        return

    with st.container(key="address_summary"):
        first, second, third, fourth = st.columns(4)
        first.metric("Addresses", f'{check["places_total"]:,}')
        second.metric("With nearby stations", f'{check["places_with_nearby"]:,}')
        third.metric("Missing", f'{check["places_missing"]:,}')
        fourth.metric("Flat records affected", f'{check["flats_missing"]:,}')
    if check["places_missing"]:
        with st.container(key="address_coverage_missing"):
            st.warning(
                f'Station coverage is missing for {check["places_missing"]:,} of '
                f'{check["places_total"]:,} addresses. Use **Update addresses** to fill the gaps.'
            )
    else:
        st.success("Every address has at least one nearby station.")

    with st.spinner("Loading addresses…"):
        rows = repository.list_address_stations(connection)
    st.caption(f"{len(rows):,} addresses")
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "block_id": st.column_config.NumberColumn("Block ID", format="%d"),
            "block_number": "Block",
            "road_name": "Road",
            "postal": "Postal code",
            "town": "Town",
            "station_count": st.column_config.NumberColumn("Stations", format="%d"),
            "nearest_m": st.column_config.NumberColumn("Nearest (m)", format="%d"),
            "nearby_stations": st.column_config.TextColumn("Nearby stations", width="large"),
        },
    )
