"""
Layer 2A: NPI Registry - All Healthcare Providers in Oklahoma
Source: CMS NPPES bulk download
Downloads full NPI CSV (~9GB), streams through it keeping only Oklahoma rows,
categorizes by taxonomy code, outputs GeoJSON.
"""

import os
import csv
import json
import zipfile
import requests
import re

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

# NPPES full replacement monthly file
NPPES_URL = "https://download.cms.gov/nppes/NPPES_Data_Dissemination_April_2026.zip"
ZIP_PATH = os.path.join(RAW_DIR, "nppes_full.zip")
OK_CSV_PATH = os.path.join(RAW_DIR, "nppes_oklahoma.csv")
OUT_PATH = os.path.join(OUT_DIR, "ok_providers.geojson")

# Taxonomy prefix → category mapping
TAXONOMY_MAP = {
    "207Q": "Primary Care (Family Medicine)",
    "207R": "Primary Care (Internal Medicine)",
    "208D": "Primary Care (General Practice)",
    "2084P": "Primary Care (Pediatrics)",
    "207V": "OB/GYN",
    "363L": "NP (Nurse Practitioner)",
    "363A": "PA (Physician Assistant)",
    "367A": "Advanced Practice Midwife",
    "261Q": "Hospital",
    "282N": "Hospital (General Acute Care)",
    "283X": "Hospital (Rehabilitation)",
    "284300000X": "Hospital (Special)",
    "333600000X": "Pharmacy",
    "3336": "Pharmacy",
    "261QU": "Urgent Care",
    "251E": "Home Health",
    "251B": "Hospice",
    "251S": "Nursing Facility",
    "261QF": "FQHC",
    "261QR": "Rural Health Clinic",
    "261QC": "Critical Access Hospital",
    "101Y": "Behavioral Health (Counselor)",
    "103T": "Behavioral Health (Psychologist)",
    "1041": "Behavioral Health (Social Worker)",
    "390200000X": "Behavioral Health (Substance Abuse)",
    "122300000X": "Dental",
    "1223": "Dental",
    "291U": "Lab (Clinical)",
    "293D": "Lab",
}


def get_category(taxonomy_code):
    """Map a taxonomy code to a human-readable category."""
    if not taxonomy_code:
        return "Other"
    code = taxonomy_code.strip()
    # Try exact match first, then progressively shorter prefixes
    for length in [len(code), 10, 6, 5, 4, 3]:
        prefix = code[:length]
        if prefix in TAXONOMY_MAP:
            return TAXONOMY_MAP[prefix]
    # Broad fallbacks by first digits
    if code.startswith("20"):
        return "Physician (Specialist)"
    if code.startswith("36"):
        return "NP/PA/Midlevel"
    if code.startswith("10"):
        return "Behavioral Health"
    if code.startswith("12"):
        return "Dental"
    if code.startswith("33"):
        return "Pharmacy"
    if code.startswith("26") or code.startswith("28"):
        return "Hospital/Facility"
    if code.startswith("25"):
        return "Facility (Other)"
    return "Other"


def find_nppes_url():
    """Try to find the current NPPES download URL."""
    # The URL changes monthly. Try current month first, then recent months.
    import datetime
    today = datetime.date.today()
    months_to_try = []
    for offset in range(0, 4):
        d = today.replace(day=1) - datetime.timedelta(days=30 * offset)
        months_to_try.append(d.strftime("%B_%Y"))

    for month_str in months_to_try:
        url = f"https://download.cms.gov/nppes/NPPES_Data_Dissemination_{month_str}.zip"
        print(f"  Trying: {url}")
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            if r.status_code == 200:
                return url
        except:
            continue

    return NPPES_URL  # fallback


def download():
    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(ZIP_PATH):
        print(f"Already downloaded: {ZIP_PATH}")
        return

    url = find_nppes_url()
    print(f"Downloading NPPES data from:\n  {url}")
    print("  This is ~1-2 GB compressed, may take a while...")

    r = requests.get(url, stream=True)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    downloaded = 0
    with open(ZIP_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                mb = downloaded / (1024 * 1024)
                print(f"\r  {mb:.0f} MB ({pct:.1f}%)", end="", flush=True)
    print(f"\n  Saved to {ZIP_PATH}")


def extract_oklahoma():
    """Stream through the NPI CSV inside the zip, keeping only Oklahoma rows."""
    if os.path.exists(OK_CSV_PATH):
        print(f"Already filtered: {OK_CSV_PATH}")
        return

    print("Extracting Oklahoma providers from NPPES zip (streaming)...")

    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        # Find the main CSV file (largest file, usually named npidata_pfile_*.csv)
        csv_name = None
        for info in z.infolist():
            if info.filename.lower().endswith(".csv") and "npidata_pfile" in info.filename.lower():
                csv_name = info.filename
                break
        if not csv_name:
            # Fall back to largest CSV
            csvs = [(i.filename, i.file_size) for i in z.infolist() if i.filename.lower().endswith(".csv")]
            csvs.sort(key=lambda x: x[1], reverse=True)
            csv_name = csvs[0][0]

        print(f"  Reading: {csv_name}")

        with z.open(csv_name) as raw:
            import io
            text_stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text_stream)

            # Find relevant column names
            fieldnames = reader.fieldnames
            print(f"  Columns: {len(fieldnames)}")

            # Key columns we need
            state_col = "Provider Business Practice Location Address State Name"
            if state_col not in fieldnames:
                # Fallback search
                for col in fieldnames:
                    if "practice" in col.lower() and "state" in col.lower():
                        state_col = col
                        break

            print(f"  State col: {state_col}")

            ok_rows = []
            total = 0
            for row in reader:
                total += 1
                if total % 500000 == 0:
                    print(f"\r  Processed {total:,} rows, found {len(ok_rows):,} OK providers", end="", flush=True)

                state = (row.get(state_col, "") or "").strip().upper()
                if state == "OK":
                    ok_rows.append(row)

            print(f"\n  Total rows: {total:,}")
            print(f"  Oklahoma providers: {len(ok_rows):,}")

            # Write filtered CSV
            with open(OK_CSV_PATH, "w", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(ok_rows)
            print(f"  Saved filtered CSV: {OK_CSV_PATH}")


def build_geojson():
    """Convert filtered Oklahoma NPI CSV to GeoJSON with categories."""
    print("\nBuilding GeoJSON from filtered data...")

    features = []
    skipped_no_address = 0

    with open(OK_CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        # Column names from NPPES data
        npi_col = "NPI"
        name_org_col = "Provider Organization Name (Legal Business Name)"
        name_last_col = "Provider Last Name (Legal Name)"
        name_first_col = "Provider First Name"
        addr1_col = "Provider First Line Business Practice Location Address"
        city_col = "Provider Business Practice Location Address City Name"
        state_col = "Provider Business Practice Location Address State Name"
        zip_col = "Provider Business Practice Location Address Postal Code"
        phone_col = "Provider Business Practice Location Address Telephone Number"
        taxonomy_col = "Healthcare Provider Taxonomy Code_1"
        entity_col = "Entity Type Code"

        print(f"  Key columns: npi={npi_col}, taxonomy={taxonomy_col}")

        for row in reader:
            npi = (row.get(npi_col, "") or "").strip()
            taxonomy = (row.get(taxonomy_col, "") or "").strip()
            category = get_category(taxonomy)

            org_name = (row.get(name_org_col, "") or "").strip()
            last = (row.get(name_last_col, "") or "").strip()
            first = (row.get(name_first_col, "") or "").strip()
            name = org_name if org_name else f"{last}, {first}".strip(", ")

            addr1 = (row.get(addr1_col, "") or "").strip()
            city = (row.get(city_col, "") or "").strip()
            zip_code = (row.get(zip_col, "") or "").strip()[:5]
            phone = (row.get(phone_col, "") or "").strip()

            if not addr1 or not city:
                skipped_no_address += 1
                continue

            feature = {
                "type": "Feature",
                "properties": {
                    "npi": npi,
                    "name": name,
                    "category": category,
                    "taxonomy": taxonomy,
                    "address": addr1,
                    "city": city,
                    "state": "OK",
                    "zip": zip_code,
                    "phone": phone,
                },
                "geometry": None,  # Will need geocoding later
            }
            features.append(feature)

    print(f"  Total features: {len(features):,}")
    print(f"  Skipped (no address): {skipped_no_address:,}")

    # Category breakdown
    from collections import Counter
    cats = Counter(f["properties"]["category"] for f in features)
    print("\n  Category breakdown:")
    for cat, count in cats.most_common(20):
        print(f"    {cat}: {count:,}")

    # Save as GeoJSON (without geometry for now - needs geocoding)
    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUT_PATH, "w") as f:
        json.dump(geojson, f)

    size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"\n  Saved: {OUT_PATH} ({size_mb:.1f} MB)")
    print("  NOTE: Geometries are null - providers need geocoding to get lat/lon")


if __name__ == "__main__":
    download()
    extract_oklahoma()
    build_geojson()
