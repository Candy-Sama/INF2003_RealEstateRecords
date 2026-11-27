from __future__ import annotations

import logging
from contextlib import closing
from datetime import date
from typing import Any

import mysql.connector
import streamlit as st
from pymongo import errors as mongo_errors

from app.app_modules.analytics import analytics_builder as builder
from app.app_modules.analytics import analytics_charts, analytics_sql, analytics_store
from app.app_modules.analytics.analytics_store import escape_markdown
from app.app_modules.database.database import (
    get_mongodb_client,
    get_mongodb_database_name,
    get_mysql_connection,
)
from app.app_modules.ui_feedback import queue_feedback, show_feedback

CACHE_TTL_SECONDS = 600
NONE_CHOICE = "(none)"
AUTO_SORT = "(automatic)"
TYPE_LABELS = {
    "auto": "Auto (recommended)",
    "table": "Table",
    "kpi": "KPI numbers",
    "bar": "Bar chart",
    "line": "Line chart",
    "area": "Area chart",
    "scatter": "Scatter plot",
    "heatmap": "Heatmap",
}
WIDTH_LABELS = {"half": "Half width", "full": "Full width"}
FORMAT_LABELS = {
    "auto": "Automatic",
    "currency": "Currency ($)",
    "integer": "Whole number",
    "percent": "Percent (value is already 0-100)",
}
MODE_LABELS = {
    "summarise": "Summarise (groups and totals, for charts)",
    "list": "List rows (a plain table)",
}
ROLE_LABELS = {
    "x": "X axis (category or time)",
    "y": "Y axis (number)",
    "color": "Group / colour (optional)",
    "value": "Value (number, sets the colour)",
}
ROLES_BY_TYPE = {
    "table": (), "kpi": (),
    "bar": ("x", "y", "color"), "line": ("x", "y", "color"), "area": ("x", "y", "color"),
    "scatter": ("x", "y", "color"), "heatmap": ("x", "y", "value"),
}
BLANK_CARD = {
    "title": "", "description": "", "sql": "", "display_type": "auto",
    "width": "half", "number_format": "auto", "mapping": {},
}
TABLE_HELP = {
    "p": "Where the flat is, and where nearby stations are measured from.",
    "sp": "Where the station itself is. Separate from the address of the flat.",
    "n": "One row per (address, station) pair, with the distance between them.",
    "calc": "Ready-made measures, so you don't have to write the formulas.",
}
SQL_RULES = (
    "One SELECT (or WITH) statement. No comments, no writes, and the `agents` table is off "
    f"limits. Runs read-only with a {analytics_sql.TIMEOUT_MS // 1000}s limit, capped at "
    f"{analytics_sql.MAX_ROWS:,} rows. Add a LIMIT if you rely on ORDER BY."
)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def run_card_query(sql: str):
    """
    Run a card's query. Cached, so a rerun doesn't hit the all the tables again.
    Validates before opening a connection
    """
    analytics_sql.validate_query(sql)
    with closing(get_mysql_connection()) as connection:
        return analytics_sql.run_query(connection, sql)


@st.cache_data(ttl=3600, show_spinner=False)
def filter_values(key: str) -> list[str]:
    """Choices for a text filter. Table and column come from the builder's catalog."""
    table, column = builder.filter_source(key)
    with closing(get_mysql_connection()) as connection:
        with connection.cursor(buffered=True) as cursor:
            cursor.execute(f"SELECT DISTINCT `{column}` FROM `{table}` ORDER BY 1 LIMIT 500")
            values = [row[0] for row in cursor.fetchall()]
    return [v for v in values if builder.is_safe_text(v)]


QUERY_ERRORS = (analytics_sql.QueryRejected, mysql.connector.Error, ValueError)


def show_error(error: Exception) -> None:
    logging.warning("Analytics query failed: %s", error)
    st.error(escape_markdown(str(error)))


def keep_valid(key: str, options: list[Any], default: Any) -> None:
    """Make sure a widget's stored value is one of its options."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
@st.fragment
def render_analytics_tab() -> None:
    agent = st.session_state.get("agent")
    if not agent:
        return
    try:
        with closing(get_mongodb_client()) as client:
            db = client[get_mongodb_database_name()]
            render_analytics(db, int(agent["agent_id"]))
    except (mongo_errors.PyMongoError, ValueError) as error:
        logging.exception("Analytics tab failed")
        st.error("Could not load analytics. Check that MongoDB is running.")
        with st.expander("Technical details"):
            st.code(str(error))


def render_analytics(db: Any, agent_id: int) -> None:
    if not st.session_state.get("an_indexes_ready"):
        analytics_store.ensure_indexes(db)
        st.session_state["an_indexes_ready"] = True
    analytics_store.seed_defaults(db, agent_id)

    title, new_col, refresh_col, restore_col = st.columns(
        [3, 1, 1, 1], vertical_alignment="center"
    )
    title.subheader("Analytics")
    new_col.button("＋ New card", type="primary", width="stretch",
                   on_click=open_editor, args=(None,))
    if refresh_col.button("Refresh data", width="stretch"):
        run_card_query.clear()
        queue_feedback("analytics", "Refreshing cards…", kind="toast")
        st.rerun(scope="fragment")
    if restore_col.button("Restore defaults", width="stretch",
                          help="Re-add any default card you have deleted."):
        added = analytics_store.restore_defaults(db, agent_id)
        if added:
            noun = "card" if added == 1 else "cards"
            queue_feedback("analytics", f"Restored {added} default {noun}.")
        else:
            queue_feedback("analytics", "All default cards are already here.", kind="info")
        st.rerun(scope="fragment")

    show_feedback("analytics")
    st.caption(
        "Each card is a saved query and a display type. "
        f"Results are cached for {CACHE_TTL_SECONDS // 60} minutes."
    )

    if st.session_state.get("an_editor") is not None:
        render_editor(db, agent_id)

    cards = analytics_store.list_cards(db, agent_id)
    if not cards:
        st.info("No cards yet. Create one, or use **Restore defaults**.")
        return
    render_grid(cards, db, agent_id)


def render_grid(cards: list[dict[str, Any]], db: Any, agent_id: int) -> None:
    """Half-width cards pair up two per row; full-width cards take a row."""
    waiting = None
    for card in cards:
        if card["width"] == "full":
            if waiting is not None:
                left, _ = st.columns(2)
                with left:
                    render_card(waiting, db, agent_id)
                waiting = None
            render_card(card, db, agent_id)
        elif waiting is None:
            waiting = card
        else:
            left, right = st.columns(2)
            with left:
                render_card(waiting, db, agent_id)
            with right:
                render_card(card, db, agent_id)
            waiting = None
    if waiting is not None:
        left, _ = st.columns(2)
        with left:
            render_card(waiting, db, agent_id)


def ask_delete(card_id: str) -> None:
    st.session_state["an_delete"] = card_id


def cancel_delete() -> None:
    st.session_state.pop("an_delete", None)


def render_card_details(card: dict[str, Any]) -> None:
    with st.expander("Query details"):
        if card.get("source") == "builder" and card.get("builder"):
            st.markdown("**Made with the visual builder**")
            for line in builder.describe_spec(card["builder"]):
                st.markdown("- " + escape_markdown(line))
            st.caption("The SQL it generated (use the copy icon to reuse it):")
        else:
            st.caption("Custom SQL query:")
        st.code(card["sql"], language="sql")


def render_card(card: dict[str, Any], db: Any, agent_id: int) -> None:
    card_id = card["id"]
    with st.container(border=True):
        head, menu = st.columns([6, 1], vertical_alignment="center")
        head.markdown(f"**{escape_markdown(card['title'])}**")
        with menu.popover("⋮"):
            st.button("Edit", key=f"an_edit_{card_id}", width="stretch",
                      on_click=open_editor, args=(card,))
            if st.button("Duplicate", key=f"an_dup_{card_id}", width="stretch"):
                try:
                    analytics_store.duplicate_card(db, agent_id, card_id)
                except ValueError as error:
                    queue_feedback("analytics", escape_markdown(str(error)), kind="warning")
                else:
                    queue_feedback("analytics", "Card duplicated.")
                st.rerun(scope="fragment")
            st.button("Delete", key=f"an_del_{card_id}", width="stretch",
                      on_click=ask_delete, args=(card_id,))

        if st.session_state.get("an_delete") == card_id:
            st.warning(f"Delete “{escape_markdown(card['title'])}”? This can't be undone.")
            yes, no = st.columns(2)
            if yes.button("Yes, delete", key=f"an_yes_{card_id}", type="primary",
                          width="stretch"):
                if analytics_store.delete_card(db, agent_id, card_id):
                    queue_feedback("analytics", "Card deleted.")
                else:
                    queue_feedback("analytics", "That card no longer exists.", kind="warning")
                st.session_state.pop("an_delete", None)
                st.rerun(scope="fragment")
            no.button("Cancel", key=f"an_no_{card_id}", width="stretch", on_click=cancel_delete)

        if card["description"]:
            st.caption(escape_markdown(card["description"]))

        try:
            frame, truncated = run_card_query(card["sql"])
            analytics_charts.render_card_body(frame, card)
            note = f"{len(frame):,} row(s) · {TYPE_LABELS.get(card['display_type'], '')}"
            if truncated:
                note += f" · truncated at {analytics_sql.MAX_ROWS:,} rows"
            st.caption(note)
        except analytics_charts.CardConfigError as error:
            st.warning(escape_markdown(str(error)))
        except QUERY_ERRORS as error:
            show_error(error)
        render_card_details(card)



def clear_editor_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(("an_b_", "an_ed_")) or key in (
            "an_editor", "an_preview", "an_auto_preview", "an_sql_dirty"
        ):
            st.session_state.pop(key, None)


def load_spec(spec: dict[str, Any] | None) -> None:
    """Put a saved builder spec (or blank defaults) into the builder's widget keys."""
    spec = spec or {}
    st.session_state["an_b_mode"] = spec.get("mode", "summarise")
    opened = {"rt"}
    for item in spec.get("fields", []):
        definition = builder.FIELDS.get(item["key"])
        if definition is None:
            continue
        st.session_state[f"an_b_chk|{item['key']}"] = True
        st.session_state[f"an_b_role|{item['key']}"] = item.get("role")
        st.session_state[f"an_b_bucket|{item['key']}"] = item.get("bucket") or "month"
        opened.add(definition.table)
    st.session_state["an_b_open"] = opened

    ids = []
    for number, item in enumerate(spec.get("filters", []), start=1):
        ids.append(number)
        st.session_state[f"an_b_ffield_{number}"] = item["key"]
        if item["op"] == "in":
            st.session_state[f"an_b_fvals_{number}"] = list(item["values"])
        elif builder.FIELDS[item["key"]].filter_kind == "date":
            for side in ("min", "max"):
                value = item.get(side)
                st.session_state[f"an_b_f{side}_{number}"] = (
                    date.fromisoformat(value) if value else None
                )
        else:
            st.session_state[f"an_b_fmin_{number}"] = item.get("min")
            st.session_state[f"an_b_fmax_{number}"] = item.get("max")
    st.session_state["an_b_filters"] = ids
    st.session_state["an_b_fseq"] = len(ids)

    sort = spec.get("sort") or {}
    st.session_state["an_b_sort"] = sort.get("field") or AUTO_SORT
    st.session_state["an_b_dir"] = "Descending" if sort.get("dir") == "desc" else "Ascending"
    st.session_state["an_b_limit"] = int(spec.get("limit", 0))
    st.session_state["an_b_nearest"] = bool(spec.get("nearest_only", True))


def open_editor(card: dict[str, Any] | None) -> None:
    """Callback: open the panel, pre-filled for an edit or blank for a new card."""
    clear_editor_state()
    source = card or BLANK_CARD
    mapping = source.get("mapping") or {}
    st.session_state["an_editor"] = {"id": card["id"] if card else None}
    st.session_state["an_ed_title"] = source["title"]
    st.session_state["an_ed_desc"] = source["description"]
    st.session_state["an_ed_width"] = source["width"]
    st.session_state["an_ed_format"] = source["number_format"]
    st.session_state["an_ed_sql"] = source["sql"]
    st.session_state["an_ed_horizontal"] = bool(mapping.get("horizontal"))

    spec = source.get("builder") if card else None
    if card is None or spec:
        st.session_state["an_ed_mode"] = "builder"
        st.session_state["an_sql_dirty"] = False
        st.session_state["an_ed_type"] = (spec or {}).get("display_choice", "auto")
        load_spec(spec)
    else:
        st.session_state["an_ed_mode"] = "sql"
        st.session_state["an_sql_dirty"] = True
        st.session_state["an_ed_type"] = source["display_type"]
        st.session_state["an_ed_x"] = mapping.get("x")
        st.session_state["an_ed_y"] = mapping.get("y")
        st.session_state["an_ed_color"] = mapping.get("color") or NONE_CHOICE
        st.session_state["an_ed_value"] = mapping.get("value")
    if card is not None:
        st.session_state["an_auto_preview"] = True


def close_editor() -> None:
    clear_editor_state()


def mark_sql_dirty() -> None:
    st.session_state["an_sql_dirty"] = True


def reset_sql() -> None:
    st.session_state["an_sql_dirty"] = False  # the next run copies the builder's SQL back


def use_builder() -> None:
    """Leave SQL-only mode and start a fresh builder."""
    st.session_state["an_ed_mode"] = "builder"
    st.session_state["an_sql_dirty"] = False
    st.session_state["an_ed_type"] = "auto"
    st.session_state.pop("an_preview", None)
    for key in list(st.session_state.keys()):
        if key.startswith("an_b_"):
            st.session_state.pop(key, None)
    load_spec(None)


def run_preview(sql: str) -> None:
    sql = sql.strip()
    try:
        frame, _ = run_card_query(sql)
        st.session_state["an_preview"] = {
            "sql": sql, "columns": list(frame.columns), "error": None,
        }
    except QUERY_ERRORS as error:
        st.session_state["an_preview"] = {"sql": sql, "columns": [], "error": str(error)}


# Builder
def read_spec(include_sort: bool = True) -> dict[str, Any]:
    """Collect the builder's widget values into a spec dict (validated later)."""
    state = st.session_state
    fields = []
    for alias in builder.UI_TABLES:
        for definition in builder.fields_for_table(alias):
            if not state.get(f"an_b_chk|{definition.key}"):
                continue
            item = {"key": definition.key,
                    "role": state.get(f"an_b_role|{definition.key}")
                    or builder.default_role(definition)}
            if definition.kind == "date":
                item["bucket"] = state.get(f"an_b_bucket|{definition.key}") or "month"
            fields.append(item)

    filters = []
    for number in state.get("an_b_filters", []):
        key = state.get(f"an_b_ffield_{number}")
        definition = builder.FIELDS.get(key)
        if definition is None or definition.filter_kind is None:
            continue
        if definition.filter_kind == "text":
            values = state.get(f"an_b_fvals_{number}") or []
            if values:
                filters.append({"key": key, "op": "in", "values": list(values)})
        else:
            low, high = state.get(f"an_b_fmin_{number}"), state.get(f"an_b_fmax_{number}")
            if low is None and high is None:
                continue
            if definition.filter_kind == "date":
                low = low.isoformat() if low else None
                high = high.isoformat() if high else None
            filters.append({"key": key, "op": "range", "min": low, "max": high})

    sort_field = state.get("an_b_sort")
    return {
        "mode": state.get("an_b_mode", "summarise"),
        "fields": fields,
        "filters": filters,
        "sort": {
            "field": sort_field if include_sort and sort_field not in (None, AUTO_SORT) else None,
            "dir": "desc" if state.get("an_b_dir") == "Descending" else "asc",
        },
        "limit": int(state.get("an_b_limit") or 0),
        "nearest_only": bool(state.get("an_b_nearest", True)),
    }


def try_compile(spec: dict[str, Any]):
    """(Compiled, None) or (None, message)."""
    if not spec["fields"]:
        return None, "Tick at least one column to get started."
    try:
        return builder.compile_spec(spec), None
    except ValueError as error:
        return None, str(error)


def add_filter() -> None:
    number = st.session_state.get("an_b_fseq", 0) + 1
    st.session_state["an_b_fseq"] = number
    st.session_state[f"an_b_ffield_{number}"] = "p.town"
    st.session_state.setdefault("an_b_filters", []).append(number)


def remove_filter(number: int) -> None:
    st.session_state["an_b_filters"] = [
        n for n in st.session_state.get("an_b_filters", []) if n != number
    ]
    for key in list(st.session_state.keys()):
        if key.endswith(f"_{number}") and key.startswith("an_b_f"):
            st.session_state.pop(key, None)


def render_table_picker(alias: str, summarise: bool) -> None:
    opened = alias in st.session_state.get("an_b_open", set())
    with st.expander(builder.TABLE_LABELS[alias], expanded=opened):
        if alias in TABLE_HELP:
            st.caption(TABLE_HELP[alias])
        for definition in builder.fields_for_table(alias):
            pick, role_slot, bucket_slot = st.columns([3, 2, 2])
            label = f"🔑 {definition.label}" if definition.is_key else definition.label
            checked = pick.checkbox(label, key=f"an_b_chk|{definition.key}",
                                    help=definition.help)
            if not (checked and summarise):
                continue
            role_key = f"an_b_role|{definition.key}"
            keep_valid(role_key, list(definition.roles), builder.default_role(definition))
            role = role_slot.selectbox(
                "Role", definition.roles, key=role_key,
                format_func=builder.ROLE_LABELS.get, label_visibility="collapsed",
            )
            if definition.kind == "date" and role == "group":
                bucket_key = f"an_b_bucket|{definition.key}"
                keep_valid(bucket_key, list(builder.BUCKETS), "month")
                bucket_slot.selectbox(
                    "Date grouping", builder.BUCKETS, key=bucket_key,
                    format_func=builder.BUCKET_LABELS.get, label_visibility="collapsed",
                )


def render_filters() -> None:
    st.markdown("**Filters** (optional)")
    for number in list(st.session_state.get("an_b_filters", [])):
        field_col, value_col, remove_col = st.columns([3, 5, 1], vertical_alignment="center")
        keys = builder.filterable_keys()
        keep_valid(f"an_b_ffield_{number}", keys, "p.town")
        key = field_col.selectbox(
            "Field", keys, key=f"an_b_ffield_{number}",
            format_func=lambda k: builder.FIELDS[k].label, label_visibility="collapsed",
        )
        kind = builder.FIELDS[key].filter_kind
        with value_col:
            if kind == "text":
                try:
                    options = filter_values(key)
                except QUERY_ERRORS as error:
                    options = []
                    show_error(error)
                saved = st.session_state.get(f"an_b_fvals_{number}") or []
                st.session_state[f"an_b_fvals_{number}"] = [v for v in saved if v in options]
                st.multiselect("Is one of", options, key=f"an_b_fvals_{number}",
                               placeholder="Choose one or more", label_visibility="collapsed")
            elif kind == "number":
                low, high = st.columns(2)
                low.number_input("Minimum", value=None, key=f"an_b_fmin_{number}",
                                 placeholder="no minimum", label_visibility="collapsed")
                high.number_input("Maximum", value=None, key=f"an_b_fmax_{number}",
                                  placeholder="no maximum", label_visibility="collapsed")
            else:
                low, high = st.columns(2)
                low.date_input("From", value=None, key=f"an_b_fmin_{number}",
                               label_visibility="collapsed")
                high.date_input("To", value=None, key=f"an_b_fmax_{number}",
                                label_visibility="collapsed")
        remove_col.button("✕", key=f"an_b_frm_{number}", on_click=remove_filter, args=(number,),
                          help="Remove this filter")
    if len(st.session_state.get("an_b_filters", [])) < builder.MAX_FILTERS:
        st.button("＋ Add filter", key="an_b_fadd", on_click=add_filter)


def render_builder() -> dict[str, Any]:
    """Draw the visual builder. Returns the current spec (may be incomplete)."""
    st.markdown("**1. Choose your data**")
    mode = st.radio("What should the card do?", list(MODE_LABELS), key="an_b_mode",
                    format_func=MODE_LABELS.get, horizontal=True, label_visibility="collapsed")
    summarise = mode == "summarise"
    st.caption(
        "Tick the columns you want. Columns from different tables are joined automatically."
        + (" Then say what to do with each one: group by it, or average / total / count it."
           if summarise else "")
    )
    for alias in builder.UI_TABLES:
        render_table_picker(alias, summarise)
    render_filters()

    compiled, _ = try_compile(read_spec(include_sort=False))
    sort_options = [AUTO_SORT] + ([o["alias"] for o in compiled.outputs] if compiled else [])
    labels = {o["alias"]: o["label"] for o in compiled.outputs} if compiled else {}
    keep_valid("an_b_sort", sort_options, AUTO_SORT)
    sort_col, dir_col, limit_col = st.columns([3, 2, 2], vertical_alignment="bottom")
    sort_col.selectbox("Sort by", sort_options, key="an_b_sort",
                       format_func=lambda a: labels.get(a, a))
    dir_col.radio("Order", ["Ascending", "Descending"], key="an_b_dir", horizontal=True)
    limit_col.number_input("Limit rows (0 = none)", min_value=0, max_value=builder.MAX_LIMIT,
                           step=10, key="an_b_limit",
                           help="With a limit and a total, you get the biggest first (a top-N).")
    if compiled and builder.nearest_rule_applies(compiled.tables):
        st.checkbox(
            "Count each flat once: use only its nearest station", key="an_b_nearest",
            help="A flat can have several nearby stations. With this on, it is matched to its "
                 "closest one only.",
        )
        if not st.session_state.get("an_b_nearest", True):
            st.warning(
                "Every flat now appears once per nearby station. Counts and totals are inflated, "
                "and averages lean towards flats with many stations nearby."
            )
    return read_spec()


# Create / edit panel
def effective_mode(mode: str, compiled: Any, sql_text: str) -> str:
    """builder: the SQL is exactly what the builder makes. sql: it was written or edited."""
    if mode == "sql":
        return "sql"
    if compiled is not None:
        return "builder" if sql_text.strip() == compiled.sql.strip() else "sql"
    return "sql" if sql_text.strip() else "incomplete"


def _show_preview(preview: dict[str, Any], draft: dict[str, Any]) -> bool:
    """Draw the preview. Returns False if it can't be shown, which blocks saving."""
    try:
        frame, _ = run_card_query(preview["sql"])
        st.markdown("**Preview**")
        analytics_charts.render_card_body(frame, draft)
        return True
    except analytics_charts.CardConfigError as error:
        st.warning(escape_markdown(str(error)))
    except QUERY_ERRORS as error:
        show_error(error)
    return False


def _builder_display(spec, compiled, choice, preview, stale):
    """Work out the display type and mapping from the builder choices, then preview."""
    try:
        base_type, _ = builder.resolve_display(compiled, spec["mode"], choice)
        horizontal = False
        if base_type == "bar":
            horizontal = st.checkbox("Horizontal bars (sorted by value)", key="an_ed_horizontal")
        display_type, mapping = builder.resolve_display(
            compiled, spec["mode"], choice, horizontal
        )
    except ValueError as error:
        st.warning(escape_markdown(str(error)))
        return False, choice, {}
    if choice == "auto":
        st.caption(f"Auto picked: {TYPE_LABELS[display_type]}.")
    draft = {"display_type": display_type, "mapping": mapping,
             "number_format": st.session_state["an_ed_format"]}
    ok = not stale and _show_preview(preview, draft)
    return ok, display_type, mapping


def render_mapping_inputs(display_type: str, columns: list[str]) -> dict[str, Any]:
    """SQL cards only: which result column plays which role."""
    roles = ROLES_BY_TYPE[display_type]
    if not roles:
        if display_type == "kpi":
            st.caption("KPI cards show the first row, one number per column (first 4 columns).")
        return {}

    defaults = {
        "x": columns[0],
        "y": columns[1] if len(columns) > 1 else columns[0],
        "value": columns[2] if len(columns) > 2 else columns[-1],
        "color": NONE_CHOICE,
    }
    mapping: dict[str, Any] = {}
    slots = st.columns(len(roles))
    for slot, role in zip(slots, roles):
        key = f"an_ed_{role}"
        options = [NONE_CHOICE, *columns] if role == "color" else list(columns)
        keep_valid(key, options, defaults[role])
        choice = slot.selectbox(ROLE_LABELS[role], options, key=key)
        mapping[role] = None if choice == NONE_CHOICE else choice
    if display_type == "bar":
        mapping["horizontal"] = st.checkbox("Horizontal bars (sorted by value)",
                                            key="an_ed_horizontal")
    return mapping


def render_editor(db: Any, agent_id: int) -> None:
    state = st.session_state
    editing_id = state["an_editor"]["id"]
    mode = state.get("an_ed_mode", "builder")

    with st.container(border=True):
        st.markdown("**Edit analytics card**" if editing_id else "**New analytics card**")
        st.text_input("Title", max_chars=analytics_store.MAX_TITLE, key="an_ed_title")
        st.text_area("Description (optional)", max_chars=analytics_store.MAX_DESCRIPTION,
                     height=70, key="an_ed_desc")

        spec, compiled, problem = None, None, None
        if mode == "builder":
            spec = render_builder()
            compiled, problem = try_compile(spec)
            if compiled and not state.get("an_sql_dirty"):
                state["an_ed_sql"] = compiled.sql  # keep the Advanced box in step with the GUI
            if compiled:
                st.caption("Result columns: " + ", ".join(o["label"] for o in compiled.outputs))
        else:
            st.markdown("**1. Your query**")
            st.info("This card uses a custom SQL query, which you edit under **Advanced (SQL)** "
                    "below.")
            st.button("Start over with the visual builder", key="an_ed_tobuilder",
                      on_click=use_builder, help="Replaces the SQL with a blank builder.")

        sql_text = state.get("an_ed_sql", "")
        effective = effective_mode(mode, compiled, sql_text)
        current_sql = compiled.sql if effective == "builder" else sql_text.strip()
        if mode == "builder" and effective == "sql":
            st.warning("You edited the SQL, so this card will be saved as a SQL-only card and "
                       "the builder choices above won't be kept. Use **Reset** under Advanced "
                       "to go back.")

        st.markdown("**2. Choose how to show it**")
        type_options = list(builder.DISPLAY_CHOICES) if effective == "builder" \
            else list(analytics_store.DISPLAY_TYPES)
        keep_valid("an_ed_type", type_options, "auto" if effective == "builder" else "table")
        type_col, width_col, format_col = st.columns(3)
        display_choice = type_col.selectbox("Display type", type_options,
                                            format_func=TYPE_LABELS.get, key="an_ed_type")
        width_col.selectbox("Card width", analytics_store.WIDTHS,
                            format_func=WIDTH_LABELS.get, key="an_ed_width")
        format_col.selectbox("Number format", analytics_store.NUMBER_FORMATS,
                             format_func=FORMAT_LABELS.get, key="an_ed_format")

        st.markdown("**3. Preview and save**")
        can_save = False
        display_type, mapping = display_choice, {}
        if effective == "incomplete":
            st.info(problem or "Choose your data above first.")
        else:
            if state.pop("an_auto_preview", False):
                run_preview(current_sql)
            if st.button("Run preview", key="an_ed_run"):
                run_preview(current_sql)
            preview = state.get("an_preview")
            if preview is None:
                st.info("Run the preview to check the result"
                        + (" and choose columns." if effective == "sql" else "."))
            elif preview["error"]:
                st.error(escape_markdown(preview["error"]))
            else:
                stale = preview["sql"] != current_sql
                if stale:
                    st.warning("The query changed after the last preview. Run the preview again.")
                if effective == "builder":
                    can_save, display_type, mapping = _builder_display(
                        spec, compiled, display_choice, preview, stale
                    )
                else:
                    mapping = render_mapping_inputs(display_choice, preview["columns"])
                    can_save = not stale and _show_preview(
                        preview, {"display_type": display_choice, "mapping": mapping,
                                  "number_format": state["an_ed_format"]})

        left, right = st.columns(2)
        with left:
            save_col, cancel_col = st.columns(2)
            if save_col.button("Save card", type="primary", disabled=not can_save,
                               key="an_ed_save", width="stretch"):
                data = {
                    "title": state["an_ed_title"],
                    "description": state["an_ed_desc"],
                    "width": state["an_ed_width"],
                    "number_format": state["an_ed_format"],
                    "display_type": display_type,
                    "mapping": mapping,
                }
                if effective == "builder":
                    data["builder"] = {**spec, "display_choice": display_choice}
                else:
                    data["sql"] = sql_text
                try:
                    if editing_id:
                        analytics_store.update_card(db, agent_id, editing_id, data)
                    else:
                        analytics_store.create_card(db, agent_id, data)
                except ValueError as error:
                    st.error(escape_markdown(str(error)))
                else:
                    queue_feedback("analytics", "Card updated." if editing_id else "Card created.")
                    close_editor()
                    st.rerun(scope="fragment")
            cancel_col.button("Cancel", key="an_ed_cancel", width="stretch",
                              on_click=close_editor)
        with right:
            with st.expander("Advanced (SQL)", expanded=(mode == "sql")):
                if mode == "builder":
                    st.caption("This is the SQL the builder generated. Copy it into a new card "
                               "to start from it, or edit it here to make this card SQL-only.")
                    st.button("Reset to the builder's SQL", key="an_ed_reset",
                              on_click=reset_sql, disabled=effective != "sql" or compiled is None)
                st.text_area("SQL query", height=260, max_chars=analytics_sql.MAX_SQL_CHARS,
                             key="an_ed_sql", on_change=mark_sql_dirty,
                             placeholder="SELECT p.town, AVG(rt.resale_price) AS avg_price\n"
                                         "FROM resale_transaction rt\n"
                                         "JOIN flat f ON f.flat_id = rt.FLAT_flat_id\n"
                                         "JOIN place p ON p.block_id = f.block_id\n"
                                         "GROUP BY p.town")
                st.caption(SQL_RULES)
