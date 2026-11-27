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

st.markdown(
    """
    <style>
    .stApp {
        /* Streamlit uses its theme background for canvas table cells. */
        background-color: light-dark(#f6f8f5, #18191b);
        --estate-accent: light-dark(#176b52, #87d3b7);
        --estate-muted: light-dark(#52635e, #c5c8cf);
        --estate-button: light-dark(#176b52, #308267);
        --estate-button-hover: light-dark(#10553f, #276950);
        --estate-border: light-dark(#6a837a, #7c7f87);
        --estate-tint: light-dark(#e1eee7, #2c2e32);
    }
    .stApp [data-testid="stCaptionContainer"] {
        color: light-dark(rgb(23 43 42 / 60%), var(--estate-muted));
        opacity: 1;
    }
    .stApp [data-testid="stDataFrame"] {
        border-radius: .5rem;
        box-shadow: 0 .5rem 1.25rem light-dark(transparent, rgb(0 0 0 / 35%));
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { max-width: 1180px; padding-top: 1.4rem; padding-bottom: 3rem; }
    .brand { font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 1.2rem; font-weight: 800; letter-spacing: -.04em; }
    .brand-mark { display: inline-grid; place-items: center; width: 2rem; height: 2rem; margin-right: .55rem; color: white; background: var(--estate-button); border-radius: .65rem; vertical-align: middle; }
    .eyebrow { color: var(--estate-accent); font-size: .76rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    .hero-title { max-width: 690px; margin: .75rem 0 1rem; font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: clamp(2.5rem, 5vw, 4.35rem); font-weight: 800; letter-spacing: -.065em; line-height: 1.05; }
    .hero-copy { max-width: 560px; color: var(--estate-muted); font-size: 1.08rem; line-height: 1.75; }
    .hero-card { min-height: 320px; padding: 2rem; color: white; border-radius: 1.25rem; background: linear-gradient(145deg, #163d35 0%, #176b52 60%, #74a887 150%); display: flex; flex-direction: column; justify-content: space-between; }
    .hero-card-label { color: #c8e3d3; font-size: .78rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
    .hero-card-title { max-width: 360px; font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 2rem; font-weight: 700; line-height: 1.2; }
    .hero-card-copy { max-width: 340px; color: #d6e8dc; line-height: 1.65; }
    .stApp .stTabs [role="tab"]:is([aria-selected="true"], :hover, :focus-visible) {
        color: var(--estate-accent);
    }
    .stApp :is(.stButton, .stFormSubmitButton, .stDownloadButton) button {
        color: white;
        background-color: var(--estate-button);
        border: 1px solid var(--estate-border);
        border-radius: .55rem;
        font-weight: 700;
    }
    .stApp :is(.stButton, .stFormSubmitButton, .stDownloadButton) button:not(:disabled):is(:hover, :active) {
        background-color: var(--estate-button-hover);
    }
    .stApp .stButtonGroup button {
        color: var(--estate-accent);
        background-color: var(--estate-tint);
        border-color: var(--estate-border);
    }
    .stApp .stButtonGroup button:not(:disabled):is(:hover, [data-focus-visible]) {
        border-color: var(--estate-accent);
    }
    .stApp .stButtonGroup button:is([data-selected], [data-testid$="Active"]):not(:disabled) {
        color: white;
        background-color: var(--estate-button);
    }
    .stApp :is(.stButton, .stFormSubmitButton, .stDownloadButton, .stButtonGroup) button:focus-visible {
        outline: 2px solid var(--estate-accent);
        outline-offset: 2px;
        box-shadow: none;
    }
    .stApp :is(.stButton, .stFormSubmitButton, .stDownloadButton, .stButtonGroup) button:disabled {
        color: var(--estate-muted);
        background-color: var(--estate-tint);
        border-color: var(--estate-border);
    }
    .nearby-stat {
        --stat-accent: var(--estate-accent);
        border: 1px solid var(--estate-border);
        border-left: 5px solid var(--stat-accent);
        background: color-mix(in srgb, var(--stat-accent) 10%, transparent);
        border-radius: .65rem;
        padding: .85rem 1rem;
        margin-bottom: .4rem;
    }
    .nearby-stat--neutral { --stat-accent: var(--estate-muted); }
    .nearby-stat--warning { --stat-accent: light-dark(#974607, #f7bb77); }
    .nearby-stat--below { --stat-accent: light-dark(#116761, #87ddd3); }
    .nearby-stat--range { --stat-accent: light-dark(#1e40af, #a9c4ff); }
    .nearby-stat-title { font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
    .nearby-stat-value { color: var(--stat-accent); font-size: 1.45rem; font-weight: 800; margin: .15rem 0; }
    .nearby-stat-note { font-size: .82rem; }
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
