import logging
import re
from contextlib import closing
from datetime import date
from typing import Any

import mysql.connector
import streamlit as st
from pymongo import errors as mongo_errors

import repository
from database import (
    get_mongodb_client,
    get_mongodb_database_name,
    get_mysql_connection,
)
from security import hash_password, verify_password


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


def valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def show_database_error(error: Exception) -> None:
    logging.exception("Database operation failed")
    st.error(
        "The database operation failed. Check that MySQL and MongoDB are running, "
        "your connection settings are correct, and the tables match the documented schema."
    )
    with st.expander("Technical details"):
        st.code(str(error))


def render_authentication() -> None:
    st.markdown(
        '<div class="brand"><span class="brand-mark">E</span>Estate Records</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    hero, account = st.columns([1.15, 0.85], gap="large", vertical_alignment="center")

    with hero:
        st.markdown('<div class="eyebrow">A clearer view of property</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="hero-title">Real estate records, all in one place.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="hero-copy">Search HDB resale history, manage property records, '
            'and keep useful searches close at hand.</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(
            """
            <div class="hero-card">
                <div class="hero-card-label">Your property workspace</div>
                <div>
                    <div class="hero-card-title">From first search to saved shortlist.</div>
                    <div class="hero-card-copy">A practical workspace for agents to review property and transaction data.</div>
                </div>
                <div class="hero-card-copy">Search &amp; filter &nbsp; · &nbsp; CRUD &nbsp; · &nbsp; Saved searches</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with account:
        with st.container(border=True):
            st.markdown("### Welcome")
            login_tab, register_tab = st.tabs(["Log in", "Create account"])

            with login_tab:
                with st.form("login_form"):
                    email = st.text_input("Email address", placeholder="you@example.com")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button(
                        "Log in", type="primary", use_container_width=True
                    )
                if submitted:
                    if not valid_email(email) or not password:
                        st.error("Enter a valid email address and password.")
                    else:
                        try:
                            with closing(get_mysql_connection()) as connection:
                                agent = repository.find_agent_by_email(
                                    connection, email.strip().lower()
                                )
                            if agent and verify_password(password, agent["password_hash"]):
                                st.session_state["agent"] = {
                                    "agent_id": agent["agent_id"],
                                    "name": agent["name"],
                                    "email": agent["email"],
                                }
                                st.rerun()
                            st.error("Email or password is incorrect.")
                        except (mysql.connector.Error, ValueError) as error:
                            show_database_error(error)

            with register_tab:
                with st.form("register_form"):
                    name = st.text_input("Full name")
                    email = st.text_input("Email address", placeholder="you@example.com")
                    phone = st.text_input("Phone number")
                    password = st.text_input("Create password", type="password")
                    confirm_password = st.text_input("Confirm password", type="password")
                    submitted = st.form_submit_button(
                        "Create account", type="primary", use_container_width=True
                    )
                if submitted:
                    if not name.strip() or not phone.strip():
                        st.error("Enter your name and phone number.")
                    elif not valid_email(email):
                        st.error("Enter a valid email address.")
                    elif len(password) < 8:
                        st.error("Choose a password with at least 8 characters.")
                    elif password != confirm_password:
                        st.error("The passwords do not match.")
                    else:
                        try:
                            with closing(get_mysql_connection()) as connection:
                                agent_id = repository.create_agent(
                                    connection,
                                    name.strip(),
                                    email.strip().lower(),
                                    phone.strip(),
                                    hash_password(password),
                                )
                            st.session_state["agent"] = {
                                "agent_id": agent_id,
                                "name": name.strip(),
                                "email": email.strip().lower(),
                            }
                            st.rerun()
                        except (mysql.connector.Error, ValueError) as error:
                            show_database_error(error)

            st.caption(
                "Accounts are stored in MySQL. Passwords are stored as salted scrypt hashes."
            )


def flat_values_form(
    places: list[dict[str, Any]],
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

    left, right = st.columns(2)
    flat_type = left.text_input(
        "Flat type", value=initial.get("flat_type", ""), key=f"{prefix}_flat_type"
    )
    flat_model = right.text_input(
        "Flat model", value=initial.get("flat_model", ""), key=f"{prefix}_flat_model"
    )
    storey_range = left.text_input(
        "Storey range", value=initial.get("storey_range", ""), key=f"{prefix}_storey"
    )
    floor_area = right.number_input(
        "Floor area (sqm)",
        min_value=1,
        max_value=1000,
        value=int(initial.get("floor_area_sqm") or 1),
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
        "flat_type": flat_type.strip(),
        "flat_model": flat_model.strip(),
        "storey_range": storey_range.strip(),
        "floor_area_sqm": floor_area,
        "block_id": block_id,
        "lease_commence_date": lease_start,
        "remaining_lease_months": remaining_lease,
    }


def render_flat_management(connection: Any) -> None:
    st.subheader("Manage flat records")
    flats = repository.list_flats(connection)
    places = repository.list_places(connection)
    if flats:
        st.dataframe(flats, use_container_width=True, hide_index=True)
    else:
        st.info("No flat records are currently available.")

    create_tab, edit_tab, delete_tab = st.tabs(["Create", "Update", "Delete"])
    with create_tab:
        if not places:
            st.warning("Add records to the `place` table before creating a flat.")
        else:
            with st.form("create_flat_form"):
                values = flat_values_form(places, "create")
                submitted = st.form_submit_button("Create flat", type="primary")
            if submitted:
                if not all(
                    values[field] for field in ("flat_type", "flat_model", "storey_range")
                ):
                    st.error("Complete the flat type, model, and storey range.")
                else:
                    repository.create_flat(connection, values)
                    st.success("Flat record created.")
                    st.rerun()

    with edit_tab:
        if not flats:
            st.info("There are no flat records to update.")
        elif not places:
            st.warning("No place records are available.")
        else:
            flat_ids = [flat["flat_id"] for flat in flats]
            selected_id = st.selectbox("Flat record", flat_ids, key="edit_flat_id")
            selected_flat = next(flat for flat in flats if flat["flat_id"] == selected_id)
            with st.form(f"edit_flat_form_{selected_id}"):
                values = flat_values_form(places, "edit", selected_flat)
                submitted = st.form_submit_button("Save changes", type="primary")
            if submitted:
                if not all(
                    values[field] for field in ("flat_type", "flat_model", "storey_range")
                ):
                    st.error("Complete the flat type, model, and storey range.")
                else:
                    repository.update_flat(connection, selected_id, values)
                    st.success("Flat record updated.")
                    st.rerun()

    with delete_tab:
        if not flats:
            st.info("There are no flat records to delete.")
        else:
            flat_ids = [flat["flat_id"] for flat in flats]
            selected_id = st.selectbox("Flat record to delete", flat_ids, key="delete_flat_id")
            st.warning(
                "MySQL foreign-key rules may prevent deleting a flat referenced by resale transactions."
            )
            if st.button("Delete flat", type="primary"):
                repository.delete_flat(connection, selected_id)
                st.success("Flat record deleted.")
                st.rerun()


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
    places = repository.list_places(connection)
    flats = repository.list_flats(connection)
    towns = ["Any", *sorted({place["town"] for place in places if place["town"]})]
    flat_types = ["Any", *sorted({flat["flat_type"] for flat in flats if flat["flat_type"]})]

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
        st.dataframe(results, use_container_width=True, hide_index=True)
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
        use_container_width=True,
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


def render_workspace(agent: dict[str, Any]) -> None:
    pending_filters = st.session_state.pop("pending_search_filters", None)
    if pending_filters is not None:
        st.session_state["filter_town"] = pending_filters.get("town") or "Any"
        st.session_state["filter_flat_type"] = pending_filters.get("flat_type") or "Any"
        st.session_state["filter_min_price"] = pending_filters.get("min_price") or 0
        st.session_state["filter_max_price"] = pending_filters.get("max_price") or 0
        st.session_state["filter_start_date"] = (
            date.fromisoformat(pending_filters["start_date"])
            if pending_filters.get("start_date")
            else None
        )
        st.session_state["filter_end_date"] = (
            date.fromisoformat(pending_filters["end_date"])
            if pending_filters.get("end_date")
            else None
        )
        st.session_state["execute_saved_search"] = True

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
            st.session_state.pop("agent", None)
            st.rerun()

    try:
        with closing(get_mysql_connection()) as connection:
            with closing(get_mongodb_client()) as mongo_client:
                mongo_database = mongo_client[get_mongodb_database_name()]
                tab_names = ["Search & filter", "Manage flats", "Saved searches"]
                search_tab, flats_tab, saved_tab = st.tabs(tab_names)
                with search_tab:
                    render_search(connection, mongo_database, agent["agent_id"])
                with flats_tab:
                    render_flat_management(connection)
                with saved_tab:
                    render_saved_searches(mongo_database, agent["agent_id"])
    except (mysql.connector.Error, mongo_errors.PyMongoError, ValueError) as error:
        show_database_error(error)


agent = st.session_state.get("agent")
if agent:
    render_workspace(agent)
else:
    render_authentication()
