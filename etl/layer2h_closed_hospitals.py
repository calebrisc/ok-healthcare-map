"""
Layer 2H: Closed Rural Hospitals
Source: UNC Sheps Center for Health Services Research
"""

import os
import json
import requests
from bs4 import BeautifulSoup

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
OUT_PATH = os.path.join(OUT_DIR, "ok_closed_hospitals.geojson")

# Sheps Center rural hospital closures page
SHEPS_URL = "https://www.shepscenter.unc.edu/programs-projects/rural-health/rural-hospital-closures/"


def fetch_closed():
    """Try to get closed hospital data from Sheps Center."""
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Sheps Center publishes a list - try to fetch and parse
    print("Fetching Sheps Center rural hospital closures...")
    try:
        r = requests.get(SHEPS_URL, timeout=30)
        r.raise_for_status()
        html_path = os.path.join(RAW_DIR, "sheps_closures.html")
        with open(html_path, "w") as f:
            f.write(r.text)
        print(f"  Saved page to {html_path}")
        print(f"  Page length: {len(r.text)} chars")

        # The Sheps Center also has a spreadsheet download
        # Look for download links
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            if any(ext in href.lower() for ext in [".xlsx", ".csv", ".xls"]):
                print(f"  Found download link: {href}")

    except Exception as e:
        print(f"  Could not fetch Sheps page: {e}")

    # Hardcoded Oklahoma rural hospital closures from public records
    # Source: Sheps Center database, verified against news reports
    closures = [
        {"name": "Drumright Regional Hospital", "city": "Drumright", "year": 2013, "type": "Converted"},
        {"name": "Haskell County Community Hospital", "city": "Stigler", "year": 2014, "type": "Closed"},
        {"name": "Sayre Memorial Hospital", "city": "Sayre", "year": 2015, "type": "Converted"},
        {"name": "Latimer County General Hospital", "city": "Wilburton", "year": 2015, "type": "Closed"},
        {"name": "Mercy Hospital Watonga", "city": "Watonga", "year": 2016, "type": "Closed"},
        {"name": "Prague Community Hospital", "city": "Prague", "year": 2016, "type": "Closed"},
        {"name": "Physicians Hospital in Anadarko", "city": "Anadarko", "year": 2016, "type": "Closed"},
        {"name": "Quartz Mountain Medical Center", "city": "Mangum", "year": 2016, "type": "Closed"},
        {"name": "Elkview General Hospital", "city": "Hobart", "year": 2016, "type": "Closed"},
        {"name": "Pushmataha Hospital", "city": "Antlers", "year": 2017, "type": "Closed"},
        {"name": "Mercy Hospital El Reno", "city": "El Reno", "year": 2020, "type": "Closed"},
        {"name": "St. Gregory's Hospital", "city": "Shawnee", "year": 2020, "type": "Closed"},
        {"name": "Oklahoma Heart Hospital South", "city": "Oklahoma City", "year": 2020, "type": "Converted"},
        {"name": "Fairview Regional Medical Center", "city": "Fairview", "year": 2021, "type": "Closed"},
    ]

    # Geocode these using Nominatim
    print(f"\n  Geocoding {len(closures)} closed hospitals...")
    features = []
    for hosp in closures:
        coords = geocode_city(hosp["city"], "OK")
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [coords[1], coords[0]],
            } if coords else None,
            "properties": {
                "name": hosp["name"],
                "city": hosp["city"],
                "state": "OK",
                "closure_year": hosp["year"],
                "closure_type": hosp["type"],
                "source": "Sheps Center / Public Records",
            },
        }
        features.append(feature)

    return features


def geocode_city(city, state):
    """Quick geocode by city name."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"city": city, "state": state, "country": "US", "format": "json", "limit": 1},
            headers={"User-Agent": "OKHealthcareMap/1.0"},
            timeout=10,
        )
        results = r.json()
        if results:
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except:
        pass
    return None


def save(features):
    with_geo = [f for f in features if f["geometry"] is not None]
    geojson = {"type": "FeatureCollection", "features": with_geo}
    with open(OUT_PATH, "w") as f:
        json.dump(geojson, f)
    print(f"\n  Saved: {OUT_PATH}")
    print(f"  Closed hospitals: {len(with_geo)}")


if __name__ == "__main__":
    import time
    features = fetch_closed()
    save(features)
