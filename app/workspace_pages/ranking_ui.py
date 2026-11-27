from __future__ import annotations

import logging
from contextlib import closing
from datetime import datetime
from typing import Any

import mysql.connector
import streamlit as st

from app import repository
from app.app_modules.database.database import get_mysql_connection
from app.app_modules.ranking import ranking

ALL_TYPES = "All flat types"


@st.fragment
def render_ranking_tab() -> None:
    try:
        with closing(get_mysql_connection()) as connection:
            render_rankings(connection)
    except (mysql.connector.Error, ValueError) as error:
        logging.exception("Ranking tab failed")
        st.error(
            "The rankings could not be loaded. Check that MySQL is running and the tables "
            "match the documented schema."
        )
        with st.expander("Technical details"):
            st.code(str(error))


def render_rankings(connection: Any) -> None:
    title, refresh = st.columns([3, 1], vertical_alignment="center")
    title.subheader("Rankings")
    with refresh:
        st.button("Refresh rankings", width="stretch")  # any click reruns and re-queries

    flat_types = repository.list_flat_options(connection)["flat_type"]
    picker, status = st.columns([1, 2], vertical_alignment="bottom")
    choice = picker.selectbox("Flat type", [ALL_TYPES, *flat_types], key="rk_flat_type")
    flat_type = None if choice == ALL_TYPES else choice

    with st.spinner("Loading rankings..."):
        latest = repository.latest_transaction_date(connection)
        boards = ranking.build_boards(
            repository.rank_towns(connection, flat_type),
            repository.rank_stations(connection, flat_type),
            repository.rank_streets(connection, flat_type),
            repository.top_sales(connection, flat_type),
        )
    as_of = latest.strftime("%B %Y") if latest else "no data"
    status.caption(
        f"Pulled from the database at {datetime.now():%H:%M:%S}. "
        f"Transactions up to {as_of}."
    )

    render_leaders(ranking.leaders(boards))
    group = None
    pending: list[dict[str, Any]] = []
    for board in boards:
        if board["group"] != group:
            flush(pending)
            group = board["group"]
            st.markdown(f'<div class="eyebrow">{group}</div>', unsafe_allow_html=True)
        pending.append(board)
        if len(pending) == 2:
            flush(pending)
    flush(pending)


def flush(pending: list[dict[str, Any]]) -> None:
    """Draw queued boards two to a row."""
    if not pending:
        return
    columns = st.columns(2)
    for slot, board in zip(columns, pending):
        with slot:
            render_board(board)
    pending.clear()


def render_leaders(items: list[dict[str, str]]) -> None:
    if not items:
        return
    for slot, item in zip(st.columns(len(items)), items):
        with slot:
            with st.container(border=True):
                st.metric(item["label"], item["name"], item["detail"], delta_color="off")


def render_board(board: dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f'**{board["title"]}**')
        st.caption(board["caption"])
        rows = board["rows"]
        if not rows:
            st.info("Not enough data for this ranking yet.")
            return

        values = [row["value"] for row in rows]
        extra_config = {
            "int": st.column_config.NumberColumn(board["extra_label"], format="%d"),
            "psm": st.column_config.NumberColumn(board["extra_label"], format="$%.0f"),
            "text": st.column_config.TextColumn(board["extra_label"]),
        }[board["extra_format"]]
        frame = [
            {
                "Rank": row["rank"],
                board["name_label"]: row["name"],
                board["value_label"]: row["value"],
                board["extra_label"]: row["extra"],
            }
            for row in rows
        ]
        st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=35 * len(frame) + 38,
            column_config={
                "Rank": st.column_config.NumberColumn("#", format="%d", width="small"),
                board["name_label"]: st.column_config.TextColumn(
                    board["name_label"], width="medium"
                ),
                board["value_label"]: st.column_config.ProgressColumn(
                    board["value_label"],
                    format=board["value_format"],
                    min_value=min(0.0, min(values)),
                    max_value=max(max(values), 0.0001),
                ),
                board["extra_label"]: extra_config,
            },
        )
