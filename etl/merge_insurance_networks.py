#!/usr/bin/env python3
"""
Merge commercial + Medicaid insurance network data into ok_counties.geojson.

For each county, calculates how many in-network providers each insurer has.
Cross-references national NPI lists (Aetna, Cigna) with OK NPPES providers,
and uses county-assigned data for OK-specific networks (BCBS, Centene, etc).

Inputs:
  - data/processed/ok_providers_*.geojson  (OK providers with coords + city)
  - data/processed/ok_counties.geojson     (county polygons)
  - data/processed/commercial_insurance_npis.json  (BCBS OK NPIs by plan)
  - data/processed/cigna_npis.json         (Cigna national NPIs)
  - data/processed/aetna_npis.json         (Aetna national NPIs)
  - data/processed/centene_providers.json   (Centene OK NPIs)
  - data/processed/humana_providers.json    (Humana OK NPIs)
  - data/raw/uhc_provider_npis.json         (UHC OK NPIs)

Output:
  - data/processed/ok_counties.geojson     (enriched with per-county insurer counts)
"""

import glob
import json
from shapely.geometry import shape, Point


def load_county_polygons(path):
    """Load county features and build shapely polygons for point-in-polygon."""
    with open(path) as f:
        data = json.load(f)
    counties = []
    for feat in data["features"]:
        poly = shape(feat["geometry"])
        name = feat["properties"]["NAME"]
        counties.append((name, poly, feat))
    return counties, data


def assign_npi_counties(provider_files, county_polys):
    """Build NPI → county mapping using point-in-polygon on geocoded providers."""
    npi_county = {}
    npi_count = 0

    for gf in sorted(provider_files):
        with open(gf) as f:
            data = json.load(f)
        for feat in data["features"]:
            npi = str(feat["properties"].get("npi", ""))
            if not npi or npi in npi_county:
                continue
            geom = feat.get("geometry")
            if not geom or not geom.get("coordinates"):
                continue
            lon, lat = geom["coordinates"]
            if lon == 0 and lat == 0:
                continue

            pt = Point(lon, lat)
            for county_name, poly, _ in county_polys:
                if poly.contains(pt):
                    npi_county[npi] = county_name
                    break
            npi_count += 1

    print(f"Assigned {len(npi_county)} of {npi_count} NPIs to counties")
    return npi_county


def count_by_county(npi_set, npi_county_map):
    """Count how many NPIs from a set fall in each county."""
    counts = {}
    matched = 0
    for npi in npi_set:
        county = npi_county_map.get(npi)
        if county:
            counts[county] = counts.get(county, 0) + 1
            matched += 1
    return counts, matched


def main():
    print("Loading county polygons...")
    county_polys, counties_gj = load_county_polygons(
        "data/processed/ok_counties.geojson"
    )

    print("Assigning NPIs to counties via point-in-polygon...")
    provider_files = glob.glob("data/processed/ok_providers_*.geojson")
    npi_county = assign_npi_counties(provider_files, county_polys)

    # Build set of all OK NPIs for filtering national networks
    ok_npis = set(npi_county.keys())
    print(f"Total OK NPIs with county: {len(ok_npis)}")

    # === Load insurer NPI lists ===

    # BCBS OK
    with open("data/processed/commercial_insurance_npis.json") as f:
        bcbs_data = json.load(f)
    bcbs_npis = set(bcbs_data["bcbs"]["npis"])
    bcbs_ok = bcbs_npis & ok_npis
    print(f"BCBS OK: {len(bcbs_npis)} total, {len(bcbs_ok)} in OK")

    # Cigna (national → filter to OK)
    with open("data/processed/cigna_npis.json") as f:
        cigna_all = set(json.load(f))
    cigna_ok = cigna_all & ok_npis
    print(f"Cigna: {len(cigna_all)} total, {len(cigna_ok)} in OK")

    # Aetna (national → filter to OK)
    with open("data/processed/aetna_npis.json") as f:
        aetna_all = set(json.load(f))
    aetna_ok = aetna_all & ok_npis
    print(f"Aetna: {len(aetna_all)} total, {len(aetna_ok)} in OK")

    # Centene (already OK-only)
    with open("data/processed/centene_providers.json") as f:
        centene_data = json.load(f)
    centene_npis = {p["npi"] for p in centene_data}
    centene_ok = centene_npis & ok_npis
    print(f"Centene: {len(centene_npis)} total, {len(centene_ok)} in OK with county")

    # Humana
    with open("data/processed/humana_providers.json") as f:
        humana_data = json.load(f)
    humana_npis = {p["npi"] for p in humana_data}
    humana_ok = humana_npis & ok_npis
    print(f"Humana: {len(humana_npis)} total, {len(humana_ok)} in OK")

    # UHC
    with open("data/raw/uhc_provider_npis.json") as f:
        uhc_data = json.load(f)
    uhc_npis = set(uhc_data.keys())
    uhc_ok = uhc_npis & ok_npis
    print(f"UHC: {len(uhc_npis)} total, {len(uhc_ok)} in OK")

    # === Count per county ===
    print("\nCounting providers per county...")

    insurers = {
        "bcbs": ("BCBS", bcbs_ok),
        "cigna": ("Cigna", cigna_ok),
        "aetna": ("Aetna", aetna_ok),
        "centene": ("Centene", centene_ok),
        "humana": ("Humana", humana_ok),
        "uhc": ("UHC", uhc_ok),
    }

    county_counts = {}  # county → {insurer_key: count}
    for key, (label, npi_set) in insurers.items():
        counts, matched = count_by_county(npi_set, npi_county)
        print(f"  {label}: {matched} NPIs across {len(counts)} counties")
        for county, count in counts.items():
            if county not in county_counts:
                county_counts[county] = {}
            county_counts[county][key] = count

    # Also count total providers per county
    all_insurance_npis = bcbs_ok | cigna_ok | aetna_ok | centene_ok | humana_ok | uhc_ok
    any_counts, _ = count_by_county(all_insurance_npis, npi_county)
    total_counts, _ = count_by_county(ok_npis, npi_county)

    # === Merge into counties geojson ===
    print("\nMerging into ok_counties.geojson...")
    for feat in counties_gj["features"]:
        name = feat["properties"]["NAME"]
        cc = county_counts.get(name, {})
        p = feat["properties"]

        # Per-insurer counts
        p["ins_bcbs"] = cc.get("bcbs", 0)
        p["ins_cigna"] = cc.get("cigna", 0)
        p["ins_aetna"] = cc.get("aetna", 0)
        p["ins_centene"] = cc.get("centene", 0)
        p["ins_humana"] = cc.get("humana", 0)
        p["ins_uhc"] = cc.get("uhc", 0)

        # Aggregate
        p["ins_any_commercial"] = len(
            {npi for npi in (bcbs_ok | cigna_ok | aetna_ok) if npi_county.get(npi) == name}
        )
        p["ins_any_medicaid"] = len(
            {npi for npi in (centene_ok | humana_ok | uhc_ok) if npi_county.get(npi) == name}
        )
        p["ins_total_providers"] = total_counts.get(name, 0)

    with open("data/processed/ok_counties.geojson", "w") as f:
        json.dump(counties_gj, f)
    print("Wrote data/processed/ok_counties.geojson")

    # Summary table
    print("\n" + "=" * 70)
    print(f"{'County':<18} {'Total':>6} {'BCBS':>6} {'Cigna':>6} {'Aetna':>6} {'Cent':>6} {'Hum':>5} {'UHC':>5}")
    print("-" * 70)
    for feat in sorted(counties_gj["features"], key=lambda f: -f["properties"].get("ins_total_providers", 0))[:10]:
        p = feat["properties"]
        print(f"{p['NAME']:<18} {p['ins_total_providers']:>6} {p['ins_bcbs']:>6} {p['ins_cigna']:>6} {p['ins_aetna']:>6} {p['ins_centene']:>6} {p['ins_humana']:>5} {p['ins_uhc']:>5}")


if __name__ == "__main__":
    main()
