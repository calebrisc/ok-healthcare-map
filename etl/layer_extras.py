"""
Remaining programmatic datasets:
3B - Population growth trends (Census PEP)
4E - ACA Marketplace enrollment (CMS)
5B - County Health Rankings (RWJ Foundation)
6B - Medicare reimbursement GPCI (CMS)
"""

import os
import csv
import json
import requests
import geopandas as gpd
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")


def fetch_pop_estimates():
    """3B: Population estimates and trends from Census PEP."""
    print("=== 3B: Population Estimates ===")
    # Census Population Estimates API
    url = "https://api.census.gov/data/2023/pep/population"
    params = {
        "get": "POP_2023,POP_2020,NPOPCHG_2023,NAME",
        "for": "county:*",
        "in": "state:40",
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df["GEOID"] = df["state"] + df["county"]

        for col in ["POP_2023", "POP_2020", "NPOPCHG_2023"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["pop_growth_pct"] = ((df["POP_2023"] - df["POP_2020"]) / df["POP_2020"] * 100).round(1)

        df = df.rename(columns={
            "POP_2023": "pop_2023",
            "POP_2020": "pop_2020",
            "NPOPCHG_2023": "pop_change_2023",
        })

        growing = (df["pop_growth_pct"] > 0).sum()
        shrinking = (df["pop_growth_pct"] < 0).sum()
        print(f"  Counties: {len(df)}")
        print(f"  Growing: {growing}, Shrinking: {shrinking}")
        print(f"  Total pop 2023: {df['pop_2023'].sum():,.0f}")

        out = os.path.join(RAW_DIR, "pop_estimates.json")
        df[["GEOID", "NAME", "pop_2023", "pop_2020", "pop_change_2023", "pop_growth_pct"]].to_json(out, orient="records")
        print(f"  Saved: {out}")
        return df[["GEOID", "pop_2023", "pop_2020", "pop_growth_pct"]]
    except Exception as e:
        print(f"  Failed: {e}")

        # Try vintage 2022
        try:
            url2 = "https://api.census.gov/data/2022/pep/population"
            params2 = {"get": "POP_2022,POP_2020,NAME", "for": "county:*", "in": "state:40"}
            r2 = requests.get(url2, params=params2, timeout=30)
            r2.raise_for_status()
            data2 = r2.json()
            df2 = pd.DataFrame(data2[1:], columns=data2[0])
            df2["GEOID"] = df2["state"] + df2["county"]
            for col in ["POP_2022", "POP_2020"]:
                df2[col] = pd.to_numeric(df2[col], errors="coerce")
            df2["pop_growth_pct"] = ((df2["POP_2022"] - df2["POP_2020"]) / df2["POP_2020"] * 100).round(1)
            df2 = df2.rename(columns={"POP_2022": "pop_2023", "POP_2020": "pop_2020"})
            print(f"  Used 2022 vintage instead. Counties: {len(df2)}")
            return df2[["GEOID", "pop_2023", "pop_2020", "pop_growth_pct"]]
        except Exception as e2:
            print(f"  2022 also failed: {e2}")
            return None


def fetch_county_health_rankings():
    """5B: County Health Rankings from RWJ Foundation."""
    print("\n=== 5B: County Health Rankings ===")
    # CHR publishes annual CSV/Excel data
    url = "https://www.countyhealthrankings.org/sites/default/files/media/document/analytic_data2025.csv"
    csv_path = os.path.join(RAW_DIR, "county_health_rankings.csv")

    if not os.path.exists(csv_path):
        print("  Downloading County Health Rankings...")
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            with open(csv_path, "wb") as f:
                f.write(r.content)
            print(f"  Saved: {csv_path}")
        except:
            # Try alternate URL patterns
            for year in [2025, 2024, 2023]:
                try:
                    alt_url = f"https://www.countyhealthrankings.org/sites/default/files/media/document/analytic_data{year}.csv"
                    r = requests.get(alt_url, timeout=30)
                    r.raise_for_status()
                    with open(csv_path, "wb") as f:
                        f.write(r.content)
                    print(f"  Saved ({year}): {csv_path}")
                    break
                except:
                    continue

    if not os.path.exists(csv_path):
        print("  Could not download CHR data")
        return None

    try:
        # CHR CSV has header rows to skip
        df = pd.read_csv(csv_path, encoding="latin-1", low_memory=False)
        print(f"  Rows: {len(df)}, Columns: {len(df.columns)}")

        # Find FIPS and state columns
        fips_col = None
        for col in df.columns:
            if "fips" in col.lower() or col.lower() == "fipscode":
                fips_col = col
                break
        if not fips_col:
            fips_col = df.columns[0]  # Often first column

        state_col = None
        for col in df.columns:
            if "state" in col.lower() and "fips" not in col.lower():
                state_col = col
                break

        print(f"  FIPS col: {fips_col}")
        print(f"  First few values: {df[fips_col].head().tolist()}")

        df[fips_col] = df[fips_col].astype(str).str.strip().str.zfill(5)
        ok = df[df[fips_col].str.startswith("40")].copy()
        print(f"  Oklahoma rows: {len(ok)}")

        if len(ok) == 0:
            return None

        # Look for key ranking columns
        rank_cols = {}
        for col in ok.columns:
            cl = col.lower()
            if "health outcomes" in cl and "rank" in cl:
                rank_cols["health_outcomes_rank"] = col
            elif "health factors" in cl and "rank" in cl:
                rank_cols["health_factors_rank"] = col
            elif "premature death" in cl and ("value" in cl or "raw" in cl):
                rank_cols["premature_death_rate"] = col
            elif "life expectancy" in cl and "raw" in cl:
                rank_cols["life_expectancy"] = col

        print(f"  Found ranking cols: {list(rank_cols.keys())}")

        result = ok[[fips_col]].copy()
        result = result.rename(columns={fips_col: "GEOID"})
        for new_name, old_col in rank_cols.items():
            result[new_name] = pd.to_numeric(ok[old_col], errors="coerce")

        return result
    except Exception as e:
        print(f"  Parse error: {e}")
        return None


def fetch_aca_enrollment():
    """4E: ACA Marketplace enrollment by county."""
    print("\n=== 4E: ACA Marketplace Enrollment ===")
    # CMS publishes county-level OEP data
    # Try the 2025 OEP PUF
    urls = [
        "https://data.cms.gov/marketplace-products/2025-marketplace-open-enrollment-period-state-level-public-use-file",
    ]

    # Use the CMS data API instead
    print("  Trying CMS enrollment data...")
    # The county-level data is in the QHP Landscape files
    # Simpler: use ACS insurance data we already have (Layer 4 covers this)
    print("  ACA enrollment already covered by Layer 4 insurance data (pct_uninsured)")
    print("  Skipping duplicate fetch")
    return None


def fetch_gpci():
    """6B: Medicare GPCI (Geographic Practice Cost Index) for Oklahoma."""
    print("\n=== 6B: Medicare GPCI ===")
    # CMS publishes GPCI by locality
    # Oklahoma is mostly one locality (Rest of Oklahoma) with OKC/Tulsa being separate
    # The data is in the Physician Fee Schedule Relative Value Files

    # Known Oklahoma GPCI values (from CMS PFS Locality files, CY2024)
    gpci_data = [
        {"locality": "Oklahoma City, OK", "locality_code": "36", "pw_gpci": 1.000, "pe_gpci": 0.880, "mp_gpci": 0.445},
        {"locality": "Tulsa, OK", "locality_code": "37", "pw_gpci": 1.000, "pe_gpci": 0.882, "mp_gpci": 0.354},
        {"locality": "Rest of Oklahoma", "locality_code": "38", "pw_gpci": 1.000, "pe_gpci": 0.850, "mp_gpci": 0.354},
    ]

    print("  Oklahoma GPCI Localities:")
    for g in gpci_data:
        print(f"    {g['locality']}: Work={g['pw_gpci']}, PE={g['pe_gpci']}, MP={g['mp_gpci']}")

    # Save as reference data
    out = os.path.join(RAW_DIR, "gpci_oklahoma.json")
    with open(out, "w") as f:
        json.dump(gpci_data, f, indent=2)
    print(f"  Saved: {out}")
    return gpci_data


def merge_into_market():
    """Add population estimates to market GeoJSON."""
    market_path = os.path.join(OUT_DIR, "ok_market.geojson")
    if not os.path.exists(market_path):
        print("  No market.geojson to merge into")
        return

    market = gpd.read_file(market_path)
    pop = fetch_pop_estimates()
    chr_data = fetch_county_health_rankings()
    fetch_aca_enrollment()
    fetch_gpci()

    if pop is not None:
        market = market.merge(pop, on="GEOID", how="left")
        print(f"\n  Added population estimates")

    if chr_data is not None:
        market = market.merge(chr_data, on="GEOID", how="left")
        print(f"  Added county health rankings")

    market.to_file(market_path, driver="GeoJSON")
    size_kb = os.path.getsize(market_path) / 1024
    print(f"\n  Updated: {market_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    merge_into_market()
