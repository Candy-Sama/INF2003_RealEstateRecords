from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import streamlit as st
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from .analytics_store import escape_markdown

AXIS_FORMATS = {"auto": None, "currency": "$,.0f", "integer": ",.0f", "percent": ",.1f"}
CHART_HEIGHT = 320
MAX_KPIS = 4


class CardConfigError(ValueError):
    """The card's column mapping doesn't fit the query result."""


def pretty(column: str) -> str:
    text = str(column).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def format_number(value: Any, number_format: str) -> str:
    """Format one KPI value."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return str(value)
    if number_format == "currency":
        return f"${value:,.0f}"
    if number_format == "integer":
        return f"{value:,.0f}"
    if number_format == "percent":
        return f"{value:,.1f}%"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _require(df: pd.DataFrame, mapping: dict[str, Any], role: str) -> str:
    column = mapping.get(role)
    if not column:
        raise CardConfigError(f"No column is chosen for '{role}'. Edit the card.")
    if column not in df.columns:
        raise CardConfigError(
            f"Column '{column}' is not in the query result. Edit the card."
        )
    return column


def _require_numeric(df: pd.DataFrame, column: str, role: str) -> None:
    if not is_numeric_dtype(df[column]) or is_bool_dtype(df[column]):
        raise CardConfigError(f"'{column}' must be a numeric column to use as '{role}'.")


def _category_type(series: pd.Series) -> str:
    if is_datetime64_any_dtype(series):
        return "temporal"
    if is_numeric_dtype(series) and not is_bool_dtype(series):
        return "ordinal"  # e.g. years
    return "nominal"


def _line_x_type(series: pd.Series) -> str:
    if is_datetime64_any_dtype(series):
        return "temporal"
    if is_numeric_dtype(series) and not is_bool_dtype(series):
        return "quantitative"
    return "ordinal"


def _color_type(series: pd.Series) -> str:
    if is_numeric_dtype(series) and not is_bool_dtype(series) and series.nunique() > 12:
        return "quantitative"
    return "nominal"


def _tooltips(df: pd.DataFrame, safe: dict[str, str]) -> list[alt.Tooltip]:
    tips = []
    for column in df.columns:
        series = df[column]
        if is_datetime64_any_dtype(series):
            tips.append(alt.Tooltip(field=safe[column], type="temporal",
                                    title=pretty(column), format="%Y-%m-%d"))
        elif is_numeric_dtype(series) and not is_bool_dtype(series):
            tips.append(alt.Tooltip(field=safe[column], type="quantitative",
                                    title=pretty(column), format=",.2~f"))
        else:
            tips.append(alt.Tooltip(field=safe[column], type="nominal", title=pretty(column)))
    return tips


def build_chart(df: pd.DataFrame, card: dict[str, Any]) -> alt.Chart:
    """Return an Altair chart for bar / line / area / scatter / heatmap cards."""
    kind = card["display_type"]
    mapping = card.get("mapping") or {}
    axis_format = AXIS_FORMATS.get(card.get("number_format", "auto"))
    value_axis = alt.Axis(format=axis_format) if axis_format else alt.Undefined

    x = _require(df, mapping, "x")
    y = _require(df, mapping, "y")
    safe = {column: f"f{i}" for i, column in enumerate(df.columns)}
    data = df.rename(columns=safe)
    tooltip = _tooltips(df, safe)

    color = None
    color_column = mapping.get("color")
    if kind != "heatmap" and color_column:
        if color_column not in df.columns:
            raise CardConfigError(f"Column '{color_column}' is not in the query result.")
        color = alt.Color(field=safe[color_column], type=_color_type(df[color_column]),
                          title=pretty(color_column))

    if kind == "heatmap":
        value = _require(df, mapping, "value")
        _require_numeric(df, value, "value")
        chart = alt.Chart(data).mark_rect().encode(
            x=alt.X(field=safe[x], type=_category_type(df[x]), title=pretty(x)),
            y=alt.Y(field=safe[y], type=_category_type(df[y]), title=pretty(y)),
            color=alt.Color(field=safe[value], type="quantitative", title=pretty(value),
                            scale=alt.Scale(scheme="greens")),
            tooltip=tooltip,
        )
        return chart.properties(height=CHART_HEIGHT)

    _require_numeric(df, y, "y")

    if kind == "bar":
        if mapping.get("horizontal"):
            chart = alt.Chart(data).mark_bar().encode(
                y=alt.Y(field=safe[x], type=_category_type(df[x]), title=pretty(x), sort="-x"),
                x=alt.X(field=safe[y], type="quantitative", title=pretty(y), axis=value_axis),
                tooltip=tooltip,
            )
        else:
            chart = alt.Chart(data).mark_bar().encode(
                x=alt.X(field=safe[x], type=_category_type(df[x]), title=pretty(x)),
                y=alt.Y(field=safe[y], type="quantitative", title=pretty(y), axis=value_axis),
                tooltip=tooltip,
            )
        if color is not None:
            chart = chart.encode(color=color)
        return chart.properties(height=CHART_HEIGHT)

    x_type = _line_x_type(df[x])
    encoding: dict[str, Any] = {
        "x": alt.X(field=safe[x], type=x_type, title=pretty(x)),
        "y": alt.Y(field=safe[y], type="quantitative", title=pretty(y), axis=value_axis),
        "tooltip": tooltip,
    }
    if color is not None:
        encoding["color"] = color

    if kind == "line":
        mark = alt.Chart(data).mark_line(point=len(df) <= 60)
    elif kind == "area":
        mark = alt.Chart(data).mark_area(opacity=0.6)
    elif kind == "scatter":
        mark = alt.Chart(data).mark_circle(size=70, opacity=0.75)
    else:
        raise CardConfigError(f"'{kind}' is not a chart type.")
    chart = mark.encode(**encoding).properties(height=CHART_HEIGHT)
    if x_type in ("quantitative", "temporal"):
        chart = chart.interactive()  # zoom and pan
    return chart


def render_kpis(df: pd.DataFrame, number_format: str) -> None:
    if df.empty:
        st.info("The query returned no rows.")
        return
    row = df.iloc[0]
    columns = list(df.columns)[:MAX_KPIS]
    for slot, column in zip(st.columns(len(columns)), columns):
        value = row[column]
        text = format_number(value, number_format)
        slot.metric(escape_markdown(pretty(column)), escape_markdown(text))
    if len(df.columns) > MAX_KPIS:
        st.caption(f"Showing the first {MAX_KPIS} columns.")


def render_card_body(df: pd.DataFrame, card: dict[str, Any]) -> None:
    """Draw the result. Raises CardConfigError if the mapping doesn't fit."""
    kind = card["display_type"]
    if df.empty:
        st.info("The query returned no rows.")
        return
    if kind == "table":
        st.dataframe(df, width="stretch", hide_index=True)
    elif kind == "kpi":
        render_kpis(df, card.get("number_format", "auto"))
    else:
        st.altair_chart(build_chart(df, card), width="stretch")
