"""
Layer 2I (partial): UnitedHealthcare Provider Directory via public FHIR API
Pulls Oklahoma providers from the UHC/Optum public FHIR R4 endpoint.
Extracts NPIs to flag which providers accept UHC (including Community Plan/Medicaid).
"""

import os
import json
import time
import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

FHIR_BASE = "https://public.fhir.flex.optum.com/R4"
UHC_CACHE = os.path.join(RAW_DIR, "uhc_provider_npis.json")


def fetch_uhc_providers():
    """Page through UHC FHIR PractitionerRole entries for Oklahoma."""
    os.makedirs(RAW_DIR, exist_ok=True)

    if os.path.exists(UHC_CACHE):
        print(f"Already fetched: {UHC_CACHE}")
        with open(UHC_CACHE) as f:
            return json.load(f)

    print("Fetching UHC Oklahoma providers via FHIR API...")
    npis = {}
    url = f"{FHIR_BASE}/PractitionerRole?location.address-state=OK&_count=100&_include=PractitionerRole:practitioner"
    page = 0

    while url:
        page += 1
        try:
            r = requests.get(url, timeout=30, headers={"Accept": "application/fhir+json"})
            r.raise_for_status()
            bundle = r.json()
        except Exception as e:
            print(f"\n  Error on page {page}: {e}")
            break

        entries = bundle.get("entry", [])
        if not entries:
            break

        for entry in entries:
            resource = entry.get("resource", {})
            res_type = resource.get("resourceType", "")

            # NPIs are on Practitioner resources (included via _include)
            if res_type == "Practitioner":
                for ident in resource.get("identifier", []):
                    system = ident.get("system", "")
                    if "npi" in system.lower() or "2.16.840.1.113883.4.6" in system:
                        npi = ident.get("value", "").strip()
                        if npi and npi not in npis:
                            npis[npi] = {
                                "active": resource.get("active", True),
                            }

        print(f"\r  Page {page}: {len(npis):,} unique NPIs", end="", flush=True)

        # Find next page link
        url = None
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                url = link.get("url", "")
                break

        # Rate limit
        time.sleep(0.5)

    print(f"\n\n  Total unique NPIs: {len(npis):,}")

    with open(UHC_CACHE, "w") as f:
        json.dump(npis, f)
    print(f"  Saved to {UHC_CACHE}")

    return npis


def enrich_providers(uhc_npis):
    """Add UHC acceptance flag to provider GeoJSON files."""
    import glob

    provider_files = glob.glob(os.path.join(OUT_DIR, "ok_providers_*.geojson"))
    total_enriched = 0
    total_providers = 0

    for filepath in sorted(provider_files):
        filename = os.path.basename(filepath)
        with open(filepath) as f:
            data = json.load(f)

        enriched = 0
        for feat in data["features"]:
            npi = feat["properties"].get("npi", "")
            total_providers += 1
            if npi in uhc_npis:
                feat["properties"]["accepts_uhc"] = True
                enriched += 1
                total_enriched += 1

        with open(filepath, "w") as f:
            json.dump(data, f)

        print(f"  {filename}: {enriched:,} / {len(data['features']):,} accept UHC")

    print(f"\nTotal: {total_enriched:,} / {total_providers:,} providers accept UHC")


if __name__ == "__main__":
    npis = fetch_uhc_providers()
    enrich_providers(npis)
