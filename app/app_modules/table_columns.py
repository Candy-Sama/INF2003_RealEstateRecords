"""Display labels and units for shared record tables."""

import streamlit as st


FLAT_RECORD_COLUMNS = {
    "flat_id": st.column_config.NumberColumn("Flat ID", format="%d"),
    "flat_type": "Flat type",
    "flat_model": "Flat model",
    "storey_range": "Storeys",
    "floor_area_sqm": st.column_config.NumberColumn("Floor area (m²)", format="%.2f"),
    "block_id": st.column_config.NumberColumn("Block ID", format="%d"),
    "lease_commence_date": st.column_config.NumberColumn("Lease start year", format="%d"),
    "remaining_lease_months": st.column_config.NumberColumn("Lease left (months)", format="%d"),
    "block_number": "Block",
    "road_name": "Road",
    "town": "Town",
    "postal": "Postal code",
}

RESALE_COLUMNS = {
    **FLAT_RECORD_COLUMNS,
    "transaction_date": st.column_config.DateColumn("Sale date", format="DD MMM YYYY"),
    "resale_price": st.column_config.NumberColumn("Resale price (S$)", format="localized"),
}
