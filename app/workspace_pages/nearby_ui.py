"""Nearby station filtering and flat comparisons UI."""

from contextlib import closing
from typing import Any

import altair as alt
import mysql.connector
import pandas as pd
import streamlit as st

from app import repository
from app.app_modules.database.database import get_mysql_connection
from app.app_modules.nearby import nearby_function
from app.app_modules.ui_feedback import show_database_error


NEARBY_PAGE_SIZE = 100
DISTANCE_BANDS = {"≤ 300 m": 300, "≤ 500 m": 500, "≤ 1 km": 1000}
CLEAR_FILTERS = "✕ Clear filters"
CLEAR_SELECTION = "✕ Clear selection"
SUBVIEWS = ["Flats near the same stations", "Recent comparable sales"]
CATCHMENT_OPTIONS = [*repository.CATCHMENT_RADII_M, "Same block", "Same town"]
PERIOD_MONTH_OPTIONS = [6, 12, 24, 36]
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
COMP_TABLE_COLUMNS = {
    "flat_id": st.column_config.NumberColumn("Flat ID"),
    "transaction_date": st.column_config.DateColumn("Sale date"),
    "resale_price": st.column_config.NumberColumn("Price ($)", format="$%.0f"),
    "price_per_sqm": st.column_config.NumberColumn("Price / m² ($)", format="$%.0f"),
    "floor_area_sqm": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
    "storey_range": "Storey range",
    "remaining_lease_months": st.column_config.NumberColumn("Remaining lease (mo)"),
    "block_number": "Block",
    "road_name": "Street",
    "town": "Town",
    "nearest_station_m": st.column_config.NumberColumn("Nearest station (m)"),
}


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
    st.session_state.pop("nb_subview", None)
    st.session_state["nb_nonce"] = st.session_state.get("nb_nonce", 0) + 1


@st.fragment
def render_nearby_tab() -> None:
    try:
        with closing(get_mysql_connection()) as connection:
            render_nearby_stations(connection)
    except (mysql.connector.Error, ValueError) as error:
        show_database_error(error)


def _render_colored_stat_card(
    title: str,
    primary_text: str,
    sub_text: str,
    tone: str = "default",
) -> None:
    st.markdown(
        f"""
        <div class="nearby-stat nearby-stat--{tone}">
            <div class="nearby-stat-title">{title}</div>
            <div class="nearby-stat-value">{primary_text}</div>
            <div class="nearby-stat-note">{sub_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_comparable_chart(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    chart_records: list[dict[str, Any]] = []
    for r in rows:
        psm = r.get("price_per_sqm")
        tx_date = r.get("transaction_date")
        if psm is not None and tx_date is not None:
            chart_records.append({
                "Sale date": str(tx_date),
                "Price per sqm": float(psm),
                "Role": "Comparable sale",
                "Label": f'{r.get("block_number", "")} {r.get("road_name", "")} ({r.get("storey_range", "")})',
            })

    if reference.get("price_per_sqm") is not None and reference.get("transaction_date") is not None:
        chart_records.append({
            "Sale date": str(reference["transaction_date"]),
            "Price per sqm": float(reference["price_per_sqm"]),
            "Role": "Selected reference flat",
            "Label": f'{reference.get("block_number", "")} {reference.get("road_name", "")} (Ref)',
        })

    if not chart_records:
        st.caption("No chartable sale dates and price-per-sqm values in the current selection.")
        return

    df = pd.DataFrame(chart_records)
    df["Sale date"] = pd.to_datetime(df["Sale date"])

    points = (
        alt.Chart(df)
        .mark_circle(size=75, opacity=1)
        .encode(
            x=alt.X("Sale date:T", title="Sale date"),
            y=alt.Y("Price per sqm:Q", title="Price per m² ($)"),
            color=alt.Color(
                "Role:N",
                scale=alt.Scale(
                    domain=["Comparable sale", "Selected reference flat"],
                    range=["#2e866c", "#b86a43"],
                ),
                title="Series",
            ),
            tooltip=["Role:N", "Label:N", "Sale date:T", alt.Tooltip("Price per sqm:Q", format="$,.0f")],
        )
    )

    layers = [points]
    median_psm = summary.get("median_psm")
    if median_psm is not None:
        median_df = pd.DataFrame({"median_psm": [float(median_psm)]})
        rule = (
            alt.Chart(median_df)
            .mark_rule(strokeDash=[5, 4], color="#298775", size=2)
            .encode(y=alt.Y("median_psm:Q"))
        )
        layers.append(rule)

    st.altair_chart(alt.layer(*layers).properties(height=300), width="stretch")


def _render_comparable_sales_subview(
    connection: Any,
    reference: dict[str, Any],
    station_ids: list[int],
    nearest_station_m: int | None,
) -> None:
    st.session_state.setdefault("nb_comp_catchment", "500 m")
    st.session_state.setdefault("nb_comp_months", 12)
    st.session_state.setdefault("nb_comp_similar_size", True)

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 2], vertical_alignment="center")
        c1.markdown(f"**Flat type:** `{reference.get('flat_type', '—')}`")
        catchment = c2.selectbox(
            "Catchment", CATCHMENT_OPTIONS, key="nb_comp_catchment",
            help="For a distance option, both flats must be within the radius of the same station.",
        )
        months = c3.selectbox(
            "Period (months)",
            PERIOD_MONTH_OPTIONS,
            key="nb_comp_months",
            format_func=lambda m: f"Last {m} months",
        )
        similar_size = c4.checkbox("Similar size (±10 m²)", key="nb_comp_similar_size")

    radius_m = repository.CATCHMENT_RADII_M.get(catchment)
    if radius_m is not None and (nearest_station_m is None or nearest_station_m > radius_m):
        st.info(
            f"No station is within {catchment} of the reference flat. "
            "Try **Same block** or **Same town**."
        )
        return

    options = {
        "catchment": catchment,
        "months": int(months),
        "similar_size": bool(similar_size),
    }
    rows, truncated, cutoff_date = repository.search_comparable_sales(
        connection, reference, station_ids, options, row_cap=repository.COMPARABLE_ROW_CAP
    )
    summary = repository.summarize_comparable_sales(rows, reference.get("price_per_sqm"))

    sample_count = summary["sample_count"]
    is_small = summary["is_small_sample"]
    sample_tone = "warning" if is_small else ("default" if sample_count > 0 else "neutral")
    sample_sub = (
        f"Under {repository.SMALL_SAMPLE_THRESHOLD} sales (thin sample)"
        if is_small
        else f"Since {cutoff_date.isoformat()}"
    )

    med_price_text = f'${summary["median_price"]:,.0f}' if summary["median_price"] is not None else "—"
    med_psm_text = f'${summary["median_psm"]:,.0f}/m²' if summary["median_psm"] is not None else "—"
    iqr_text = (
        f'${summary["psm_p25"]:,.0f} – ${summary["psm_p75"]:,.0f}/m²'
        if summary["psm_p25"] is not None and summary["psm_p75"] is not None
        else "—"
    )
    iqr_price_sub = (
        f'Price P25–P75: ${summary["price_p25"]:,.0f} – ${summary["price_p75"]:,.0f}'
        if summary["price_p25"] is not None and summary["price_p75"] is not None
        else "No percentile spread"
    )

    diff_pct = summary["diff_vs_median_pct"]
    if diff_pct is None:
        diff_text = "—"
        diff_sub = "Reference sale price/m² unavailable"
        diff_tone = "neutral"
    else:
        sign = "+" if diff_pct >= 0 else ""
        diff_text = f"{sign}{diff_pct:.1f}%"
        ref_psm_val = summary["reference_psm"]
        diff_sub = f'Ref ${ref_psm_val:,.0f}/m² vs median' if ref_psm_val is not None else "vs median"
        if diff_pct > 5:
            diff_tone = "warning"
        elif diff_pct < -5:
            diff_tone = "below"
        else:
            diff_tone = "default"

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        _render_colored_stat_card("Sample count", f"{sample_count:,}", sample_sub, sample_tone)
    with k2:
        _render_colored_stat_card("Median price / m²", med_psm_text, f"Median price: {med_price_text}")
    with k3:
        _render_colored_stat_card("Typical range (P25–P75)", iqr_text, iqr_price_sub, "range")
    with k4:
        _render_colored_stat_card("Reference vs. median", diff_text, diff_sub, diff_tone)

    if truncated:
        st.caption(
            f"Showing the most recent {repository.COMPARABLE_ROW_CAP:,} comparable sales "
            f"(result cap reached; narrow catchment, period, or size for a fuller slice)."
        )

    if not rows:
        st.info("No comparable sales match the selected catchment, period, and size criteria.")
        return

    _render_comparable_chart(rows, summary, reference)

    st.session_state.setdefault("nb_comp_nonce", 0)
    st.markdown("**Comparable sales behind the summary** (select a row to set it as the new reference flat)")
    event = st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config=COMP_TABLE_COLUMNS,
        on_select="rerun",
        selection_mode="single-row",
        key=f'nb_comp_table_{st.session_state["nb_comp_nonce"]}',
    )

    csv_bytes = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download comparable sales CSV",
        data=csv_bytes,
        file_name=f"comparable_sales_flat_{reference['flat_id']}.csv",
        mime="text/csv",
    )

    st.caption(
        "Notes: Station catchments can overlap across adjacent MRT/LRT stations; station distances "
        "in `nearby` are straight-line sphere distances; smaller sample counts have wider variance."
    )

    if event.selection.rows:
        picked = rows[event.selection.rows[0]]
        st.session_state["nearby_focus"] = {
            "flat_id": int(picked["flat_id"]),
            "origin": "Comparable sales",
        }
        st.session_state["nb_comp_nonce"] += 1
        st.rerun(scope="fragment")


def render_nearby_stations(connection: Any) -> None:
    if not nearby_function.has_distance_column(connection):
        st.warning(nearby_function.MIGRATION_REQUIRED)
        return
    st.session_state.setdefault("nb_nonce", 0)
    focus = st.session_state.get("nearby_focus")

    title, clear_column = st.columns([3, 1], vertical_alignment="center")
    title.subheader("Nearby MRT / LRT stations")

    if not nearby_function.is_ready(connection):
        with st.spinner("`nearby` is empty, filling it now..."):
            filled = nearby_function.ensure_populated(connection)
        if filled is None:
            st.warning("There are no stations loaded. Run `python -m setup.import_data_script.import` first.")
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
        origin = focus["origin"]
        if origin == "Manage flats":
            origin = "Flat records"
        with st.container(border=True):
            st.markdown(f"**Selected flat** · picked from {origin}")
            st.dataframe(
                selected, width="stretch", hide_index=True, column_config=FLAT_TABLE_COLUMNS
            )
            if not station_ids:
                st.info(
                    "This flat's block has no nearby stations yet. Use **Update addresses** "
                    "on the Address tab."
                )
            if origin == "Flat records" and st.button("← Back to Flat records"):
                st.session_state["pending_tab"] = origin
                st.rerun()

        subview = st.radio(
            "Comparison view",
            SUBVIEWS,
            horizontal=True,
            label_visibility="collapsed",
            key="nb_subview",
        )
        if subview == "Recent comparable sales":
            ref_profile = repository.get_reference_flat_profile(connection, focus["flat_id"]) or selected[0]
            _render_comparable_sales_subview(connection, ref_profile, station_ids, selected[0]["nearest_m"])
            return

        total = repository.count_similar_flats(connection, focus["flat_id"], station_ids)
        st.markdown("**Flats near the same stations** · most shared stations first")

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

    if total == 0:
        st.info("No flats to show.")
        return

    offset = (page - 1) * NEARBY_PAGE_SIZE
    if focus is None:
        rows = repository.search_nearby_flats(
            connection, filters, NEARBY_PAGE_SIZE, offset, matching_flat_count=total,
        )
    else:
        rows = repository.search_similar_flats(
            connection, focus["flat_id"], station_ids, NEARBY_PAGE_SIZE, offset
        )
    if not rows:
        st.info("No flats to show.")
        return

    st.markdown("**Select a row** to see other flats near the same stations.")
    event = st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config=FLAT_TABLE_COLUMNS,
        on_select="rerun",
        selection_mode="single-row",
        key=f'nb_table_{st.session_state["nb_nonce"]}',
    )
    if event.selection.rows:
        picked = rows[event.selection.rows[0]]
        st.session_state["nearby_focus"] = {
            "flat_id": int(picked["flat_id"]),
            "origin": "Nearby stations",
        }
        st.session_state["nb_nonce"] += 1
        st.rerun(scope="fragment")
