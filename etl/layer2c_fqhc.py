"""
Layer 2C: FQHCs (Federally Qualified Health Centers)
Source: HRSA Health Center Program data
Already geocoded, includes services and patient counts.
"""

import os
import json
import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
OUT_PATH = os.path.join(OUT_DIR, "ok_fqhc.geojson")

# HRSA Health Center Service Delivery Sites API
HRSA_URL = "https://data.hrsa.gov/data/download"


def fetch_fqhc():
    """Fetch FQHCs from HRSA API."""
    os.makedirs(OUT_DIR, exist_ok=True)

    # HRSA has a direct API for health center sites
    api_url = "https://data.hrsa.gov/api/listSites"
    params = {"state": "OK"}

    print("Fetching FQHCs from HRSA API...")
    try:
        r = requests.get(api_url, params=params, timeout=30)
        if r.status_code == 200:
            data = r.json()
            print(f"  Got {len(data)} sites from API")
            return process_api(data)
    except Exception as e:
        print(f"  API failed: {e}")

    # Fallback: try the health center locator
    print("  Trying Health Center Site CSV...")
    return fetch_fqhc_csv()


def fetch_fqhc_csv():
    """Download HRSA health center site data."""
    # HRSA publishes site-level data
    csv_url = "https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv"
    csv_path = os.path.join(RAW_DIR, "hrsa_health_centers.csv")

    if not os.path.exists(csv_path):
        print("  Downloading HRSA Health Center Sites CSV...")
        r = requests.get(csv_url, timeout=60)
        r.raise_for_status()
        with open(csv_path, "wb") as f:
            f.write(r.content)
        print(f"  Saved to {csv_path}")

    import csv as csvmod
    features = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csvmod.DictReader(f)
        cols = reader.fieldnames
        print(f"  Columns: {cols[:15]}...")

        for row in reader:
            # Find state column
            state = ""
            for col in cols:
                if "state" in col.lower() and "abbr" in col.lower():
                    state = (row.get(col, "") or "").strip()
                    break
            if not state:
                for col in cols:
                    if col.lower() in ["state", "site state"]:
                        state = (row.get(col, "") or "").strip()
                        break
            if not state:
                state = (row.get("Site State Abbreviation", "") or row.get("State", "") or "").strip()

            if state.upper() != "OK":
                continue

            # Get coordinates
            lat = lon = None
            for col in cols:
                cl = col.lower()
                if "latitude" in cl or "lat" == cl:
                    try:
                        lat = float(row.get(col, ""))
                    except:
                        pass
                elif "longitude" in cl or "lon" == cl or "long" == cl:
                    try:
                        lon = float(row.get(col, ""))
                    except:
                        pass

            # Get site info
            name = ""
            for col in cols:
                if "site name" in col.lower():
                    name = (row.get(col, "") or "").strip()
                    break
            if not name:
                name = (row.get("Site Name", "") or row.get("Health Center Name", "") or "").strip()

            addr = ""
            for col in cols:
                if "address" in col.lower() and ("site" in col.lower() or "street" in col.lower()):
                    addr = (row.get(col, "") or "").strip()
                    break
            if not addr:
                addr = (row.get("Site Address", "") or row.get("Address", "") or "").strip()

            city = ""
            for col in cols:
                if "city" in col.lower() and "site" in col.lower():
                    city = (row.get(col, "") or "").strip()
                    break
            if not city:
                city = (row.get("Site City", "") or row.get("City", "") or "").strip()

            zip_code = ""
            for col in cols:
                if "zip" in col.lower():
                    zip_code = (row.get(col, "") or "").strip()[:5]
                    break

            phone = ""
            for col in cols:
                if "phone" in col.lower() or "telephone" in col.lower():
                    phone = (row.get(col, "") or "").strip()
                    break

            site_type = ""
            for col in cols:
                if "site type" in col.lower() or "setting" in col.lower():
                    site_type = (row.get(col, "") or "").strip()
                    break

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                } if lat and lon else None,
                "properties": {
                    "name": name,
                    "address": addr,
                    "city": city,
                    "state": "OK",
                    "zip": zip_code,
                    "phone": phone,
                    "type": "FQHC",
                    "site_type": site_type,
                    "source": "HRSA",
                },
            }
            features.append(feature)

    print(f"  Oklahoma FQHCs/sites: {len(features)}")
    return features


def process_api(data):
    """Process HRSA API JSON."""
    features = []
    for site in data:
        lat = site.get("Latitude") or site.get("latitude")
        lon = site.get("Longitude") or site.get("longitude")
        try:
            lat = float(lat)
            lon = float(lon)
        except:
            lat = lon = None

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            } if lat and lon else None,
            "properties": {
                "name": site.get("Site Name", site.get("siteName", "")),
                "address": site.get("Address", site.get("address", "")),
                "city": site.get("City", site.get("city", "")),
                "state": "OK",
                "zip": str(site.get("Zip", site.get("zip", "")))[:5],
                "phone": site.get("Phone", site.get("phone", "")),
                "type": "FQHC",
                "source": "HRSA",
            },
        }
        features.append(feature)

    return features


def save(features):
    with_geo = [f for f in features if f["geometry"] is not None]
    without = len(features) - len(with_geo)
    if without:
        print(f"  {without} sites without coordinates")

    geojson = {"type": "FeatureCollection", "features": with_geo}
    with open(OUT_PATH, "w") as f:
        json.dump(geojson, f)

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\n  Saved: {OUT_PATH} ({size_kb:.0f} KB)")
    print(f"  FQHC sites with coordinates: {len(with_geo)}")


if __name__ == "__main__":
    features = fetch_fqhc()
    save(features)
