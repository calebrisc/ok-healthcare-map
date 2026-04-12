#!/usr/bin/env python3
"""
ETL: Commercial insurance provider NPIs from CMS Transparency in Coverage files.
Extracts NPI numbers from machine-readable in-network rate files.

Sources:
  - BCBS of Oklahoma (multiple plans)
  - Aetna (TBD)
  - Cigna (TBD)

Output: data/processed/commercial_insurance_npis.json
"""

import gzip
import json
import re
import subprocess
import sys
from urllib.request import urlopen

OUT_PATH = "data/processed/commercial_insurance_npis.json"

# BCBS OK plan files from CMS Transparency in Coverage index
BCBS_PLANS = {
    "Blue Advantage PPO": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_Blue-Advantage-PPO_in-network-rates.json.gz",
    "Blue Traditional PAR": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_Blue-Traditional-PAR_in-network-rates.json.gz",
    "Blue Choice PPO": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_Blue-Choice-PPO_in-network-rates.json.gz",
    "BlueLincs HMO": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_BlueLincs-HMO_in-network-rates.json.gz",
    "BlueOptions PPO": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_BlueOptions-PPO_in-network-rates.json.gz",
    "Blue Preferred PPO": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_Blue-Preferred-PPO_in-network-rates.json.gz",
    "BlueSolutions PPO": "https://app0004702110a5prdnc311.blob.core.windows.net/output/2026-03-15_Blue-Cross-and-Blue-Shield-of-Oklahoma_BlueSolutions-PPO_in-network-rates.json.gz",
}


def extract_npis_from_url(url, label):
    """Stream-download gzipped JSON and extract all NPIs via regex."""
    print(f"  Downloading {label}...", end=" ", flush=True)
    npis = set()

    # Use curl + gunzip for streaming (more reliable than urllib for huge files)
    proc = subprocess.Popen(
        ["bash", "-c", f'curl -sL -m 600 "{url}" | gunzip'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1024 * 1024,
    )

    chunk_buffer = ""
    bytes_read = 0
    for chunk in iter(lambda: proc.stdout.read(1024 * 512), ""):
        bytes_read += len(chunk)
        chunk_buffer += chunk
        # Extract NPIs from buffer
        for m in re.finditer(r'"npi":\[([0-9,]+)\]', chunk_buffer):
            for npi in m.group(1).split(","):
                npis.add(npi.strip())
        # Keep overlap to catch split matches
        if len(chunk_buffer) > 100000:
            chunk_buffer = chunk_buffer[-2000:]

    proc.wait()
    print(f"{len(npis)} NPIs ({bytes_read // (1024*1024)}MB)")
    return npis


def main():
    results = {}  # insurer → {plan → set of NPIs}

    # === BCBS of Oklahoma ===
    print("BCBS of Oklahoma:")
    bcbs_all = set()
    bcbs_plans = {}
    for plan_name, url in BCBS_PLANS.items():
        npis = extract_npis_from_url(url, plan_name)
        bcbs_plans[plan_name] = len(npis)
        bcbs_all.update(npis)

    print(f"  BCBS total unique NPIs: {len(bcbs_all)}")
    print(f"  Per plan: {bcbs_plans}")

    # Build output
    output = {
        "bcbs": {
            "insurer": "Blue Cross Blue Shield of Oklahoma",
            "total_npis": len(bcbs_all),
            "plans": bcbs_plans,
            "npis": sorted(bcbs_all),
        },
    }

    with open(OUT_PATH, "w") as f:
        json.dump(output, f)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
