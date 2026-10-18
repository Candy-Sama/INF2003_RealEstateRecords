import pandas as pd
import numpy as np

print("Loading HDB data...")
df = pd.read_csv("data/raw/hdb_resale_transactions.csv")

# 1. Rename columns to match our ERD
df = df.rename(columns={
    "month": "transaction_date",
    "block": "block_number",
    "street_name": "street_name",
    "flat_type": "flat_type",
    "storey_range": "storey_range",
    "floor_area_sqm": "floor_area_sqm",
    "flat_model": "flat_model",
    "lease_commence_date": "lease_commence_date",
    "remaining_lease": "remaining_lease_raw",
    "resale_price": "resale_price",
    "town": "town"
})

# 2. Convert month (YYYY-MM) to a proper date
#df["transaction_date"] = pd.to_datetime(df["transaction_date"], format="%Y-%m") OLD_Unused
df["transaction_date"] = pd.to_datetime(df["transaction_date"], format="%Y-%m").dt.to_period("M")

# 3. Create a full address column for geocoding later
df["full_address"] = df["block_number"].astype(str) + " " + df["street_name"]

# 4. Convert remaining lease (e.g. "61 years 04 months") to numeric months
def lease_to_months(x):
    if pd.isna(x):
        return np.nan
    x = str(x).strip()
    years = 0
    months = 0
    if "year" in x:
        years = int(x.split("year")[0].strip())
    if "month" in x:
        part = x.split("month")[0].strip()
        if "year" in x:
            months = int(part.split()[-1])
        else:
            months = int(part)
    return years * 12 + months

df["remaining_lease_months"] = df["remaining_lease_raw"].apply(lease_to_months)

# 5. Drop rows with missing critical data
df = df.dropna(subset=["resale_price", "block_number", "street_name", "town"])

# 6. Standardise text to uppercase and strip whitespace
for col in ["town", "flat_type", "flat_model", "street_name"]:
    df[col] = df[col].astype(str).str.strip().str.upper()

# 7. Save cleaned file
df.to_csv("data/cleaned/hdb_resale_cleaned.csv", index=False)
print(f"Success! Cleaned HDB data saved: {df.shape[0]} rows, {df.shape[1]} columns")