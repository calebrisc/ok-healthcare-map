"""
Retry failed geocodes using OpenStreetMap Nominatim.
Nominatim usage policy: max 1 request/second, include User-Agent.
"""

import os
import json
import time
import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
GEOCODE_CACHE = os.path.join(RAW_DIR, "geocode_cache.json")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "OKHealthcareMap/1.0 (research project)"}


def run():
    print("Loading geocode cache...")
    with open(GEOCODE_CACHE) as f:
        cache = json.load(f)

    # Find entries that failed (null value)
    failed = {k: v for k, v in cache.items() if v is None}
    print(f"  Total cache entries: {len(cache):,}")
    print(f"  Failed entries to retry: {len(failed):,}")

    if not failed:
        print("  Nothing to retry!")
        return

    recovered = 0
    total = len(failed)

    for i, (key, _) in enumerate(failed.items()):
        parts = key.split("|")
        if len(parts) != 4:
            continue

        addr, city, state, zip_code = parts

        # Try structured query
        params = {
            "street": addr,
            "city": city,
            "state": state,
            "postalcode": zip_code,
            "country": "US",
            "format": "json",
            "limit": 1,
        }

        try:
            r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            results = r.json()

            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                cache[key] = [lat, lon]
                recovered += 1
            else:
                # Try free-form query as fallback
                q = f"{addr}, {city}, {state} {zip_code}"
                params2 = {"q": q, "format": "json", "limit": 1, "countrycodes": "us"}
                r2 = requests.get(NOMINATIM_URL, params=params2, headers=HEADERS, timeout=10)
                results2 = r2.json()
                if results2:
                    lat = float(results2[0]["lat"])
                    lon = float(results2[0]["lon"])
                    cache[key] = [lat, lon]
                    recovered += 1

        except Exception as e:
            pass

        if (i + 1) % 100 == 0:
            print(f"\r  Progress: {i+1}/{total} | Recovered: {recovered}", end="", flush=True)
            # Save periodically
            with open(GEOCODE_CACHE, "w") as f:
                json.dump(cache, f)

        # Rate limit: 1 request per second
        time.sleep(1.1)

    # Final save
    with open(GEOCODE_CACHE, "w") as f:
        json.dump(cache, f)

    print(f"\n\n  Done. Recovered {recovered:,} / {total:,} ({recovered/total*100:.1f}%)")
    print(f"  Run fix_providers.py again to rebuild with new geocodes")


if __name__ == "__main__":
    run()
