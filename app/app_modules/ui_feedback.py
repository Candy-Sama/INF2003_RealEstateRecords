"""Shared database error feedback for the Streamlit UI."""

import logging

import streamlit as st


def show_database_error(error: Exception) -> None:
    logging.exception("Database operation failed")
    st.error(
        "The database operation failed. Check that MySQL and MongoDB are running, "
        "your connection settings are correct, and the tables match the documented schema."
    )
    with st.expander("Technical details"):
        st.code(str(error))
