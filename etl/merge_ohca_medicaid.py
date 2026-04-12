#!/usr/bin/env python3
"""
Merge OHCA enrollment data + Medicaid provider network counts into ok_counties.geojson.
Also produces ok_medicaid_providers.geojson with per-county acceptance counts.

Inputs:
  - data/processed/ok_counties.geojson (existing county features)
  - data/processed/ohca_enrollment.json (OHCA enrollment by county)
  - data/processed/centene_providers.json (Centene/OCH NPIs + counties)
  - data/processed/humana_providers.json (Humana NPIs)
  - data/raw/uhc_provider_npis.json (UHC NPIs)
  - data/raw/nppes_oklahoma.csv (NPI → county mapping for Humana/UHC)

Output:
  - data/processed/ok_counties.geojson (enriched with OHCA + Medicaid network fields)
"""

import csv
import json

COUNTIES_PATH = "data/processed/ok_counties.geojson"
OHCA_PATH = "data/processed/ohca_enrollment.json"
CENTENE_PATH = "data/processed/centene_providers.json"
HUMANA_PATH = "data/processed/humana_providers.json"
UHC_PATH = "data/raw/uhc_provider_npis.json"
NPPES_PATH = "data/raw/nppes_oklahoma.csv"


def build_npi_county_map():
    """Build NPI → county from NPPES data."""
    npi_county = {}
    with open(NPPES_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            npi = row.get("NPI", "").strip()
            # Try practice location city → we'll map by the provider's county from geocoded data
            county = row.get("county", "").strip()
            if npi and county:
                npi_county[npi] = county
    return npi_county


def main():
    # Load counties
    with open(COUNTIES_PATH) as f:
        counties_gj = json.load(f)

    # Load OHCA enrollment
    with open(OHCA_PATH) as f:
        ohca = json.load(f)
    ohca_by_county = {r["county"]: r for r in ohca}

    # Load Centene providers (already has county mapping)
    with open(CENTENE_PATH) as f:
        centene = json.load(f)

    # Count Centene NPIs per county
    centene_by_county = {}
    centene_npis = set()
    for p in centene:
        centene_npis.add(p["npi"])
        for c in p.get("counties", []):
            centene_by_county[c] = centene_by_county.get(c, 0) + 1

    # Load Humana
    with open(HUMANA_PATH) as f:
        humana = json.load(f)
    humana_npis = {p["npi"] for p in humana}

    # Load UHC
    with open(UHC_PATH) as f:
        uhc = json.load(f)
    uhc_npis = set(uhc.keys())

    # All Medicaid NPIs (any network)
    all_medicaid_npis = centene_npis | humana_npis | uhc_npis
    print(f"Centene NPIs: {len(centene_npis)}")
    print(f"Humana NPIs: {len(humana_npis)}")
    print(f"UHC NPIs: {len(uhc_npis)}")
    print(f"Total unique Medicaid NPIs: {len(all_medicaid_npis)}")

    # Merge into county features
    merged = 0
    for feature in counties_gj["features"]:
        name = feature["properties"]["NAME"]
        p = feature["properties"]

        # OHCA enrollment data
        ohca_rec = ohca_by_county.get(name)
        if ohca_rec:
            merged += 1
            p["ohca_total_enrollment"] = ohca_rec.get("total_enrollment")
            p["ohca_medicaid_pct"] = ohca_rec.get("medicaid_pct")
            p["ohca_medicaid_rank"] = ohca_rec.get("medicaid_pct_rank")
            p["ohca_pop_estimate"] = ohca_rec.get("pop_estimate")
            p["ohca_expenditures"] = ohca_rec.get("expenditures")
            p["ohca_expenditures_rank"] = ohca_rec.get("expenditures_rank")
            p["ohca_avg_monthly_per_member"] = ohca_rec.get("avg_monthly_per_member")
            p["ohca_dual_enrollees"] = ohca_rec.get("dual_enrollees")
            p["ohca_expansion"] = ohca_rec.get("expansion")
            p["ohca_children_parents"] = (
                (ohca_rec.get("children_parents_adult") or 0)
                + (ohca_rec.get("children_parents_child") or 0)
            )
            p["ohca_abd"] = (
                (ohca_rec.get("abd_adult") or 0) + (ohca_rec.get("abd_child") or 0)
            )
            p["ohca_unduplicated"] = ohca_rec.get("unduplicated_members")
            p["ohca_deliveries"] = ohca_rec.get("deliveries")
            p["ohca_avg_annual_per_pop"] = ohca_rec.get("avg_annual_per_pop")

            # Race breakdown
            p["ohca_race_ai"] = ohca_rec.get("race_american_indian")
            p["ohca_race_caucasian"] = ohca_rec.get("race_caucasian")
            p["ohca_race_black"] = ohca_rec.get("race_black")
            p["ohca_race_hispanic"] = ohca_rec.get("race_hispanic")
        else:
            print(f"  WARNING: No OHCA data for {name}")

        # Centene provider count for this county
        p["centene_providers"] = centene_by_county.get(name, 0)

    print(f"\nMerged OHCA data for {merged}/77 counties")

    # Handle Le Flore vs LeFlore name mismatch
    mismatches = [
        name for name in ohca_by_county
        if not any(
            f["properties"]["NAME"] == name for f in counties_gj["features"]
        )
    ]
    if mismatches:
        print(f"Unmatched OHCA counties: {mismatches}")
        # Try fuzzy match
        for mm in mismatches:
            for feature in counties_gj["features"]:
                gj_name = feature["properties"]["NAME"]
                if gj_name.replace(" ", "").lower() == mm.replace(" ", "").lower():
                    print(f"  Fuzzy match: '{mm}' → '{gj_name}'")
                    ohca_rec = ohca_by_county[mm]
                    p = feature["properties"]
                    p["ohca_total_enrollment"] = ohca_rec.get("total_enrollment")
                    p["ohca_medicaid_pct"] = ohca_rec.get("medicaid_pct")
                    p["ohca_medicaid_rank"] = ohca_rec.get("medicaid_pct_rank")
                    p["ohca_pop_estimate"] = ohca_rec.get("pop_estimate")
                    p["ohca_expenditures"] = ohca_rec.get("expenditures")
                    p["ohca_expenditures_rank"] = ohca_rec.get("expenditures_rank")
                    p["ohca_avg_monthly_per_member"] = ohca_rec.get("avg_monthly_per_member")
                    p["ohca_dual_enrollees"] = ohca_rec.get("dual_enrollees")
                    p["ohca_expansion"] = ohca_rec.get("expansion")
                    p["ohca_children_parents"] = (
                        (ohca_rec.get("children_parents_adult") or 0)
                        + (ohca_rec.get("children_parents_child") or 0)
                    )
                    p["ohca_abd"] = (
                        (ohca_rec.get("abd_adult") or 0) + (ohca_rec.get("abd_child") or 0)
                    )
                    p["ohca_unduplicated"] = ohca_rec.get("unduplicated_members")
                    p["ohca_deliveries"] = ohca_rec.get("deliveries")
                    p["ohca_avg_annual_per_pop"] = ohca_rec.get("avg_annual_per_pop")
                    p["ohca_race_ai"] = ohca_rec.get("race_american_indian")
                    p["ohca_race_caucasian"] = ohca_rec.get("race_caucasian")
                    p["ohca_race_black"] = ohca_rec.get("race_black")
                    p["ohca_race_hispanic"] = ohca_rec.get("race_hispanic")
                    p["centene_providers"] = centene_by_county.get(mm, 0)
                    merged += 1

    # Also check "Texas co." → "Texas"
    for feature in counties_gj["features"]:
        name = feature["properties"]["NAME"]
        if feature["properties"].get("ohca_total_enrollment") is None:
            # Try with "co." suffix
            alt = f"{name} co."
            ohca_rec = ohca_by_county.get(alt)
            if ohca_rec:
                print(f"  Alt match: '{alt}' → '{name}'")
                p = feature["properties"]
                p["ohca_total_enrollment"] = ohca_rec.get("total_enrollment")
                p["ohca_medicaid_pct"] = ohca_rec.get("medicaid_pct")
                p["ohca_medicaid_rank"] = ohca_rec.get("medicaid_pct_rank")
                p["ohca_pop_estimate"] = ohca_rec.get("pop_estimate")
                p["ohca_expenditures"] = ohca_rec.get("expenditures")

    # Write enriched counties
    with open(COUNTIES_PATH, "w") as f:
        json.dump(counties_gj, f)
    print(f"\nWrote enriched {COUNTIES_PATH}")

    # Quick stats
    has_pct = sum(
        1 for f in counties_gj["features"]
        if f["properties"].get("ohca_medicaid_pct") is not None
    )
    print(f"Counties with Medicaid %: {has_pct}/77")
    has_centene = sum(
        1 for f in counties_gj["features"]
        if f["properties"].get("centene_providers", 0) > 0
    )
    print(f"Counties with Centene providers: {has_centene}/77")


if __name__ == "__main__":
    main()
