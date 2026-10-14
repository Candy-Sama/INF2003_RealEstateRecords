import pandas as pd

print("Loading MRT location data...")
df = pd.read_csv("data/raw/mrt_station_locations.csv")

# 1. Clean column names (strip spaces, uppercase)
df.columns = df.columns.str.strip().str.upper()

# 2. Rename to match our ERD
df = df.rename(columns={
    "STATION_NAME": "station_name",
    "TYPE": "transport_type",
    "LAT": "latitude",
    "LNG": "longitude"
})

# 3. Keep only the columns we need
df = df[["station_name", "transport_type", "latitude", "longitude"]]

# 4. Standardise station names
df["station_name"] = df["station_name"].astype(str).str.strip().str.upper()

# 5. Drop duplicates
df = df.drop_duplicates(subset=["station_name"], keep="first")

# 6. Save cleaned file
df.to_csv("data/cleaned/mrt_stations_cleaned.csv", index=False)
print(f"Success! Cleaned MRT data saved: {df.shape[0]} rows, {df.shape[1]} columns")