"""
Layer 1A: Oklahoma County Boundaries
Source: Census Bureau Cartographic Boundary Files
Downloads county shapefile, filters to Oklahoma (FIPS 40), outputs GeoJSON.
"""

import os
import zipfile
import requests
import geopandas as gpd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
ZIP_PATH = os.path.join(RAW_DIR, "cb_2023_us_county_500k.zip")
OUT_PATH = os.path.join(OUT_DIR, "ok_counties.geojson")

OK_FIPS = "40"


def download():
    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(ZIP_PATH):
        print(f"Already downloaded: {ZIP_PATH}")
        return
    print(f"Downloading county shapefile...")
    r = requests.get(COUNTY_URL, stream=True)
    r.raise_for_status()
    with open(ZIP_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved to {ZIP_PATH}")


def extract_and_convert():
    os.makedirs(OUT_DIR, exist_ok=True)
    extract_dir = os.path.join(RAW_DIR, "counties")
    os.makedirs(extract_dir, exist_ok=True)

    print("Extracting...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(extract_dir)

    shp_file = None
    for f in os.listdir(extract_dir):
        if f.endswith(".shp"):
            shp_file = os.path.join(extract_dir, f)
            break

    if not shp_file:
        raise FileNotFoundError("No .shp file found in extracted archive")

    print("Reading shapefile...")
    gdf = gpd.read_file(shp_file)

    print(f"Total US counties: {len(gdf)}")
    ok = gdf[gdf["STATEFP"] == OK_FIPS].copy()
    print(f"Oklahoma counties: {len(ok)}")

    ok = ok.to_crs(epsg=4326)

    keep_cols = ["GEOID", "NAME", "COUNTYFP", "ALAND", "AWATER", "geometry"]
    ok = ok[[c for c in keep_cols if c in ok.columns]]

    ok.to_file(OUT_PATH, driver="GeoJSON")
    print(f"Saved: {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1024:.0f} KB)")


if __name__ == "__main__":
    download()
    extract_and_convert()
