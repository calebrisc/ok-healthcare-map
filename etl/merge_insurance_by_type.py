#!/usr/bin/env python3
"""
Merge insurance network data into ok_counties.geojson, broken down by provider type.

For each county, counts providers by category × insurer.
Categories: pcp, np_pa, specialist, dental, behavioral, therapy, hospital, facility, pharmacy

Output fields on each county:
  ins_{category}_{insurer}  (e.g., ins_pcp_bcbs = 54)
  ins_{category}_total      (e.g., ins_pcp_total = 203)
"""

import glob
import json
from shapely.geometry import shape, Point

COUNTIES_PATH = "data/processed/ok_counties.geojson"

# Map provider files to display categories
PROVIDER_CATEGORIES = {
    "ok_providers_primary_care.geojson": "pcp",
    "ok_providers_np_pa.geojson": "np_pa",
    "ok_providers_specialists.geojson": "specialist",
    "ok_providers_dental.geojson": "dental",
    "ok_providers_behavioral.geojson": "behavioral",
    "ok_providers_therapy.geojson": "therapy",
    "ok_providers_hospitals.geojson": "hospital",
    "ok_providers_facilities.geojson": "facility",
    "ok_providers_pharmacy.geojson": "pharmacy",
}

INSURERS = ["bcbs", "cigna", "aetna", "centene", "humana", "uhc"]

CATEGORY_LABELS = {
    "pcp": "Primary Care",
    "np_pa": "NP / PA",
    "specialist": "Specialists",
    "dental": "Dental",
    "behavioral": "Behavioral Health",
    "therapy": "Therapy",
    "hospital": "Hospitals",
    "facility": "Facilities",
    "pharmacy": "Pharmacy",
}


def main():
    # Load county polygons
    print("Loading county polygons...")
    with open(COUNTIES_PATH) as f:
        counties_gj = json.load(f)
    county_polys = []
    for feat in counties_gj["features"]:
        poly = shape(feat["geometry"])
        county_polys.append((feat["properties"]["NAME"], poly))

    # Load insurer NPI sets
    print("Loading insurer NPIs...")
    with open("data/processed/commercial_insurance_npis.json") as f:
        bcbs_npis = set(json.load(f)["bcbs"]["npis"])
    with open("data/processed/cigna_npis.json") as f:
        cigna_npis = set(json.load(f))
    with open("data/processed/aetna_npis.json") as f:
        aetna_npis = set(json.load(f))
    with open("data/processed/centene_providers.json") as f:
        centene_npis = {p["npi"] for p in json.load(f)}
    with open("data/processed/humana_providers.json") as f:
        humana_npis = {p["npi"] for p in json.load(f)}
    with open("data/raw/uhc_provider_npis.json") as f:
        uhc_npis = set(json.load(f).keys())

    insurer_sets = {
        "bcbs": bcbs_npis,
        "cigna": cigna_npis,
        "aetna": aetna_npis,
        "centene": centene_npis,
        "humana": humana_npis,
        "uhc": uhc_npis,
    }

    # Process each provider category
    # Result: county_data[county][category][insurer] = count
    county_data = {feat["properties"]["NAME"]: {} for feat in counties_gj["features"]}

    for filename, category in PROVIDER_CATEGORIES.items():
        filepath = f"data/processed/{filename}"
        print(f"  {category}: {filepath}...")

        with open(filepath) as f:
            data = json.load(f)

        # Assign each provider to county + check insurer membership
        for feat in data["features"]:
            npi = str(feat["properties"].get("npi", ""))
            geom = feat.get("geometry")
            if not npi or not geom or not geom.get("coordinates"):
                continue
            lon, lat = geom["coordinates"]
            if lon == 0 and lat == 0:
                continue

            # Point-in-polygon
            pt = Point(lon, lat)
            county_name = None
            for cname, poly in county_polys:
                if poly.contains(pt):
                    county_name = cname
                    break
            if not county_name:
                continue

            # Initialize category for this county
            if category not in county_data[county_name]:
                county_data[county_name][category] = {ins: 0 for ins in INSURERS}
                county_data[county_name][category]["total"] = 0

            county_data[county_name][category]["total"] += 1
            for ins_key, ins_set in insurer_sets.items():
                if npi in ins_set:
                    county_data[county_name][category][ins_key] += 1

    # Merge into counties geojson
    print("\nMerging into ok_counties.geojson...")
    for feat in counties_gj["features"]:
        name = feat["properties"]["NAME"]
        p = feat["properties"]
        cd = county_data.get(name, {})

        for cat in PROVIDER_CATEGORIES.values():
            cat_data = cd.get(cat, {})
            for ins in INSURERS:
                p[f"ins_{cat}_{ins}"] = cat_data.get(ins, 0)
            p[f"ins_{cat}_total"] = cat_data.get("total", 0)

    with open(COUNTIES_PATH, "w") as f:
        json.dump(counties_gj, f)
    print(f"Wrote {COUNTIES_PATH}")

    # Summary for top counties
    print("\n" + "=" * 80)
    print("Top 5 counties — Primary Care breakdown:")
    print(f"{'County':<16} {'Total':>6} {'BCBS':>6} {'Cigna':>6} {'Aetna':>6} {'Cent':>6}")
    print("-" * 80)
    ranked = sorted(
        counties_gj["features"],
        key=lambda f: -f["properties"].get("ins_pcp_total", 0),
    )
    for feat in ranked[:5]:
        p = feat["properties"]
        print(
            f"{p['NAME']:<16} {p['ins_pcp_total']:>6} {p['ins_pcp_bcbs']:>6} "
            f"{p['ins_pcp_cigna']:>6} {p['ins_pcp_aetna']:>6} {p['ins_pcp_centene']:>6}"
        )

    print("\nTop 5 counties — NP/PA breakdown:")
    print(f"{'County':<16} {'Total':>6} {'BCBS':>6} {'Cigna':>6} {'Aetna':>6} {'Cent':>6}")
    print("-" * 80)
    ranked = sorted(
        counties_gj["features"],
        key=lambda f: -f["properties"].get("ins_np_pa_total", 0),
    )
    for feat in ranked[:5]:
        p = feat["properties"]
        print(
            f"{p['NAME']:<16} {p['ins_np_pa_total']:>6} {p['ins_np_pa_bcbs']:>6} "
            f"{p['ins_np_pa_cigna']:>6} {p['ins_np_pa_aetna']:>6} {p['ins_np_pa_centene']:>6}"
        )


if __name__ == "__main__":
    main()
