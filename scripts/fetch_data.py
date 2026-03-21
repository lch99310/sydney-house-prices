#!/usr/bin/env python3
"""
NSW Property Sales Data Fetcher
================================
Downloads real property sales data from the NSW Valuer General PSI portal,
filters for Greater Sydney, and outputs JSON for the web app.

Data source:
  Weekly:  https://www.valuergeneral.nsw.gov.au/_psi/weekly/YYYYMMDD.zip
  Yearly:  https://www.valuergeneral.nsw.gov.au/_psi/yearly/YYYY.zip

The NSW VG publishes weekly data every Monday. DAT files inside the ZIPs
are semicolon-delimited with 25 columns per the PSI specification.

Run:
  pip install -r requirements.txt
  python fetch_data.py              # full fetch (yearly + recent weekly)
  python fetch_data.py --weekly     # incremental weekly update only

Output:
  ../public/data/properties.json   — processed sales data (last 2 years)
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
import argparse
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

# ── Greater Sydney postcode ranges ────────────────────────────────────────────
# Covers the 33 LGAs of Greater Sydney
# Reference: https://www.abs.gov.au/census/find-census-data/search-by-area
SYDNEY_POSTCODES = set(
    list(range(2000, 2250))   # City / Inner / Eastern / Northern suburbs
    + list(range(2555, 2575)) # Macarthur / South-west
    + list(range(2740, 2790)) # Penrith / Blue Mountains fringe
    + list(range(2140, 2200)) # Inner West / Canterbury-Bankstown
    + list(range(2200, 2235)) # St George / Sutherland
    + list(range(2256, 2265)) # Central Coast fringe (Gosford)
    + list(range(2745, 2780)) # Western Sydney
    + list(range(2100, 2140)) # Northern Beaches / Ryde
    + list(range(2060, 2100)) # Lower North Shore / Northern Beaches
    + list(range(2040, 2060)) # Inner West
    + list(range(2010, 2040)) # Eastern suburbs
    + list(range(2560, 2571)) # Camden / Campbelltown
    + list(range(2145, 2180)) # Hills / Parramatta / Blacktown
    + list(range(2745, 2770)) # Penrith
    + list(range(2750, 2760)) # Penrith
    + list(range(2228, 2235)) # Sutherland south
    + list(range(2760, 2775)) # Blue Mountains / Hawkesbury
    + list(range(2565, 2575)) # Wollondilly
)

# ── Allowed property purposes (residential + commercial) ─────────────────────
ALLOWED_PURPOSES = {
    "RESIDENCE", "RESIDENTIAL", "COMMERCIAL", "MIXED USE",
    "HOME UNIT", "STRATA UNIT", "VILLA", "TOWNHOUSE",
    "VACANT LAND", "DUPLEX",
}

def is_allowed_purpose(primary_purpose, nature_of_property):
    """Keep residential and commercial sales, discard others (rural, industrial, etc.)."""
    purpose = str(primary_purpose or "").upper().strip()
    nature = str(nature_of_property or "").upper().strip()

    # Always allow if purpose matches
    for kw in ALLOWED_PURPOSES:
        if kw in purpose or kw in nature:
            return True

    # Allow any R-zoned property (R1, R2, R3, R4, etc.)
    # Allow B-zoned property (B1-B8 commercial/business)
    # These are common in the "zoning" field
    return False


# ── Property type classification ──────────────────────────────────────────────
def classify_property_type(strata_lot, zone_code, primary_purpose, nature_of_property, area_m2):
    """
    Classify property type using NSW VG fields.

    Logic:
    1. Strata lot number > 0 → Unit (apartments are strata-titled)
    2. Check nature_of_property / primary_purpose for keywords
    3. Fall back to zoning code + land area heuristic
    """
    nature = str(nature_of_property or "").upper()
    purpose = str(primary_purpose or "").upper()
    zone = str(zone_code or "").upper().strip()

    # 1. Strata = Unit
    try:
        lot = int(strata_lot or 0)
    except (ValueError, TypeError):
        lot = 0
    if lot > 0:
        return "Unit"

    # 2. Keywords in nature/purpose
    for kw in ("VILLA", "TOWNHOUSE", "TOWN HOUSE", "TERRACE", "SEMI"):
        if kw in nature or kw in purpose:
            return "Townhouse"

    for kw in ("HOME UNIT", "STRATA UNIT", "UNIT", "APARTMENT", "FLAT"):
        if kw in nature or kw in purpose:
            return "Unit"

    if "VACANT LAND" in nature or "VACANT LAND" in purpose:
        return "Land"

    if "COMMERCIAL" in nature or "COMMERCIAL" in purpose:
        return "Commercial"

    if "DUPLEX" in nature or "DUPLEX" in purpose:
        return "Townhouse"

    # 3. Zoning + area heuristic
    if zone.startswith("R") or "RESID" in purpose:
        try:
            area = float(area_m2 or 0)
        except (ValueError, TypeError):
            area = 0
        if area > 400:
            return "House"
        elif area > 150:
            return "Townhouse"
        else:
            return "House"  # small lot house is still a house

    if zone.startswith("B") or zone.startswith("E"):
        return "Commercial"

    return "House"  # default for residential zones


# ── NSW VG PSI data columns ──────────────────────────────────────────────────
# PSI DAT file format: semicolon-delimited, multi-record type
#   A = district header, B = sale record, C = cross-reference, D = additional info
# Only B records contain the sale data we need.
# See: https://www.valuergeneral.nsw.gov.au/land_values/where_can_i_learn_more/
#
# Real example B record (semicolon-delimited):
# B;144;1595525;1;20260316 01:01;;;5;JACKSON CL;MENAI;2234;642.1;M;20251217;20260311;2500000;C4;R;RESIDENCE;;CRE;;;AV936780;
VG_B_COLUMNS = [
    "record_type", "district_code", "property_id",
    "sale_counter", "download_date", "property_name", "unit_number",
    "street_number", "street_name", "locality", "post_code",
    "area", "area_type", "contract_date", "settlement_date",
    "purchase_price", "zoning", "nature_of_property", "primary_purpose",
    "strata_lot_number", "component_code", "sale_code", "interest_of_sale",
    "dealing_number",
]

def parse_vg_line(line, delimiter=";"):
    """Parse a B-record line from a NSW VG DAT file. Returns None for non-B records."""
    stripped = line.strip()
    if not stripped:
        return None
    # Only parse B (sale) records; skip A (header), C (cross-ref), D (detail)
    if not stripped.startswith("B;"):
        return None
    parts = stripped.split(delimiter)
    if len(parts) < len(VG_B_COLUMNS):
        return None
    return dict(zip(VG_B_COLUMNS, parts))

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
    """Filter: arm's-length sales in Greater Sydney with valid price."""
    try:
        price = int(row.get("purchase_price", 0) or 0)
    except ValueError:
        return False
    if price < 50_000:
        return False

    sale_code = str(row.get("sale_code", "") or "").upper().strip()
    # NSW VG sale codes: blank or empty = normal sale
    # Other codes indicate non-arm's-length transactions
    if sale_code and sale_code not in ("", " "):
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
# When we don't have exact property coordinates, we place properties
# at the suburb centroid with a small random jitter.
# This table is dynamically extended when we encounter new suburbs
# by computing centroids from the GeoJSON suburb boundaries.

# Seed centroids for the most common Sydney suburbs
SUBURB_CENTROIDS = {}
SUBURB_POLYGONS = {}  # suburb_name -> list of [lng, lat] ring coordinates

def load_centroids_from_geojson():
    """Load suburb centroids and polygon boundaries from the GeoJSON file."""
    global SUBURB_CENTROIDS, SUBURB_POLYGONS
    if not SUBURBS_FILE.exists():
        return
    try:
        with open(SUBURBS_FILE) as f:
            geojson = json.load(f)
        for feature in geojson.get("features", []):
            name = (
                feature.get("properties", {}).get("LOC_NAME", "")
                or feature.get("properties", {}).get("suburb", "")
            ).upper().strip()
            if not name:
                continue
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates")
            if not coords:
                continue
            # Store polygon ring for point-in-polygon placement
            if geom.get("type") == "Polygon":
                SUBURB_POLYGONS[name] = coords[0]
            elif geom.get("type") == "MultiPolygon":
                SUBURB_POLYGONS[name] = coords[0][0]
            # Flatten all coordinate pairs for centroid
            all_coords = []
            def flatten(arr):
                if isinstance(arr[0], (int, float)):
                    all_coords.append(arr)
                else:
                    for sub in arr:
                        flatten(sub)
            try:
                flatten(coords)
            except (IndexError, TypeError):
                continue
            if not all_coords:
                continue
            lngs = [c[0] for c in all_coords]
            lats = [c[1] for c in all_coords]
            SUBURB_CENTROIDS[name] = (
                (min(lats) + max(lats)) / 2,
                (min(lngs) + max(lngs)) / 2,
            )
        log.info(f"Loaded {len(SUBURB_CENTROIDS)} suburb centroids from GeoJSON")
    except Exception as e:
        log.warning(f"Failed to load centroids from GeoJSON: {e}")


# Fallback centroids for suburbs not in GeoJSON
# Centroids for coastal/peninsula suburbs are shifted inland to prevent
# jittered points from landing in the water.
FALLBACK_CENTROIDS = {
    # ── CBD & Inner City ──
    "SYDNEY": (-33.8688, 151.2093), "BARANGAROO": (-33.8615, 151.2015),
    "MILLERS POINT": (-33.8580, 151.2040), "THE ROCKS": (-33.8590, 151.2085),
    "DAWES POINT": (-33.8560, 151.2095),
    "CHIPPENDALE": (-33.8893, 151.1989), "HAYMARKET": (-33.8800, 151.2050),
    "ULTIMO": (-33.8792, 151.1970), "PYRMONT": (-33.8710, 151.1945),
    "SURRY HILLS": (-33.8876, 151.2115), "DARLINGHURST": (-33.8764, 151.2178),
    "POTTS POINT": (-33.8710, 151.2230), "ELIZABETH BAY": (-33.8700, 151.2260),
    "RUSHCUTTERS BAY": (-33.8740, 151.2280), "WOOLLOOMOOLOO": (-33.8700, 151.2170),
    "PADDINGTON": (-33.8848, 151.2264), "CENTENNIAL PARK": (-33.8970, 151.2360),
    "MOORE PARK": (-33.8950, 151.2210),
    # ── Inner West ──
    "NEWTOWN": (-33.8979, 151.1793), "CAMPERDOWN": (-33.8891, 151.1779),
    "GLEBE": (-33.8810, 151.1852), "FOREST LODGE": (-33.8820, 151.1810),
    "LEICHHARDT": (-33.8839, 151.1567), "LILYFIELD": (-33.8720, 151.1620),
    "BALMAIN": (-33.8600, 151.1790), "BALMAIN EAST": (-33.8580, 151.1830),
    "BIRCHGROVE": (-33.8530, 151.1760),
    "ROZELLE": (-33.8622, 151.1720), "ANNANDALE": (-33.8835, 151.1658),
    "ENMORE": (-33.9000, 151.1745), "ERSKINEVILLE": (-33.9032, 151.1862),
    "MARRICKVILLE": (-33.9115, 151.1552), "SYDENHAM": (-33.9170, 151.1680),
    "TEMPE": (-33.9230, 151.1640), "ST PETERS": (-33.9072, 151.1895),
    "PETERSHAM": (-33.8950, 151.1545), "STANMORE": (-33.8960, 151.1650),
    "LEWISHAM": (-33.8960, 151.1480), "SUMMER HILL": (-33.8920, 151.1380),
    "DULWICH HILL": (-33.9076, 151.1400), "HABERFIELD": (-33.8820, 151.1380),
    "ASHFIELD": (-33.8880, 151.1247), "CROYDON": (-33.8840, 151.1160),
    "CONCORD": (-33.8590, 151.1030), "DRUMMOYNE": (-33.8560, 151.1510),
    "FIVE DOCK": (-33.8657, 151.1290), "ABBOTSFORD": (-33.8530, 151.1290),
    "CANADA BAY": (-33.8600, 151.1000), "BURWOOD": (-33.8774, 151.1042),
    # ── Eastern Suburbs ──
    "WOOLLAHRA": (-33.8879, 151.2383), "DOUBLE BAY": (-33.8780, 151.2430),
    "BONDI": (-33.8908, 151.2700), "BONDI BEACH": (-33.8920, 151.2720),
    "BONDI JUNCTION": (-33.8913, 151.2531), "QUEENS PARK": (-33.8990, 151.2500),
    "COOGEE": (-33.9210, 151.2560), "RANDWICK": (-33.9147, 151.2427),
    "KINGSFORD": (-33.9208, 151.2272), "MAROUBRA": (-33.9477, 151.2384),
    "BRONTE": (-33.9040, 151.2600), "WAVERLEY": (-33.8960, 151.2530),
    "VAUCLUSE": (-33.8570, 151.2760), "ROSE BAY": (-33.8720, 151.2640),
    "BELLEVUE HILL": (-33.8800, 151.2550), "DOVER HEIGHTS": (-33.8700, 151.2790),
    "POINT PIPER": (-33.8660, 151.2560),
    # ── South Sydney ──
    "REDFERN": (-33.8938, 151.2041), "WATERLOO": (-33.8992, 151.2076),
    "ZETLAND": (-33.9070, 151.2120), "ALEXANDRIA": (-33.9065, 151.2035),
    "BEACONSFIELD": (-33.9120, 151.2020), "EVELEIGH": (-33.8960, 151.1940),
    "ROSEBERY": (-33.9187, 151.2043), "MASCOT": (-33.9260, 151.1925),
    "WOLLI CREEK": (-33.9338, 151.1535), "ARNCLIFFE": (-33.9372, 151.1470),
    "TURRELLA": (-33.9330, 151.1440), "BARDWELL PARK": (-33.9270, 151.1300),
    "BARDWELL VALLEY": (-33.9300, 151.1370),
    # ── Lower North Shore ──  (centroids shifted inland for coastal suburbs)
    "NORTH SYDNEY": (-33.8402, 151.2073), "KIRRIBILLI": (-33.8490, 151.2170),
    "NEUTRAL BAY": (-33.8358, 151.2197), "CREMORNE": (-33.8340, 151.2250),
    "MOSMAN": (-33.8310, 151.2410), "WOLLSTONECRAFT": (-33.8310, 151.1960),
    "WAVERTON": (-33.8390, 151.2000), "MCMAHONS POINT": (-33.8430, 151.2040),
    "CROWS NEST": (-33.8260, 151.2020), "ST LEONARDS": (-33.8230, 151.1960),
    "CAMMERAY": (-33.8210, 151.2120),
    # ── Upper North Shore ──
    "CHATSWOOD": (-33.7970, 151.1819), "LANE COVE": (-33.8163, 151.1661),
    "ARTARMON": (-33.8101, 151.1892), "WILLOUGHBY": (-33.8020, 151.1980),
    "CASTLE COVE": (-33.7890, 151.2080), "NAREMBURN": (-33.8160, 151.2000),
    "LINDFIELD": (-33.7750, 151.1650), "KILLARA": (-33.7660, 151.1620),
    "GORDON": (-33.7570, 151.1530), "PYMBLE": (-33.7450, 151.1420),
    "WAHROONGA": (-33.7180, 151.1170), "TURRAMURRA": (-33.7350, 151.1310),
    "ROSEVILLE": (-33.7840, 151.1770),
    # ── Northern Beaches ──
    "MANLY": (-33.7980, 151.2840), "DEE WHY": (-33.7517, 151.2893),
    "BROOKVALE": (-33.7618, 151.2618), "FRESHWATER": (-33.7770, 151.2850),
    "CURL CURL": (-33.7680, 151.2870), "NARRABEEN": (-33.7160, 151.2980),
    "COLLAROY": (-33.7340, 151.3020), "MONA VALE": (-33.6770, 151.3030),
    "NEWPORT": (-33.6560, 151.3190), "AVALON BEACH": (-33.6350, 151.3280),
    "WARRIEWOOD": (-33.6870, 151.2950), "BALGOWLAH": (-33.7940, 151.2600),
    "SEAFORTH": (-33.7950, 151.2500),
    # ── Parramatta & Western Sydney ──
    "PARRAMATTA": (-33.8148, 151.0042), "HARRIS PARK": (-33.8210, 151.0100),
    "GRANVILLE": (-33.8340, 151.0100), "MERRYLANDS": (-33.8350, 150.9920),
    "AUBURN": (-33.8494, 151.0296), "LIDCOMBE": (-33.8640, 151.0475),
    "HOMEBUSH": (-33.8629, 151.0897), "HOMEBUSH WEST": (-33.8630, 151.0690),
    "STRATHFIELD": (-33.8742, 151.0821),
    "WENTWORTH POINT": (-33.8350, 151.0730), "RHODES": (-33.8310, 151.0870),
    "MEADOWBANK": (-33.8170, 151.0900), "WEST RYDE": (-33.8070, 151.0890),
    "RYDE": (-33.8155, 151.1045), "NORTH RYDE": (-33.7960, 151.1280),
    "MACQUARIE PARK": (-33.7760, 151.1230),
    "GLADESVILLE": (-33.8350, 151.1300), "HUNTERS HILL": (-33.8370, 151.1430),
    "EASTWOOD": (-33.7912, 151.0805), "EPPING": (-33.7730, 151.0823),
    "CARLINGFORD": (-33.7830, 151.0490),
    # ── Canterbury-Bankstown ──
    "CAMPSIE": (-33.9116, 151.1024), "CANTERBURY": (-33.9116, 151.1180),
    "BANKSTOWN": (-33.9173, 151.0335), "PUNCHBOWL": (-33.9280, 151.0540),
    "LAKEMBA": (-33.9190, 151.0750), "BELMORE": (-33.9200, 151.0870),
    "ROSELANDS": (-33.9340, 151.0780), "REVESBY": (-33.9500, 151.0180),
    "PADSTOW": (-33.9520, 151.0370), "BASS HILL": (-33.9030, 150.9920),
    # ── St George ──
    "KOGARAH": (-33.9632, 151.1338), "ROCKDALE": (-33.9533, 151.1368),
    "HURSTVILLE": (-33.9644, 151.1033), "BLAKEHURST": (-33.9890, 151.1100),
    "SANS SOUCI": (-33.9920, 151.1250), "RAMSGATE": (-33.9840, 151.1400),
    "BEXLEY": (-33.9500, 151.1240), "ALLAWAH": (-33.9700, 151.1120),
    "CARLTON": (-33.9680, 151.1210), "PENSHURST": (-33.9600, 151.0900),
    "MORTDALE": (-33.9680, 151.0770), "OATLEY": (-33.9830, 151.0760),
    # ── Sutherland Shire ──
    "CRONULLA": (-34.0540, 151.1520), "MIRANDA": (-34.0364, 151.1015),
    "SUTHERLAND": (-34.0310, 151.0575), "CARINGBAH": (-34.0420, 151.1230),
    "SYLVANIA": (-34.0210, 151.1050), "ENGADINE": (-34.0660, 151.0100),
    "MENAI": (-34.0150, 151.0150), "GYMEA": (-34.0360, 151.0850),
    "JANNALI": (-34.0200, 151.0660), "KIRRAWEE": (-34.0370, 151.0740),
    "PORT HACKING": (-34.0720, 151.1290),
    # ── Hills Shire ──
    "CASTLE HILL": (-33.7300, 151.0038), "BAULKHAM HILLS": (-33.7580, 150.9880),
    "KELLYVILLE": (-33.7200, 150.9600), "ROUSE HILL": (-33.6880, 150.9150),
    "BELLA VISTA": (-33.7400, 150.9560), "NORWEST": (-33.7320, 150.9560),
    # ── Hornsby Shire ──
    "HORNSBY": (-33.7033, 151.0993), "WAITARA": (-33.7100, 151.1050),
    "BEECROFT": (-33.7500, 151.0650), "THORNLEIGH": (-33.7280, 151.0780),
    "PENNANT HILLS": (-33.7380, 151.0720), "NORMANHURST": (-33.7200, 151.0950),
    "ASQUITH": (-33.6900, 151.1060),
    # ── Blacktown / Penrith / Western ──
    "BLACKTOWN": (-33.7686, 150.9053), "PENRITH": (-33.7511, 150.6942),
    "ST MARYS": (-33.7620, 150.7740), "EMU PLAINS": (-33.7470, 150.6590),
    "SEVEN HILLS": (-33.7740, 150.9360), "MOUNT DRUITT": (-33.7680, 150.8220),
    "ROOTY HILL": (-33.7700, 150.8430),
    # ── Liverpool / Fairfield / Campbelltown ──
    "LIVERPOOL": (-33.9200, 150.9238), "FAIRFIELD": (-33.8690, 150.9560),
    "CABRAMATTA": (-33.8930, 150.9370), "CASULA": (-33.9530, 150.9040),
    "GREEN VALLEY": (-33.9060, 150.8730),
    "CAMPBELLTOWN": (-34.0655, 150.8142), "INGLEBURN": (-34.0000, 150.8650),
    "LEUMEAH": (-34.0520, 150.8330),
    # ── Camden / Wollondilly ──
    "CAMDEN": (-34.0540, 150.6960), "ORAN PARK": (-34.0040, 150.7440),
    "NARELLAN": (-34.0430, 150.7280), "GREGORY HILLS": (-34.0280, 150.7700),
    "PICTON": (-34.1800, 150.6050), "TAHMOOR": (-34.2240, 150.5910),
    # ── Blue Mountains ──
    "KATOOMBA": (-33.7150, 150.3120), "SPRINGWOOD": (-33.6990, 150.5640),
    "LEURA": (-33.7140, 150.3350),
    # ── Hawkesbury ──
    "RICHMOND": (-33.5980, 150.7510), "WINDSOR": (-33.6130, 150.8140),
    # ── Bayside ──
    "BOTANY": (-33.9450, 151.1960), "EASTGARDENS": (-33.9420, 151.2250),
    "PAGEWOOD": (-33.9360, 151.2220), "EASTLAKES": (-33.9300, 151.2140),
    "BANKSMEADOW": (-33.9600, 151.2100),
}


# Postcode-area centroids: fallback for suburbs not in centroid tables.
# Maps postcode prefix (first 3 digits) to approximate lat/lng.
POSTCODE_AREA_CENTROIDS = {
    "200": (-33.8688, 151.2093),  # Sydney CBD
    "201": (-33.8740, 151.2210),  # Potts Point / Elizabeth Bay
    "201": (-33.8740, 151.2210),
    "202": (-33.8890, 151.2450),  # Bondi Junction area
    "203": (-33.9100, 151.2400),  # Randwick / Coogee
    "204": (-33.8800, 151.1600),  # Leichhardt / Inner West
    "205": (-33.9300, 151.1500),  # Arncliffe / Wolli Creek
    "206": (-33.8700, 151.2050),  # CBD fringe
    "207": (-33.8792, 151.1970),  # Ultimo
    "208": (-33.8893, 151.1989),  # Chippendale
    "209": (-33.8710, 151.1945),  # Pyrmont
    "210": (-33.8876, 151.2115),  # Surry Hills
    "211": (-33.8350, 151.1300),  # Gladesville / Ryde area
    "212": (-33.8155, 151.1045),  # Ryde
    "213": (-33.7760, 151.1230),  # Macquarie Park
    "214": (-33.8170, 151.0900),  # Meadowbank
    "215": (-33.8148, 151.0042),  # Parramatta
    "216": (-33.9533, 151.1368),  # Rockdale
    "217": (-33.9632, 151.1338),  # Kogarah
    "218": (-33.9187, 151.2043),  # Rosebery
    "219": (-33.9116, 151.1024),  # Campsie
    "220": (-33.9644, 151.1033),  # Hurstville
    "221": (-33.9600, 151.0900),  # Penshurst
    "222": (-34.0364, 151.1015),  # Miranda / Sutherland
    "223": (-34.0540, 151.1520),  # Cronulla
    "225": (-34.0310, 151.0575),  # Sutherland
    "226": (-33.9500, 151.0180),  # Revesby
    "227": (-33.7300, 151.0038),  # Castle Hill
    "228": (-33.7686, 150.9053),  # Blacktown area
    "229": (-33.7580, 150.9880),  # Baulkham Hills
    "206": (-33.8600, 151.2073),
    "207": (-33.8792, 151.1970),
    "213": (-33.7830, 151.0490),  # Carlingford
    "214": (-33.8170, 151.0900),
    "215": (-33.8148, 151.0042),
    "216": (-33.9533, 151.1368),
    "217": (-33.9632, 151.1338),
    "256": (-33.7340, 151.3020),  # Central Coast fringe
    "274": (-33.7511, 150.6942),  # Penrith
    "275": (-33.7620, 150.7740),  # St Marys
    "276": (-33.7470, 150.6590),  # Blue Mountains
    "277": (-33.7150, 150.3120),  # Katoomba
    "256": (-34.0655, 150.8142),  # Campbelltown
}


def _point_in_polygon(lng, lat, polygon):
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def get_centroid_with_jitter(suburb_name, postcode=None):
    """Get lat/lng for suburb with realistic spread within suburb boundary.

    Uses polygon boundary when available to place points within the actual
    suburb area. Falls back to moderate jitter or postcode-area centroid.
    """
    sub = suburb_name.upper().strip()
    centroid = SUBURB_CENTROIDS.get(sub) or FALLBACK_CENTROIDS.get(sub)

    # Fallback: use postcode prefix to get approximate location
    if not centroid and postcode:
        pc = str(postcode).strip()
        centroid = POSTCODE_AREA_CENTROIDS.get(pc[:3])

    if not centroid:
        return None, None

    lat, lng = centroid

    # Try to place within suburb polygon if available
    polygon = SUBURB_POLYGONS.get(sub)
    if polygon:
        plngs = [p[0] for p in polygon]
        plats = [p[1] for p in polygon]
        min_lng, max_lng = min(plngs), max(plngs)
        min_lat, max_lat = min(plats), max(plats)
        for _ in range(30):
            rlng = random.uniform(min_lng, max_lng)
            rlat = random.uniform(min_lat, max_lat)
            if _point_in_polygon(rlng, rlat, polygon):
                return round(rlat, 6), round(rlng, 6)
        # Fallback: reduced bbox jitter
        range_lat = (max_lat - min_lat) * 0.35
        range_lng = (max_lng - min_lng) * 0.35
        return (round(lat + random.uniform(-range_lat, range_lat), 6),
                round(lng + random.uniform(-range_lng, range_lng), 6))

    # No polygon: moderate jitter (~330m)
    jitter_lat = random.uniform(-0.003, 0.003)
    jitter_lng = random.uniform(-0.003, 0.003)
    return round(lat + jitter_lat, 6), round(lng + jitter_lng, 6)


# ── Download NSW VG PSI data ─────────────────────────────────────────────────
PSI_BASE_URL = "https://www.valuergeneral.nsw.gov.au/_psi"

def get_weekly_urls(weeks_back=4, from_start_of_year=False):
    """
    Return list of (label, url) for recent weekly ZIPs.
    NSW VG publishes weekly data on Mondays.
    URL format: https://www.valuergeneral.nsw.gov.au/_psi/weekly/YYYYMMDD.zip

    If from_start_of_year=True, generate URLs from the first Monday of the
    current year up to now (used in full mode to cover the current year which
    has no yearly file yet).
    """
    urls = []
    today = date.today()

    # Find the most recent Monday
    days_since_monday = today.weekday()  # 0=Mon, 6=Sun
    last_monday = today - timedelta(days=days_since_monday)

    if from_start_of_year:
        # Generate all weekly URLs from the first Monday of the current year
        # NSW VG weekly files typically start on the first Monday of January
        jan1 = date(today.year, 1, 1)
        first_monday = jan1 + timedelta(days=(7 - jan1.weekday()) % 7)
        if first_monday > jan1 + timedelta(days=6):
            first_monday = jan1  # Jan 1 is already a Monday
        target = first_monday
        while target <= last_monday:
            date_str = target.strftime("%Y%m%d")
            url = f"{PSI_BASE_URL}/weekly/{date_str}.zip"
            urls.append((f"weekly-{date_str}", url))
            target += timedelta(weeks=1)
    else:
        for i in range(weeks_back):
            target = last_monday - timedelta(weeks=i)
            date_str = target.strftime("%Y%m%d")
            url = f"{PSI_BASE_URL}/weekly/{date_str}.zip"
            urls.append((f"weekly-{date_str}", url))

    return urls


def get_yearly_urls():
    """
    Return list of (label, url) for yearly data ZIPs.
    Used for initial backfill of historical data (past 2 years).
    URL format: https://www.valuergeneral.nsw.gov.au/_psi/yearly/YYYY.zip

    Only fetches COMPLETED years — the current year has no yearly file
    (data is only available as weekly files until the year ends).
    """
    current_year = date.today().year
    urls = []
    # Only previous years (current year is not yet complete)
    for year in [current_year - 2, current_year - 1]:
        url = f"{PSI_BASE_URL}/yearly/{year}.zip"
        urls.append((f"yearly-{year}", url))
    return urls


def download_and_parse_zip(label, url, cutoff_date):
    """Download a ZIP, extract and parse DAT files. Returns list of sale dicts."""
    log.info(f"Downloading {label} from {url}")
    properties = []

    try:
        response = requests.get(url, timeout=180, stream=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning(f"Failed to download {label}: {e}")
        return properties

    size_mb = len(response.content) / 1024 / 1024
    log.info(f"Downloaded {size_mb:.1f} MB for {label}")

    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            dat_files = [n for n in zf.namelist() if n.lower().endswith(".dat")]
            log.info(f"Found {len(dat_files)} DAT files in {label}")

            for dat_name in dat_files:
                with zf.open(dat_name) as f:
                    lines = f.read().decode("latin-1", errors="replace").splitlines()

                parsed = 0
                for line in lines:
                    row = parse_vg_line(line)
                    if not row:
                        continue
                    if not is_valid_sale(row):
                        continue

                    # contract_date = date of exchange (成交日期), when buyer & seller sign.
                    # settlement_date = later administrative transfer date (usually +42 days).
                    # We use contract_date as it reflects actual market timing.
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
                        address = "Unknown Address"

                    try:
                        area = float(row.get("area", 0) or 0)
                    except ValueError:
                        area = 0

                    prop_type = classify_property_type(
                        row.get("strata_lot_number"),
                        row.get("zoning"),
                        row.get("primary_purpose"),
                        row.get("nature_of_property"),
                        area,
                    )

                    postcode_str = str(row.get("post_code", "") or "").strip()
                    lat, lng = get_centroid_with_jitter(locality, postcode_str)
                    if lat is None:
                        # Unknown suburb — skip (not in our centroid tables)
                        continue

                    # Unique ID from dealing number + property ID
                    uid_src = f"{row.get('dealing_number', '')}-{row.get('property_id', '')}-{row.get('sale_counter', '')}"
                    uid = hashlib.md5(uid_src.encode()).hexdigest()[:12]

                    zoning = str(row.get("zoning", "") or "").strip()

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
                        "zoning": zoning if zoning else None,
                    })
                    parsed += 1

                if parsed:
                    log.info(f"  {dat_name}: {parsed} valid Sydney sales")

    except zipfile.BadZipFile as e:
        log.warning(f"Bad ZIP for {label}: {e}")

    log.info(f"  → {len(properties)} total valid Sydney sales from {label}")
    return properties


# ── Download suburb GeoJSON ──────────────────────────────────────────────────
SUBURBS_GEOJSON_URL = (
    "https://raw.githubusercontent.com/tonywr71/GeoJson-Data/master/suburb-10-nsw.geojson"
)


# Greater Sydney bounding box for GeoJSON filtering
SYDNEY_BOUNDS = {
    "lat_min": -34.35,  # South (Wollondilly / Campbelltown)
    "lat_max": -33.40,  # North (Hawkesbury / Hornsby)
    "lng_min": 150.20,  # West (Blue Mountains)
    "lng_max": 151.55,  # East (coast)
}


def download_suburb_geojson():
    """Download NSW suburb boundaries and filter to Greater Sydney area."""
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
        SUBURBS_FILE.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        return False

    # Filter to Greater Sydney suburbs using geographic bounding box
    # This captures all suburbs in the Greater Sydney area automatically
    known_names = set(FALLBACK_CENTROIDS.keys())
    sydney_features = []

    for f in geojson.get("features", []):
        name = (
            f.get("properties", {}).get("LOC_NAME", "")
            or f.get("properties", {}).get("suburb", "")
        ).upper().strip()
        if not name:
            continue

        # Include if suburb name is in our known list
        if name in known_names:
            sydney_features.append(f)
            continue

        # Otherwise, include if the suburb's centroid falls within Greater Sydney bounds
        coords = f.get("geometry", {}).get("coordinates")
        if not coords:
            continue
        try:
            all_coords = []
            def flatten(arr):
                if isinstance(arr[0], (int, float)):
                    all_coords.append(arr)
                else:
                    for sub in arr:
                        flatten(sub)
            flatten(coords)
            if not all_coords:
                continue
            avg_lng = sum(c[0] for c in all_coords) / len(all_coords)
            avg_lat = sum(c[1] for c in all_coords) / len(all_coords)
            if (SYDNEY_BOUNDS["lat_min"] <= avg_lat <= SYDNEY_BOUNDS["lat_max"]
                    and SYDNEY_BOUNDS["lng_min"] <= avg_lng <= SYDNEY_BOUNDS["lng_max"]):
                sydney_features.append(f)
        except (IndexError, TypeError, ZeroDivisionError):
            continue

    filtered = {
        "type": "FeatureCollection",
        "features": sydney_features,
    }

    SUBURBS_FILE.write_text(json.dumps(filtered, separators=(",", ":")))
    log.info(f"Saved {len(sydney_features)} Sydney suburb polygons to {SUBURBS_FILE}")
    return True


# ── Merge with existing data ─────────────────────────────────────────────────
def load_existing_properties():
    """Load existing properties from the JSON file, if any."""
    if not PROPERTIES_FILE.exists():
        return []
    try:
        with open(PROPERTIES_FILE) as f:
            data = json.load(f)
        return data.get("properties", [])
    except (json.JSONDecodeError, KeyError):
        return []


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch NSW VG property sales data")
    parser.add_argument(
        "--weekly", action="store_true",
        help="Only fetch the latest weekly data (incremental update)"
    )
    parser.add_argument(
        "--weeks", type=int, default=8,
        help="Number of weekly ZIPs to try downloading (default: 8)"
    )
    args = parser.parse_args()

    random.seed(42)  # reproducible jitter

    # We keep data from the last 2 years
    cutoff = date.today() - timedelta(days=730)

    all_properties = []

    # 1. Download suburb GeoJSON (only needed once)
    download_suburb_geojson()

    # 2. Load centroids from GeoJSON for better coordinate mapping
    load_centroids_from_geojson()

    if args.weekly:
        # ── Incremental mode: weekly data + merge with existing ──────────
        log.info("=== Incremental weekly update mode ===")

        # Load existing data
        existing = load_existing_properties()
        log.info(f"Loaded {len(existing)} existing properties")

        # Download latest weekly ZIPs
        for label, url in get_weekly_urls(weeks_back=args.weeks):
            props = download_and_parse_zip(label, url, cutoff)
            all_properties.extend(props)

        # Merge: new data overwrites old for same ID
        existing_by_id = {p["id"]: p for p in existing}
        for p in all_properties:
            existing_by_id[p["id"]] = p
        all_properties = list(existing_by_id.values())

    else:
        # ── Full mode: yearly + weekly backfill ──────────────────────────
        log.info("=== Full data fetch mode ===")

        # First download yearly data for completed years
        for label, url in get_yearly_urls():
            props = download_and_parse_zip(label, url, cutoff)
            all_properties.extend(props)

        # Then download ALL weekly data for the current year
        # (no yearly file exists for the current year)
        for label, url in get_weekly_urls(from_start_of_year=True):
            props = download_and_parse_zip(label, url, cutoff)
            all_properties.extend(props)

    # ── Fallback to sample data if nothing downloaded ────────────────────
    use_sample = False
    if not all_properties:
        log.warning("No properties fetched! Check network access and data URLs.")
        log.warning("Generating sample data as fallback…")
        from generate_sample import generate_sample_data
        all_properties = generate_sample_data()
        use_sample = True

    # 3. Deduplicate (by ID, keep the latest entry)
    seen = {}
    for p in all_properties:
        key = p["id"]
        if key not in seen or p["date"] > seen[key]["date"]:
            seen[key] = p
    unique = list(seen.values())

    # 4. Remove properties older than 2 years
    unique = [p for p in unique if p["date"] >= cutoff.isoformat()]

    # 5. Sort by date descending
    unique.sort(key=lambda p: p["date"], reverse=True)

    # 6. Write output
    output = {
        "lastUpdated": date.today().isoformat(),
        "totalCount": len(unique),
        "dataSource": "NSW Valuer General - Property Sales Information",
        "properties": unique,
    }
    if use_sample:
        output["note"] = "SAMPLE DATA — for development/demo only. Run fetch_data.py with network access for real NSW VG data."

    PROPERTIES_FILE.write_text(json.dumps(output, separators=(",", ":")))
    log.info(f"✅ Saved {len(unique)} properties to {PROPERTIES_FILE}")
    log.info(f"   Suburbs covered: {len({p['suburb'] for p in unique})}")
    log.info(f"   Date range: {unique[-1]['date'] if unique else 'N/A'} → {unique[0]['date'] if unique else 'N/A'}")

    # Print suburb summary
    suburb_counts = {}
    for p in unique:
        suburb_counts[p["suburb"]] = suburb_counts.get(p["suburb"], 0) + 1
    top_15 = sorted(suburb_counts.items(), key=lambda x: -x[1])[:15]
    log.info("Top 15 suburbs by transaction count:")
    for sub, count in top_15:
        log.info(f"  {sub}: {count}")

    # Type breakdown
    type_counts = {}
    for p in unique:
        type_counts[p["type"]] = type_counts.get(p["type"], 0) + 1
    log.info("Property type breakdown:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        log.info(f"  {t}: {c}")


if __name__ == "__main__":
    main()
