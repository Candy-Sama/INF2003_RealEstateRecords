import logging
import re
from contextlib import closing
from datetime import date
from typing import Any

import mysql.connector
import streamlit as st
from pymongo import errors as mongo_errors

import nearby_function
import repository
from analytics_ui import render_analytics_tab
from ranking_ui import render_ranking_tab
from database import (
    get_flat_record_admin_email,
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
                        "Log in", type="primary", width="stretch"
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
                        "Create account", type="primary", width="stretch"
                    )
                if submitted:
                    if not name.strip() or not phone.strip():
                        st.error("Enter your name and phone number.")
                    elif not valid_email(email):
                        st.error("Enter a valid email address.")
                    elif email.strip().lower() == get_flat_record_admin_email():
                        st.error(
                            "The administrator account must be provisioned before it can log in."
                        )
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
    total_flats = repository.count_flats(connection)
    page_size = 100
    page_count = max(1, (total_flats + page_size - 1) // page_size)
    if st.session_state.get("flat_records_page", 1) > page_count:
        st.session_state["flat_records_page"] = page_count
    page = st.number_input(
        "Flat records page",
        min_value=1,
        max_value=page_count,
        step=1,
        key="flat_records_page",
    )
    flats = repository.list_flats(
        connection, limit=page_size, offset=(int(page) - 1) * page_size
    )
    st.session_state.setdefault("mf_nonce", 0)
    if flats:
        st.caption(f"Showing page {page} of {page_count} ({total_flats} flat records).")
        event = st.dataframe(
            flats, width="stretch",
            hide_index=True, 
            on_select="rerun",
            selection_mode="single-row",
            key=f'mf_table_{st.session_state["mf_nonce"]}',
        )
        st.caption("Select a row to see its nearby MRT / LRT stations.")
        if event.selection.rows:
            go_to_nearby(flats[event.selection.rows[0]]["flat_id"], "Manage flats")
            st.session_state["mf_nonce"] += 1  # reset selection for when you come back
            st.rerun()
    else:
        st.info("No flat records are currently available.")

    if not is_admin:
        st.info("Flat records are read-only for agent accounts.")
        with st.form("view_flat_form"):
            flat_search_id = st.number_input(
                "Look up a flat by ID",
                min_value=1,
                step=1,
                key="view_flat_search_id",
            )
            view_submitted = st.form_submit_button("Find flat")
        if view_submitted:
            st.session_state["view_flat_selected_id"] = int(flat_search_id)
        selected_id = st.session_state.get("view_flat_selected_id")
        if selected_id is not None:
            selected_flat = repository.get_flat(connection, selected_id)
            if selected_flat is None:
                st.warning("No flat record exists with that ID.")
            else:
                st.dataframe([selected_flat], width="stretch", hide_index=True)
        return

    action = st.radio(
        "Flat record action",
        ["Create", "Update"],
        horizontal=True,
        label_visibility="collapsed",
        key="flat_management_action",
    )
    if action == "Create":
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
                repository.create_flat(connection, values)
                st.success("Flat record created.")
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
    selected_flat = repository.get_flat(connection, selected_id)
    if selected_flat is None:
        st.warning("No flat record exists with that ID.")
        return
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
            repository.update_flat(connection, selected_id, values)
            st.success("Flat record updated.")
            st.rerun()


def render_agent_transactions(connection: Any, agent_id: int) -> None:
    st.subheader("My resale transactions")
    transactions = repository.list_agent_transactions(connection, agent_id)
    if transactions:
        st.caption("Showing up to 100 of your most recent transactions.")
        st.dataframe(transactions, width="stretch", hide_index=True)
    else:
        st.info("You have not recorded any resale transactions.")

    action = st.radio(
        "Transaction action",
        ["Create", "Update", "Delete"],
        horizontal=True,
        label_visibility="collapsed",
        key="transaction_action",
    )
    if action == "Create":
        with st.form("create_transaction_form"):
            flat_id = st.number_input(
                "Flat ID sold",
                min_value=1,
                step=1,
                key="create_transaction_flat_id",
            )
            transaction_date = st.date_input(
                "Transaction date", value=date.today(), key="create_transaction_date"
            )
            resale_price = st.number_input(
                "Resale price",
                min_value=0.01,
                max_value=20_000_000.0,
                step=1000.0,
                value=0.01,
                key="create_transaction_price",
            )
            submitted = st.form_submit_button("Create transaction", type="primary")
        if submitted:
            flat = repository.get_flat(connection, int(flat_id))
            if flat is None:
                st.error("No flat record exists with that ID.")
            else:
                try:
                    repository.create_agent_transaction(
                        connection, agent_id, int(flat_id), transaction_date, resale_price
                    )
                    st.success("Transaction created.")
                    st.rerun()
                except mysql.connector.IntegrityError:
                    st.error("You already recorded a transaction for this flat.")
        return

    if not transactions:
        st.info("Enter a transaction's flat ID to update or delete it.")
    with st.form("find_owned_transaction_form"):
        transaction_flat_id = st.number_input(
            "Transaction flat ID",
            min_value=1,
            step=1,
            key="transaction_lookup_flat_id",
        )
        lookup_submitted = st.form_submit_button("Find my transaction")
    if lookup_submitted:
        st.session_state["selected_transaction_flat_id"] = int(transaction_flat_id)

    selected_flat_id = st.session_state.get("selected_transaction_flat_id")
    if selected_flat_id is None:
        return
    selected_transaction = repository.get_agent_transaction(
        connection, agent_id, selected_flat_id
    )
    if selected_transaction is None:
        st.warning("That transaction no longer exists in your account.")
        return

    if action == "Update":
        with st.form(f"edit_transaction_{selected_flat_id}"):
            new_flat_id = st.number_input(
                "Flat ID sold",
                min_value=1,
                step=1,
                value=int(selected_flat_id),
                key=f"edit_transaction_flat_{selected_flat_id}",
            )
            transaction_date = st.date_input(
                "Transaction date",
                value=selected_transaction["transaction_date"],
                key=f"edit_transaction_date_{selected_flat_id}",
            )
            resale_price = st.number_input(
                "Resale price",
                min_value=0.01,
                max_value=20_000_000.0,
                step=1000.0,
                value=float(selected_transaction["resale_price"]),
                key=f"edit_transaction_price_{selected_flat_id}",
            )
            submitted = st.form_submit_button("Save transaction", type="primary")
        if submitted:
            if repository.get_flat(connection, int(new_flat_id)) is None:
                st.error("No flat record exists with that ID.")
            else:
                try:
                    updated = repository.update_agent_transaction(
                        connection,
                        agent_id,
                        selected_flat_id,
                        int(new_flat_id),
                        transaction_date,
                        resale_price,
                    )
                except mysql.connector.IntegrityError:
                    st.error("You already have a transaction recorded for that flat.")
                else:
                    if updated:
                        st.session_state["selected_transaction_flat_id"] = int(new_flat_id)
                        st.success("Transaction updated.")
                        st.rerun()
                    else:
                        st.error("The transaction could not be updated.")
    else:
        st.write(
            f'Flat **{selected_flat_id}** — {selected_transaction["flat_type"]}, '
            f'{selected_transaction["block_number"]} '
            f'{selected_transaction["road_name"]}, {selected_transaction["town"]}'
        )
        if st.button("Delete transaction", type="primary"):
            if repository.delete_agent_transaction(connection, agent_id, selected_flat_id):
                st.session_state.pop("selected_transaction_flat_id", None)
                st.success("Transaction deleted.")
                st.rerun()
            else:
                st.error("The transaction could not be deleted.")


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


# ---------------------------------------------------------------------------
# Address tab: every `place` row with its nearby stations
# ---------------------------------------------------------------------------
@st.fragment
def render_address_tab() -> None:
    # A fragment reruns on its own, so it opens its own connection.
    try:
        with closing(get_mysql_connection()) as connection:
            render_addresses(connection)
    except (mysql.connector.Error, ValueError) as error:
        show_database_error(error)


def render_addresses(connection: Any) -> None:
    title, action = st.columns([3, 1], vertical_alignment="center")
    title.subheader("Addresses & nearby stations")
    with action:
        update_clicked = st.button("Update addresses", type="primary", width="stretch")

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
    check = nearby_function.coverage(connection)
    if not check["has_column"]:
        st.warning("`nearby` has no `distance_m` column yet. Click **Update addresses** to set it up.")
        return
    if check["stations_total"] == 0:
        st.warning("The `stations` table is empty. Run `import.py` first.")
        return

    first, second, third, fourth = st.columns(4)
    first.metric("Addresses", f'{check["places_total"]:,}')
    second.metric("With nearby stations", f'{check["places_with_nearby"]:,}')
    third.metric("Missing", f'{check["places_missing"]:,}')
    fourth.metric("Flat records affected", f'{check["flats_missing"]:,}')
    if check["places_missing"]:
        st.warning(
            f'{check["places_missing"]:,} address(es) have no nearby stations, which leaves '
            f'{check["flats_missing"]:,} flat record(s) without any. Click **Update addresses**.'
        )
    else:
        st.success("Every address has at least one nearby station.")

    rows = repository.list_address_stations(connection)
    st.caption(f"{len(rows):,} addresses")
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "block_id": st.column_config.NumberColumn("Block ID"),
            "block_number": "Block",
            "road_name": "Road",
            "postal": "Postal",
            "town": "Town",
            "station_count": st.column_config.NumberColumn("Stations"),
            "nearest_m": st.column_config.NumberColumn("Nearest (m)"),
            "nearby_stations": st.column_config.TextColumn("Nearby stations", width="large"),
        },
    )


# ---------------------------------------------------------------------------
# Nearby stations tab
#   state 0: all flats, no filters
#   state 1: station filter pills (transport type / line / distance)
#   state 2: a flat picked on Manage flats
#   state 3: a flat picked on this tab
# ---------------------------------------------------------------------------
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
    st.session_state.setdefault("nb_nonce", 0)
    focus = st.session_state.get("nearby_focus")

    title, clear_column = st.columns([3, 1], vertical_alignment="center")
    title.subheader("Nearby MRT / LRT stations")

    if not nearby_function.is_ready(connection):
        with st.spinner("`nearby` is empty, filling it now..."):
            filled = nearby_function.ensure_populated(connection)
        if filled is None:
            st.warning("There are no stations loaded to measure against. Run `import.py` first.")
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
        with st.container(border=True):
            st.markdown(f'**Selected flat** · picked from {focus["origin"]}')
            st.dataframe(
                selected, width="stretch", hide_index=True, column_config=FLAT_TABLE_COLUMNS
            )
            if not station_ids:
                st.info(
                    "This flat's block has no nearby stations yet. Use **Update addresses** "
                    "on the Address tab."
                )
            if focus["origin"] == "Manage flats" and st.button("← Back to Manage flats"):
                st.session_state["pending_tab"] = "Manage flats"
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
    towns = ["Any", *[town for town in repository.list_towns(connection) if town]]
    flat_types = ["Any", *[value for value in repository.list_flat_types(connection) if value]]

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
        st.dataframe(results, width="stretch", hide_index=True)
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


def render_workspace(agent: dict[str, Any]) -> None:
    pending_filters = st.session_state.pop("pending_search_filters", None)
    if pending_filters is not None:
        st.session_state["workspace_section"] = "Search & filter"
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
                if is_flat_admin:
                    st.caption("Administrator access: you can create and edit flat records.")
                else:
                    st.caption("You can view flat records; only the configured admin can edit them.")
                render_flat_management(connection, is_flat_admin)
            elif page == "My transactions":
                render_agent_transactions(connection, agent["agent_id"])
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