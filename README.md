# Oklahoma Healthcare Access Map

An interactive map of healthcare access in Oklahoma: where the providers are, where they aren't, and who's underserved. Built because the answer to "where does Oklahoma actually need more clinics" turned out to be scattered across a dozen federal datasets and six insurers' provider directories, and nobody had put them on one map.

**Live map: https://calebrisc.github.io/ok-healthcare-map/frontend/**

## What's on the map

Federal designations and geography:

- HPSA (Health Professional Shortage Areas) — geographic, population, and facility designations from HRSA
- MUA/MUP (Medically Underserved Areas/Populations), down to the census tract
- Tribal lands, IHS facilities, and NHSC sites
- Rural-Urban Continuum Codes and Health Service Areas
- Census demographics, insurance coverage, and income by tract
- Disease prevalence layers

Providers and facilities:

- Every Oklahoma provider from the NPI registry, split by type (primary care, behavioral, dental, NP/PA, specialists, therapy, pharmacy)
- CMS hospital data, plus closed hospitals — rural closures are a big part of the access story
- FQHCs and Rural Health Clinics
- Insurance network participation pulled from the machine-readable provider directories that Aetna, BCBS, Cigna, Humana, Centene, and UnitedHealthcare are federally required to publish — so you can see not just where providers are, but who takes which coverage, including Medicaid networks

## How it's built

`etl/` is a layered pipeline — each `layerNx_*.py` script pulls one source, cleans it, geocodes what needs geocoding (Nominatim, no API key needed), and writes a geojson into `data/processed/`. The merge scripts reconcile provider identities across insurer directories, which is the ugly part: the same doctor appears in six directories with six slightly different names and addresses, and NPI is the only thing that saves you.

The frontend is plain Leaflet — no build step, no framework. Open `frontend/index.html` over any static server (it fetches the geojson with relative paths):

```bash
python -m http.server
# then http://localhost:8000/frontend/
```

To rebuild the data from scratch:

```bash
pip install -r requirements.txt
# run etl scripts in layer order: layer1a → layer6
```

All source data is public. Provider records come from the public NPI registry and the insurers' mandated public directories; nothing here is scraped from behind a login.

## Caveats

Data was pulled April 2026 — provider directories churn constantly and insurer directories are notoriously stale even on the day you download them (ghost networks are a known problem; this map inherits that). Treat the network layers as "the insurer claims this provider is in-network," which is itself an interesting thing to map. Oklahoma only, but nothing in the pipeline is Oklahoma-specific except the bounding boxes and source URLs — porting it to another state is mostly find-and-replace plus patience.
