#!/usr/bin/env python3
"""
ETL: Humana Healthy Horizons — SoonerSelect provider directory
Source: assets.humana.com Humana OK Medicaid directory PDF
Input:  data/raw/humana/humana_dir_1.pdf (148 pages)
Output: data/processed/humana_providers.json

Extracts NPI numbers and provider categories.
"""

import json
import re
import pdfplumber

PDF_PATH = "data/raw/humana/humana_dir_1.pdf"
OUT_PATH = "data/processed/humana_providers.json"

CATEGORY_PATTERNS = [
    ("Hospital", r"^Hospital"),
    ("PCP", r"Primary Care Provider"),
    ("Specialist", r"^Specialist"),
    ("Behavioral Health", r"Behavioral"),
    ("Clinic", r"^Clinic"),
    ("Pharmacy", r"^Pharmac"),
    ("Vision", r"^Vision"),
    ("Dental", r"^Dental"),
    ("Ancillary", r"^Ancillary"),
    ("LTSS", r"Long[ -]Term"),
    ("Transportation", r"Transport"),
]


def main():
    pdf = pdfplumber.open(PDF_PATH)
    print(f"Processing {len(pdf.pages)} pages...")

    providers = {}
    current_category = "Unknown"

    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue

        # Detect section from first line
        first_line = text.split("\n")[0]
        for cat, pat in CATEGORY_PATTERNS:
            if re.search(pat, first_line, re.IGNORECASE):
                current_category = cat
                break

        # Extract NPIs
        for m in re.finditer(r"NPI:\s*(\d{10})", text):
            npi = m.group(1)
            if npi not in providers:
                providers[npi] = {
                    "npi": npi,
                    "categories": set(),
                }
            providers[npi]["categories"].add(current_category)

    # Convert sets to sorted lists
    results = []
    for p in providers.values():
        p["categories"] = sorted(p["categories"])
        p["network"] = "Humana Healthy Horizons"
        results.append(p)

    results.sort(key=lambda x: x["npi"])

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
