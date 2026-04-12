"""
Layer 2B: Hospitals & Nursing Facilities from CMS Provider of Services
Source: CMS Provider Data - Hospital General Information
Already has lat/lon, bed counts, ownership type, ratings.
"""

import os
import json
import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

# CMS Hospital General Information API (Socrata)
CMS_HOSPITAL_URL = "https://data.cms.gov/provider-data/api/1/datastore/sql"
OUT_PATH = os.path.join(OUT_DIR, "ok_hospitals_cms.geojson")


def fetch_hospitals():
    """Fetch Oklahoma hospitals from CMS Provider Data API."""
    os.makedirs(OUT_DIR, exist_ok=True)

    # CMS Provider Data uses Socrata-style API
    # Hospital General Information dataset
    url = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
    params = {
        "conditions[0][property]": "state",
        "conditions[0][value]": "OK",
        "conditions[0][operator]": "=",
        "limit": 500,
        "offset": 0,
    }

    print("Fetching Oklahoma hospitals from CMS...")
    r = requests.get(url, params=params, timeout=30)

    if r.status_code != 200:
        print(f"  API returned {r.status_code}, trying alternative approach...")
        return fetch_hospitals_csv()

    data = r.json()
    results = data.get("results", [])
    print(f"  Got {len(results)} hospitals")

    if not results:
        print("  No results from API, trying CSV download...")
        return fetch_hospitals_csv()

    return process_results(results)


def fetch_hospitals_csv():
    """Fallback: download the full CSV from CMS."""
    csv_url = "https://data.cms.gov/provider-data/sites/default/files/resources/092256becd267d9a932f8c47c7d6f4db/Hospital_General_Information.csv"
    csv_path = os.path.join(RAW_DIR, "cms_hospital_general.csv")

    if not os.path.exists(csv_path):
        print("  Downloading Hospital General Information CSV...")
        r = requests.get(csv_url, timeout=60)
        r.raise_for_status()
        with open(csv_path, "wb") as f:
            f.write(r.content)
        print(f"  Saved to {csv_path}")

    import csv as csvmod
    features = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csvmod.DictReader(f)
        print(f"  Columns: {reader.fieldnames[:15]}...")
        for row in reader:
            state = (row.get("State", "") or "").strip()
            if state != "OK":
                continue

            lat = row.get("Location", "")
            lon = ""
            # Try various location field formats
            if not lat:
                lat = row.get("Latitude", "") or row.get("latitude", "")
                lon = row.get("Longitude", "") or row.get("longitude", "")

            # CMS sometimes has "POINT (lon lat)" format
            location = row.get("Location", "") or ""
            if "POINT" in location:
                import re
                m = re.search(r'POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)', location)
                if m:
                    lon, lat = m.group(1), m.group(2)

            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (ValueError, TypeError):
                lat_f = lon_f = None

            name = row.get("Facility Name", "") or row.get("Hospital Name", "")
            addr = row.get("Address", "")
            city = row.get("City", "")
            zip_code = row.get("ZIP Code", "")
            phone = row.get("Phone Number", "")
            hospital_type = row.get("Hospital Type", "")
            ownership = row.get("Hospital Ownership", "")
            rating = row.get("Hospital overall rating", "")
            emergency = row.get("Emergency Services", "")

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon_f, lat_f],
                } if lat_f and lon_f else None,
                "properties": {
                    "name": name,
                    "address": addr,
                    "city": city,
                    "state": "OK",
                    "zip": zip_code,
                    "phone": phone,
                    "hospital_type": hospital_type,
                    "ownership": ownership,
                    "rating": rating,
                    "emergency_services": emergency,
                    "source": "CMS",
                },
            }
            features.append(feature)

    print(f"  Oklahoma hospitals: {len(features)}")
    return features


def process_results(results):
    """Process API JSON results into GeoJSON features."""
    features = []
    for r in results:
        lat = r.get("latitude") or r.get("Latitude")
        lon = r.get("longitude") or r.get("Longitude")

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (ValueError, TypeError):
            lat_f = lon_f = None

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon_f, lat_f],
            } if lat_f and lon_f else None,
            "properties": {
                "name": r.get("facility_name", r.get("Facility Name", "")),
                "address": r.get("address", r.get("Address", "")),
                "city": r.get("city", r.get("City", "")),
                "state": "OK",
                "zip": r.get("zip_code", r.get("ZIP Code", "")),
                "phone": r.get("phone_number", r.get("Phone Number", "")),
                "hospital_type": r.get("hospital_type", r.get("Hospital Type", "")),
                "ownership": r.get("hospital_ownership", r.get("Hospital Ownership", "")),
                "rating": r.get("hospital_overall_rating", r.get("Hospital overall rating", "")),
                "emergency_services": r.get("emergency_services", r.get("Emergency Services", "")),
                "source": "CMS",
            },
        }
        features.append(feature)

    print(f"  Oklahoma hospitals: {len(features)}")
    return features


def save(features):
    # Filter to features with geometry
    with_geo = [f for f in features if f["geometry"] is not None]
    without_geo = len(features) - len(with_geo)
    if without_geo:
        print(f"  {without_geo} hospitals without coordinates (dropped)")

    geojson = {"type": "FeatureCollection", "features": with_geo}
    with open(OUT_PATH, "w") as f:
        json.dump(geojson, f)

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\n  Saved: {OUT_PATH} ({size_kb:.0f} KB)")
    print(f"  Hospitals with coordinates: {len(with_geo)}")

    # Type breakdown
    from collections import Counter
    types = Counter(f["properties"]["hospital_type"] for f in with_geo)
    for t, c in types.most_common():
        print(f"    {t}: {c}")


if __name__ == "__main__":
    features = fetch_hospitals()
    save(features)
