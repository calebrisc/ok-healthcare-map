"""
Layer 1F: Rural-Urban Continuum Codes (RUCC)
Source: USDA Economic Research Service
Downloads RUCC CSV, joins to county boundaries, outputs GeoJSON.
"""

import os
import requests
import pandas as pd
import geopandas as gpd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
COUNTY_PATH = os.path.join(OUT_DIR, "ok_counties.geojson")

RUCC_URL = "https://www.ers.usda.gov/media/5768/2023-rural-urban-continuum-codes.csv?v=97862"
RUCC_CSV = os.path.join(RAW_DIR, "rucc2023.csv")
OUT_PATH = os.path.join(OUT_DIR, "ok_rucc.geojson")


def download():
    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(RUCC_CSV):
        print(f"Already downloaded: {RUCC_CSV}")
        return
    print("Downloading RUCC data...")
    r = requests.get(RUCC_URL)
    r.raise_for_status()
    with open(RUCC_CSV, "wb") as f:
        f.write(r.content)
    print(f"Saved to {RUCC_CSV}")


def process():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Reading RUCC CSV...")
    df = pd.read_csv(RUCC_CSV, dtype=str, encoding="latin-1")

    # Filter to Oklahoma
    df["FIPS"] = df["FIPS"].str.strip().str.zfill(5)
    ok = df[df["FIPS"].str.startswith("40")].copy()
    print(f"  Oklahoma rows: {len(ok)}")

    # Pivot from long format (Attribute/Value) to wide
    pivoted = ok.pivot(index="FIPS", columns="Attribute", values="Value").reset_index()
    pivoted = pivoted.rename(columns={
        "FIPS": "GEOID",
        "RUCC_2023": "rucc_code",
        "Description": "rucc_desc",
        "Population_2020": "pop_2020",
    })
    pivoted["rucc_code"] = pd.to_numeric(pivoted["rucc_code"], errors="coerce")
    pivoted["pop_2020"] = pd.to_numeric(pivoted["pop_2020"], errors="coerce")
    print(f"  Counties: {len(pivoted)}")
    print(f"  RUCC distribution:\n{pivoted['rucc_code'].value_counts().sort_index().to_string()}")

    # Load county boundaries and join
    print("\nLoading county boundaries...")
    counties = gpd.read_file(COUNTY_PATH)
    merged = counties.merge(pivoted[["GEOID", "rucc_code", "rucc_desc", "pop_2020"]], on="GEOID", how="left")
    print(f"  Matched: {merged['rucc_code'].notna().sum()} / {len(merged)}")

    merged.to_file(OUT_PATH, driver="GeoJSON")
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\nSaved: {OUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    download()
    process()
