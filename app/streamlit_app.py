import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import mysql.connector
import streamlit as st
from pymongo import errors as mongo_errors

# Streamlit adds this script's directory to the import path. The app package lives one level up.
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.app_modules.address_ui import render_address_tab
from app.app_modules.analytics.analytics_ui import render_analytics_tab
from app.app_modules.authentication_ui import render_authentication
from app.app_modules.database.database import (
    get_flat_record_admin_email,
    get_mongodb_client,
    get_mongodb_database_name,
    get_mysql_connection,
)
from app.app_modules.flat_records_ui import render_flat_management
from app.app_modules.nearby.nearby_ui import render_nearby_tab
from app.app_modules.ranking.ranking_ui import render_ranking_tab
from app.app_modules.saved_searches_ui import render_saved_searches
from app.app_modules.search_ui import apply_saved_search_filters, render_search
from app.app_modules.transactions_ui import clear_transaction_batch, render_agent_transactions
from app.app_modules.ui_feedback import show_database_error


st.set_page_config(
    page_title="Estate Records",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        --ink: #172b2a;
        --muted: #61716d;
        --green: #176b52;
        --line: #e4ebe7;
        --paper: #f6f8f5;
    }
    html, body, [class*="css"] { font-family: 'DM Sans', 'Segoe UI', sans-serif; color: var(--ink); }
    .stApp { background: var(--paper); }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { max-width: 1180px; padding-top: 1.4rem; padding-bottom: 3rem; }
    .brand { font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 1.2rem; font-weight: 800; letter-spacing: -.04em; }
    .brand-mark { display: inline-grid; place-items: center; width: 2rem; height: 2rem; margin-right: .55rem; color: white; background: var(--green); border-radius: .65rem; vertical-align: middle; }
    .eyebrow { color: var(--green); font-size: .76rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    .hero-title { max-width: 690px; margin: .75rem 0 1rem; color: var(--ink); font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: clamp(2.5rem, 5vw, 4.35rem); font-weight: 800; letter-spacing: -.065em; line-height: 1.05; }
    .hero-copy { max-width: 560px; color: var(--muted); font-size: 1.08rem; line-height: 1.75; }
    .hero-card { min-height: 320px; padding: 2rem; color: white; border-radius: 1.25rem; background: linear-gradient(145deg, #163d35 0%, #176b52 60%, #74a887 150%); display: flex; flex-direction: column; justify-content: space-between; }
    .hero-card-label { color: #c8e3d3; font-size: .78rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
    .hero-card-title { max-width: 360px; font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 2rem; font-weight: 700; line-height: 1.2; }
    .hero-card-copy { max-width: 340px; color: #d6e8dc; line-height: 1.65; }
    div.stButton > button[kind="primary"] { color: white; background: var(--green); border-color: var(--green); border-radius: .55rem; font-weight: 700; }
    div.stButton > button[kind="primary"]:hover { background: #10553f; border-color: #10553f; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_workspace(agent: dict[str, Any]) -> None:
    pending_filters = st.session_state.pop("pending_search_filters", None)
    if pending_filters is not None:
        st.session_state["workspace_section"] = "Search & filter"
        apply_saved_search_filters(pending_filters)

    st.markdown(
        '<div class="brand"><span class="brand-mark">E</span>Estate Records</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    greeting, logout_column = st.columns([4, 1])
    with greeting:
        st.subheader(f'Welcome, {agent["name"]}')
        st.caption("Property catalogue, resale transactions, and your saved searches.")
    with logout_column:
        if st.button("Log out"):
            clear_transaction_batch(agent["agent_id"])
            st.session_state.pop("agent", None)
            st.rerun()

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
    )

    try:
        if page == "My transactions":
            render_agent_transactions(agent["agent_id"])
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
            elif page == "Address":
                render_address_tab()
            elif page == "Nearby stations":
                render_nearby_tab()
            elif page == "Analytics":
                render_analytics_tab()
            elif page == "Ranking":
                render_ranking_tab()
            else:
                with closing(get_mongodb_client()) as mongo_client:
                    mongo_database = mongo_client[get_mongodb_database_name()]
                    render_saved_searches(mongo_database, agent["agent_id"])
    except (mysql.connector.Error, mongo_errors.PyMongoError, ValueError) as error:
        show_database_error(error)


agent = st.session_state.get("agent")
if agent:
    render_workspace(agent)
else:
    render_authentication()
