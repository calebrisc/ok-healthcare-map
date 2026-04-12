"""
Fix provider data:
1. Rebuild categories using full NUCC taxonomy (883 codes vs ~30)
2. Filter out deactivated NPIs
3. Aggregate by address into facility-level view
"""

import os
import csv
import json

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
OK_CSV = os.path.join(RAW_DIR, "nppes_oklahoma.csv")
TAXONOMY_CSV = os.path.join(RAW_DIR, "nucc_taxonomy.csv")


def load_taxonomy_map():
    """Build a complete taxonomy code → category mapping from NUCC CSV."""
    taxonomy = {}
    with open(TAXONOMY_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["Code"].strip()
            grouping = row.get("Grouping", "").strip()
            classification = row.get("Classification", "").strip()
            specialization = row.get("Specialization", "").strip()
            display = row.get("Display Name", "").strip()

            # Build a useful category from the NUCC fields
            category = map_to_category(grouping, classification, specialization, display)
            taxonomy[code] = {
                "category": category,
                "display": display or classification,
                "grouping": grouping,
                "classification": classification,
                "specialization": specialization,
            }

    print(f"  Loaded {len(taxonomy)} taxonomy codes")
    return taxonomy


def map_to_category(grouping, classification, specialization, display):
    """Map NUCC grouping/classification into our map pin categories."""
    g = grouping.lower()
    c = classification.lower()
    s = specialization.lower()
    d = display.lower()

    # Primary Care
    if any(x in c for x in ["family medicine", "family practice", "general practice"]):
        return "Primary Care (Family Medicine)"
    if c == "internal medicine" and not s:
        return "Primary Care (Internal Medicine)"
    if "pediatric" in c and "sub" not in c and not s:
        return "Primary Care (Pediatrics)"
    if "obstetrics" in c or "gynecolog" in c:
        return "OB/GYN"

    # NP / PA / Midlevel
    if "nurse practitioner" in c or "nurse practitioner" in d:
        return "NP (Nurse Practitioner)"
    if "physician assistant" in c or "physician assistant" in d:
        return "PA (Physician Assistant)"
    if "midwife" in c:
        return "Midwife"
    if "nurse" in c and "anesthetist" in c:
        return "Nurse Anesthetist (CRNA)"
    if "nurse" in c and ("specialist" in c or "clinical" in c):
        return "Clinical Nurse Specialist"

    # Behavioral Health
    if any(x in c for x in ["psycholog", "counselor", "social worker", "marriage",
                             "behavioral", "psychiatr", "neuropsych"]):
        return "Behavioral Health"
    if "substance" in c or "addiction" in c:
        return "Behavioral Health (Substance Abuse)"
    if "mental health" in c:
        return "Behavioral Health"

    # Dental
    if "dental" in g or "dentist" in c or "dental" in c:
        return "Dental"

    # Pharmacy
    if "pharmacy" in c or "pharmac" in g:
        return "Pharmacy"

    # Hospitals
    if "hospital" in c:
        if "psychiatric" in s or "psychiatric" in c:
            return "Behavioral Health Facility"
        if "critical access" in s or "critical access" in c:
            return "Critical Access Hospital"
        if "rehabilitation" in s:
            return "Rehabilitation Hospital"
        return "Hospital"

    # Clinics
    if "clinic" in c or "clinic" in g:
        if "rural health" in c or "rural health" in s:
            return "Rural Health Clinic"
        if "federally qualified" in c or "fqhc" in d.lower():
            return "FQHC"
        if "urgent care" in s or "urgent care" in c:
            return "Urgent Care"
        if "community health" in s:
            return "Community Health Center"
        return "Clinic/Center"

    # Other facilities
    if "nursing" in c and "facility" in c:
        return "Nursing Facility"
    if "home health" in c:
        return "Home Health"
    if "hospice" in c:
        return "Hospice"
    if "laboratory" in c or "lab" in c:
        return "Laboratory"
    if "ambulance" in c or "ems" in c:
        return "EMS/Ambulance"
    if "radiology" in c or "radiolog" in c:
        return "Radiology"
    if "emergency" in c:
        return "Emergency Medicine"

    # Physicians (specialists)
    if "allopathic" in g or "osteopathic" in g:
        if specialization:
            return f"Physician ({classification})"
        return f"Physician ({classification})"

    # Other clinical
    if "chiropract" in c or "chiropract" in g:
        return "Chiropractic"
    if "optometr" in c or "optometr" in g:
        return "Optometry"
    if "podiatr" in c or "podiatr" in g:
        return "Podiatry"
    if "dietitian" in c or "nutrition" in c:
        return "Dietitian/Nutritionist"
    if "occupational therap" in c:
        return "Occupational Therapy"
    if "physical therap" in c:
        return "Physical Therapy"
    if "speech" in c:
        return "Speech-Language Pathology"
    if "respiratory" in c:
        return "Respiratory Therapy"
    if "acupunctur" in c:
        return "Acupuncture"

    # Suppliers / DME
    if "supplier" in g or "durable medical" in c:
        return "DME Supplier"

    # Groups
    if "group" in g or "group" in c:
        return "Group Practice"

    # Transportation
    if "transport" in c:
        return "Medical Transport"

    # Case managers, coordinators, peer specialists → care coordination
    if any(x in c for x in ["case manager", "care coordinator", "peer specialist",
                             "community health worker", "doula"]):
        return "Care Coordination"

    # Behavior technicians and analysts → behavioral health
    if any(x in c for x in ["behavior technician", "behavior analyst",
                             "applied behavior"]):
        return "Behavioral Health"

    # Students → skip
    if "student" in c:
        return "_STUDENT"

    # Catch remaining by grouping
    if "nursing" in g:
        return "Nursing"
    if "technolog" in g or "technic" in g:
        return "Technologist/Technician"
    if "agency" in c:
        return "Agency"

    return f"Other ({classification})" if classification else "Other"


# Map our detailed categories into pin layer groups
PIN_LAYER_MAP = {
    "primary_care": [
        "Primary Care (Family Medicine)", "Primary Care (Internal Medicine)",
        "Primary Care (General Practice)", "Primary Care (Pediatrics)", "OB/GYN",
    ],
    "np_pa": [
        "NP (Nurse Practitioner)", "PA (Physician Assistant)", "Midwife",
        "Nurse Anesthetist (CRNA)", "Clinical Nurse Specialist",
    ],
    "hospitals": [
        "Hospital", "Critical Access Hospital", "Rehabilitation Hospital",
        "FQHC", "Rural Health Clinic", "Urgent Care", "Community Health Center",
        "Clinic/Center", "Emergency Medicine",
    ],
    "behavioral": [
        "Behavioral Health", "Behavioral Health (Substance Abuse)",
        "Behavioral Health Facility",
    ],
    "dental": ["Dental"],
    "pharmacy": ["Pharmacy"],
    "specialists": [],  # Catches all "Physician (...)" patterns
    "therapy": [
        "Physical Therapy", "Occupational Therapy", "Speech-Language Pathology",
        "Respiratory Therapy", "Chiropractic",
    ],
    "facilities": [
        "Nursing Facility", "Home Health", "Hospice", "Laboratory",
        "EMS/Ambulance", "Radiology", "Nursing",
    ],
    "other": [
        "DME Supplier", "Group Practice", "Medical Transport",
        "Dietitian/Nutritionist", "Acupuncture", "Optometry", "Podiatry",
        "Technologist/Technician", "Agency", "Care Coordination",
    ],
}


def get_pin_layer(category):
    for layer, cats in PIN_LAYER_MAP.items():
        if category in cats:
            return layer
    if category.startswith("Physician ("):
        return "specialists"
    if category.startswith("Other ("):
        return "other"
    return "other"


def rebuild_providers():
    """Rebuild provider GeoJSON with full taxonomy and deactivation filtering."""
    taxonomy = load_taxonomy_map()

    # Load geocode cache
    cache_path = os.path.join(RAW_DIR, "geocode_cache.json")
    with open(cache_path) as f:
        geocode_cache = json.load(f)
    print(f"  Geocode cache: {len(geocode_cache):,} entries")

    print("\nProcessing Oklahoma providers...")
    layers = {name: [] for name in PIN_LAYER_MAP}
    total = 0
    deactivated = 0
    no_address = 0
    no_geocode = 0
    category_counts = {}

    with open(OK_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1

            # Filter deactivated
            deact_date = (row.get("NPI Deactivation Date", "") or "").strip()
            if deact_date:
                deactivated += 1
                continue

            # Get address
            addr = (row.get("Provider First Line Business Practice Location Address", "") or "").strip()
            city = (row.get("Provider Business Practice Location Address City Name", "") or "").strip()
            state = (row.get("Provider Business Practice Location Address State Name", "") or "").strip()
            zip_code = (row.get("Provider Business Practice Location Address Postal Code", "") or "").strip()[:5]
            phone = (row.get("Provider Business Practice Location Address Telephone Number", "") or "").strip()

            if not addr or not city:
                no_address += 1
                continue

            # Geocode lookup
            cache_key = f"{addr}|{city}|{state}|{zip_code}"
            coords = geocode_cache.get(cache_key)
            if not coords:
                no_geocode += 1
                continue

            # Get taxonomy and category
            tax_code = (row.get("Healthcare Provider Taxonomy Code_1", "") or "").strip()
            tax_info = taxonomy.get(tax_code)
            if tax_info:
                category = tax_info["category"]
                display_name = tax_info["display"]
            else:
                category = "Other"
                display_name = ""

            # Skip students
            if category == "_STUDENT":
                continue

            category_counts[category] = category_counts.get(category, 0) + 1

            # Build name
            org_name = (row.get("Provider Organization Name (Legal Business Name)", "") or "").strip()
            last = (row.get("Provider Last Name (Legal Name)", "") or "").strip()
            first = (row.get("Provider First Name", "") or "").strip()
            name = org_name if org_name else f"{last}, {first}".strip(", ")

            npi = (row.get("NPI", "") or "").strip()
            entity_type = (row.get("Entity Type Code", "") or "").strip()

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [coords[1], coords[0]],
                },
                "properties": {
                    "npi": npi,
                    "name": name,
                    "category": category,
                    "specialty": display_name,
                    "address": addr,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "phone": phone,
                    "entity": "Organization" if entity_type == "2" else "Individual",
                },
            }

            pin_layer = get_pin_layer(category)
            layers[pin_layer].append(feature)

    print(f"\n  Total rows: {total:,}")
    print(f"  Deactivated (filtered): {deactivated:,}")
    print(f"  No address: {no_address:,}")
    print(f"  No geocode: {no_geocode:,}")
    print(f"  Final providers: {sum(len(v) for v in layers.values()):,}")

    print(f"\n  Category breakdown (top 30):")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1])[:30]:
        print(f"    {cat}: {count:,}")

    # Count "Other" categories
    other_count = sum(v for k, v in category_counts.items() if k.startswith("Other"))
    print(f"\n  Remaining 'Other': {other_count:,}")

    # Save each layer
    print("\n  Saving layers:")
    for name, features in layers.items():
        if not features:
            print(f"    {name}: 0 (skipping)")
            continue
        out_path = os.path.join(OUT_DIR, f"ok_providers_{name}.geojson")
        geojson = {"type": "FeatureCollection", "features": features}
        with open(out_path, "w") as f:
            json.dump(geojson, f)
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"    {name}: {len(features):,} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    rebuild_providers()
