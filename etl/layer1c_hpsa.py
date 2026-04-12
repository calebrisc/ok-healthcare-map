"""
Layer 1C: HPSA Boundaries (Health Professional Shortage Areas)
Source: HRSA bulk data download
Downloads HPSA CSV, joins to county/tract geometries,
dissolves into HPSA boundary polygons with scores and metadata.
"""

import os
import requests
import pandas as pd
import geopandas as gpd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
TRACT_PATH = os.path.join(OUT_DIR, "ok_tracts.geojson")

HPSA_URL = "https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv"
HPSA_DENTAL_URL = "https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_DH.csv"
HPSA_MH_URL = "https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_MH.csv"

OUT_PATH = os.path.join(OUT_DIR, "ok_hpsa.geojson")


def download_file(url, filename):
    path = os.path.join(RAW_DIR, filename)
    if os.path.exists(path):
        print(f"Already downloaded: {path}")
        return path
    print(f"Downloading {filename}...")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved to {path}")
    return path


def load_hpsa_data():
    """Download and combine all three HPSA discipline files, filtered to Oklahoma."""
    files = [
        (HPSA_URL, "hpsa_primary_care.csv", "Primary Care"),
        (HPSA_DENTAL_URL, "hpsa_dental.csv", "Dental Health"),
        (HPSA_MH_URL, "hpsa_mental_health.csv", "Mental Health"),
    ]

    all_dfs = []
    for url, filename, discipline in files:
        path = download_file(url, filename)
        print(f"Reading {filename}...")
        df = pd.read_csv(path, dtype=str, low_memory=False)

        # Filter to Oklahoma
        ok_df = df[df["Primary State Abbreviation"].str.strip().str.upper() == "OK"].copy()
        print(f"  Oklahoma rows: {len(ok_df)}")

        # Filter out withdrawn designations
        ok_df = ok_df[ok_df["HPSA Status"].str.strip() != "Withdrawn"].copy()
        print(f"  After removing withdrawn: {len(ok_df)}")

        ok_df["discipline"] = discipline
        all_dfs.append(ok_df)

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal active Oklahoma HPSA records: {len(combined)}")
    return combined


def build_boundaries(hpsa_df):
    """Join HPSA records to census tract geometries and dissolve into HPSA polygons."""
    print("\nLoading census tracts...")
    tracts = gpd.read_file(TRACT_PATH)
    tracts["county_fips"] = tracts["GEOID"].str[:5]
    print(f"  Tracts loaded: {len(tracts)}")

    # Deduplicate: one row per HPSA ID + discipline + county
    # Each HPSA can span multiple component rows but we join by county FIPS
    hpsa_df["county_fips"] = hpsa_df["Common State County FIPS Code"].str.strip().str.zfill(5)

    # Keep the fields we care about, deduplicate per HPSA+county
    keep_fields = {
        "HPSA ID": "hpsa_id",
        "HPSA Name": "name",
        "HPSA Score": "score",
        "Designation Type": "type",
        "HPSA Status": "status",
        "Rural Status": "rural",
        "HPSA Provider Ratio Goal": "provider_ratio",
        "HPSA Designation Population": "designation_pop",
        "HPSA Estimated Underserved Population": "underserved_pop",
        "% of Population Below 100% Poverty": "pct_poverty",
        "discipline": "discipline",
        "county_fips": "county_fips",
    }

    slim = hpsa_df[[c for c in keep_fields.keys() if c in hpsa_df.columns]].copy()
    slim = slim.rename(columns=keep_fields)
    slim["score"] = pd.to_numeric(slim["score"], errors="coerce")

    # Deduplicate: keep one row per HPSA + county (an HPSA can cover multiple counties)
    slim = slim.drop_duplicates(subset=["hpsa_id", "discipline", "county_fips"])
    print(f"  Unique HPSA-county combinations: {len(slim)}")

    # Join tracts to HPSAs by county FIPS
    merged = tracts.merge(slim, on="county_fips", how="inner")
    print(f"  Matched tracts: {len(merged)}")

    # Dissolve tracts into HPSA polygons
    print("Dissolving into HPSA polygons...")
    dissolved = merged.dissolve(
        by=["hpsa_id", "discipline"],
        aggfunc={
            "name": "first",
            "score": "first",
            "type": "first",
            "status": "first",
            "rural": "first",
            "provider_ratio": "first",
            "designation_pop": "first",
            "underserved_pop": "first",
            "pct_poverty": "first",
        },
    ).reset_index()

    print(f"  HPSA polygons: {len(dissolved)}")

    # Keep only useful columns
    out_cols = ["hpsa_id", "name", "score", "discipline", "type", "status",
                "rural", "provider_ratio", "designation_pop", "underserved_pop",
                "pct_poverty", "geometry"]
    dissolved = dissolved[[c for c in out_cols if c in dissolved.columns]]

    return dissolved


def run():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    hpsa_df = load_hpsa_data()
    result = build_boundaries(hpsa_df)

    if result is not None and len(result) > 0:
        result.to_file(OUT_PATH, driver="GeoJSON")
        size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
        print(f"\nSaved: {OUT_PATH} ({size_mb:.1f} MB)")
        print(f"Total HPSA areas: {len(result)}")
        print(f"\nBy discipline:\n{result['discipline'].value_counts().to_string()}")
        print(f"\nScore range: {result['score'].min()} - {result['score'].max()}")
        print(f"Score mean: {result['score'].mean():.1f}")
    else:
        print("\nERROR: No HPSA boundaries generated")


if __name__ == "__main__":
    run()
