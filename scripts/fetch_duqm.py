"""Fetch Duqm AIS data from Datalastic API."""
import json, csv, time, sys, os
from urllib.request import urlopen, Request
from datetime import datetime, timedelta

API_KEY = "b51bab23-b9e6-4da4-9d29-9de3ca5bddb1"
BASE = "https://api.datalastic.com/api/v0"
DUQM_LAT, DUQM_LON, RADIUS = 19.67459, 57.70646, 50
OUT_DIR = "/home/abdullah/projects/cue2case/data"

def api_get(endpoint, params):
    params["api-key"] = API_KEY
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{endpoint}?{qs}"
    with urlopen(url, timeout=30) as r:
        return json.loads(r.read())

# Step 1: Get all vessels currently near Duqm
print("Fetching live vessels near Duqm...")
live = api_get("vessel_inradius", {"lat": DUQM_LAT, "lon": DUQM_LON, "radius": RADIUS})
vessels = live["data"]["vessels"]
print(f"  Found {len(vessels)} vessels")

# Step 2: Get historical positions for each vessel (last 7 days)
date_to = datetime.utcnow().strftime("%Y-%m-%d")
date_from = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
print(f"Fetching histories {date_from} to {date_to}...")

all_positions = []
credits_used = 0
for i, v in enumerate(vessels):
    mmsi = v.get("mmsi")
    if not mmsi:
        continue
    name = v.get("name", "UNKNOWN")
    vtype = v.get("type_specific", v.get("type", ""))
    
    try:
        hist = api_get("vessel_history", {
            "mmsi": mmsi,
            "date_from": date_from,
            "date_to": date_to
        })
        positions = hist.get("data", {}).get("positions", [])
        for p in positions:
            all_positions.append({
                "MMSI": mmsi,
                "BaseDateTime": p.get("last_position_UTC", ""),
                "LAT": p.get("lat", ""),
                "LON": p.get("lon", ""),
                "SOG": p.get("speed", ""),
                "COG": p.get("course", ""),
                "Heading": p.get("heading", 511) or 511,
                "VesselName": name,
                "VesselType": vtype,
                "Status": p.get("navigational_status", ""),
                "Destination": p.get("destination", ""),
            })
        credits_used += 1  # approximate
        print(f"  [{i+1}/{len(vessels)}] {name} (MMSI:{mmsi}): {len(positions)} positions")
    except Exception as e:
        print(f"  [{i+1}/{len(vessels)}] {name} FAILED: {e}")
    
    time.sleep(0.3)  # rate limit courtesy

# Step 3: Write CSV in NOAA-compatible format
os.makedirs(OUT_DIR, exist_ok=True)
outpath = f"{OUT_DIR}/duqm_ais_{date_from}_to_{date_to}.csv"
fields = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "VesselType", "Status", "Destination"]
with open(outpath, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(all_positions)

print(f"\nDone! {len(all_positions)} positions from {len(vessels)} vessels")
print(f"Saved to: {outpath}")
print(f"API calls: ~{credits_used + 1}")
