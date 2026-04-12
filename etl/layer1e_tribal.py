"""
Layer 1E: Tribal Jurisdiction / Trust Land Boundaries
Source: Census Bureau TIGER/Line AIANNH shapefiles
Downloads AIANNH shapefile, filters to Oklahoma, outputs GeoJSON.
"""

import os
import zipfile
import requests
import geopandas as gpd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

AIANNH_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_aiannh_500k.zip"
ZIP_PATH = os.path.join(RAW_DIR, "cb_2023_us_aiannh_500k.zip")
OUT_PATH = os.path.join(OUT_DIR, "ok_tribal.geojson")

# Oklahoma bounding box (rough) for spatial filter
OK_BBOX = (-103.1, 33.6, -94.4, 37.1)


def download():
    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(ZIP_PATH):
        print(f"Already downloaded: {ZIP_PATH}")
        return
    print("Downloading AIANNH shapefile...")
    r = requests.get(AIANNH_URL, stream=True)
    r.raise_for_status()
    with open(ZIP_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved to {ZIP_PATH}")


def process():
    os.makedirs(OUT_DIR, exist_ok=True)
    extract_dir = os.path.join(RAW_DIR, "aiannh")
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
        raise FileNotFoundError("No .shp file found")

    print("Reading shapefile...")
    gdf = gpd.read_file(shp_file)
    gdf = gdf.to_crs(epsg=4326)
    print(f"  Total AIANNH areas: {len(gdf)}")
    print(f"  Columns: {list(gdf.columns)}")

    # Filter by STATEFP if available, otherwise spatial filter
    if "STATEFP" in gdf.columns:
        ok = gdf[gdf["STATEFP"] == "40"].copy()
        print(f"  Oklahoma (by STATEFP): {len(ok)}")
    else:
        # Spatial filter: keep areas that intersect Oklahoma bbox
        from shapely.geometry import box
        ok_box = box(*OK_BBOX)
        ok = gdf[gdf.intersects(ok_box)].copy()
        print(f"  Oklahoma (by bbox): {len(ok)}")

    if len(ok) == 0:
        print("  No results from state/bbox filter, trying all...")
        print(f"  Sample names: {gdf['NAME'].head(20).tolist()}")
        # Oklahoma tribal nations often have "Oklahoma" or "OK" in name
        ok = gdf[gdf["NAME"].str.contains("Oklahoma|Okla", case=False, na=False)].copy()
        print(f"  Oklahoma (by name): {len(ok)}")

    print(f"\n  Tribal areas found: {len(ok)}")
    if len(ok) > 0:
        print(f"  Names: {ok['NAME'].tolist()[:20]}")

    keep_cols = ["GEOID", "NAME", "NAMELSAD", "AIANNH", "geometry"]
    ok = ok[[c for c in keep_cols if c in ok.columns]]

    ok.to_file(OUT_PATH, driver="GeoJSON")
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\nSaved: {OUT_PATH} ({size_kb:.0f} KB)")
    print(f"Total tribal areas: {len(ok)}")


if __name__ == "__main__":
    download()
    process()
