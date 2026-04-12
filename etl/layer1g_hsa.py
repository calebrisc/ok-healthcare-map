"""
Layer 1G: Hospital Service Areas (HSA)
Source: Dartmouth Atlas of Health Care
Downloads HSA boundary shapefile, filters to Oklahoma, outputs GeoJSON.
"""

import os
import zipfile
import requests
import geopandas as gpd
from shapely.geometry import box

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

HSA_URL = "https://data.dartmouthatlas.org/downloads/geography/HSA_Bdry__AK_HI_unmodified.zip"
ZIP_PATH = os.path.join(RAW_DIR, "hsa_boundary.zip")
OUT_PATH = os.path.join(OUT_DIR, "ok_hsa.geojson")

OK_BBOX = box(-103.1, 33.6, -94.4, 37.1)


def download():
    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(ZIP_PATH):
        print(f"Already downloaded: {ZIP_PATH}")
        return
    print("Downloading HSA boundaries...")
    r = requests.get(HSA_URL, stream=True)
    r.raise_for_status()
    with open(ZIP_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved to {ZIP_PATH}")


def process():
    os.makedirs(OUT_DIR, exist_ok=True)
    extract_dir = os.path.join(RAW_DIR, "hsa")
    os.makedirs(extract_dir, exist_ok=True)

    print("Extracting...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(extract_dir)

    shp_file = None
    for root, dirs, files in os.walk(extract_dir):
        if "__MACOSX" in root:
            continue
        for f in files:
            if f.endswith(".shp") and not f.startswith("._"):
                shp_file = os.path.join(root, f)
                break
        if shp_file:
            break

    if not shp_file:
        raise FileNotFoundError("No .shp file found")

    print(f"Reading {shp_file}...")
    gdf = gpd.read_file(shp_file)
    gdf = gdf.to_crs(epsg=4326)
    print(f"  Total HSAs: {len(gdf)}")
    print(f"  Columns: {list(gdf.columns)}")

    # Filter to Oklahoma area
    if "HSASTATE" in gdf.columns:
        ok = gdf[gdf["HSASTATE"] == "OK"].copy()
        print(f"  Oklahoma HSAs (by state): {len(ok)}")
    else:
        ok = gdf[gdf.intersects(OK_BBOX)].copy()
        print(f"  Oklahoma HSAs (by bbox): {len(ok)}")

    if len(ok) > 0:
        print(f"  Sample columns: {ok.iloc[0].to_dict()}")

    ok.to_file(OUT_PATH, driver="GeoJSON")
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\nSaved: {OUT_PATH} ({size_kb:.0f} KB)")
    print(f"Total HSAs: {len(ok)}")


if __name__ == "__main__":
    download()
    process()
