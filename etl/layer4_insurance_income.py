"""
Layer 4: Insurance & Income from Census ACS 5-Year Estimates
Pulls tract-level insurance coverage and income data.

Tables:
  S2701 / B27001 - Health Insurance Coverage
  B19013 - Median Household Income
  B17001 - Poverty Status
  B27010 - Insurance type breakdown
"""

import os
import json
import requests
import geopandas as gpd
import pandas as pd

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
DEMO_PATH = os.path.join(OUT_DIR, "ok_demographics.geojson")
OUT_PATH = os.path.join(OUT_DIR, "ok_insurance_income.geojson")

CENSUS_API = "https://api.census.gov/data/2023/acs/acs5"
STATE_FIPS = "40"


def fetch_acs(variables, label=""):
    var_str = ",".join(variables)
    url = f"{CENSUS_API}?get={var_str}&for=tract:*&in=state:{STATE_FIPS}"
    print(f"  Fetching {label}...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    return df


def run():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load existing demographics GeoJSON (has tract geometry + demo data)
    print("Loading demographics layer...")
    tracts = gpd.read_file(DEMO_PATH)
    print(f"  Tracts: {len(tracts)}")

    # 1. Insurance coverage (B27001 - by age, insured/uninsured)
    print("\n--- Insurance Coverage ---")
    ins_vars = [
        "B27001_001E",  # Total civilian noninstitutionalized
        "B27001_005E",  # Male under 6, no insurance
        "B27001_008E",  # Male 6-18, no insurance
        "B27001_011E",  # Male 19-25, no insurance
        "B27001_014E",  # Male 26-34, no insurance
        "B27001_017E",  # Male 35-44, no insurance
        "B27001_020E",  # Male 45-54, no insurance
        "B27001_023E",  # Male 55-64, no insurance
        "B27001_026E",  # Male 65-74, no insurance
        "B27001_029E",  # Male 75+, no insurance
        "B27001_033E",  # Female under 6, no insurance
        "B27001_036E",  # Female 6-18, no insurance
        "B27001_039E",  # Female 19-25, no insurance
        "B27001_042E",  # Female 26-34, no insurance
        "B27001_045E",  # Female 35-44, no insurance
        "B27001_048E",  # Female 45-54, no insurance
        "B27001_051E",  # Female 55-64, no insurance
        "B27001_054E",  # Female 65-74, no insurance
        "B27001_057E",  # Female 75+, no insurance
    ]
    ins_df = fetch_acs(ins_vars, "Insurance Coverage")
    for col in ins_vars:
        ins_df[col] = pd.to_numeric(ins_df[col], errors="coerce")

    ins_df["total_civ"] = ins_df["B27001_001E"]
    uninsured_cols = [c for c in ins_vars if c != "B27001_001E"]
    ins_df["uninsured"] = ins_df[uninsured_cols].sum(axis=1)
    ins_df["pct_uninsured"] = (ins_df["uninsured"] / ins_df["total_civ"] * 100).round(1)
    ins_df.loc[ins_df["pct_uninsured"] < 0, "pct_uninsured"] = None

    ins_keep = ins_df[["GEOID", "pct_uninsured"]]
    print(f"  Avg uninsured rate: {ins_df['pct_uninsured'].mean():.1f}%")

    # 2. Insurance type breakdown (B27010)
    print("\n--- Insurance Type ---")
    type_vars = [
        "B27010_001E",  # Total
        "B27010_003E",  # Under 19 employer
        "B27010_004E",  # Under 19 direct purchase
        "B27010_005E",  # Under 19 Medicare
        "B27010_006E",  # Under 19 Medicaid
        "B27010_007E",  # Under 19 TRICARE
        "B27010_008E",  # Under 19 VA
        "B27010_020E",  # 19-34 employer
        "B27010_021E",  # 19-34 direct purchase
        "B27010_022E",  # 19-34 Medicare
        "B27010_023E",  # 19-34 Medicaid
        "B27010_024E",  # 19-34 TRICARE
        "B27010_025E",  # 19-34 VA
        "B27010_036E",  # 35-64 employer
        "B27010_037E",  # 35-64 direct purchase
        "B27010_038E",  # 35-64 Medicare
        "B27010_039E",  # 35-64 Medicaid
        "B27010_040E",  # 35-64 TRICARE
        "B27010_041E",  # 35-64 VA
        "B27010_050E",  # 65+ employer
        "B27010_051E",  # 65+ direct purchase
        "B27010_052E",  # 65+ Medicare
        "B27010_053E",  # 65+ Medicaid
        "B27010_054E",  # 65+ TRICARE
        "B27010_055E",  # 65+ VA
    ]
    type_df = fetch_acs(type_vars, "Insurance Type")
    for col in type_vars:
        type_df[col] = pd.to_numeric(type_df[col], errors="coerce")

    total = type_df["B27010_001E"]

    # Sum across age groups for each type
    employer_cols = ["B27010_003E", "B27010_020E", "B27010_036E", "B27010_050E"]
    medicaid_cols = ["B27010_006E", "B27010_023E", "B27010_039E", "B27010_053E"]
    medicare_cols = ["B27010_005E", "B27010_022E", "B27010_038E", "B27010_052E"]
    va_cols = ["B27010_008E", "B27010_025E", "B27010_041E", "B27010_055E"]

    type_df["pct_employer"] = (type_df[employer_cols].sum(axis=1) / total * 100).round(1)
    type_df["pct_medicaid"] = (type_df[medicaid_cols].sum(axis=1) / total * 100).round(1)
    type_df["pct_medicare"] = (type_df[medicare_cols].sum(axis=1) / total * 100).round(1)
    type_df["pct_va"] = (type_df[va_cols].sum(axis=1) / total * 100).round(1)

    # Clean negative values
    for col in ["pct_employer", "pct_medicaid", "pct_medicare", "pct_va"]:
        type_df.loc[type_df[col] < 0, col] = None

    type_keep = type_df[["GEOID", "pct_employer", "pct_medicaid", "pct_medicare", "pct_va"]]

    # 3. Median Household Income
    print("\n--- Income ---")
    inc_df = fetch_acs(["B19013_001E"], "Median Household Income")
    inc_df["median_income"] = pd.to_numeric(inc_df["B19013_001E"], errors="coerce")
    inc_df.loc[inc_df["median_income"] < 0, "median_income"] = None
    inc_keep = inc_df[["GEOID", "median_income"]]
    print(f"  Median income (avg of tracts): ${inc_df['median_income'].mean():,.0f}")

    # 4. Poverty
    print("\n--- Poverty ---")
    pov_vars = ["B17001_001E", "B17001_002E"]  # Total, Below poverty
    pov_df = fetch_acs(pov_vars, "Poverty Status")
    for col in pov_vars:
        pov_df[col] = pd.to_numeric(pov_df[col], errors="coerce")
    pov_df["pct_poverty"] = (pov_df["B17001_002E"] / pov_df["B17001_001E"] * 100).round(1)
    pov_df.loc[pov_df["pct_poverty"] < 0, "pct_poverty"] = None
    pov_keep = pov_df[["GEOID", "pct_poverty"]]
    print(f"  Avg poverty rate: {pov_df['pct_poverty'].mean():.1f}%")

    # --- Merge all into demographics layer ---
    print("\n--- Merging ---")
    insurance = ins_keep.copy()
    for df in [type_keep, inc_keep, pov_keep]:
        insurance = insurance.merge(df, on="GEOID", how="left")

    merged = tracts.merge(insurance, on="GEOID", how="left")
    print(f"  Final tracts: {len(merged)}")

    merged.to_file(OUT_PATH, driver="GeoJSON")
    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"\nSaved: {OUT_PATH} ({size_mb:.1f} MB)")

    print(f"\nOklahoma Insurance & Income Summary:")
    print(f"  Uninsured: {merged['pct_uninsured'].mean():.1f}%")
    print(f"  Employer-sponsored: {merged['pct_employer'].mean():.1f}%")
    print(f"  Medicaid: {merged['pct_medicaid'].mean():.1f}%")
    print(f"  Medicare: {merged['pct_medicare'].mean():.1f}%")
    print(f"  VA/TRICARE: {merged['pct_va'].mean():.1f}%")
    print(f"  Median Income: ${merged['median_income'].mean():,.0f}")
    print(f"  Poverty Rate: {merged['pct_poverty'].mean():.1f}%")


if __name__ == "__main__":
    run()
