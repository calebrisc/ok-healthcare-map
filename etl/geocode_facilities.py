"""
Geocode CMS hospitals and HRSA FQHCs using Census batch geocoder.
"""

import os
import csv
import json
import io
import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def geocode_batch(rows):
    """rows: list of (id, address, city, state, zip)"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)

    r = requests.post(
        CENSUS_URL,
        files={"addressFile": ("addr.csv", buf.getvalue(), "text/csv")},
        data={"benchmark": "Public_AR_Current", "returntype": "locations"},
        timeout=300,
    )
    r.raise_for_status()

    results = {}
    for line in r.text.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip('"').split('","')
        if len(parts) >= 6:
            row_id = parts[0].strip('"')
            match = parts[2].strip('"') if len(parts) > 2 else ""
            if match in ("Match", "Exact"):
                coords = parts[5].strip('"')
                if "," in coords:
                    lon, lat = coords.split(",")
                    try:
                        results[row_id] = (float(lat), float(lon))
                    except ValueError:
                        pass
    return results


def geocode_cms_hospitals():
    """Rebuild CMS hospitals with geocoded coordinates."""
    print("=== CMS Hospitals ===")
    url = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"

    all_results = []
    offset = 0
    while True:
        params = {
            "conditions[0][property]": "state",
            "conditions[0][value]": "OK",
            "conditions[0][operator]": "=",
            "limit": 500,
            "offset": offset,
        }
        r = requests.get(url, params=params, timeout=30)
        data = r.json()
        batch = data.get("results", [])
        if not batch:
            break
        all_results.extend(batch)
        offset += len(batch)
        if len(batch) < 500:
            break

    print(f"  Fetched {len(all_results)} hospitals from CMS API")

    # Build geocode batch
    batch = []
    for i, h in enumerate(all_results):
        addr = h.get("address", "")
        city = h.get("citytown", h.get("city", ""))
        state = h.get("state", "OK")
        zip_code = str(h.get("zip_code", ""))[:5]
        batch.append((str(i), addr, city, state, zip_code))

    print(f"  Geocoding {len(batch)} addresses...")
    coords = geocode_batch(batch)
    print(f"  Matched: {len(coords)}")

    # Build GeoJSON
    features = []
    for i, h in enumerate(all_results):
        coord = coords.get(str(i))
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [coord[1], coord[0]],
            } if coord else None,
            "properties": {
                "name": h.get("facility_name", ""),
                "address": h.get("address", ""),
                "city": h.get("citytown", ""),
                "state": "OK",
                "zip": str(h.get("zip_code", ""))[:5],
                "phone": h.get("telephone_number", ""),
                "hospital_type": h.get("hospital_type", ""),
                "ownership": h.get("hospital_ownership", ""),
                "rating": h.get("hospital_overall_rating", ""),
                "emergency_services": h.get("emergency_services", ""),
                "source": "CMS",
            },
        }
        if feature["geometry"]:
            features.append(feature)

    out = os.path.join(OUT_DIR, "ok_hospitals_cms.geojson")
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    print(f"  Saved: {len(features)} hospitals to {out}")

    from collections import Counter
    types = Counter(f["properties"]["hospital_type"] for f in features)
    for t, c in types.most_common():
        print(f"    {t}: {c}")


def geocode_fqhcs():
    """Rebuild FQHCs with geocoded coordinates."""
    print("\n=== FQHCs ===")
    csv_path = os.path.join(RAW_DIR, "hrsa_health_centers.csv")

    sites = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = (row.get("Site State Abbreviation", "") or "").strip()
            if state.upper() != "OK":
                continue
            sites.append(row)

    print(f"  Oklahoma FQHC sites: {len(sites)}")

    # Build geocode batch
    batch = []
    for i, s in enumerate(sites):
        addr = (s.get("Site Address", "") or "").strip()
        city = (s.get("Site City", "") or "").strip()
        zip_code = (s.get("Site Postal Code", "") or "").strip()[:5]
        batch.append((str(i), addr, city, "OK", zip_code))

    print(f"  Geocoding {len(batch)} addresses...")
    coords = geocode_batch(batch)
    print(f"  Matched: {len(coords)}")

    features = []
    for i, s in enumerate(sites):
        coord = coords.get(str(i))
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [coord[1], coord[0]],
            } if coord else None,
            "properties": {
                "name": (s.get("Site Name", "") or "").strip(),
                "address": (s.get("Site Address", "") or "").strip(),
                "city": (s.get("Site City", "") or "").strip(),
                "state": "OK",
                "zip": (s.get("Site Postal Code", "") or "").strip()[:5],
                "phone": (s.get("Site Telephone Number", "") or "").strip(),
                "type": "FQHC",
                "site_type": (s.get("Health Center Service Delivery Site Location Setting Description", "") or "").strip(),
                "center_type": (s.get("Health Center Type", "") or "").strip(),
                "source": "HRSA",
            },
        }
        if feature["geometry"]:
            features.append(feature)

    out = os.path.join(OUT_DIR, "ok_fqhc.geojson")
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    print(f"  Saved: {len(features)} FQHC sites to {out}")


if __name__ == "__main__":
    geocode_cms_hospitals()
    geocode_fqhcs()
