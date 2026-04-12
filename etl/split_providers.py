"""
Split the large ok_providers.geojson into smaller category-based files
for efficient frontend loading.
"""

import os
import json

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
PROVIDERS_PATH = os.path.join(OUT_DIR, "ok_providers.geojson")

# Group categories into broader pin layers
LAYER_MAP = {
    "primary_care": [
        "Primary Care (Family Medicine)",
        "Primary Care (Internal Medicine)",
        "Primary Care (General Practice)",
        "Primary Care (Pediatrics)",
        "OB/GYN",
    ],
    "np_pa": [
        "NP (Nurse Practitioner)",
        "PA (Physician Assistant)",
        "NP/PA/Midlevel",
        "Advanced Practice Midwife",
    ],
    "specialists": [
        "Physician (Specialist)",
    ],
    "hospitals": [
        "Hospital",
        "Hospital (General Acute Care)",
        "Hospital (Rehabilitation)",
        "Hospital (Special)",
        "Critical Access Hospital",
        "FQHC",
        "Rural Health Clinic",
    ],
    "behavioral": [
        "Behavioral Health",
        "Behavioral Health (Counselor)",
        "Behavioral Health (Psychologist)",
        "Behavioral Health (Social Worker)",
        "Behavioral Health (Substance Abuse)",
    ],
    "dental": [
        "Dental",
    ],
    "pharmacy": [
        "Pharmacy",
    ],
    "facilities": [
        "Nursing Facility",
        "Home Health",
        "Hospice",
        "Facility (Other)",
        "Hospital/Facility",
        "Lab (Clinical)",
        "Lab",
        "Urgent Care",
    ],
    "other": [
        "Other",
    ],
}


def run():
    print("Loading providers...")
    with open(PROVIDERS_PATH) as f:
        data = json.load(f)
    print(f"  Total: {len(data['features']):,}")

    # Build reverse map: category → layer name
    cat_to_layer = {}
    for layer_name, cats in LAYER_MAP.items():
        for cat in cats:
            cat_to_layer[cat] = layer_name

    # Split
    layers = {name: [] for name in LAYER_MAP}
    for feat in data["features"]:
        cat = feat["properties"].get("category", "Other")
        layer_name = cat_to_layer.get(cat, "other")
        layers[layer_name].append(feat)

    # Save each layer
    for name, features in layers.items():
        if not features:
            continue
        out_path = os.path.join(OUT_DIR, f"ok_providers_{name}.geojson")
        geojson = {"type": "FeatureCollection", "features": features}
        with open(out_path, "w") as f:
            json.dump(geojson, f)
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"  {name}: {len(features):,} providers ({size_mb:.1f} MB)")

    # Remove the monolithic file
    os.remove(PROVIDERS_PATH)
    print(f"\n  Removed monolithic file")


if __name__ == "__main__":
    run()
