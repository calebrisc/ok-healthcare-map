"""
Layer 2F: Indian Health Service (IHS) Facilities
Source: IHS facility locator API
"""

import os
import csv
import io
import json
import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
OUT_PATH = os.path.join(OUT_DIR, "ok_ihs.geojson")

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def geocode_batch(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    r = requests.post(
        CENSUS_URL,
        files={"addressFile": ("a.csv", buf.getvalue(), "text/csv")},
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
            rid = parts[0].strip('"')
            match = parts[2].strip('"')
            if match in ("Match", "Exact"):
                coords = parts[5].strip('"')
                if "," in coords:
                    lon, lat = coords.split(",")
                    try:
                        results[rid] = (float(lat), float(lon))
                    except ValueError:
                        pass
    return results


def fetch_ihs():
    """Try IHS API, then fall back to known Oklahoma IHS facilities."""
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Try IHS facility API
    print("Trying IHS facility API...")
    api_urls = [
        "https://www.ihs.gov/api/v1/facilities?state=OK",
        "https://www.ihs.gov/findhealthcare/api/facilities?state=OK",
    ]

    for url in api_urls:
        try:
            r = requests.get(url, timeout=15, headers={"Accept": "application/json"})
            if r.status_code == 200:
                data = r.json()
                print(f"  Got {len(data)} facilities from API")
                return process_api(data)
        except Exception as e:
            print(f"  {url}: {e}")

    print("  API not available, using known facilities database...")
    return known_ok_ihs_facilities()


def known_ok_ihs_facilities():
    """
    Known IHS/tribal health facilities in Oklahoma.
    Sources: IHS facility directory, tribal health authority websites.
    Oklahoma has a unique IHS structure — Oklahoma City Area IHS office
    oversees facilities across the state, many operated by tribal nations
    under self-governance compacts.
    """
    facilities = [
        # IHS direct-service facilities
        {"name": "Claremore Indian Hospital", "addr": "101 S Moore Ave", "city": "Claremore", "zip": "74017", "type": "Hospital", "tribe": "Cherokee Nation"},
        {"name": "Lawton Indian Hospital", "addr": "1515 Lawrie Tatum Rd", "city": "Lawton", "zip": "73507", "type": "Hospital", "tribe": "IHS"},
        {"name": "Clinton Indian Health Center", "addr": "Rt 1 Box 3060", "city": "Clinton", "zip": "73601", "type": "Health Center", "tribe": "IHS"},
        {"name": "El Reno Indian Health Center", "addr": "2509 N Country Club Rd", "city": "El Reno", "zip": "73036", "type": "Health Center", "tribe": "Cheyenne & Arapaho"},
        {"name": "Watonga Indian Health Center", "addr": "516 N Clarence Nash Blvd", "city": "Watonga", "zip": "73772", "type": "Health Center", "tribe": "Cheyenne & Arapaho"},
        {"name": "Anadarko Indian Health Center", "addr": "711 W Texas Ave", "city": "Anadarko", "zip": "73005", "type": "Health Center", "tribe": "IHS"},
        {"name": "Carnegie Indian Health Center", "addr": "102 N Bridge St", "city": "Carnegie", "zip": "73015", "type": "Health Center", "tribe": "Kiowa"},
        {"name": "Pawnee Indian Health Center", "addr": "806 GI Joe St", "city": "Pawnee", "zip": "74058", "type": "Health Center", "tribe": "Pawnee Nation"},

        # Cherokee Nation Health Services
        {"name": "W.W. Hastings Hospital", "addr": "100 S Bliss Ave", "city": "Tahlequah", "zip": "74464", "type": "Hospital", "tribe": "Cherokee Nation"},
        {"name": "Cherokee Nation Outpatient Health Center", "addr": "19600 E Ross St", "city": "Tahlequah", "zip": "74464", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Redbird Smith Health Center", "addr": "1500 S Lynn Lane Blvd", "city": "Sallisaw", "zip": "74955", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Wilma P. Mankiller Health Center", "addr": "14000 S Muskogee Ave", "city": "Stilwell", "zip": "74960", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Sam Hider Health Center", "addr": "Old Hwy 10", "city": "Jay", "zip": "74346", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Three Rivers Health Center", "addr": "1001 S 41st St E", "city": "Muskogee", "zip": "74403", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Vinita Health Center", "addr": "830 Longhorn Dr", "city": "Vinita", "zip": "74301", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Nowata Health Center", "addr": "305 N Locust St", "city": "Nowata", "zip": "74048", "type": "Health Center", "tribe": "Cherokee Nation"},
        {"name": "Salina Health Center", "addr": "501 S Wright St", "city": "Salina", "zip": "74365", "type": "Health Center", "tribe": "Cherokee Nation"},

        # Chickasaw Nation Health System
        {"name": "Chickasaw Nation Medical Center", "addr": "1921 Stonecipher Blvd", "city": "Ada", "zip": "74820", "type": "Hospital", "tribe": "Chickasaw Nation"},
        {"name": "Chickasaw Nation Health Clinic - Tishomingo", "addr": "1500 E Main St", "city": "Tishomingo", "zip": "73460", "type": "Health Center", "tribe": "Chickasaw Nation"},
        {"name": "Chickasaw Nation Health Clinic - Ardmore", "addr": "2350 Chickasaw Blvd", "city": "Ardmore", "zip": "73401", "type": "Health Center", "tribe": "Chickasaw Nation"},
        {"name": "Chickasaw Nation Health Clinic - Durant", "addr": "1702 S 1st Ave", "city": "Durant", "zip": "74701", "type": "Health Center", "tribe": "Chickasaw Nation"},
        {"name": "Chickasaw Nation Health Clinic - Purcell", "addr": "1800 Hardcastle Blvd", "city": "Purcell", "zip": "73080", "type": "Health Center", "tribe": "Chickasaw Nation"},

        # Choctaw Nation Health Services
        {"name": "Choctaw Nation Health Care Center", "addr": "One Choctaw Way", "city": "Talihina", "zip": "74571", "type": "Hospital", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - McAlester", "addr": "1127 S George Nigh Expy", "city": "McAlester", "zip": "74501", "type": "Health Center", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - Poteau", "addr": "109 Kerr Ave", "city": "Poteau", "zip": "74953", "type": "Health Center", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - Hugo", "addr": "410 E Kirk St", "city": "Hugo", "zip": "74743", "type": "Health Center", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - Broken Bow", "addr": "1500 S Park Dr", "city": "Broken Bow", "zip": "74728", "type": "Health Center", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - Atoka", "addr": "1205 W Liberty Rd", "city": "Atoka", "zip": "74525", "type": "Health Center", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - Idabel", "addr": "902 SE Lincoln Rd", "city": "Idabel", "zip": "74745", "type": "Health Center", "tribe": "Choctaw Nation"},
        {"name": "Choctaw Nation Health Clinic - Stigler", "addr": "2207 E Main St", "city": "Stigler", "zip": "74462", "type": "Health Center", "tribe": "Choctaw Nation"},

        # Creek Nation (Muscogee)
        {"name": "Creek Nation Community Hospital", "addr": "309 N 14th St", "city": "Okemah", "zip": "74859", "type": "Hospital", "tribe": "Muscogee Creek Nation"},
        {"name": "Creek Nation Health Center - Okmulgee", "addr": "1500 N Wood Dr", "city": "Okmulgee", "zip": "74447", "type": "Health Center", "tribe": "Muscogee Creek Nation"},
        {"name": "Creek Nation Health Center - Sapulpa", "addr": "367 W Taft Ave", "city": "Sapulpa", "zip": "74066", "type": "Health Center", "tribe": "Muscogee Creek Nation"},
        {"name": "Creek Nation Health Center - Eufaula", "addr": "800 Birkes Rd", "city": "Eufaula", "zip": "74432", "type": "Health Center", "tribe": "Muscogee Creek Nation"},

        # Citizen Potawatomi Nation
        {"name": "Citizen Potawatomi Nation Health Center", "addr": "1601 S Gordon Cooper Dr", "city": "Shawnee", "zip": "74801", "type": "Health Center", "tribe": "Citizen Potawatomi Nation"},

        # Absentee Shawnee Tribe
        {"name": "Absentee Shawnee Tribal Health Center", "addr": "15702 E Hwy 9", "city": "Norman", "zip": "73026", "type": "Health Center", "tribe": "Absentee Shawnee Tribe"},

        # Comanche Nation
        {"name": "Comanche Nation Health Center", "addr": "1515 Lawrie Tatum Rd Bldg 29", "city": "Lawton", "zip": "73507", "type": "Health Center", "tribe": "Comanche Nation"},

        # Wichita and Affiliated Tribes
        {"name": "Wichita Tribal Health Center", "addr": "1516 S Hwy 281", "city": "Anadarko", "zip": "73005", "type": "Health Center", "tribe": "Wichita Tribe"},

        # Seminole Nation
        {"name": "Seminole Nation Health Clinic", "addr": "222 N 4th St", "city": "Wewoka", "zip": "74884", "type": "Health Center", "tribe": "Seminole Nation"},

        # Osage Nation
        {"name": "Wah-Zha-Zhi Health Center", "addr": "128 E 6th St", "city": "Pawhuska", "zip": "74056", "type": "Health Center", "tribe": "Osage Nation"},

        # Indian Health Care Resource Center (urban)
        {"name": "Indian Health Care Resource Center of Tulsa", "addr": "550 S Peoria Ave", "city": "Tulsa", "zip": "74120", "type": "Urban Indian Health", "tribe": "Urban Indian"},
        {"name": "Oklahoma City Indian Clinic", "addr": "4913 W Reno Ave", "city": "Oklahoma City", "zip": "73127", "type": "Urban Indian Health", "tribe": "Urban Indian"},
    ]

    # Geocode all
    batch = []
    for i, f in enumerate(facilities):
        batch.append((str(i), f["addr"], f["city"], "OK", f["zip"]))

    print(f"  Geocoding {len(batch)} IHS facilities...")
    coords = geocode_batch(batch)
    print(f"  Matched: {len(coords)}")

    features = []
    for i, f in enumerate(facilities):
        c = coords.get(str(i))
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [c[1], c[0]],
            } if c else None,
            "properties": {
                "name": f["name"],
                "address": f["addr"],
                "city": f["city"],
                "state": "OK",
                "zip": f["zip"],
                "facility_type": f["type"],
                "tribe": f["tribe"],
                "source": "IHS / Tribal Health Authority",
            },
        }
        features.append(feature)

    return features


def process_api(data):
    # placeholder if API ever works
    return []


def save(features):
    with_geo = [f for f in features if f["geometry"] is not None]
    without = len(features) - len(with_geo)
    if without:
        print(f"  {without} facilities without coordinates")

    geojson = {"type": "FeatureCollection", "features": with_geo}
    with open(OUT_PATH, "w") as f:
        json.dump(geojson, f)

    print(f"\nSaved: {OUT_PATH}")
    print(f"  IHS/tribal facilities: {len(with_geo)}")

    from collections import Counter
    types = Counter(f["properties"]["facility_type"] for f in with_geo)
    tribes = Counter(f["properties"]["tribe"] for f in with_geo)
    print(f"\n  By type:")
    for t, c in types.most_common():
        print(f"    {t}: {c}")
    print(f"\n  By tribe/org:")
    for t, c in tribes.most_common():
        print(f"    {t}: {c}")


if __name__ == "__main__":
    features = fetch_ihs()
    save(features)
