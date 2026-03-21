#!/usr/bin/env python3
"""
Sample data generator for development and testing.
Generates realistic-looking Sydney property sales data.

Run standalone:  python generate_sample.py
Or import:       from generate_sample import generate_sample_data
"""

import json
import random
import hashlib
from datetime import date, timedelta
from pathlib import Path

# ── Suburb polygon data for realistic coordinate distribution ────────────────
_SUBURB_POLYGONS = {}  # loaded lazily: suburb_name -> list of (lng, lat) tuples


def _load_suburb_polygons():
    """Load suburb boundary polygons from suburbs.geojson."""
    if _SUBURB_POLYGONS:
        return
    geojson_path = Path(__file__).parent.parent / "public" / "data" / "suburbs.geojson"
    if not geojson_path.exists():
        return
    data = json.loads(geojson_path.read_text())
    for feat in data.get("features", []):
        name = (feat.get("properties", {}).get("suburb") or
                feat.get("properties", {}).get("LOC_NAME", "")).upper().strip()
        coords = feat.get("geometry", {}).get("coordinates")
        if name and coords:
            # Handle Polygon (coords[0]) and MultiPolygon (coords[0][0])
            ring = coords[0] if feat["geometry"]["type"] == "Polygon" else coords[0][0]
            _SUBURB_POLYGONS[name] = ring  # list of [lng, lat]


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


def _random_point_in_suburb(suburb_name, centroid_lat, centroid_lng):
    """Generate a random point within the suburb polygon, or with scaled jitter."""
    _load_suburb_polygons()
    polygon = _SUBURB_POLYGONS.get(suburb_name.upper().strip())

    if polygon:
        lngs = [p[0] for p in polygon]
        lats = [p[1] for p in polygon]
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)
        # Try to place point inside polygon (rejection sampling)
        for _ in range(30):
            lng = random.uniform(min_lng, max_lng)
            lat = random.uniform(min_lat, max_lat)
            if _point_in_polygon(lng, lat, polygon):
                return round(lat, 6), round(lng, 6)
        # Fallback: use bbox center with reduced jitter
        range_lat = (max_lat - min_lat) * 0.35
        range_lng = (max_lng - min_lng) * 0.35
        return (round(centroid_lat + random.uniform(-range_lat, range_lat), 6),
                round(centroid_lng + random.uniform(-range_lng, range_lng), 6))

    # No polygon available: use moderate jitter (~330m)
    return (round(centroid_lat + random.uniform(-0.003, 0.003), 6),
            round(centroid_lng + random.uniform(-0.003, 0.003), 6))

# ── Price ranges per suburb and type ─────────────────────────────────────────
SUBURB_PROFILES = {
    # ── CBD & Inner City ──
    "SYDNEY":         {"Unit": (800_000, 1_600_000), "Commercial": (1_000_000, 3_000_000)},
    "BARANGAROO":     {"Unit": (1_200_000, 2_500_000)},
    "CHIPPENDALE":    {"Unit": (600_000, 1_100_000), "House": (1_500_000, 2_800_000), "Townhouse": (1_000_000, 1_600_000)},
    "HAYMARKET":      {"Unit": (700_000, 1_300_000), "Commercial": (800_000, 2_000_000)},
    "ULTIMO":         {"Unit": (700_000, 1_200_000), "House": (1_500_000, 2_500_000), "Townhouse": (1_000_000, 1_800_000)},
    "PYRMONT":        {"Unit": (800_000, 1_500_000), "Townhouse": (1_200_000, 2_000_000)},
    "SURRY HILLS":    {"Unit": (750_000, 1_300_000), "House": (2_000_000, 3_500_000), "Townhouse": (1_400_000, 2_200_000)},
    "DARLINGHURST":   {"Unit": (700_000, 1_400_000), "House": (2_500_000, 5_000_000)},
    "POTTS POINT":    {"Unit": (600_000, 1_300_000)},
    "ELIZABETH BAY":  {"Unit": (550_000, 1_200_000)},
    "WOOLLOOMOOLOO":  {"Unit": (600_000, 1_100_000)},
    # ── Inner West ──
    "NEWTOWN":        {"Unit": (650_000, 1_100_000), "House": (1_500_000, 2_800_000), "Townhouse": (1_000_000, 1_700_000)},
    "CAMPERDOWN":     {"Unit": (600_000, 1_000_000), "House": (1_500_000, 2_600_000)},
    "GLEBE":          {"Unit": (700_000, 1_200_000), "House": (1_800_000, 3_000_000)},
    "FOREST LODGE":   {"Unit": (650_000, 1_100_000), "House": (1_700_000, 2_800_000)},
    "LEICHHARDT":     {"Unit": (600_000, 1_000_000), "House": (1_400_000, 2_500_000), "Townhouse": (900_000, 1_600_000)},
    "LILYFIELD":      {"Unit": (650_000, 1_100_000), "House": (1_600_000, 2_800_000)},
    "BALMAIN":        {"Unit": (800_000, 1_400_000), "House": (2_500_000, 4_500_000)},
    "BIRCHGROVE":     {"Unit": (850_000, 1_500_000), "House": (2_800_000, 5_000_000)},
    "ROZELLE":        {"Unit": (750_000, 1_200_000), "House": (2_000_000, 3_500_000)},
    "ANNANDALE":      {"Unit": (600_000, 1_000_000), "House": (1_800_000, 3_200_000)},
    "ENMORE":         {"Unit": (600_000, 1_000_000), "House": (1_500_000, 2_600_000)},
    "ERSKINEVILLE":   {"Unit": (650_000, 1_100_000), "House": (1_600_000, 2_800_000)},
    "MARRICKVILLE":   {"Unit": (550_000, 950_000), "House": (1_400_000, 2_500_000), "Townhouse": (900_000, 1_500_000)},
    "SYDENHAM":       {"Unit": (500_000, 850_000), "House": (1_300_000, 2_200_000)},
    "TEMPE":          {"Unit": (500_000, 850_000), "House": (1_300_000, 2_200_000)},
    "ST PETERS":      {"Unit": (550_000, 900_000), "House": (1_400_000, 2_500_000)},
    "PETERSHAM":      {"Unit": (550_000, 950_000), "House": (1_500_000, 2_500_000)},
    "STANMORE":       {"Unit": (600_000, 1_000_000), "House": (1_600_000, 2_800_000)},
    "LEWISHAM":       {"Unit": (500_000, 900_000), "House": (1_400_000, 2_400_000)},
    "SUMMER HILL":    {"Unit": (550_000, 950_000), "House": (1_500_000, 2_600_000)},
    "DULWICH HILL":   {"Unit": (500_000, 900_000), "House": (1_500_000, 2_600_000)},
    "HABERFIELD":     {"Unit": (650_000, 1_100_000), "House": (2_000_000, 3_500_000)},
    "ASHFIELD":       {"Unit": (500_000, 900_000), "House": (1_500_000, 2_500_000)},
    "CROYDON":        {"Unit": (500_000, 900_000), "House": (1_500_000, 2_500_000)},
    "CONCORD":        {"Unit": (600_000, 1_100_000), "House": (2_000_000, 3_500_000)},
    "DRUMMOYNE":      {"Unit": (700_000, 1_300_000), "House": (2_200_000, 4_000_000)},
    "FIVE DOCK":      {"Unit": (600_000, 1_100_000), "House": (1_800_000, 3_200_000)},
    "BURWOOD":        {"Unit": (550_000, 1_000_000), "House": (1_800_000, 3_200_000)},
    # ── Eastern Suburbs ──
    "PADDINGTON":     {"Unit": (900_000, 1_600_000), "House": (2_500_000, 5_000_000), "Townhouse": (1_500_000, 2_800_000)},
    "WOOLLAHRA":      {"Unit": (1_000_000, 1_800_000), "House": (3_000_000, 7_000_000)},
    "DOUBLE BAY":     {"Unit": (1_200_000, 2_500_000), "House": (5_000_000, 12_000_000)},
    "BELLEVUE HILL":  {"Unit": (1_100_000, 2_200_000), "House": (5_000_000, 15_000_000)},
    "ROSE BAY":       {"Unit": (1_000_000, 2_000_000), "House": (4_000_000, 10_000_000)},
    "VAUCLUSE":       {"Unit": (1_200_000, 2_500_000), "House": (5_000_000, 15_000_000)},
    "BONDI":          {"Unit": (1_000_000, 1_800_000), "House": (3_000_000, 5_500_000)},
    "BONDI BEACH":    {"Unit": (1_100_000, 2_000_000), "House": (3_500_000, 7_000_000)},
    "BONDI JUNCTION": {"Unit": (800_000, 1_400_000), "House": (2_500_000, 4_500_000), "Townhouse": (1_200_000, 2_200_000)},
    "BRONTE":         {"Unit": (900_000, 1_600_000), "House": (3_000_000, 6_000_000)},
    "WAVERLEY":       {"Unit": (800_000, 1_400_000), "House": (2_500_000, 4_500_000)},
    "COOGEE":         {"Unit": (900_000, 1_600_000), "House": (2_500_000, 5_000_000)},
    "RANDWICK":       {"Unit": (700_000, 1_300_000), "House": (2_000_000, 3_800_000), "Townhouse": (1_000_000, 2_000_000)},
    "KINGSFORD":      {"Unit": (550_000, 900_000), "House": (1_500_000, 2_500_000)},
    "MAROUBRA":       {"Unit": (600_000, 1_000_000), "House": (1_800_000, 3_000_000)},
    "CENTENNIAL PARK":{"Unit": (900_000, 1_800_000), "House": (3_000_000, 6_000_000)},
    # ── South Sydney ──
    "REDFERN":        {"Unit": (600_000, 1_100_000), "House": (1_500_000, 2_800_000)},
    "WATERLOO":       {"Unit": (550_000, 950_000), "House": (1_600_000, 2_800_000)},
    "ZETLAND":        {"Unit": (600_000, 1_000_000), "Townhouse": (950_000, 1_600_000)},
    "ALEXANDRIA":     {"Unit": (600_000, 1_100_000), "House": (1_600_000, 3_000_000), "Townhouse": (1_000_000, 1_800_000)},
    "BEACONSFIELD":   {"Unit": (600_000, 1_000_000), "House": (1_500_000, 2_700_000)},
    "ROSEBERY":       {"Unit": (600_000, 1_050_000), "Townhouse": (900_000, 1_500_000)},
    "MASCOT":         {"Unit": (550_000, 950_000), "Townhouse": (800_000, 1_400_000)},
    "WOLLI CREEK":    {"Unit": (450_000, 800_000), "Townhouse": (700_000, 1_200_000)},
    "ARNCLIFFE":      {"Unit": (450_000, 800_000), "House": (1_200_000, 2_000_000)},
    # ── Lower North Shore ──
    "NORTH SYDNEY":   {"Unit": (700_000, 1_300_000), "House": (2_500_000, 4_500_000)},
    "KIRRIBILLI":     {"Unit": (1_000_000, 2_500_000), "House": (4_000_000, 10_000_000)},
    "NEUTRAL BAY":    {"Unit": (800_000, 1_500_000), "House": (2_500_000, 5_000_000)},
    "CREMORNE":       {"Unit": (900_000, 1_600_000), "House": (3_000_000, 5_500_000)},
    "MOSMAN":         {"Unit": (1_200_000, 2_200_000), "House": (4_000_000, 9_000_000)},
    "CROWS NEST":     {"Unit": (700_000, 1_200_000), "House": (2_200_000, 4_000_000)},
    "ST LEONARDS":    {"Unit": (650_000, 1_100_000)},
    "WOLLSTONECRAFT": {"Unit": (650_000, 1_100_000), "House": (2_000_000, 3_500_000)},
    "WAVERTON":       {"Unit": (700_000, 1_200_000), "House": (2_200_000, 4_000_000)},
    # ── Upper North Shore ──
    "CHATSWOOD":      {"Unit": (750_000, 1_300_000), "House": (2_000_000, 3_500_000), "Townhouse": (1_100_000, 1_900_000)},
    "LANE COVE":      {"Unit": (600_000, 1_100_000), "House": (1_800_000, 3_500_000)},
    "ARTARMON":       {"Unit": (700_000, 1_200_000), "House": (2_000_000, 3_500_000)},
    "WILLOUGHBY":     {"Unit": (650_000, 1_100_000), "House": (2_000_000, 3_500_000)},
    "GORDON":         {"Unit": (650_000, 1_100_000), "House": (2_200_000, 4_000_000)},
    "PYMBLE":         {"Unit": (600_000, 1_000_000), "House": (2_000_000, 3_800_000)},
    "LINDFIELD":      {"Unit": (600_000, 1_100_000), "House": (2_200_000, 4_000_000)},
    "KILLARA":        {"Unit": (700_000, 1_200_000), "House": (2_500_000, 4_500_000)},
    "ROSEVILLE":      {"Unit": (650_000, 1_100_000), "House": (2_200_000, 3_800_000)},
    "WAHROONGA":      {"Unit": (600_000, 1_000_000), "House": (2_000_000, 3_500_000)},
    "TURRAMURRA":     {"Unit": (600_000, 1_000_000), "House": (1_800_000, 3_200_000)},
    # ── Northern Beaches ──
    "MANLY":          {"Unit": (1_100_000, 2_000_000), "House": (3_500_000, 7_500_000)},
    "DEE WHY":        {"Unit": (700_000, 1_200_000), "House": (2_000_000, 3_500_000)},
    "BROOKVALE":      {"Unit": (650_000, 1_100_000), "House": (1_800_000, 3_200_000)},
    "FRESHWATER":     {"Unit": (800_000, 1_400_000), "House": (2_500_000, 4_500_000)},
    "MONA VALE":      {"Unit": (750_000, 1_300_000), "House": (2_000_000, 3_800_000)},
    # ── Parramatta & Western ──
    "PARRAMATTA":     {"Unit": (400_000, 750_000), "House": (1_000_000, 1_800_000), "Townhouse": (700_000, 1_200_000)},
    "STRATHFIELD":    {"Unit": (550_000, 950_000), "House": (1_600_000, 3_000_000)},
    "HOMEBUSH":       {"Unit": (500_000, 850_000), "House": (1_400_000, 2_500_000)},
    "RHODES":         {"Unit": (600_000, 1_100_000), "Townhouse": (900_000, 1_500_000)},
    "MEADOWBANK":     {"Unit": (550_000, 950_000), "House": (1_400_000, 2_400_000)},
    "RYDE":           {"Unit": (550_000, 1_000_000), "House": (1_600_000, 2_800_000), "Townhouse": (900_000, 1_500_000)},
    "WEST RYDE":      {"Unit": (500_000, 900_000), "House": (1_400_000, 2_500_000)},
    "EASTWOOD":       {"Unit": (550_000, 950_000), "House": (1_600_000, 2_800_000)},
    "EPPING":         {"Unit": (550_000, 1_000_000), "House": (1_800_000, 3_200_000), "Townhouse": (900_000, 1_600_000)},
    "MACQUARIE PARK": {"Unit": (500_000, 900_000)},
    "GLADESVILLE":    {"Unit": (600_000, 1_100_000), "House": (1_800_000, 3_200_000)},
    "HUNTERS HILL":   {"Unit": (900_000, 1_500_000), "House": (3_000_000, 6_000_000)},
    "LIDCOMBE":       {"Unit": (450_000, 800_000), "House": (1_000_000, 1_800_000), "Townhouse": (700_000, 1_200_000)},
    "WENTWORTH POINT":{"Unit": (500_000, 900_000)},
    "CARLINGFORD":    {"Unit": (550_000, 950_000), "House": (1_600_000, 2_800_000), "Townhouse": (850_000, 1_500_000)},
    "AUBURN":         {"Unit": (380_000, 650_000), "House": (900_000, 1_600_000)},
    # ── Canterbury-Bankstown ──
    "CAMPSIE":        {"Unit": (400_000, 700_000), "House": (1_100_000, 1_900_000)},
    "CANTERBURY":     {"Unit": (400_000, 700_000), "House": (1_200_000, 2_000_000)},
    "BANKSTOWN":      {"Unit": (380_000, 650_000), "House": (900_000, 1_600_000)},
    "LAKEMBA":        {"Unit": (350_000, 600_000), "House": (900_000, 1_500_000)},
    "PUNCHBOWL":      {"Unit": (380_000, 620_000), "House": (900_000, 1_500_000)},
    "BELMORE":        {"Unit": (380_000, 650_000), "House": (1_000_000, 1_700_000)},
    # ── St George ──
    "HURSTVILLE":     {"Unit": (500_000, 900_000), "House": (1_400_000, 2_500_000)},
    "KOGARAH":        {"Unit": (500_000, 900_000), "House": (1_300_000, 2_200_000)},
    "ROCKDALE":       {"Unit": (500_000, 850_000), "House": (1_200_000, 2_200_000)},
    "BEXLEY":         {"Unit": (450_000, 800_000), "House": (1_200_000, 2_000_000)},
    "PENSHURST":      {"Unit": (480_000, 850_000), "House": (1_300_000, 2_200_000)},
    # ── Sutherland Shire ──
    "CRONULLA":       {"Unit": (700_000, 1_300_000), "House": (2_000_000, 4_000_000)},
    "MIRANDA":        {"Unit": (550_000, 900_000), "House": (1_200_000, 2_200_000)},
    "SUTHERLAND":     {"Unit": (500_000, 850_000), "House": (1_100_000, 2_000_000)},
    "CARINGBAH":      {"Unit": (550_000, 950_000), "House": (1_300_000, 2_300_000)},
    # ── Hills & Hornsby ──
    "CASTLE HILL":    {"Unit": (600_000, 1_100_000), "House": (1_600_000, 3_000_000), "Townhouse": (850_000, 1_500_000)},
    "BAULKHAM HILLS": {"Unit": (550_000, 950_000), "House": (1_400_000, 2_600_000), "Townhouse": (800_000, 1_400_000)},
    "KELLYVILLE":     {"Unit": (500_000, 900_000), "House": (1_200_000, 2_200_000), "Townhouse": (750_000, 1_300_000)},
    "HORNSBY":        {"Unit": (500_000, 900_000), "House": (1_400_000, 2_500_000)},
    "PENNANT HILLS":  {"Unit": (500_000, 900_000), "House": (1_500_000, 2_800_000)},
    # ── Outer West / South West ──
    "BLACKTOWN":      {"Unit": (350_000, 600_000), "House": (700_000, 1_200_000), "Townhouse": (550_000, 900_000)},
    "PENRITH":        {"Unit": (350_000, 600_000), "House": (650_000, 1_100_000)},
    "LIVERPOOL":      {"Unit": (350_000, 600_000), "House": (700_000, 1_300_000)},
    "CAMPBELLTOWN":   {"Unit": (350_000, 550_000), "House": (650_000, 1_100_000)},
    "FAIRFIELD":      {"Unit": (330_000, 550_000), "House": (700_000, 1_200_000)},
}

STREET_NAMES = [
    "George St", "Pitt St", "King St", "Park Rd", "Oxford St",
    "Crown St", "Bourke St", "Elizabeth St", "William St", "Victoria Rd",
    "Pacific Hwy", "Military Rd", "Sydney Rd", "Church St", "Station St",
    "Forest Rd", "High St", "New South Head Rd", "Princes Hwy", "Canterbury Rd",
    "Carrington Rd", "Edgecliff Rd", "Darling St", "Glebe Point Rd", "Enmore Rd",
    "King Street", "Campbell Pde", "Arden St", "Coogee Bay Rd", "Avoca St",
]

POSTCODE_MAP = {
    # CBD & Inner City
    "SYDNEY": "2000", "BARANGAROO": "2000", "CHIPPENDALE": "2008",
    "HAYMARKET": "2000", "ULTIMO": "2007", "PYRMONT": "2009",
    "SURRY HILLS": "2010", "DARLINGHURST": "2010", "POTTS POINT": "2011",
    "ELIZABETH BAY": "2011", "WOOLLOOMOOLOO": "2011",
    # Inner West
    "NEWTOWN": "2042", "CAMPERDOWN": "2050", "GLEBE": "2037",
    "FOREST LODGE": "2037", "LEICHHARDT": "2040", "LILYFIELD": "2040",
    "BALMAIN": "2041", "BIRCHGROVE": "2041", "ROZELLE": "2039",
    "ANNANDALE": "2038", "ENMORE": "2042", "ERSKINEVILLE": "2043",
    "MARRICKVILLE": "2204", "SYDENHAM": "2044", "TEMPE": "2044",
    "ST PETERS": "2044", "PETERSHAM": "2049", "STANMORE": "2048",
    "LEWISHAM": "2049", "SUMMER HILL": "2130", "DULWICH HILL": "2203",
    "HABERFIELD": "2045", "ASHFIELD": "2131", "CROYDON": "2132",
    "CONCORD": "2137", "DRUMMOYNE": "2047", "FIVE DOCK": "2046",
    "BURWOOD": "2134",
    # Eastern Suburbs
    "PADDINGTON": "2021", "WOOLLAHRA": "2025", "DOUBLE BAY": "2028",
    "BELLEVUE HILL": "2023", "ROSE BAY": "2029", "VAUCLUSE": "2030",
    "BONDI": "2026", "BONDI BEACH": "2026", "BONDI JUNCTION": "2022",
    "BRONTE": "2024", "WAVERLEY": "2024", "COOGEE": "2034",
    "RANDWICK": "2031", "KINGSFORD": "2032", "MAROUBRA": "2035",
    "CENTENNIAL PARK": "2021",
    # South Sydney
    "REDFERN": "2016", "WATERLOO": "2017", "ZETLAND": "2017",
    "ALEXANDRIA": "2015", "BEACONSFIELD": "2015", "ROSEBERY": "2018",
    "MASCOT": "2020", "WOLLI CREEK": "2205", "ARNCLIFFE": "2205",
    # Lower North Shore
    "NORTH SYDNEY": "2060", "KIRRIBILLI": "2061", "NEUTRAL BAY": "2089",
    "CREMORNE": "2090", "MOSMAN": "2088", "CROWS NEST": "2065",
    "ST LEONARDS": "2065", "WOLLSTONECRAFT": "2065", "WAVERTON": "2060",
    # Upper North Shore
    "CHATSWOOD": "2067", "LANE COVE": "2066", "ARTARMON": "2064",
    "WILLOUGHBY": "2068", "GORDON": "2072", "PYMBLE": "2073",
    "LINDFIELD": "2070", "KILLARA": "2071", "ROSEVILLE": "2069",
    "WAHROONGA": "2076", "TURRAMURRA": "2074",
    # Northern Beaches
    "MANLY": "2095", "DEE WHY": "2099", "BROOKVALE": "2100",
    "FRESHWATER": "2096", "MONA VALE": "2103",
    # Parramatta & Western
    "PARRAMATTA": "2150", "STRATHFIELD": "2135", "HOMEBUSH": "2140",
    "RHODES": "2138", "MEADOWBANK": "2114", "RYDE": "2112",
    "WEST RYDE": "2114", "EASTWOOD": "2122", "EPPING": "2121",
    "MACQUARIE PARK": "2113", "GLADESVILLE": "2111", "HUNTERS HILL": "2110",
    "LIDCOMBE": "2141", "WENTWORTH POINT": "2127", "CARLINGFORD": "2118",
    "AUBURN": "2144",
    # Canterbury-Bankstown
    "CAMPSIE": "2194", "CANTERBURY": "2193", "BANKSTOWN": "2200",
    "LAKEMBA": "2195", "PUNCHBOWL": "2196", "BELMORE": "2192",
    # St George
    "HURSTVILLE": "2220", "KOGARAH": "2217", "ROCKDALE": "2216",
    "BEXLEY": "2207", "PENSHURST": "2222",
    # Sutherland
    "CRONULLA": "2230", "MIRANDA": "2228", "SUTHERLAND": "2232",
    "CARINGBAH": "2229",
    # Hills & Hornsby
    "CASTLE HILL": "2154", "BAULKHAM HILLS": "2153",
    "KELLYVILLE": "2155", "HORNSBY": "2077", "PENNANT HILLS": "2120",
    # Outer
    "BLACKTOWN": "2148", "PENRITH": "2750", "LIVERPOOL": "2170",
    "CAMPBELLTOWN": "2560", "FAIRFIELD": "2165",
}

CENTROID_DATA = {
    # CBD & Inner City
    "SYDNEY": (-33.8688, 151.2093), "BARANGAROO": (-33.8615, 151.2015),
    "CHIPPENDALE": (-33.8893, 151.1989), "HAYMARKET": (-33.8800, 151.2050),
    "ULTIMO": (-33.8792, 151.1970), "PYRMONT": (-33.8710, 151.1945),
    "SURRY HILLS": (-33.8876, 151.2115), "DARLINGHURST": (-33.8764, 151.2178),
    "POTTS POINT": (-33.8710, 151.2230), "ELIZABETH BAY": (-33.8700, 151.2260),
    "WOOLLOOMOOLOO": (-33.8700, 151.2170),
    # Inner West
    "NEWTOWN": (-33.8979, 151.1793), "CAMPERDOWN": (-33.8891, 151.1779),
    "GLEBE": (-33.8810, 151.1852), "FOREST LODGE": (-33.8820, 151.1810),
    "LEICHHARDT": (-33.8839, 151.1567), "LILYFIELD": (-33.8720, 151.1620),
    "BALMAIN": (-33.8600, 151.1790), "BIRCHGROVE": (-33.8530, 151.1760),
    "ROZELLE": (-33.8622, 151.1720), "ANNANDALE": (-33.8835, 151.1658),
    "ENMORE": (-33.9000, 151.1745), "ERSKINEVILLE": (-33.9032, 151.1862),
    "MARRICKVILLE": (-33.9115, 151.1552), "SYDENHAM": (-33.9170, 151.1680),
    "TEMPE": (-33.9230, 151.1640), "ST PETERS": (-33.9072, 151.1895),
    "PETERSHAM": (-33.8950, 151.1545), "STANMORE": (-33.8960, 151.1650),
    "LEWISHAM": (-33.8960, 151.1480), "SUMMER HILL": (-33.8920, 151.1380),
    "DULWICH HILL": (-33.9076, 151.1400), "HABERFIELD": (-33.8820, 151.1380),
    "ASHFIELD": (-33.8880, 151.1247), "CROYDON": (-33.8840, 151.1160),
    "CONCORD": (-33.8590, 151.1030), "DRUMMOYNE": (-33.8560, 151.1510),
    "FIVE DOCK": (-33.8657, 151.1290), "BURWOOD": (-33.8774, 151.1042),
    # Eastern Suburbs
    "PADDINGTON": (-33.8848, 151.2264), "WOOLLAHRA": (-33.8879, 151.2383),
    "DOUBLE BAY": (-33.8780, 151.2430), "BELLEVUE HILL": (-33.8800, 151.2550),
    "ROSE BAY": (-33.8720, 151.2640), "VAUCLUSE": (-33.8570, 151.2760),
    "BONDI": (-33.8908, 151.2700), "BONDI BEACH": (-33.8920, 151.2720),
    "BONDI JUNCTION": (-33.8913, 151.2531), "BRONTE": (-33.9040, 151.2600),
    "WAVERLEY": (-33.8960, 151.2530), "COOGEE": (-33.9210, 151.2560),
    "RANDWICK": (-33.9147, 151.2427), "KINGSFORD": (-33.9208, 151.2272),
    "MAROUBRA": (-33.9477, 151.2384), "CENTENNIAL PARK": (-33.8970, 151.2360),
    # South Sydney
    "REDFERN": (-33.8938, 151.2041), "WATERLOO": (-33.8992, 151.2076),
    "ZETLAND": (-33.9070, 151.2120), "ALEXANDRIA": (-33.9065, 151.2035),
    "BEACONSFIELD": (-33.9120, 151.2020), "ROSEBERY": (-33.9187, 151.2043),
    "MASCOT": (-33.9260, 151.1925), "WOLLI CREEK": (-33.9338, 151.1535),
    "ARNCLIFFE": (-33.9372, 151.1470),
    # Lower North Shore
    "NORTH SYDNEY": (-33.8402, 151.2073), "KIRRIBILLI": (-33.8490, 151.2170),
    "NEUTRAL BAY": (-33.8358, 151.2197), "CREMORNE": (-33.8340, 151.2250),
    "MOSMAN": (-33.8310, 151.2410), "CROWS NEST": (-33.8260, 151.2020),
    "ST LEONARDS": (-33.8230, 151.1960), "WOLLSTONECRAFT": (-33.8310, 151.1960),
    "WAVERTON": (-33.8390, 151.2000),
    # Upper North Shore
    "CHATSWOOD": (-33.7970, 151.1819), "LANE COVE": (-33.8163, 151.1661),
    "ARTARMON": (-33.8101, 151.1892), "WILLOUGHBY": (-33.8020, 151.1980),
    "GORDON": (-33.7570, 151.1530), "PYMBLE": (-33.7450, 151.1420),
    "LINDFIELD": (-33.7750, 151.1650), "KILLARA": (-33.7660, 151.1620),
    "ROSEVILLE": (-33.7840, 151.1770), "WAHROONGA": (-33.7180, 151.1170),
    "TURRAMURRA": (-33.7350, 151.1310),
    # Northern Beaches
    "MANLY": (-33.7980, 151.2840), "DEE WHY": (-33.7517, 151.2893),
    "BROOKVALE": (-33.7618, 151.2618), "FRESHWATER": (-33.7770, 151.2850),
    "MONA VALE": (-33.6770, 151.3030),
    # Parramatta & Western
    "PARRAMATTA": (-33.8148, 151.0042), "STRATHFIELD": (-33.8742, 151.0821),
    "HOMEBUSH": (-33.8629, 151.0897), "RHODES": (-33.8310, 151.0870),
    "MEADOWBANK": (-33.8170, 151.0900), "RYDE": (-33.8155, 151.1045),
    "WEST RYDE": (-33.8070, 151.0890), "EASTWOOD": (-33.7912, 151.0805),
    "EPPING": (-33.7730, 151.0823), "MACQUARIE PARK": (-33.7760, 151.1230),
    "GLADESVILLE": (-33.8350, 151.1300), "HUNTERS HILL": (-33.8370, 151.1430),
    "LIDCOMBE": (-33.8640, 151.0475), "WENTWORTH POINT": (-33.8350, 151.0730),
    "CARLINGFORD": (-33.7830, 151.0490), "AUBURN": (-33.8494, 151.0296),
    # Canterbury-Bankstown
    "CAMPSIE": (-33.9116, 151.1024), "CANTERBURY": (-33.9116, 151.1180),
    "BANKSTOWN": (-33.9173, 151.0335), "LAKEMBA": (-33.9190, 151.0750),
    "PUNCHBOWL": (-33.9280, 151.0540), "BELMORE": (-33.9200, 151.0870),
    # St George
    "HURSTVILLE": (-33.9644, 151.1033), "KOGARAH": (-33.9632, 151.1338),
    "ROCKDALE": (-33.9533, 151.1368), "BEXLEY": (-33.9500, 151.1240),
    "PENSHURST": (-33.9600, 151.0900),
    # Sutherland
    "CRONULLA": (-34.0540, 151.1520), "MIRANDA": (-34.0364, 151.1015),
    "SUTHERLAND": (-34.0310, 151.0575), "CARINGBAH": (-34.0420, 151.1230),
    # Hills & Hornsby
    "CASTLE HILL": (-33.7300, 151.0038), "BAULKHAM HILLS": (-33.7580, 150.9880),
    "KELLYVILLE": (-33.7200, 150.9600), "HORNSBY": (-33.7033, 151.0993),
    "PENNANT HILLS": (-33.7380, 151.0720),
    # Outer
    "BLACKTOWN": (-33.7686, 150.9053), "PENRITH": (-33.7511, 150.6942),
    "LIVERPOOL": (-33.9200, 150.9238), "CAMPBELLTOWN": (-34.0655, 150.8142),
    "FAIRFIELD": (-33.8690, 150.9560),
}


def generate_sample_data(months_back=18, seed=42):
    """Generate a realistic set of sample Sydney property sales."""
    random.seed(seed)
    today = date.today()
    start = today - timedelta(days=months_back * 30)

    properties = []
    prop_id = 1000

    for suburb, type_ranges in SUBURB_PROFILES.items():
        lat_base, lng_base = CENTROID_DATA.get(suburb, (-33.87, 151.21))
        postcode = POSTCODE_MAP.get(suburb, "2000")

        # Determine how many sales to generate (volume weighted)
        n = random.randint(15, 45)

        for _ in range(n):
            prop_type = random.choice(list(type_ranges.keys()))
            lo, hi = type_ranges[prop_type]

            # Apply mild upward trend over time (Sydney prices rising)
            base_price = random.randint(lo, hi)

            # Random sale date
            days_offset = random.randint(0, months_back * 30)
            sale_date = today - timedelta(days=days_offset)

            # Price with slight upward trend
            trend_factor = 1 + (0.07 * (1 - days_offset / (months_back * 30)))
            price = round(base_price * trend_factor / 1000) * 1000

            # Random address
            street_no = random.randint(1, 200)
            street = random.choice(STREET_NAMES)
            address = f"{street_no} {street}"

            if prop_type == "Unit":
                unit = random.randint(1, 50)
                floor = random.randint(1, 20)
                address = f"{unit}/{street_no} {street}"

            # Land area (matches real NSW VG data — no bedroom/bathroom info)
            area = {
                "House": random.randint(300, 1200),
                "Unit": random.randint(55, 150),
                "Townhouse": random.randint(150, 350),
                "Land": random.randint(400, 2000),
                "Commercial": random.randint(50, 500),
            }[prop_type]

            # Zoning code (matches NSW VG format)
            zoning = {
                "House": random.choice(["R2", "R3", "R4"]),
                "Unit": random.choice(["R4", "R3", "B4"]),
                "Townhouse": random.choice(["R3", "R2"]),
                "Land": random.choice(["R2", "R3"]),
                "Commercial": random.choice(["B1", "B2", "B4"]),
            }[prop_type]

            # Distribute within suburb polygon for realistic map placement
            lat, lng = _random_point_in_suburb(suburb, lat_base, lng_base)

            uid_src = f"sample-{prop_id}"
            uid = hashlib.md5(uid_src.encode()).hexdigest()[:12]

            properties.append({
                "id": uid,
                "address": address,
                "suburb": suburb,
                "postcode": postcode,
                "lat": lat,
                "lng": lng,
                "price": price,
                "date": sale_date.isoformat(),
                "type": prop_type,
                "area": area,
                "zoning": zoning,
            })

            prop_id += 1

    # Sort by date descending
    properties.sort(key=lambda p: p["date"], reverse=True)
    return properties


def main():
    """Standalone execution: write sample data to public/data/"""
    output_dir = Path(__file__).parent.parent / "public" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    data = generate_sample_data()

    output = {
        "lastUpdated": date.today().isoformat(),
        "totalCount": len(data),
        "note": "SAMPLE DATA — for development/demo only. Run fetch_data.py for real data.",
        "properties": data,
    }

    out_path = output_dir / "properties.json"
    out_path.write_text(json.dumps(output, separators=(",", ":")))
    print(f"✅ Generated {len(data)} sample properties → {out_path}")

    # Stats
    from collections import Counter
    suburb_counts = Counter(p["suburb"] for p in data)
    print(f"   Suburbs: {len(suburb_counts)}")
    print("   Top 5:", suburb_counts.most_common(5))


if __name__ == "__main__":
    main()
