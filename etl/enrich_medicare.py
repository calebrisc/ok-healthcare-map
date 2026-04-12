"""
Enrich provider GeoJSON files with Medicare acceptance data.
"""

import os
import json
import glob

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
MEDICARE_PATH = os.path.join(RAW_DIR, "medicare_enrollment.json")


def run():
    print("Loading Medicare enrollment data...")
    with open(MEDICARE_PATH) as f:
        medicare = json.load(f)
    print(f"  NPIs with Medicare data: {len(medicare):,}")

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
            if npi in medicare:
                m = medicare[npi]
                feat["properties"]["accepts_medicare"] = m["accepts_medicare"]
                feat["properties"]["medicare_specialty"] = m["specialty"]
                feat["properties"]["credential"] = m["credential"]
                feat["properties"]["telehealth"] = m["telehealth"]
                feat["properties"]["facility_affiliation"] = m["facility"]
                enriched += 1
                total_enriched += 1

        with open(filepath, "w") as f:
            json.dump(data, f)

        print(f"  {filename}: {enriched:,} / {len(data['features']):,} enriched")

    print(f"\nTotal: {total_enriched:,} / {total_providers:,} providers enriched with Medicare data")


if __name__ == "__main__":
    run()
