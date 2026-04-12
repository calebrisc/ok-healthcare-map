"""
Layer 6: Market Intelligence
6A - Drive time proxy (provider density per tract, computed from existing data)
6B - Medicare reimbursement rates (GPCI)
6C - Broadband access (FCC)
6D - Employer data (County Business Patterns)
"""

import os
import json
import requests
import geopandas as gpd
import pandas as pd

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
COUNTY_PATH = os.path.join(OUT_DIR, "ok_counties.geojson")
OUT_PATH = os.path.join(OUT_DIR, "ok_market.geojson")

STATE_FIPS = "40"


def fetch_cbp():
    """6D: County Business Patterns — employer size distribution."""
    print("--- County Business Patterns ---")
    url = "https://api.census.gov/data/2022/cbp"
    params = {
        "get": "ESTAB,EMP,PAYANN",
        "for": "county:*",
        "in": "state:40",
        "NAICS2017": "62",  # Healthcare and Social Assistance
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df["GEOID"] = df["state"] + df["county"]

        for col in ["ESTAB", "EMP", "PAYANN"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.rename(columns={
            "ESTAB": "healthcare_establishments",
            "EMP": "healthcare_employees",
            "PAYANN": "healthcare_payroll_1000",
        })
        print(f"  Counties: {len(df)}")
        print(f"  Total healthcare establishments: {df['healthcare_establishments'].sum():,.0f}")
        print(f"  Total healthcare employees: {df['healthcare_employees'].sum():,.0f}")
        return df[["GEOID", "healthcare_establishments", "healthcare_employees", "healthcare_payroll_1000"]]
    except Exception as e:
        print(f"  CBP fetch failed: {e}")
        return None


def fetch_cbp_all_industries():
    """Total businesses by county for context."""
    print("\n--- All Industries CBP ---")
    url = f"https://api.census.gov/data/2022/cbp?get=ESTAB,EMP&for=county:*&in=state:{STATE_FIPS}"

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df["GEOID"] = df["state"] + df["county"]

        for col in ["ESTAB", "EMP"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.rename(columns={
            "ESTAB": "total_establishments",
            "EMP": "total_employees",
        })
        print(f"  Counties: {len(df)}")
        print(f"  Total establishments: {df['total_establishments'].sum():,.0f}")
        return df[["GEOID", "total_establishments", "total_employees"]]
    except Exception as e:
        print(f"  All-industry CBP failed: {e}")
        return None


def fetch_small_biz():
    """Small employers (< 50 employees) — indicator of low ESI rates."""
    print("\n--- Small Business Data ---")
    url = "https://api.census.gov/data/2022/cbp"
    params = {
        "get": "ESTAB",
        "for": "county:*",
        "in": "state:40",
        "NAICS2017": "00",
        "EMPSZES": "212",  # 1-49 employees
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df["GEOID"] = df["state"] + df["county"]
        df["small_biz_count"] = pd.to_numeric(df["ESTAB"], errors="coerce")
        return df[["GEOID", "small_biz_count"]]
    except Exception as e:
        print(f"  Small biz fetch failed: {e}")
        return None


def compute_provider_density():
    """6A proxy: Count providers per county from NPI data."""
    print("\n--- Provider Density ---")
    import glob

    provider_files = glob.glob(os.path.join(OUT_DIR, "ok_providers_*.geojson"))
    county_counts = {}

    for filepath in provider_files:
        with open(filepath) as f:
            data = json.load(f)
        for feat in data["features"]:
            if feat["geometry"]:
                # Use zip code prefix to approximate county
                zip_code = feat["properties"].get("zip", "")
                city = feat["properties"].get("city", "")
                key = city.upper()
                county_counts[key] = county_counts.get(key, 0) + 1

    print(f"  Cities with providers: {len(county_counts)}")
    print(f"  Total provider locations: {sum(county_counts.values()):,}")
    return county_counts


def fetch_broadband():
    """6C: FCC broadband data — check for county-level availability."""
    print("\n--- Broadband Access ---")
    # FCC Broadband Map API is complex. Use the FCC Form 477 summary data instead.
    # Try the FCC fixed broadband deployment data
    url = "https://broadbandmap.fcc.gov/api/public/map"

    # The FCC API is hard to use in bulk. Let's use a simpler approach:
    # USDA has broadband data by county
    print("  FCC API requires complex queries. Using ACS internet access data instead...")

    acs_url = f"https://api.census.gov/data/2023/acs/acs5?get=B28002_001E,B28002_002E,B28002_004E,B28002_013E&for=county:*&in=state:{STATE_FIPS}"
    try:
        r = requests.get(acs_url, timeout=30)
        r.raise_for_status()
        data = r.json()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df["GEOID"] = df["state"] + df["county"]

        for col in ["B28002_001E", "B28002_002E", "B28002_004E", "B28002_013E"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["pct_internet"] = (df["B28002_002E"] / df["B28002_001E"] * 100).round(1)
        df["pct_broadband"] = (df["B28002_004E"] / df["B28002_001E"] * 100).round(1)
        df["pct_no_internet"] = (df["B28002_013E"] / df["B28002_001E"] * 100).round(1)

        df.loc[df["pct_internet"] < 0, "pct_internet"] = None
        df.loc[df["pct_broadband"] < 0, "pct_broadband"] = None
        df.loc[df["pct_no_internet"] < 0, "pct_no_internet"] = None

        print(f"  Counties: {len(df)}")
        print(f"  Avg broadband: {df['pct_broadband'].mean():.1f}%")
        print(f"  Avg no internet: {df['pct_no_internet'].mean():.1f}%")
        return df[["GEOID", "pct_internet", "pct_broadband", "pct_no_internet"]]
    except Exception as e:
        print(f"  ACS internet fetch failed: {e}")
        return None


def run():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load county boundaries
    print("Loading county boundaries...")
    counties = gpd.read_file(COUNTY_PATH)
    print(f"  Counties: {len(counties)}")

    # Fetch all data
    cbp_health = fetch_cbp()
    cbp_all = fetch_cbp_all_industries()
    small_biz = fetch_small_biz()
    broadband = fetch_broadband()

    # Merge everything into counties
    merged = counties.copy()

    if cbp_health is not None:
        merged = merged.merge(cbp_health, on="GEOID", how="left")

    if cbp_all is not None:
        merged = merged.merge(cbp_all, on="GEOID", how="left")
        if cbp_health is not None:
            merged["healthcare_pct_of_biz"] = (
                merged["healthcare_establishments"] / merged["total_establishments"] * 100
            ).round(1)

    if small_biz is not None:
        merged = merged.merge(small_biz, on="GEOID", how="left")
        if cbp_all is not None:
            merged["pct_small_biz"] = (
                merged["small_biz_count"] / merged["total_establishments"] * 100
            ).round(1)

    if broadband is not None:
        merged = merged.merge(broadband, on="GEOID", how="left")

    # Save
    merged.to_file(OUT_PATH, driver="GeoJSON")
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\nSaved: {OUT_PATH} ({size_kb:.0f} KB)")

    print(f"\nMarket Intelligence Summary:")
    if "healthcare_establishments" in merged.columns:
        print(f"  Healthcare establishments: {merged['healthcare_establishments'].sum():,.0f}")
        print(f"  Healthcare employees: {merged['healthcare_employees'].sum():,.0f}")
    if "pct_small_biz" in merged.columns:
        print(f"  Avg % small business: {merged['pct_small_biz'].mean():.1f}%")
    if "pct_no_internet" in merged.columns:
        print(f"  Avg % no internet: {merged['pct_no_internet'].mean():.1f}%")


if __name__ == "__main__":
    run()
