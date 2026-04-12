"""
Layer 5: Disease Burden from CDC PLACES (wide format, tract level)
Source: data.cdc.gov resource yjkw-uj5s
Already pivoted — one row per tract with _crudeprev columns.
"""

import os
import requests
import geopandas as gpd
import pandas as pd

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
TRACT_PATH = os.path.join(OUT_DIR, "ok_tracts.geojson")
OUT_PATH = os.path.join(OUT_DIR, "ok_disease.geojson")

PLACES_URL = "https://data.cdc.gov/resource/yjkw-uj5s.json"

# Measures we want (key = column prefix, value = display label)
MEASURES = {
    "diabetes": "Diabetes",
    "obesity": "Obesity",
    "bphigh": "High Blood Pressure",
    "highchol": "High Cholesterol",
    "copd": "COPD",
    "casthma": "Asthma",
    "chd": "Heart Disease",
    "stroke": "Stroke",
    "cancer": "Cancer",
    "depression": "Depression",
    "mhlth": "Poor Mental Health (14+ days)",
    "phlth": "Poor Physical Health (14+ days)",
    "csmoking": "Smoking",
    "binge": "Binge Drinking",
    "lpa": "Physical Inactivity",
    "access2": "Lack of Insurance",
    "checkup": "No Routine Checkup",
    "teethlost": "All Teeth Lost (65+)",
    "sleep": "Sleep < 7 Hours",
    "disability": "Disability",
    "cognition": "Cognitive Difficulty",
}


def fetch():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Fetching CDC PLACES tract data for Oklahoma...")

    all_data = []
    offset = 0
    limit = 5000

    while True:
        params = {
            "$where": "stateabbr='OK'",
            "$limit": limit,
            "$offset": offset,
        }
        print(f"  Offset {offset}...", end="", flush=True)
        r = requests.get(PLACES_URL, params=params, timeout=60)
        r.raise_for_status()
        batch = r.json()
        print(f" {len(batch)} rows")

        if not batch:
            break
        all_data.extend(batch)
        offset += limit
        if len(batch) < limit:
            break

    print(f"  Total rows: {len(all_data):,}")
    return pd.DataFrame(all_data)


def process(df):
    print(f"\nProcessing...")

    # Build GEOID from tractfips
    df["GEOID"] = df["tractfips"].astype(str).str.zfill(11)
    print(f"  Tracts: {df['GEOID'].nunique()}")

    # Extract crude prevalence columns
    prev_cols = [f"{m}_crudeprev" for m in MEASURES.keys()]
    keep_cols = ["GEOID"] + [c for c in prev_cols if c in df.columns]

    slim = df[keep_cols].copy()
    # Convert to numeric
    for col in keep_cols[1:]:
        slim[col] = pd.to_numeric(slim[col], errors="coerce")

    # Rename to clean names (drop _crudeprev suffix)
    rename = {f"{m}_crudeprev": m for m in MEASURES.keys() if f"{m}_crudeprev" in slim.columns}
    slim = slim.rename(columns=rename)

    return slim


def run():
    df = fetch()
    slim = process(df)

    print("\nLoading tract boundaries...")
    tracts = gpd.read_file(TRACT_PATH)

    merged = tracts.merge(slim, on="GEOID", how="left")
    print(f"  Merged: {len(merged)}")
    print(f"  With disease data: {merged['diabetes'].notna().sum()}")

    merged.to_file(OUT_PATH, driver="GeoJSON")
    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"\nSaved: {OUT_PATH} ({size_mb:.1f} MB)")

    print(f"\nOklahoma Disease Prevalence (crude %, avg across tracts):")
    for key, label in MEASURES.items():
        if key in merged.columns:
            val = merged[key].mean()
            if pd.notna(val):
                print(f"  {label}: {val:.1f}%")


if __name__ == "__main__":
    run()
