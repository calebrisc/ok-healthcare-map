#!/usr/bin/env python3
"""
ETL: OHCA SoonerCare Total Enrollment by County (PDF → JSON)
Source: oklahoma.gov/ohca/research/data-and-reports
Input:  data/raw/ohca_enrollment_by_county.pdf (77 pages, 1 per county)
Output: data/processed/ohca_enrollment.json
"""

import json
import re
import pdfplumber

PDF_PATH = "data/raw/ohca_enrollment_by_county.pdf"
OUT_PATH = "data/processed/ohca_enrollment.json"


def parse_int(s):
    """Parse integer from string, handling commas and <10."""
    if not s or s.strip() == "":
        return None
    s = s.strip().replace(",", "")
    if s == "<10":
        return 5  # midpoint estimate
    try:
        return int(s)
    except ValueError:
        return None


def parse_pct(s):
    """Parse percentage like '66%' → 0.66"""
    if not s:
        return None
    m = re.search(r"(\d+)%", s)
    return int(m.group(1)) / 100 if m else None


def parse_money(s):
    """Parse dollar amount like '$72,430,307' → 72430307"""
    if not s:
        return None
    m = re.search(r"\$([\d,]+)", s)
    return int(m.group(1).replace(",", "")) if m else None


def parse_money_float(s):
    """Parse dollar amount like '$3,690' → 3690"""
    if not s:
        return None
    m = re.search(r"\$([\d,.]+)", s)
    return float(m.group(1).replace(",", "")) if m else None


def extract_field(text, pattern, parser=parse_int):
    """Extract a single value from text using regex."""
    m = re.search(pattern, text)
    if m:
        return parser(m.group(1))
    return None


def parse_page(text):
    """Parse one county page into a dict."""
    county = {}

    # County name — first line: "Adair February 2026 Fast Facts"
    m = re.match(r"^(.+?)\s+February\s+2026", text)
    if not m:
        return None
    county["county"] = m.group(1).strip()

    # === Total Enrollment by Aid Category ===
    aid_patterns = {
        "abd_adult": r"Aged/Blind/Disabled\s+Adult\s+([\d,<]+)",
        "abd_child": r"Aged/Blind/Disabled\s+Child\s+([\d,<]+)",
        "breast_cervical": r"Breast & Cervical Cancer\s+Adult\s+([\d,<]+)",
        "children_parents_adult": r"Children/Parents\s+Adult\s+([\d,<]+)",
        "children_parents_child": r"Children/Parents\s+Child\s+([\d,<]+)",
        "family_planning_adult": r"Family Planning\s+Adult\s+([\d,<]+)",
        "family_planning_child": r"Family Planning\s+Child\s+([\d,<]+)",
        "other_adult": r"Other\s+Adult\s+([\d,<]+)",
        "other_child": r"Other\s+Child\s+([\d,<]+)",
        "tefra": r"TEFRA\s+Child\s+([\d,<]+)",
        "expansion": r"Expansion\s+Adult\s+([\d,<]+)",
    }
    for key, pat in aid_patterns.items():
        county[key] = extract_field(text, pat)

    # Total enrollment — "Total 7909 Caucasian 84" (two columns merged on one line)
    # Always follows the Expansion line
    m = re.search(r"Expansion\s+Adult\s+[\d,<]+.*?\n.*?Total\s+([\d,]+)", text)
    if m:
        county["total_enrollment"] = parse_int(m.group(1))

    # === Age Breakdown ===
    county["adults_19_64"] = extract_field(text, r"Adults Age 19 to 64\s+([\d,]+)")
    county["adults_65_plus"] = extract_field(text, r"Adults Age 65 and Over\s+([\d,]+)")
    county["children_under_18"] = extract_field(text, r"Children Age 18 and Under\s+([\d,]+)")

    # === Race Breakdown ===
    # Text layout merges columns, so race data appears as "RRR American Indian 3838"
    # or "Race Breakdown Members\nAmerican Indian 3838" depending on extraction
    # Use first occurrence of each race (before Pregnant Women section)
    pregnant_pos = text.find("Pregnant Women")
    race_text = text[:pregnant_pos] if pregnant_pos > 0 else text
    county["race_american_indian"] = extract_field(race_text, r"American Indian\s+([\d,<]+)", parse_int)
    county["race_asian_pi"] = extract_field(race_text, r"Asian or Pacific Islander\s+([\d,<]+)", parse_int)
    county["race_black"] = extract_field(race_text, r"Black or African American\s+([\d,<]+)", parse_int)
    county["race_caucasian"] = extract_field(race_text, r"(?<!\n)Caucasian\s+([\d,<]+)", parse_int)
    county["race_two_plus"] = extract_field(race_text, r"Two or More Races\s+([\d,<]+)", parse_int)
    county["race_hispanic"] = extract_field(race_text, r"Hispanic or Latino\s+([\d,<]+)", parse_int)

    # === Special Populations ===
    county["dual_enrollees"] = extract_field(
        text, r"Medicare \(Dual Enrollees\)\s+([\d,]+)"
    )
    county["long_term_care"] = extract_field(
        text, r"long-term care facility\s+([\d,]+)"
    )
    county["hcbs_waivers"] = extract_field(
        text, r"Community Based Services waivers\*\*\s+([\d,]+)"
    )

    # === New Members ===
    county["new_members_adult"] = extract_field(text, r"New Members.*?Adult\s+([\d,]+)")
    county["new_members_child"] = extract_field(text, r"New Members.*?Child\s+([\d,]+)")

    # === SFY 2024 Figures ===
    county["pop_estimate"] = extract_field(
        text, r"Population Estimate \(2024\)\s+([\d,]+)"
    )
    # Ranks are on separate lines; some lines have mixed content from two columns
    # Strategy: find all "Statewide Rank N" occurrences in order
    # Order is: pop_rank, unduplicated_rank, medicaid_pct_rank, expenditures_rank,
    #           avg_per_pop_rank, avg_per_member_rank
    ranks = [int(m.group(1)) for m in re.finditer(r"Statewide Rank\s+(\d+)", text)]

    county["unduplicated_members"] = extract_field(
        text, r"Unduplicated Members\s+([\d,]+)"
    )
    county["medicaid_pct"] = extract_field(
        text, r"Pop\. Covered by Medicaid\s+(\d+%)", parse_pct
    )
    county["expenditures"] = extract_field(
        text, r"Expenditures\s+(\$[\d,]+)", parse_money
    )

    # Assign ranks by position
    county["pop_rank"] = ranks[0] if len(ranks) > 0 else None
    county["unduplicated_rank"] = ranks[1] if len(ranks) > 1 else None
    county["medicaid_pct_rank"] = ranks[2] if len(ranks) > 2 else None
    county["expenditures_rank"] = ranks[3] if len(ranks) > 3 else None
    county["avg_annual_per_pop"] = extract_field(
        text, r"Average Annual Per Est\. Pop\.\s+(\$[\d,.]+)", parse_money_float
    )
    county["avg_monthly_per_member"] = extract_field(
        text, r"Average Monthly Per Members?\s+(\$[\d,.]+)", parse_money_float
    )

    # === Deliveries ===
    county["deliveries"] = extract_field(text, r"SFY 2023 Deliveries\s+([\d,]+)")

    return county


def main():
    pdf = pdfplumber.open(PDF_PATH)
    print(f"Parsing {len(pdf.pages)} pages...")

    counties = []
    errors = []

    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            errors.append(f"Page {i+1}: no text extracted")
            continue

        record = parse_page(text)
        if not record:
            errors.append(f"Page {i+1}: couldn't parse county name")
            continue

        # Validate key fields
        missing = []
        if record.get("total_enrollment") is None:
            missing.append("total_enrollment")
        if record.get("medicaid_pct") is None:
            missing.append("medicaid_pct")
        if record.get("pop_estimate") is None:
            missing.append("pop_estimate")
        if missing:
            errors.append(f"Page {i+1} ({record['county']}): missing {', '.join(missing)}")

        counties.append(record)

    # Summary
    print(f"\nParsed: {len(counties)} counties")
    if errors:
        print(f"Warnings ({len(errors)}):")
        for e in errors:
            print(f"  {e}")

    # Quick stats
    valid_pct = [c["medicaid_pct"] for c in counties if c.get("medicaid_pct") is not None]
    if valid_pct:
        print(f"\nMedicaid coverage range: {min(valid_pct)*100:.0f}% - {max(valid_pct)*100:.0f}%")
        print(f"Mean: {sum(valid_pct)/len(valid_pct)*100:.1f}%")

    valid_enroll = [c["total_enrollment"] for c in counties if c.get("total_enrollment")]
    if valid_enroll:
        print(f"Enrollment range: {min(valid_enroll):,} - {max(valid_enroll):,}")

    with open(OUT_PATH, "w") as f:
        json.dump(counties, f, indent=2)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
