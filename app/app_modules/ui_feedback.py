"""Shared action and database feedback for the Streamlit UI."""

import logging
from typing import Literal

import streamlit as st


def queue_feedback(
    page: str,
    message: str,
    kind: Literal["success", "toast", "warning", "info"] = "success",
) -> None:
    """Keep a message for the next render of the page after a rerun."""
    st.session_state[f"feedback_{page}"] = (kind, message)


def show_feedback(page: str) -> None:
    """Display and clear the message queued for this page."""
    if feedback := st.session_state.pop(f"feedback_{page}", None):
        kind, message = feedback
        if kind == "success":
            with st.container(key=f"action_success_{page}"):
                st.success(message)
        else:
            getattr(st, kind)(message)


def show_database_error(error: Exception) -> None:
    logging.exception("Database operation failed")
    st.error(
        "The database operation failed. Check that MySQL and MongoDB are running, "
        "your connection settings are correct, and the tables match the documented schema."
    )
    with st.expander("Technical details"):
        st.code(str(error))
