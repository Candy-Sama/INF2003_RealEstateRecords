"""Login and account registration UI."""

import re
from contextlib import closing

import mysql.connector
import streamlit as st

from app import repository
from app.app_modules.database.database import get_flat_record_admin_email, get_mysql_connection
from app.app_modules.security.security import hash_password, verify_password
from app.app_modules.ui_feedback import queue_feedback, show_database_error


def valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def render_authentication() -> None:
    st.markdown(
        '<div class="brand"><span class="brand-mark" aria-hidden="true">E</span>Estate Records</div>',
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
                <div class="hero-card-title">From first search to saved shortlist.</div>
                <div class="hero-card-copy">A practical workspace for agents to review property and transaction data.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with account:
        with st.container(border=True, key="account_panel"):
            st.markdown("### Welcome")
            login_tab, register_tab = st.tabs(["Log in", "Create account"])

            with login_tab:
                with st.form("login_form", border=False):
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
                with st.form("register_form", border=False):
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
                            queue_feedback("workspace", "Account created.")
                            st.rerun()
                        except (mysql.connector.Error, ValueError) as error:
                            show_database_error(error)

            st.caption(
                "Accounts are stored in MySQL. Passwords are stored as salted scrypt hashes."
            )
