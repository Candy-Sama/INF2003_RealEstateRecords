from __future__ import annotations

from datetime import date
from typing import Any

BOARD_SIZE = 10
MIN_WINDOW_SALES = 30  # a town needs this many sales in each 12-month window to be ranked


def _f(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _rows(items: list[tuple[str, float, Any]]) -> list[dict[str, Any]]:
    return [
        {"rank": position, "name": name, "value": value, "extra": extra}
        for position, (name, value, extra) in enumerate(items[:BOARD_SIZE], start=1)
    ]


def _board(**fields: Any) -> dict[str, Any]:
    return {"extra_label": "Sales", "extra_format": "int", **fields}


def _month(value: Any) -> str:
    return value.strftime("%b %Y") if isinstance(value, date) else str(value)


def build_boards(
    towns: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    streets: list[dict[str, Any]],
    sales: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_psm = sorted(towns, key=lambda t: _f(t["avg_psm"]), reverse=True)
    by_volume = sorted(towns, key=lambda t: int(t["sales"]), reverse=True)

    rising = []
    for town in towns:
        recent_n, prior_n = int(town["recent_sales"] or 0), int(town["prior_sales"] or 0)
        prior = _f(town["prior_psm"])
        if recent_n >= MIN_WINDOW_SALES and prior_n >= MIN_WINDOW_SALES and prior > 0:
            change = (_f(town["recent_psm"]) / prior - 1) * 100
            rising.append((town["town"], change, _f(town["recent_psm"])))
    rising.sort(key=lambda item: item[1], reverse=True)

    station_rows = [
        (f'{s["station_name"]} ({s["station_code"]})', _f(s["avg_psm"]), int(s["sales"]))
        for s in stations
    ]
    station_volume = sorted(
        ((name, float(extra), extra) for name, _, extra in station_rows),
        key=lambda item: item[1], reverse=True,
    )

    return [
        _board(
            id="towns_priciest", group="Towns", title="Most expensive towns",
            caption="Average resale price per sqm.",
            name_label="Town", value_label="Price per sqm", value_format="$%.0f",
            rows=_rows([(t["town"], _f(t["avg_psm"]), int(t["sales"])) for t in by_psm]),
        ),
        _board(
            id="towns_affordable", group="Towns", title="Most affordable towns",
            caption="Lowest average resale price per sqm.",
            name_label="Town", value_label="Price per sqm", value_format="$%.0f",
            rows=_rows([(t["town"], _f(t["avg_psm"]), int(t["sales"])) for t in reversed(by_psm)]),
        ),
        _board(
            id="towns_busiest", group="Towns", title="Busiest towns",
            caption="Number of resale transactions.",
            name_label="Town", value_label="Transactions", value_format="%d",
            extra_label="Price per sqm", extra_format="psm",
            rows=_rows([(t["town"], float(t["sales"]), _f(t["avg_psm"])) for t in by_volume]),
        ),
        _board(
            id="towns_rising", group="Towns", title="Fastest rising towns",
            caption=(f"Price per sqm over the latest 12 months against the 12 before. "
                     f"Needs {MIN_WINDOW_SALES}+ sales in each."),
            name_label="Town", value_label="Change (%)", value_format="%.1f",
            extra_label="Latest 12 months", extra_format="psm",
            rows=_rows(rising),
        ),
        _board(
            id="stations_priciest", group="Stations", title="Priciest station neighbourhoods",
            caption="Average price per sqm for flats within 500 m. Catchments can overlap.",
            name_label="Station", value_label="Price per sqm", value_format="$%.0f",
            rows=_rows(sorted(station_rows, key=lambda r: r[1], reverse=True)),
        ),
        _board(
            id="stations_busiest", group="Stations", title="Busiest station neighbourhoods",
            caption="Transactions for flats within 500 m of the station.",
            name_label="Station", value_label="Transactions", value_format="%d",
            extra_label="Price per sqm", extra_format="psm",
            rows=_rows([(n, v, _f(next(r[1] for r in station_rows if r[0] == n)))
                        for n, v, _ in station_volume]),
        ),
        _board(
            id="streets_priciest", group="Streets and sales", title="Most expensive streets",
            caption="Average resale price, in thousands. Streets with 30+ sales.",
            name_label="Street", value_label="Average price (k)", value_format="$%.0fk",
            rows=_rows([(f'{s["road_name"]}, {s["town"]}', _f(s["avg_price"]) / 1000, int(s["sales"]))
                        for s in streets]),
        ),
        _board(
            id="sales_highest", group="Streets and sales", title="Highest recorded sales",
            caption="The most expensive single transactions.",
            name_label="Flat", value_label="Price (k)", value_format="$%.0fk",
            extra_label="Type and month", extra_format="text",
            rows=_rows([
                (f'Blk {s["block_number"]} {s["road_name"]}, {s["town"]}',
                 _f(s["resale_price"]) / 1000,
                 f'{s["flat_type"].title()}, {_month(s["transaction_date"])}')
                for s in sales
            ]),
        ),
    ]


def leaders(boards: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The #1 entry of four boards, for the summary strip."""
    wanted = (
        ("towns_priciest", "Most expensive town", "${value:,.0f} per sqm"),
        ("towns_busiest", "Busiest town", "{value:,.0f} transactions"),
        ("towns_rising", "Fastest rising town", "{value:+.1f}% over 12 months"),
        ("stations_priciest", "Priciest station area", "${value:,.0f} per sqm"),
    )
    by_id = {b["id"]: b for b in boards}
    found = []
    for board_id, label, template in wanted:
        rows = by_id[board_id]["rows"]
        if rows:
            found.append({"label": label, "name": rows[0]["name"],
                          "detail": template.format(value=rows[0]["value"])})
    return found
