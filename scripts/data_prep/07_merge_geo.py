import pandas as pd

print("Merging coordinates into HDB data...")
hdb = pd.read_csv("data/cleaned/hdb_resale_cleaned.csv")
geo = pd.read_csv("data/geo/hdb_block_coordinates.csv")

# Merge on the full_address column
merged = hdb.merge(geo, on="full_address", how="left")

# Save the final enriched dataset
merged.to_csv("data/cleaned/hdb_resale_enriched.csv", index=False)

match_rate = merged["latitude"].notna().mean()
print(f"Success! Merged data saved. Match rate: {match_rate:.1%}")