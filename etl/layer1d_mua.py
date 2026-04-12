"""
Layer 1D: MUA/MUP Boundaries (Medically Underserved Areas/Populations)
Source: HRSA bulk data download
Downloads MUA CSV, joins to county/tract geometries, outputs GeoJSON.
"""

import os
import requests
import pandas as pd
import geopandas as gpd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
TRACT_PATH = os.path.join(OUT_DIR, "ok_tracts.geojson")

MUA_URL = "https://data.hrsa.gov/DataDownload/DD_Files/MUA_DET.csv"
MUA_CSV = os.path.join(RAW_DIR, "mua_det.csv")
OUT_PATH = os.path.join(OUT_DIR, "ok_mua.geojson")


def download():
    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(MUA_CSV):
        print(f"Already downloaded: {MUA_CSV}")
        return
    print("Downloading MUA data...")
    r = requests.get(MUA_URL, stream=True)
    r.raise_for_status()
    with open(MUA_CSV, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved to {MUA_CSV}")


def process():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Reading MUA CSV...")
    df = pd.read_csv(MUA_CSV, dtype=str, low_memory=False)
    print(f"  Total rows: {len(df)}")
    print(f"  Columns: {list(df.columns)}")

    # Find state column
    state_col = None
    for col in df.columns:
        if "state" in col.lower() and "abbrev" in col.lower():
            state_col = col
            break
    if not state_col:
        for col in df.columns:
            if "common_state" in col.lower():
                state_col = col
                break
    if not state_col:
        # Try all columns for OK values
        for col in df.columns:
            if "state" in col.lower():
                vals = df[col].dropna().str.strip().str.upper().unique()
                if "OK" in vals or "OKLAHOMA" in vals:
                    state_col = col
                    break

    print(f"  State column: {state_col}")
    ok = df[df[state_col].str.strip().str.upper().isin(["OK", "OKLAHOMA"])].copy()
    print(f"  Oklahoma rows: {len(ok)}")

    # Filter to active designations
    status_col = None
    for col in ok.columns:
        if "status" in col.lower() and "design" in col.lower():
            status_col = col
            break
    if not status_col:
        for col in ok.columns:
            if "status" in col.lower():
                status_col = col
                break

    if status_col:
        print(f"  Status column: {status_col}")
        print(f"  Statuses: {ok[status_col].value_counts().to_dict()}")
        ok = ok[~ok[status_col].str.strip().str.upper().isin(["W", "WITHDRAWN"])].copy()
        print(f"  After removing withdrawn: {len(ok)}")

    # Print sample to understand structure
    print(f"\n  Sample row:\n{ok.iloc[0].to_dict()}")

    # Find key columns
    mua_id_col = None
    for col in ok.columns:
        col_l = col.lower()
        if "mua" in col_l and ("id" in col_l or "source" in col_l) and "service" not in col_l:
            mua_id_col = col
            break

    score_col = None
    for col in ok.columns:
        if col.strip() == "IMU Score":
            score_col = col
            break
    if not score_col:
        for col in ok.columns:
            if "imu" in col.lower() and "score" in col.lower():
                score_col = col
                break

    name_col = None
    for col in ok.columns:
        col_l = col.lower()
        if ("mua" in col_l or "area" in col_l) and "name" in col_l:
            name_col = col
            break

    county_fips_col = None
    for col in ok.columns:
        col_l = col.lower()
        if "county" in col_l and "fips" in col_l and "state" in col_l:
            county_fips_col = col
            break
    if not county_fips_col:
        for col in ok.columns:
            if "county" in col.lower() and "fips" in col.lower():
                county_fips_col = col
                break

    desig_type_col = None
    for col in ok.columns:
        if "designation" in col.lower() and "type" in col.lower():
            desig_type_col = col
            break

    print(f"\n  Detected: id={mua_id_col}, score={score_col}, name={name_col}, county={county_fips_col}, type={desig_type_col}")

    # Load tracts
    print("\nLoading census tracts...")
    tracts = gpd.read_file(TRACT_PATH)
    tracts["county_fips"] = tracts["GEOID"].str[:5]

    # Build slim dataframe
    cols_map = {}
    if mua_id_col: cols_map[mua_id_col] = "mua_id"
    if name_col: cols_map[name_col] = "name"
    if score_col: cols_map[score_col] = "score"
    if desig_type_col: cols_map[desig_type_col] = "type"
    if status_col: cols_map[status_col] = "status"
    if county_fips_col: cols_map[county_fips_col] = "county_fips_raw"

    slim = ok[[c for c in cols_map.keys()]].copy()
    slim = slim.rename(columns=cols_map)

    if "score" in slim.columns:
        slim["score"] = pd.to_numeric(slim["score"], errors="coerce")

    slim["county_fips"] = slim["county_fips_raw"].str.strip().str.zfill(5)
    slim = slim.drop(columns=["county_fips_raw"])
    slim = slim.drop_duplicates(subset=["mua_id", "county_fips"])
    print(f"  Unique MUA-county combos: {len(slim)}")

    # Join
    merged = tracts.merge(slim, on="county_fips", how="inner")
    print(f"  Matched tracts: {len(merged)}")

    # Dissolve
    print("Dissolving into MUA polygons...")
    agg = {}
    if "name" in merged.columns: agg["name"] = "first"
    if "score" in merged.columns: agg["score"] = "first"
    if "type" in merged.columns: agg["type"] = "first"
    if "status" in merged.columns: agg["status"] = "first"

    dissolved = merged.dissolve(by="mua_id", aggfunc=agg).reset_index()
    print(f"  MUA polygons: {len(dissolved)}")

    out_cols = ["mua_id", "name", "score", "type", "status", "geometry"]
    dissolved = dissolved[[c for c in out_cols if c in dissolved.columns]]

    dissolved.to_file(OUT_PATH, driver="GeoJSON")
    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"\nSaved: {OUT_PATH} ({size_mb:.1f} MB)")
    print(f"Total MUA/MUP areas: {len(dissolved)}")
    if "score" in dissolved.columns:
        print(f"IMU Score range: {dissolved['score'].min()} - {dissolved['score'].max()}")
    if "type" in dissolved.columns:
        print(f"By type:\n{dissolved['type'].value_counts().to_string()}")


if __name__ == "__main__":
    download()
    process()
