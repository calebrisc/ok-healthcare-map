#!/usr/bin/env python3
"""
ETL: Centene / Oklahoma Complete Health — SoonerSelect provider directory
Source: oklahomacompletehealth.com provider directory PDFs (40 county-grouped files)
Input:  data/raw/centene/och_*.pdf
Output: data/processed/centene_providers.json

Extracts NPI numbers and provider categories from each PDF.
The key value: which NPIs accept SoonerSelect Medicaid via Centene.
"""

import json
import re
import glob
import pdfplumber

RAW_DIR = "data/raw/centene"
OUT_PATH = "data/processed/centene_providers.json"

# County mapping from the directory page (PDF number → counties)
PDF_COUNTIES = {
    "01": ["Cimarron"],
    "02": ["Texas"],
    "03": ["Beaver", "Harper"],
    "04": ["Ellis", "Woodward"],
    "05": ["Roger Mills", "Custer", "Dewey"],
    "06": ["Harmon", "Beckham", "Greer"],
    "07": ["Washita", "Jackson", "Kiowa", "Tillman"],
    "08": ["Caddo", "Comanche"],
    "09": ["Major", "Blaine", "Kingfisher"],
    "10": ["Garfield", "Noble", "Logan"],
    "11": ["Woods", "Alfalfa"],
    "12": ["Grant", "Kay"],
    "13": ["Pawnee", "Osage", "Washington"],
    "14": ["Payne", "Creek"],
    "15": ["Lincoln", "Seminole", "Pottawatomie"],
    "16": ["Oklahoma"],
    "17": ["Cleveland"],
    "18": ["Canadian"],
    "19": ["McClain", "Grady", "Garvin"],
    "20": ["Cotton"],
    "21": ["Stephens", "Jefferson"],
    "22": ["Love"],
    "23": ["Carter", "Murray"],
    "24": ["Atoka", "Bryan"],
    "25": ["Johnston", "Marshall"],
    "26": ["Pontotoc", "Coal"],
    "27": ["Okfuskee", "Hughes"],
    "28": ["McIntosh", "Okmulgee", "Pittsburg"],
    "29": ["Wagoner"],
    "30": ["Muskogee"],
    "31": ["Tulsa"],
    "32": ["Nowata", "Rogers"],  # "Montgomery" in listing is likely Nowata
    "33": ["Craig", "Ottawa"],
    "34": ["Delaware", "Mayes"],
    "35": ["Adair", "Cherokee"],
    "36": ["Sequoyah"],
    "37": ["Haskell", "Latimer", "Pushmataha"],
    "38": ["Le Flore"],
    "39": ["Choctaw"],
    "40": ["McCurtain"],
}

# Provider category detection from section headers
CATEGORY_PATTERNS = [
    ("PCP", r"Primary Care Provider"),
    ("Clinic", r"^Clinic\b"),
    ("Hospital", r"^Hospital\b"),
    ("Ancillary", r"^Ancillary\b"),
    ("Behavioral Health", r"Behavioral Health"),
    ("Pharmacy", r"^Pharmacy\b"),
    ("Vision", r"^Vision\b"),
    ("Dental", r"^Dental\b"),
    ("Specialist", r"^Specialist\b"),
    ("LTSS", r"Long[ -]Term"),
    ("Transportation", r"Transportation"),
]


def extract_from_pdf(filepath):
    """Extract NPIs, names, and categories from a single PDF."""
    pdf = pdfplumber.open(filepath)
    providers = {}
    current_category = "Unknown"

    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        # Detect section headers to track category
        first_line = text.split("\n")[0] if text else ""
        for cat, pat in CATEGORY_PATTERNS:
            if re.search(pat, first_line, re.IGNORECASE):
                current_category = cat
                break

        # Extract all NPIs on this page
        for m in re.finditer(r"NPI:\s*(\d{10})", text):
            npi = m.group(1)
            if npi not in providers:
                providers[npi] = {
                    "npi": npi,
                    "categories": set(),
                }
            providers[npi]["categories"].add(current_category)

    pdf.close()

    # Convert sets to lists for JSON
    for p in providers.values():
        p["categories"] = sorted(p["categories"])

    return providers


def main():
    files = sorted(glob.glob(f"{RAW_DIR}/och_*.pdf"))
    print(f"Processing {len(files)} PDFs...")

    all_providers = {}  # NPI → provider record
    npi_counties = {}   # NPI → set of counties

    for filepath in files:
        # Extract PDF number from filename
        num = re.search(r"och_(\d+)\.pdf", filepath).group(1)
        counties = PDF_COUNTIES.get(num, [f"Unknown-{num}"])

        print(f"  {filepath} ({', '.join(counties)})...", end=" ", flush=True)
        providers = extract_from_pdf(filepath)
        print(f"{len(providers)} NPIs")

        for npi, prov in providers.items():
            if npi not in all_providers:
                all_providers[npi] = prov
                npi_counties[npi] = set()
            else:
                # Merge categories
                existing = set(all_providers[npi]["categories"])
                existing.update(prov["categories"])
                all_providers[npi]["categories"] = sorted(existing)
            npi_counties[npi].update(counties)

    # Add counties to each provider
    for npi in all_providers:
        all_providers[npi]["counties"] = sorted(npi_counties[npi])

    results = sorted(all_providers.values(), key=lambda x: x["npi"])

    # Summary
    print(f"\nTotal unique NPIs: {len(results)}")
    cat_counts = {}
    for p in results:
        for c in p["categories"]:
            cat_counts[c] = cat_counts.get(c, 0) + 1
    print("By category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
