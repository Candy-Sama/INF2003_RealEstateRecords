import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

DATA_DIR = Path(__file__).resolve().parents[2]
INPUT = DATA_DIR / "cleaned" / "hdb_resale_cleaned.csv"
OUTPUT = DATA_DIR / "geo" / "hdb_block_coordinates.csv"

load_dotenv(DATA_DIR.parent / ".env", override=False)
API_TOKEN = os.getenv("ONEMAP_API_TOKEN", "").strip()
if not API_TOKEN:
    raise SystemExit("Set ONEMAP_API_TOKEN before running HDB geocoding.")

OUTPUT.parent.mkdir(exist_ok=True)

print("Loading cleaned HDB data...")
df = pd.read_csv(INPUT)
addresses = df["full_address"].dropna().unique()
print(f"Found {len(addresses)} unique addresses to geocode.")

if OUTPUT.exists():
    done = pd.read_csv(OUTPUT)
    done_set = set(done["full_address"])
    print(f"Resuming from {len(done_set)} already geocoded addresses.")
else:
    done = pd.DataFrame(columns=["full_address", "latitude", "longitude"])
    done_set = set()

session = requests.Session()
# Add the Authorization header with your token
session.headers.update({
    "Authorization": API_TOKEN,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})

def geocode(addr, retries=3):
    url = "https://www.onemap.gov.sg/api/common/elastic/search"
    params = {"searchVal": addr, "returnGeom": "Y", "getAddrDetails": "Y"}
    
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("found", 0) > 0:
                    res = data["results"][0]
                    return float(res["LATITUDE"]), float(res["LONGITUDE"])
                return None, None  # No result found, but no error
            elif r.status_code in (401, 403):
                raise SystemExit("OneMap rejected ONEMAP_API_TOKEN. Supply a valid token.")
            elif r.status_code == 429:
                wait = 5 * (attempt + 1)  # Exponential backoff: 5s, 10s, 15s
                print(f"Rate limited. Waiting {wait}s before retrying {addr}")
                time.sleep(wait)
            else:
                print(f"HTTP {r.status_code} for {addr}: {r.text[:100]}")
                return None, None
        except Exception as e:
            print(f"Error for {addr} (attempt {attempt+1}): {e}")
            time.sleep(2)
    
    return None, None  # All retries failed

results = []
for i, addr in enumerate(addresses):
    if addr in done_set:
        continue
    
    lat, lon = geocode(addr)
    results.append({"full_address": addr, "latitude": lat, "longitude": lon})
    
    if (i + 1) % 100 == 0:
        print(f"Progress: {i+1}/{len(addresses)}")
        pd.concat([done, pd.DataFrame(results)]).to_csv(OUTPUT, index=False)
    
    time.sleep(0.5)  # ~2 requests per second, safely under the 250/min limit

final = pd.concat([done, pd.DataFrame(results)])
final.to_csv(OUTPUT, index=False)
print(f"Success! Geocoded {len(final)} addresses.")