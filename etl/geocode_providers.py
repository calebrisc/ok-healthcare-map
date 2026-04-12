"""
Geocode Oklahoma NPI providers using Census Bureau batch geocoder.
Deduplicates addresses first, geocodes unique ones, then joins back.
Census batch API: max 10,000 per request.
"""

import os
import csv
import json
import time
import requests
import io

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
PROVIDERS_PATH = os.path.join(OUT_DIR, "ok_providers.geojson")
GEOCODE_CACHE = os.path.join(RAW_DIR, "geocode_cache.json")
OUT_PATH = os.path.join(OUT_DIR, "ok_providers.geojson")

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 9000  # Stay under 10k limit


def load_providers():
    print("Loading providers...")
    with open(PROVIDERS_PATH) as f:
        data = json.load(f)
    print(f"  Total providers: {len(data['features']):,}")
    return data


def extract_unique_addresses(data):
    """Get unique address strings for geocoding."""
    addresses = {}
    for feat in data["features"]:
        p = feat["properties"]
        addr = p.get("address", "").strip()
        city = p.get("city", "").strip()
        state = p.get("state", "OK")
        zip_code = p.get("zip", "").strip()

        if not addr or not city:
            continue

        key = f"{addr}|{city}|{state}|{zip_code}"
        if key not in addresses:
            addresses[key] = {
                "address": addr,
                "city": city,
                "state": state,
                "zip": zip_code,
            }

    print(f"  Unique addresses: {len(addresses):,}")
    return addresses


def load_cache():
    if os.path.exists(GEOCODE_CACHE):
        with open(GEOCODE_CACHE) as f:
            cache = json.load(f)
        print(f"  Loaded geocode cache: {len(cache):,} entries")
        return cache
    return {}


def save_cache(cache):
    with open(GEOCODE_CACHE, "w") as f:
        json.dump(cache, f)


def geocode_batch(batch):
    """
    Send a batch of addresses to Census geocoder.
    batch: list of (id, address, city, state, zip) tuples
    Returns dict of {id: (lat, lon)} for matched addresses.
    """
    # Build CSV for upload
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    for row in batch:
        writer.writerow(row)
    csv_content = csv_buffer.getvalue()

    try:
        r = requests.post(
            CENSUS_GEOCODER_URL,
            files={"addressFile": ("addresses.csv", csv_content, "text/csv")},
            data={"benchmark": "Public_AR_Current", "returntype": "locations"},
            timeout=300,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"\n  ERROR in batch geocode: {e}")
        return {}

    results = {}
    for line in r.text.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip('"').split('","')
        if len(parts) >= 6:
            row_id = parts[0].strip('"')
            match_type = parts[2].strip('"') if len(parts) > 2 else ""
            if match_type in ("Match", "Exact"):
                # Coordinates are in format: lon,lat
                coords = parts[5].strip('"') if len(parts) > 5 else ""
                if "," in coords:
                    lon, lat = coords.split(",")
                    try:
                        results[row_id] = (float(lat), float(lon))
                    except ValueError:
                        pass

    return results


def geocode_all(addresses):
    """Geocode all unique addresses using Census batch API with caching."""
    cache = load_cache()

    # Filter to uncached addresses
    to_geocode = {}
    for key, info in addresses.items():
        if key not in cache:
            to_geocode[key] = info

    print(f"  Already cached: {len(addresses) - len(to_geocode):,}")
    print(f"  Need geocoding: {len(to_geocode):,}")

    if not to_geocode:
        return cache

    # Process in batches
    keys = list(to_geocode.keys())
    total_batches = (len(keys) + BATCH_SIZE - 1) // BATCH_SIZE
    matched = 0

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(keys))
        batch_keys = keys[start:end]

        # Build batch
        batch = []
        for i, key in enumerate(batch_keys):
            info = to_geocode[key]
            row_id = str(start + i)
            batch.append((row_id, info["address"], info["city"], info["state"], info["zip"]))

        print(f"\n  Batch {batch_num + 1}/{total_batches} ({len(batch)} addresses)...", end="", flush=True)
        results = geocode_batch(batch)
        print(f" matched {len(results)}", end="", flush=True)
        matched += len(results)

        # Update cache
        for i, key in enumerate(batch_keys):
            row_id = str(start + i)
            if row_id in results:
                cache[key] = list(results[row_id])
            else:
                cache[key] = None  # Mark as attempted but unmatched

        # Save cache after each batch
        save_cache(cache)

        # Rate limit
        if batch_num < total_batches - 1:
            time.sleep(2)

    print(f"\n\n  Geocoding complete. Matched: {matched:,} / {len(to_geocode):,}")
    return cache


def apply_geocodes(data, cache):
    """Apply geocoded coordinates to provider features."""
    matched = 0
    unmatched = 0

    for feat in data["features"]:
        p = feat["properties"]
        key = f"{p.get('address', '')}|{p.get('city', '')}|{p.get('state', 'OK')}|{p.get('zip', '')}"

        coords = cache.get(key)
        if coords:
            feat["geometry"] = {
                "type": "Point",
                "coordinates": [coords[1], coords[0]],  # GeoJSON is [lon, lat]
            }
            matched += 1
        else:
            unmatched += 1

    print(f"\n  Geocoded: {matched:,}")
    print(f"  Unmatched: {unmatched:,}")

    # Remove features without geometry
    data["features"] = [f for f in data["features"] if f["geometry"] is not None]
    print(f"  Final features (with coordinates): {len(data['features']):,}")

    return data


def run():
    data = load_providers()
    addresses = extract_unique_addresses(data)
    cache = geocode_all(addresses)
    data = apply_geocodes(data, cache)

    with open(OUT_PATH, "w") as f:
        json.dump(data, f)

    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"\n  Saved: {OUT_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    run()
