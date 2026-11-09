import pandas as pd
import requests
import time
import os

INPUT = "data/cleaned/hdb_resale_cleaned.csv"
OUTPUT = "data/geo/hdb_block_coordinates.csv"

# --- PASTE YOUR TOKEN HERE ---
API_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoyNjk5NywiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc5MTk2ODYwOCwibmJmIjoxNzkxOTY4NjA4LCJleHAiOjE3OTIyMjc4MDgsImp0aSI6ImFmZTYzZDU5LTQ2NTYtNDk0NC04NWJlLWRiZWE3OTZkYTE2ZCJ9.gMJTDlIh1uRLAs3SsnhTzjS3v3aSxB4Ig1Q56PMqFle9f2egZH_zCsoIvmysjyZ4vWiXqCxXMReDvQ1gMw2YrEI_Qi2Ap-kTmv7T-edPHgzRF6aFLCBxC0jTQXoUL7ni3muHiPwI2C7BJXUHWd0xNsEsPH4dHsmtaQxcXm_CG9ztFSACayDYhUA1Md17QHg7TsqiZf9b_wcM3ddS-7N7B1mV4gD6WYGKTd3psUZxjJ-zmHZw6qHs6BqPkBI0ir3sWXSo_8b5yHys26oOqMtu2FkoIQv9miRKJLxqIeskRUna9Y5JVrTNd6NOX6ZRLYRWjCvSW4pV6xz6acNjlBlnFg" 
# -----------------------------

os.makedirs("data/geo", exist_ok=True)

print("Loading cleaned HDB data...")
df = pd.read_csv(INPUT)
addresses = df["full_address"].dropna().unique()
print(f"Found {len(addresses)} unique addresses to geocode.")

if os.path.exists(OUTPUT):
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