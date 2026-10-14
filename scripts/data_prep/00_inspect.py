import pandas as pd

files = {
    "HDB RESALE": "data/raw/hdb_resale_transactions.csv",
    "MRT LOCATIONS": "data/raw/mrt_station_locations.csv",
    "MRT FULL LIST": "data/raw/mrt_lrt_full_list.csv",
}

for name, path in files.items():
    print("=" * 60)
    print(f"--- {name} ---")
    try:
        df = pd.read_csv(path)
        print(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
        print("\nColumns:")
        for col in df.columns:
            print(f"  - {col}")
        print("\nFirst 3 rows:")
        print(df.head(3))
        print("\nData Types:")
        print(df.dtypes)
    except FileNotFoundError:
        print(f"Error: Could not find {path}. Did you rename it correctly?")
    print("\n")