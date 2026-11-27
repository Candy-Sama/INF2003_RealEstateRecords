from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2]

print("Loading MRT location data...")
df = pd.read_csv(DATA_DIR / "raw" / "mrt_lrt_full_list.csv")

# 1. Clean column names (strip spaces, uppercase)
df.columns = df.columns.str.strip().str.upper()

# 2. Rename to match our ERD
df = df.rename(columns={
    "STATION_NAME_ENGLISH": "station_name",
    "TRANSPORT_TYPE": "transport_type",
    "LATITUDE": "latitude",
    "LONGITUDE": "longitude"
})

# 3. Keep only the columns we need
df = df[["station_name", "transport_type", "latitude", "longitude"]]

# 4. Standardise station names
df["station_name"] = df["station_name"].astype(str).str.strip().str.upper()

# 5. Drop duplicates
df = df.drop_duplicates(subset=["station_name"], keep="first")

# 6. Save cleaned file
df.to_csv(DATA_DIR / "cleaned" / "mrt_stations_cleaned.csv", index=False)
print(f"Success! Cleaned MRT data saved: {df.shape[0]} rows, {df.shape[1]} columns")
