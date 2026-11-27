from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2]
SAMPLES_DIR = DATA_DIR / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)

print("Loading cleaned data...")
hdb = pd.read_csv(DATA_DIR / "cleaned" / "hdb_resale_cleaned.csv")
mrt = pd.read_csv(DATA_DIR / "cleaned" / "mrt_stations_cleaned.csv")

# Save first 1000 rows of HDB, and all 172 MRT rows
hdb.head(1000).to_csv(SAMPLES_DIR / "hdb_resale_sample.csv", index=False)
mrt.to_csv(SAMPLES_DIR / "mrt_stations_sample.csv", index=False)

print("Success! Sample files saved to data/samples/")
