#!/usr/bin/env python3
"""
NSW Property Sales Data Fetcher
================================
Downloads bulk property sales data from the NSW Valuer General's office,
filters for Sydney metropolitan area, and outputs JSON for the web app.

Data source:
  https://valuation.property.nsw.gov.au/embed/propertySalesInformation
  (NSW Valuer General - Official NSW Government property sales data)

Run:
  pip install -r requirements.txt
  python fetch_data.py

Output:
  ../public/data/properties.json   — processed sales data
  ../public/data/suburbs.geojson   — suburb boundary polygons (downloaded once)
"""

import os
import sys
import json
import zipfile
import io
import re
import math
import random
import logging
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "public" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROPERTIES_FILE = OUTPUT_DIR / "properties.json"
SUBURBS_FILE    = OUTPUT_DIR / "suburbs.geojson"

# ── Sydney postcode ranges ─────────────────────────────────────────────────────
# Covers Greater Sydney (inner, middle, outer ring)
SYDNEY_POSTCODES = set(
    list(range(2000, 2240))   # Inner + eastern + northern suburbs
    + list(range(2555, 2570)) # South-west
    + list(range(2740, 2780)) # Penrith / western
    + list(range(2155, 2170)) # Hills district
    + list(range(2195, 2220)) # South Sydney
)

# ── Property type mapping ──────────────────────────────────────────────────────
def classify_property_type(strata_lot, zone_code, primary_purpose, area_m2):
    """
    Classify based on NSW VG field values.
    Strata lot > 0 → Unit.
    Otherwise use zone/purpose heuristics.
    """
    try:
        lot = int(strata_lot or 0)
    except (ValueError, TypeError):
        lot = 0

    if lot > 0:
        return "Unit"

    purpose = str(primary_purpose or "").upper()
    zone = str(zone_code or "").upper()

    if "RESIDENTIAL" in purpose or zone.startswith("R"):
        try:
            area = float(area_m2 or 0)
        except (ValueError, TypeError):
            area = 0
        if area > 350:
            return "House"
        elif area > 120:
            return "Townhouse"
        else:
            return "Unit"

    if "RURAL" in purpose or "FARM" in purpose:
        return "Land"

    return "House"  # default residential

# ── NSW VG data columns ───────────────────────────────────────────────────────
# Format: semicolon-delimited with these headers (in order)
VG_COLUMNS = [
    "district_code", "source", "valuation_number", "property_id",
    "sale_counter", "download_date", "property_name", "unit_number",
    "street_number", "street_name", "locality", "post_code",
    "area", "area_type", "contract_date", "settlement_date",
    "purchase_price", "zoning", "nature_of_property", "primary_purpose",
    "strata_lot_number", "component_code", "sale_code", "interest_of_sale",
    "dealing_number",
]

def parse_vg_line(line, delimiter=";"):
    """Parse a single line from a NSW VG DAT file."""
    parts = line.strip().split(delimiter)
    if len(parts) < len(VG_COLUMNS):
        return None
    return dict(zip(VG_COLUMNS, parts))

def parse_date(date_str):
    """Parse dates in YYYYMMDD or DD/MM/YYYY format."""
    if not date_str or date_str.strip() == "":
        return None
    s = date_str.strip()
    for fmt in ("%Y%m%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def is_valid_sale(row):
    """Filter out non-arm's-length and invalid sales."""
    try:
        price = int(row.get("purchase_price", 0) or 0)
    except ValueError:
        return False
    if price < 50_000:
        return False

    sale_code = str(row.get("sale_code", "") or "").upper()
    # NSW VG sale codes: blank or "N" = normal sale; others are non-arms-length
    if sale_code not in ("", "N", "0"):
        return False

    locality = str(row.get("locality", "") or "").strip()
    if not locality:
        return False

    postcode_str = str(row.get("post_code", "") or "").strip()
    try:
        postcode = int(postcode_str)
    except ValueError:
        return False

    return postcode in SYDNEY_POSTCODES

# ── Suburb centroid lookup ─────────────────────────────────────────────────────
# Approximate centroids for Sydney suburbs (lat, lng)
# Used when we don't have exact coordinates
SUBURB_CENTROIDS = {
    "ULTIMO": (-33.8792, 151.1970),
    "PYRMONT": (-33.8694, 151.1925),
    "SURRY HILLS": (-33.8876, 151.2115),
    "NEWTOWN": (-33.8979, 151.1793),
    "GLEBE": (-33.8810, 151.1852),
    "LEICHHARDT": (-33.8839, 151.1567),
    "BALMAIN": (-33.8587, 151.1800),
    "ROZELLE": (-33.8622, 151.1720),
    "ANNANDALE": (-33.8835, 151.1658),
    "CAMPERDOWN": (-33.8891, 151.1779),
    "DARLINGHURST": (-33.8764, 151.2178),
    "PADDINGTON": (-33.8848, 151.2264),
    "WOOLLAHRA": (-33.8879, 151.2383),
    "DOUBLE BAY": (-33.8758, 151.2455),
    "BONDI": (-33.8908, 151.2740),
    "BONDI BEACH": (-33.8917, 151.2770),
    "BONDI JUNCTION": (-33.8913, 151.2531),
    "COOGEE": (-33.9215, 151.2589),
    "RANDWICK": (-33.9147, 151.2427),
    "KINGSFORD": (-33.9208, 151.2272),
    "MAROUBRA": (-33.9477, 151.2384),
    "ST PETERS": (-33.9072, 151.1895),
    "ALEXANDRIA": (-33.9065, 151.2035),
    "ZETLAND": (-33.9070, 151.2120),
    "WATERLOO": (-33.8992, 151.2076),
    "REDFERN": (-33.8938, 151.2041),
    "CHIPPENDALE": (-33.8893, 151.1989),
    "HAYMARKET": (-33.8800, 151.2050),
    "SYDNEY": (-33.8688, 151.2093),
    "MANLY": (-33.7967, 151.2872),
    "MOSMAN": (-33.8294, 151.2433),
    "CREMORNE": (-33.8327, 151.2273),
    "NEUTRAL BAY": (-33.8358, 151.2197),
    "NORTH SYDNEY": (-33.8402, 151.2073),
    "CHATSWOOD": (-33.7970, 151.1819),
    "LANE COVE": (-33.8163, 151.1661),
    "ARTARMON": (-33.8101, 151.1892),
    "WILLOUGHBY": (-33.8037, 151.2025),
    "CROWS NEST": (-33.8269, 151.2062),
    "ST LEONARDS": (-33.8249, 151.1960),
    "PARRAMATTA": (-33.8148, 151.0042),
    "HOMEBUSH": (-33.8629, 151.0897),
    "STRATHFIELD": (-33.8742, 151.0821),
    "AUBURN": (-33.8494, 151.0296),
    "MERRYLANDS": (-33.8333, 150.9944),
    "GRANVILLE": (-33.8349, 151.0143),
    "BANKSTOWN": (-33.9173, 151.0335),
    "LIVERPOOL": (-33.9200, 150.9238),
    "CAMPBELLTOWN": (-34.0655, 150.8142),
    "PENRITH": (-33.7511, 150.6942),
    "BLACKTOWN": (-33.7686, 150.9053),
    "CASTLE HILL": (-33.7300, 151.0038),
    "HORNSBY": (-33.7033, 151.0993),
    "HURSTVILLE": (-33.9644, 151.1033),
    "KOGARAH": (-33.9632, 151.1338),
    "ROCKDALE": (-33.9533, 151.1368),
    "SUTHERLAND": (-34.0310, 151.0575),
    "CRONULLA": (-34.0555, 151.1533),
    "MIRANDA": (-34.0364, 151.1015),
    "BROOKVALE": (-33.7618, 151.2618),
    "DEE WHY": (-33.7517, 151.2893),
    "NARRAWEENA": (-33.7550, 151.2704),
    "FRESHWATER": (-33.7741, 151.2818),
    "BALGOWLAH": (-33.7932, 151.2678),
    "FAIRLIGHT": (-33.7992, 151.2769),
    "KIRRIBILLI": (-33.8481, 151.2164),
    "MILSONS POINT": (-33.8503, 151.2117),
    "LAVENDER BAY": (-33.8481, 151.2094),
    "MCMAHONS POINT": (-33.8527, 151.2010),
    "WAVERTON": (-33.8372, 151.1998),
    "WOLLSTONECRAFT": (-33.8302, 151.1964),
    "NAREMBURN": (-33.8224, 151.1967),
    "CAMMERAY": (-33.8222, 151.2096),
    "NORTHBRIDGE": (-33.8124, 151.2206),
    "CASTLECRAG": (-33.8064, 151.2249),
    "MIDDLE COVE": (-33.7981, 151.2207),
    "ROSEVILLE": (-33.7878, 151.1806),
    "LINDFIELD": (-33.7763, 151.1683),
    "KILLARA": (-33.7669, 151.1624),
    "GORDON": (-33.7561, 151.1538),
    "PYMBLE": (-33.7460, 151.1398),
    "TURRAMURRA": (-33.7283, 151.1274),
    "WAHROONGA": (-33.7179, 151.1148),
    "WARRAWEE": (-33.7197, 151.1046),
    "ST IVES": (-33.7330, 151.1656),
    "BELROSE": (-33.7334, 151.2199),
    "FRENCHS FOREST": (-33.7536, 151.2370),
    "FORESTVILLE": (-33.7649, 151.2278),
    "KILLARNEY HEIGHTS": (-33.7710, 151.2448),
    "ALLAMBIE HEIGHTS": (-33.7814, 151.2481),
    "RHODES": (-33.8310, 151.0870),
    "MEADOWBANK": (-33.8170, 151.0900),
    "RYDE": (-33.8155, 151.1045),
    "WEST RYDE": (-33.8070, 151.0890),
    "EASTWOOD": (-33.7912, 151.0805),
    "EPPING": (-33.7730, 151.0823),
    "MACQUARIE PARK": (-33.7770, 151.1260),
    "MARSFIELD": (-33.7780, 151.1150),
    "CONCORD": (-33.8590, 151.1030),
    "DRUMMOYNE": (-33.8530, 151.1530),
    "FIVE DOCK": (-33.8657, 151.1290),
    "BURWOOD": (-33.8774, 151.1042),
    "ASHFIELD": (-33.8880, 151.1247),
    "SUMMER HILL": (-33.8920, 151.1383),
    "MARRICKVILLE": (-33.9115, 151.1552),
    "DULWICH HILL": (-33.9076, 151.1400),
    "ENMORE": (-33.9000, 151.1745),
    "ERSKINEVILLE": (-33.9032, 151.1862),
    "MASCOT": (-33.9260, 151.1925),
    "BOTANY": (-33.9450, 151.1970),
    "ROSEBERY": (-33.9187, 151.2043),
    "WOLLI CREEK": (-33.9338, 151.1535),
    "ARNCLIFFE": (-33.9372, 151.1470),
    "TEMPE": (-33.9200, 151.1630),
    "SYDENHAM": (-33.9166, 151.1690),
    "PETERSHAM": (-33.8950, 151.1545),
    "STANMORE": (-33.8960, 151.1650),
    "CAMPSIE": (-33.9116, 151.1024),
    "CANTERBURY": (-33.9116, 151.1180),
    "BELMORE": (-33.9212, 151.0907),
    "LAKEMBA": (-33.9197, 151.0755),
    "PUNCHBOWL": (-33.9253, 151.0555),
    "REVESBY": (-33.9503, 151.0153),
    "PADSTOW": (-33.9522, 151.0340),
    "RIVERWOOD": (-33.9523, 151.0520),
    "MORTDALE": (-33.9638, 151.0630),
    "OATLEY": (-33.9777, 151.0730),
    "COMO": (-34.0053, 151.0690),
    "JANNALI": (-34.0163, 151.0580),
    "ENGADINE": (-34.0640, 151.0130),
    "HEATHCOTE": (-34.0860, 151.0070),
    "CARINGBAH": (-34.0374, 151.1230),
    "GYMEA": (-34.0380, 151.0860),
    "KIRRAWEE": (-34.0380, 151.0740),
    "SUTHERLAND": (-34.0310, 151.0575),
    "MENAI": (-34.0120, 151.0100),
    "BEXLEY": (-33.9500, 151.1225),
    "KINGSGROVE": (-33.9395, 151.1005),
    "BEVERLEY HILLS": (-33.9453, 151.0815),
    "NARWEE": (-33.9508, 151.0688),
    "SYLVANIA": (-34.0200, 151.1030),
    "CASULA": (-33.9585, 150.9095),
    "CABRAMATTA": (-33.8949, 150.9378),
    "FAIRFIELD": (-33.8710, 150.9565),
    "LIDCOMBE": (-33.8640, 151.0475),
    "OLYMPIC PARK": (-33.8467, 151.0694),
    "WENTWORTH POINT": (-33.8350, 151.0730),
    "NEWINGTON": (-33.8410, 151.0580),
    "SILVERWATER": (-33.8380, 151.0440),
    "ERMINGTON": (-33.8133, 151.0400),
    "DUNDAS": (-33.8050, 151.0380),
    "CARLINGFORD": (-33.7830, 151.0490),
    "BEECROFT": (-33.7530, 151.0630),
    "PENNANT HILLS": (-33.7380, 151.0720),
    "THORNLEIGH": (-33.7240, 151.0810),
    "NORMANHURST": (-33.7190, 151.0910),
    "WAHROONGA": (-33.7179, 151.1148),
    "TURRAMURRA": (-33.7283, 151.1274),
    "NORTH RYDE": (-33.7950, 151.1280),
    "GLADESVILLE": (-33.8350, 151.1300),
    "HUNTERS HILL": (-33.8350, 151.1450),
    "PUTNEY": (-33.8260, 151.1230),
    "CABARITA": (-33.8440, 151.1310),
    "ABBOTSFORD": (-33.8530, 151.1290),
    "CANADA BAY": (-33.8640, 151.1130),
    "LIBERTY GROVE": (-33.8440, 151.0840),
    "BREAKFAST POINT": (-33.8520, 151.1070),
    "MORTLAKE": (-33.8440, 151.1110),
    "HABERFIELD": (-33.8820, 151.1380),
    "CROYDON": (-33.8830, 151.1130),
    "CROYDON PARK": (-33.8950, 151.1040),
    "ENFIELD": (-33.8950, 151.0920),
    "GREENACRE": (-33.9050, 151.0540),
    "BASS HILL": (-33.9010, 150.9930),
    "CHESTER HILL": (-33.8930, 150.9980),
    "VILLAWOOD": (-33.8880, 151.0120),
    "BERALA": (-33.8700, 151.0350),
    "REGENTS PARK": (-33.8780, 151.0260),
    "SEFTON": (-33.8900, 151.0170),
    "BIRRONG": (-33.8920, 151.0230),
    "YAGOONA": (-33.9050, 151.0230),
    "CONDELL PARK": (-33.9230, 151.0120),
    "PANANIA": (-33.9530, 151.0000),
    "EAST HILLS": (-33.9600, 150.9910),
    "LUGARNO": (-33.9830, 151.0410),
    "PEAKHURST": (-33.9620, 151.0660),
    "PENSHURST": (-33.9640, 151.0870),
    "ALLAWAH": (-33.9690, 151.1110),
    "CARLTON": (-33.9720, 151.1170),
    "SANS SOUCI": (-33.9880, 151.1320),
    "RAMSGATE": (-33.9860, 151.1410),
    "BRIGHTON LE SANDS": (-33.9610, 151.1500),
    "MONTEREY": (-33.9660, 151.1480),
    "KYEEMAGH": (-33.9490, 151.1575),
    "BEXLEY NORTH": (-33.9430, 151.1230),
    "BARDWELL PARK": (-33.9290, 151.1290),
    "BARDWELL VALLEY": (-33.9280, 151.1210),
    "TURRELLA": (-33.9300, 151.1470),
    "EARLWOOD": (-33.9230, 151.1270),
    "CLEMTON PARK": (-33.9180, 151.1100),
    "HURLSTONE PARK": (-33.9090, 151.1355),
    "LEWISHAM": (-33.8950, 151.1475),
    "LILYFIELD": (-33.8700, 151.1630),
    "BIRCHGROVE": (-33.8530, 151.1730),
    "CHISWICK": (-33.8490, 151.1530),
    "RODD POINT": (-33.8630, 151.1440),
    "RUSSELL LEA": (-33.8580, 151.1390),
    "WAREEMBA": (-33.8590, 151.1340),
}


def get_centroid_with_jitter(suburb_name):
    """Get lat/lng for suburb with small random offset."""
    sub = suburb_name.upper().strip()
    if sub in SUBURB_CENTROIDS:
        lat, lng = SUBURB_CENTROIDS[sub]
        # Add small jitter so points don't all overlap
        jitter_lat = random.uniform(-0.004, 0.004)
        jitter_lng = random.uniform(-0.005, 0.005)
        return round(lat + jitter_lat, 6), round(lng + jitter_lng, 6)
    return None, None


# ── Download NSW VG data ──────────────────────────────────────────────────────
VG_BASE_URL = "https://www.valuergeneral.nsw.gov.au/siteassets/land_value_summaries/files/property-sales-information"

def get_download_urls():
    """Return list of (year, url) tuples to download."""
    current_year = datetime.now().year
    urls = []
    # Download current year and previous year for 12+ months of data
    for year in [current_year - 1, current_year]:
        url = f"{VG_BASE_URL}/property-sales-information-{year}.zip"
        urls.append((year, url))
    return urls


def download_and_parse_zip(year, url, cutoff_date):
    """Download a ZIP, extract and parse DAT files. Returns list of sale dicts."""
    log.info(f"Downloading {year} data from {url}")
    properties = []

    try:
        response = requests.get(url, timeout=120, stream=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning(f"Failed to download {year}: {e}")
        return properties

    log.info(f"Downloaded {len(response.content) / 1024 / 1024:.1f} MB for {year}")

    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            dat_files = [n for n in zf.namelist() if n.lower().endswith(".dat")]
            log.info(f"Found {len(dat_files)} DAT files in {year} ZIP")

            for dat_name in dat_files:
                log.info(f"  Parsing {dat_name}…")
                with zf.open(dat_name) as f:
                    lines = f.read().decode("latin-1", errors="replace").splitlines()

                # Skip header line if present
                start = 1 if lines and not lines[0][0].isdigit() else 0

                for line in lines[start:]:
                    row = parse_vg_line(line)
                    if not row:
                        continue
                    if not is_valid_sale(row):
                        continue

                    contract_date = parse_date(row.get("contract_date"))
                    if not contract_date or contract_date < cutoff_date:
                        continue

                    try:
                        price = int(row.get("purchase_price", 0) or 0)
                    except ValueError:
                        continue

                    locality = str(row.get("locality", "")).strip().upper()

                    # Build address
                    unit = str(row.get("unit_number", "") or "").strip()
                    street_no = str(row.get("street_number", "") or "").strip()
                    street_name = str(row.get("street_name", "") or "").strip()
                    address_parts = filter(None, [
                        f"{unit}/{street_no}" if unit else street_no,
                        street_name,
                    ])
                    address = " ".join(address_parts).title()
                    if not address:
                        address = "Unknown address"

                    try:
                        area = float(row.get("area", 0) or 0)
                    except ValueError:
                        area = 0

                    prop_type = classify_property_type(
                        row.get("strata_lot_number"),
                        row.get("zoning"),
                        row.get("primary_purpose"),
                        area,
                    )

                    lat, lng = get_centroid_with_jitter(locality)
                    if lat is None:
                        continue  # Skip suburbs outside our centroid table

                    # Unique ID from key fields
                    uid_src = f"{row.get('dealing_number', '')}-{row.get('property_id', '')}"
                    uid = hashlib.md5(uid_src.encode()).hexdigest()[:12]

                    properties.append({
                        "id": uid,
                        "address": address,
                        "suburb": locality,
                        "postcode": str(row.get("post_code", "")).strip(),
                        "lat": lat,
                        "lng": lng,
                        "price": price,
                        "date": contract_date.isoformat(),
                        "type": prop_type,
                        "area": round(area, 1) if area else None,
                    })

    except zipfile.BadZipFile as e:
        log.warning(f"Bad ZIP for {year}: {e}")

    log.info(f"  → {len(properties)} valid Sydney sales from {year}")
    return properties


# ── Download suburb GeoJSON ───────────────────────────────────────────────────
SUBURBS_GEOJSON_URL = (
    "https://raw.githubusercontent.com/tonywr71/GeoJson-Data/master/suburb-10-nsw.geojson"
)

SYDNEY_SUBURB_NAMES = set(SUBURB_CENTROIDS.keys())


def download_suburb_geojson():
    """Download NSW suburb boundaries and filter to Sydney suburbs."""
    if SUBURBS_FILE.exists():
        log.info("Suburb GeoJSON already exists, skipping download")
        return True

    log.info(f"Downloading suburb GeoJSON from {SUBURBS_GEOJSON_URL}")
    try:
        r = requests.get(SUBURBS_GEOJSON_URL, timeout=60)
        r.raise_for_status()
        geojson = r.json()
    except Exception as e:
        log.warning(f"Failed to download suburb GeoJSON: {e}")
        # Create empty placeholder so app doesn't crash
        SUBURBS_FILE.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        return False

    # Filter to Sydney suburbs only to reduce file size
    sydney_features = [
        f for f in geojson.get("features", [])
        if (f.get("properties", {}).get("LOC_NAME", "")
            or f.get("properties", {}).get("suburb", "")).upper() in SYDNEY_SUBURB_NAMES
    ]

    filtered = {
        "type": "FeatureCollection",
        "features": sydney_features,
    }

    SUBURBS_FILE.write_text(json.dumps(filtered, separators=(",", ":")))
    log.info(f"Saved {len(sydney_features)} Sydney suburb polygons to {SUBURBS_FILE}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    random.seed(42)  # reproducible jitter

    # We want data from the last 24 months
    cutoff = date.today() - timedelta(days=730)

    all_properties = []

    # 1. Download suburb GeoJSON (only needed once)
    download_suburb_geojson()

    # 2. Download and parse NSW VG data
    for year, url in get_download_urls():
        props = download_and_parse_zip(year, url, cutoff)
        all_properties.extend(props)

    use_sample = False
    if not all_properties:
        log.warning("No properties fetched! Check network access and data URLs.")
        log.warning("Generating sample data as fallback…")
        from generate_sample import generate_sample_data
        all_properties = generate_sample_data()
        use_sample = True

    # 3. Deduplicate
    seen = set()
    unique = []
    for p in all_properties:
        key = p["id"]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # 4. Sort by date descending
    unique.sort(key=lambda p: p["date"], reverse=True)

    # 5. Write output
    output = {
        "lastUpdated": date.today().isoformat(),
        "totalCount": len(unique),
        "properties": unique,
    }
    if use_sample:
        output["note"] = "SAMPLE DATA — for development/demo only. Run fetch_data.py with network access for real NSW VG data."

    PROPERTIES_FILE.write_text(json.dumps(output, separators=(",", ":")))
    log.info(f"✅ Saved {len(unique)} properties to {PROPERTIES_FILE}")
    log.info(f"   Suburbs covered: {len({p['suburb'] for p in unique})}")

    # Print suburb summary
    suburb_counts = {}
    for p in unique:
        suburb_counts[p["suburb"]] = suburb_counts.get(p["suburb"], 0) + 1
    top_10 = sorted(suburb_counts.items(), key=lambda x: -x[1])[:10]
    log.info("Top 10 suburbs by transaction count:")
    for sub, count in top_10:
        log.info(f"  {sub}: {count}")


if __name__ == "__main__":
    main()
