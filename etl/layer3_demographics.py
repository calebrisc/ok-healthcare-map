"""
Layer 3: Population & Demographics from Census ACS 5-Year Estimates
Pulls tract-level demographic data via Census API, joins to tract GeoJSON.

Tables:
  B01001 - Total population by age/sex
  B02001 - Race
  B03003 - Hispanic/Latino
  B18101 - Disability status
  B08201 - Households without vehicle
"""

import os
import json
import requests
import geopandas as gpd
import pandas as pd

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
TRACT_PATH = os.path.join(OUT_DIR, "ok_tracts.geojson")
OUT_PATH = os.path.join(OUT_DIR, "ok_demographics.geojson")

CENSUS_API = "https://api.census.gov/data/2023/acs/acs5"
STATE_FIPS = "40"


def fetch_acs(variables, label=""):
    """Fetch ACS data for all Oklahoma tracts."""
    var_str = ",".join(variables)
    url = f"{CENSUS_API}?get={var_str}&for=tract:*&in=state:{STATE_FIPS}"
    print(f"  Fetching {label or var_str[:50]}...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    # Build GEOID: state(2) + county(3) + tract(6)
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    return df


def run():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Loading tract boundaries...")
    tracts = gpd.read_file(TRACT_PATH)
    print(f"  Tracts: {len(tracts)}")

    # --- Fetch demographic tables ---

    # 1. Total population + age groups
    print("\n--- Population & Age ---")
    pop_vars = [
        "B01001_001E",  # Total population
        "B01001_003E", "B01001_004E", "B01001_005E", "B01001_006E",  # Male under 5, 5-9, 10-14, 15-17
        "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",  # Male 65+
        "B01001_027E", "B01001_028E", "B01001_029E", "B01001_030E",  # Female under 5, 5-9, 10-14, 15-17
        "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",  # Female 65+
        "B01002_001E",  # Median age
    ]
    pop_df = fetch_acs(pop_vars, "Population & Age")

    # Calculate derived fields
    pop_df["total_pop"] = pd.to_numeric(pop_df["B01001_001E"], errors="coerce")
    pop_df["median_age"] = pd.to_numeric(pop_df["B01002_001E"], errors="coerce")
    pop_df.loc[pop_df["median_age"] < 0, "median_age"] = None  # Census uses negative for missing

    # Under 18 (rough: under 5 + 5-9 + 10-14 + 15-17 for both sexes)
    under18_cols = ["B01001_003E", "B01001_004E", "B01001_005E", "B01001_006E",
                    "B01001_027E", "B01001_028E", "B01001_029E", "B01001_030E"]
    for col in under18_cols:
        pop_df[col] = pd.to_numeric(pop_df[col], errors="coerce")
    pop_df["pop_under_18"] = pop_df[under18_cols].sum(axis=1)

    # 65 and over
    over65_cols = ["B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
                   "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E"]
    for col in over65_cols:
        pop_df[col] = pd.to_numeric(pop_df[col], errors="coerce")
    pop_df["pop_65_plus"] = pop_df[over65_cols].sum(axis=1)

    pop_df["pct_under_18"] = (pop_df["pop_under_18"] / pop_df["total_pop"] * 100).round(1)
    pop_df["pct_65_plus"] = (pop_df["pop_65_plus"] / pop_df["total_pop"] * 100).round(1)

    pop_keep = pop_df[["GEOID", "total_pop", "median_age", "pop_under_18", "pop_65_plus", "pct_under_18", "pct_65_plus"]]
    print(f"  Total OK population: {pop_df['total_pop'].sum():,.0f}")

    # 2. Race
    print("\n--- Race ---")
    race_vars = [
        "B02001_001E",  # Total
        "B02001_002E",  # White alone
        "B02001_003E",  # Black alone
        "B02001_004E",  # AIAN alone
        "B02001_005E",  # Asian alone
        "B02001_008E",  # Two or more
    ]
    race_df = fetch_acs(race_vars, "Race")
    for col in race_vars:
        race_df[col] = pd.to_numeric(race_df[col], errors="coerce")

    race_total = race_df["B02001_001E"]
    race_df["pct_white"] = (race_df["B02001_002E"] / race_total * 100).round(1)
    race_df["pct_black"] = (race_df["B02001_003E"] / race_total * 100).round(1)
    race_df["pct_aian"] = (race_df["B02001_004E"] / race_total * 100).round(1)
    race_df["pct_asian"] = (race_df["B02001_005E"] / race_total * 100).round(1)
    race_df["pct_two_plus"] = (race_df["B02001_008E"] / race_total * 100).round(1)

    race_keep = race_df[["GEOID", "pct_white", "pct_black", "pct_aian", "pct_asian", "pct_two_plus"]]

    # 3. Hispanic/Latino
    print("\n--- Hispanic/Latino ---")
    hisp_vars = ["B03003_001E", "B03003_003E"]  # Total, Hispanic
    hisp_df = fetch_acs(hisp_vars, "Hispanic/Latino")
    for col in hisp_vars:
        hisp_df[col] = pd.to_numeric(hisp_df[col], errors="coerce")
    hisp_df["pct_hispanic"] = (hisp_df["B03003_003E"] / hisp_df["B03003_001E"] * 100).round(1)
    hisp_keep = hisp_df[["GEOID", "pct_hispanic"]]

    # 4. Disability
    print("\n--- Disability ---")
    dis_vars = ["B18101_001E", "B18101_004E", "B18101_007E", "B18101_010E", "B18101_013E",
                "B18101_016E", "B18101_019E",  # Male with disability by age
                "B18101_023E", "B18101_026E", "B18101_029E", "B18101_032E",
                "B18101_035E", "B18101_038E"]  # Female with disability by age
    dis_df = fetch_acs(dis_vars, "Disability")
    for col in dis_vars:
        dis_df[col] = pd.to_numeric(dis_df[col], errors="coerce")
    dis_df["total_pop_dis"] = dis_df["B18101_001E"]
    dis_cols = [c for c in dis_vars if c != "B18101_001E"]
    dis_df["pop_disabled"] = dis_df[dis_cols].sum(axis=1)
    dis_df["pct_disabled"] = (dis_df["pop_disabled"] / dis_df["total_pop_dis"] * 100).round(1)
    dis_keep = dis_df[["GEOID", "pct_disabled"]]

    # 5. Households without vehicle
    print("\n--- Vehicle Access ---")
    veh_vars = ["B08201_001E", "B08201_002E"]  # Total HH, No vehicle
    veh_df = fetch_acs(veh_vars, "Vehicle Access")
    for col in veh_vars:
        veh_df[col] = pd.to_numeric(veh_df[col], errors="coerce")
    veh_df["pct_no_vehicle"] = (veh_df["B08201_002E"] / veh_df["B08201_001E"] * 100).round(1)
    veh_keep = veh_df[["GEOID", "pct_no_vehicle"]]

    # --- Merge everything ---
    print("\n--- Merging ---")
    demo = pop_keep.copy()
    for df in [race_keep, hisp_keep, dis_keep, veh_keep]:
        demo = demo.merge(df, on="GEOID", how="left")

    print(f"  Demographics rows: {len(demo)}")

    # Join to tract geometries
    merged = tracts.merge(demo, on="GEOID", how="left")
    print(f"  Merged tracts: {len(merged)}")
    print(f"  Tracts with pop data: {merged['total_pop'].notna().sum()}")

    # Save
    merged.to_file(OUT_PATH, driver="GeoJSON")
    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"\nSaved: {OUT_PATH} ({size_mb:.1f} MB)")

    # Summary stats
    print(f"\nOklahoma Demographics Summary:")
    print(f"  Total Population: {merged['total_pop'].sum():,.0f}")
    print(f"  Median Age (avg of tracts): {merged['median_age'].mean():.1f}")
    print(f"  % Under 18: {merged['pop_under_18'].sum() / merged['total_pop'].sum() * 100:.1f}%")
    print(f"  % 65+: {merged['pop_65_plus'].sum() / merged['total_pop'].sum() * 100:.1f}%")
    print(f"  % White: {merged['pct_white'].mean():.1f}%")
    print(f"  % AIAN: {merged['pct_aian'].mean():.1f}%")
    print(f"  % Hispanic: {merged['pct_hispanic'].mean():.1f}%")
    print(f"  % Disabled: {merged['pct_disabled'].mean():.1f}%")
    print(f"  % No Vehicle: {merged['pct_no_vehicle'].mean():.1f}%")


if __name__ == "__main__":
    run()
