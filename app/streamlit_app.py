import sys
from contextlib import closing
from html import escape
from pathlib import Path
from typing import Any

import mysql.connector
import streamlit as st
from pymongo import errors as mongo_errors

# Streamlit adds this script's directory to the import path. The app package lives one level up.
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.app_modules.authentication_ui import render_authentication
from app.app_modules.database.database import (
    get_flat_record_admin_email,
    get_mongodb_client,
    get_mongodb_database_name,
    get_mysql_connection,
)
from app.app_modules.ui_feedback import show_database_error, show_feedback
from app.workspace_pages.address_ui import render_address_tab
from app.workspace_pages.analytics_ui import render_analytics_tab
from app.workspace_pages.flat_records_ui import render_flat_management
from app.workspace_pages.nearby_ui import render_nearby_tab
from app.workspace_pages.ranking_ui import render_ranking_tab
from app.workspace_pages.saved_searches_ui import render_saved_searches
from app.workspace_pages.search_ui import apply_saved_search_filters, render_search
from app.workspace_pages.transactions_ui import render_agent_transactions


st.set_page_config(
    page_title="Estate Records",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.html(Path(__file__).with_name("styles.css"))


def render_workspace(agent: dict[str, Any]) -> None:
    pending_filters = st.session_state.pop("pending_search_filters", None)
    if pending_filters is not None:
        st.session_state["workspace_section"] = "Search & filter"
        apply_saved_search_filters(pending_filters)

    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center",
        key="workspace_header",
    ):
        st.markdown(
            '<div class="brand"><span class="brand-mark" aria-hidden="true">E</span>Estate Records</div>',
            unsafe_allow_html=True,
            width="content",
        )
        with st.container(horizontal=True, vertical_alignment="center", width="content"):
            st.markdown(
                f'<span class="workspace-user">Signed in as <strong>{escape(agent["name"])}</strong></span>',
                unsafe_allow_html=True,
                width="content",
            )
            if st.button("Log out", type="tertiary"):
                st.session_state.clear()
                st.rerun()
    show_feedback("workspace")

    pages = [
        "Search & filter",
        "Flat records",
        "My transactions",
        "Saved searches",
        "Address",
        "Nearby stations",
        "Analytics",
        "Ranking",
    ]

    pending_page = st.session_state.pop("pending_tab", None)
    if pending_page in pages:
        st.session_state["workspace_section"] = pending_page
    page = st.radio(
        "Workspace section",
        pages,
        horizontal=True,
        label_visibility="collapsed",
        key="workspace_section",
        width="stretch",
    )

    try:
        if page == "My transactions":
            render_agent_transactions(agent["agent_id"])
            return
        fragment = {
            "Address": render_address_tab,
            "Nearby stations": render_nearby_tab,
            "Analytics": render_analytics_tab,
            "Ranking": render_ranking_tab,
        }.get(page)
        if fragment is not None:
            fragment()
            return

        with closing(get_mysql_connection()) as connection:
            if page == "Search & filter":
                with closing(get_mongodb_client()) as mongo_client:
                    mongo_database = mongo_client[get_mongodb_database_name()]
                    render_search(connection, mongo_database, agent["agent_id"])
            elif page == "Flat records":
                admin_email = get_flat_record_admin_email()
                is_flat_admin = bool(
                    admin_email
                    and agent["email"].strip().lower() == admin_email
                )
                render_flat_management(connection, is_flat_admin)
            else:
                with closing(get_mongodb_client()) as mongo_client:
                    mongo_database = mongo_client[get_mongodb_database_name()]
                    render_saved_searches(connection, mongo_database, agent["agent_id"])
    except (mysql.connector.Error, mongo_errors.PyMongoError, ValueError) as error:
        show_database_error(error)


agent = st.session_state.get("agent")
if agent:
    render_workspace(agent)
else:
    render_authentication()
