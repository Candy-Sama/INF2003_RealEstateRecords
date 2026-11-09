import pandas as pd
import os

# Ensure the samples directory exists
os.makedirs("data/samples", exist_ok=True)

print("Loading cleaned data...")
hdb = pd.read_csv("data/cleaned/hdb_resale_cleaned.csv")
mrt = pd.read_csv("data/cleaned/mrt_stations_cleaned.csv")

# Save first 1000 rows of HDB, and all 172 MRT rows
hdb.head(1000).to_csv("data/samples/hdb_resale_sample.csv", index=False)
mrt.to_csv("data/samples/mrt_stations_sample.csv", index=False)

print("Success! Sample files saved to data/samples/")