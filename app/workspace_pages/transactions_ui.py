"""Agent transaction and batch entry UI."""

import logging
from contextlib import closing
from datetime import date
from typing import Any

import mysql.connector
import streamlit as st
from mysql.connector import errorcode

from app import repository
from app.app_modules.database.database import get_mysql_connection
from app.app_modules.table_columns import RESALE_COLUMNS
from app.app_modules.ui_feedback import queue_feedback, show_feedback


def transaction_draft_fields(
    draft: repository.PlannedTransaction | None = None,
) -> repository.PlannedTransaction:
    return {
        "flat_id": st.number_input(
            "Flat ID sold", min_value=1, max_value=2_147_483_647,
            value=draft["flat_id"] if draft else 1, step=1,
        ),
        "transaction_date": st.date_input(
            "Transaction date", value=draft["transaction_date"] if draft else date.today(),
        ),
        "resale_price": st.number_input(
            "Resale price (S$)", min_value=0.01, max_value=20_000_000.0,
            value=float(draft["resale_price"]) if draft else 0.01, step=0.01, format="%.2f",
        ),
    }


def render_transaction_batch(agent_id: int) -> None:
    drafts_key = f"transaction_batch_{agent_id}"
    feedback_page = f"transaction_batch_{agent_id}"
    drafts: list[repository.PlannedTransaction] = st.session_state.setdefault(drafts_key, [])
    show_feedback(feedback_page)
    st.markdown("Drafts stay in this session until you **commit the batch** or log out.")

    with st.form("add_transaction_draft", clear_on_submit=True):
        draft = transaction_draft_fields()
        if st.form_submit_button("Add draft"):
            drafts.append(draft)
            st.toast("Draft added. Commit the batch to save it.")

    if not drafts:
        st.info("Add a draft to begin the batch.")
        return

    st.dataframe(
        [
            {
                "Draft": number,
                "Flat ID": row["flat_id"],
                "Transaction date": row["transaction_date"],
                "Resale price (S$)": row["resale_price"],
            }
            for number, row in enumerate(drafts, start=1)
        ],
        hide_index=True,
        width="stretch",
    )
    selected = st.selectbox(
        "Draft to edit or remove",
        range(len(drafts)),
        format_func=lambda index: f"Draft {index + 1} (flat {drafts[index]['flat_id']})",
        key=f"transaction_batch_selection_{agent_id}_{len(drafts)}",
    )
    with st.form(f"edit_transaction_draft_{agent_id}_{len(drafts)}_{selected}"):
        edited = transaction_draft_fields(drafts[selected])
        if st.form_submit_button("Save draft changes"):
            drafts[selected] = edited
            queue_feedback(feedback_page, "Draft updated.", kind="toast")
            st.rerun()
    if st.button("Remove draft", key="danger_remove_draft"):
        del drafts[selected]
        queue_feedback(feedback_page, "Draft removed.", kind="toast")
        st.rerun()

    if not st.button("Commit batch", type="primary"):
        return

    committed = 0
    try:
        with st.spinner("Saving transaction batch…"), closing(get_mysql_connection()) as connection:
            committed = repository.create_agent_transactions_batch(connection, agent_id, drafts)
    except ValueError as error:
        st.error(f"The batch could not be saved. {error} Your drafts were kept.")
        return
    except mysql.connector.Error as error:
        if not committed:
            if error.errno == errorcode.ER_DUP_ENTRY:
                st.error(
                    "Batch rolled back. A flat appears twice or already has a transaction for your account. "
                    "Your drafts were kept."
                )
            elif error.errno == errorcode.ER_NO_REFERENCED_ROW_2:
                st.error("Batch rolled back. A draft refers to a missing flat or agent. Your drafts were kept.")
            else:
                logging.exception("Could not confirm the transaction batch commit")
                st.error(
                    "The commit could not be confirmed. Your drafts were kept. "
                    "Check your recorded transactions before retrying."
                )
            return
        logging.exception("Could not close the connection after committing the transaction batch")

    st.session_state.pop(drafts_key, None)
    noun = "transaction" if committed == 1 else "transactions"
    queue_feedback(feedback_page, f"{committed:,} {noun} saved.")
    st.rerun()


def render_agent_transactions(agent_id: int) -> None:
    st.subheader("My resale transactions")
    action = st.radio(
        "Transaction action",
        ["Create", "Batch create", "Update", "Delete"],
        horizontal=True,
        label_visibility="collapsed",
        key="transaction_action",
    )
    if action == "Batch create":
        render_transaction_batch(agent_id)
        return

    with closing(get_mysql_connection()) as connection:
        render_recorded_transactions(connection, agent_id, action)


def render_recorded_transactions(connection: Any, agent_id: int, action: str) -> None:
    feedback_page = f"recorded_transactions_{agent_id}"
    show_feedback(feedback_page)
    with st.spinner("Loading your transactions…"):
        transactions = repository.list_agent_transactions(connection, agent_id)
    if transactions:
        st.caption("Showing up to 100 of your most recent transactions.")
        st.dataframe(transactions, width="stretch", hide_index=True, column_config=RESALE_COLUMNS)
    else:
        st.info("You have not recorded any resale transactions.")

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
            with st.spinner("Checking flat record…"):
                flat = repository.get_flat(connection, int(flat_id))
            if flat is None:
                st.error("No flat record exists with that ID.")
            else:
                try:
                    with st.spinner("Creating transaction…"):
                        repository.create_agent_transaction(
                            connection, agent_id, int(flat_id), transaction_date, resale_price
                        )
                    queue_feedback(feedback_page, "Transaction created.")
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
    with st.spinner("Looking up your transaction…"):
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
            with st.spinner("Checking flat record…"):
                flat = repository.get_flat(connection, int(new_flat_id))
            if flat is None:
                st.error("No flat record exists with that ID.")
            else:
                try:
                    with st.spinner("Saving transaction…"):
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
                        queue_feedback(feedback_page, "Transaction updated.")
                        st.rerun()
                    else:
                        st.error("The transaction could not be updated.")
    else:
        st.write(
            f'Flat **{selected_flat_id}** — {selected_transaction["flat_type"]}, '
            f'{selected_transaction["block_number"]} '
            f'{selected_transaction["road_name"]}, {selected_transaction["town"]}'
        )
        if st.button("Delete transaction", type="primary", key="danger_delete_transaction"):
            with st.spinner("Deleting transaction…"):
                deleted = repository.delete_agent_transaction(connection, agent_id, selected_flat_id)
            if deleted:
                st.session_state.pop("selected_transaction_flat_id", None)
                queue_feedback(feedback_page, "Transaction deleted.")
                st.rerun()
            else:
                st.error("The transaction could not be deleted.")
