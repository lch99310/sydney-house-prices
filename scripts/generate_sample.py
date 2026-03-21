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

# ── Price ranges per suburb and type ─────────────────────────────────────────
SUBURB_PROFILES = {
    "ULTIMO":         {"Unit": (700_000, 1_200_000), "House": (1_500_000, 2_500_000), "Townhouse": (1_000_000, 1_800_000)},
    "PYRMONT":        {"Unit": (800_000, 1_500_000), "Townhouse": (1_200_000, 2_000_000)},
    "SURRY HILLS":    {"Unit": (750_000, 1_300_000), "House": (2_000_000, 3_500_000), "Townhouse": (1_400_000, 2_200_000)},
    "NEWTOWN":        {"Unit": (650_000, 1_100_000), "House": (1_500_000, 2_800_000), "Townhouse": (1_000_000, 1_700_000)},
    "GLEBE":          {"Unit": (700_000, 1_200_000), "House": (1_800_000, 3_000_000)},
    "LEICHHARDT":     {"Unit": (600_000, 1_000_000), "House": (1_400_000, 2_500_000), "Townhouse": (900_000, 1_600_000)},
    "BALMAIN":        {"Unit": (800_000, 1_400_000), "House": (2_500_000, 4_500_000)},
    "ROZELLE":        {"Unit": (750_000, 1_200_000), "House": (2_000_000, 3_500_000)},
    "ANNANDALE":      {"Unit": (600_000, 1_000_000), "House": (1_800_000, 3_200_000)},
    "DARLINGHURST":   {"Unit": (700_000, 1_400_000), "House": (2_500_000, 5_000_000)},
    "PADDINGTON":     {"Unit": (900_000, 1_600_000), "House": (2_500_000, 5_000_000), "Townhouse": (1_500_000, 2_800_000)},
    "WOOLLAHRA":      {"Unit": (1_000_000, 1_800_000), "House": (3_000_000, 7_000_000)},
    "DOUBLE BAY":     {"Unit": (1_200_000, 2_500_000), "House": (5_000_000, 12_000_000)},
    "BONDI":          {"Unit": (1_000_000, 1_800_000), "House": (3_000_000, 5_500_000)},
    "BONDI BEACH":    {"Unit": (1_100_000, 2_000_000), "House": (3_500_000, 7_000_000)},
    "BONDI JUNCTION": {"Unit": (800_000, 1_400_000), "House": (2_500_000, 4_500_000), "Townhouse": (1_200_000, 2_200_000)},
    "COOGEE":         {"Unit": (900_000, 1_600_000), "House": (2_500_000, 5_000_000)},
    "RANDWICK":       {"Unit": (700_000, 1_300_000), "House": (2_000_000, 3_800_000), "Townhouse": (1_000_000, 2_000_000)},
    "KINGSFORD":      {"Unit": (550_000, 900_000), "House": (1_500_000, 2_500_000)},
    "MAROUBRA":       {"Unit": (600_000, 1_000_000), "House": (1_800_000, 3_000_000)},
    "REDFERN":        {"Unit": (600_000, 1_100_000), "House": (1_500_000, 2_800_000)},
    "WATERLOO":       {"Unit": (550_000, 950_000), "House": (1_600_000, 2_800_000)},
    "ZETLAND":        {"Unit": (600_000, 1_000_000), "Townhouse": (950_000, 1_600_000)},
    "ALEXANDRIA":     {"Unit": (600_000, 1_100_000), "House": (1_600_000, 3_000_000), "Townhouse": (1_000_000, 1_800_000)},
    "ST PETERS":      {"Unit": (550_000, 900_000), "House": (1_400_000, 2_500_000)},
    "MANLY":          {"Unit": (1_100_000, 2_000_000), "House": (3_500_000, 7_500_000)},
    "MOSMAN":         {"Unit": (1_200_000, 2_200_000), "House": (4_000_000, 9_000_000)},
    "CREMORNE":       {"Unit": (900_000, 1_600_000), "House": (3_000_000, 5_500_000)},
    "NEUTRAL BAY":    {"Unit": (800_000, 1_500_000), "House": (2_500_000, 5_000_000)},
    "NORTH SYDNEY":   {"Unit": (700_000, 1_300_000), "House": (2_500_000, 4_500_000)},
    "CHATSWOOD":      {"Unit": (750_000, 1_300_000), "House": (2_000_000, 3_500_000), "Townhouse": (1_100_000, 1_900_000)},
    "LANE COVE":      {"Unit": (600_000, 1_100_000), "House": (1_800_000, 3_500_000)},
    "ARTARMON":       {"Unit": (700_000, 1_200_000), "House": (2_000_000, 3_500_000)},
    "PARRAMATTA":     {"Unit": (400_000, 750_000), "House": (1_000_000, 1_800_000), "Townhouse": (700_000, 1_200_000)},
    "STRATHFIELD":    {"Unit": (550_000, 950_000), "House": (1_600_000, 3_000_000)},
    "HOMEBUSH":       {"Unit": (500_000, 850_000), "House": (1_400_000, 2_500_000)},
    "BANKSTOWN":      {"Unit": (380_000, 650_000), "House": (900_000, 1_600_000)},
    "HURSTVILLE":     {"Unit": (500_000, 900_000), "House": (1_400_000, 2_500_000)},
    "KOGARAH":        {"Unit": (500_000, 900_000), "House": (1_300_000, 2_200_000)},
    "ROCKDALE":       {"Unit": (500_000, 850_000), "House": (1_200_000, 2_200_000)},
    "CRONULLA":       {"Unit": (700_000, 1_300_000), "House": (2_000_000, 4_000_000)},
    "MIRANDA":        {"Unit": (550_000, 900_000), "House": (1_200_000, 2_200_000)},
    "CASTLE HILL":    {"Unit": (600_000, 1_100_000), "House": (1_600_000, 3_000_000), "Townhouse": (850_000, 1_500_000)},
    "HORNSBY":        {"Unit": (500_000, 900_000), "House": (1_400_000, 2_500_000)},
    "DEE WHY":        {"Unit": (700_000, 1_200_000), "House": (2_000_000, 3_500_000)},
    "BROOKVALE":      {"Unit": (650_000, 1_100_000), "House": (1_800_000, 3_200_000)},
    "KIRRIBILLI":     {"Unit": (1_000_000, 2_500_000), "House": (4_000_000, 10_000_000)},
    "RHODES":         {"Unit": (600_000, 1_100_000), "Townhouse": (900_000, 1_500_000)},
    "MEADOWBANK":     {"Unit": (550_000, 950_000), "House": (1_400_000, 2_400_000)},
    "RYDE":           {"Unit": (550_000, 1_000_000), "House": (1_600_000, 2_800_000), "Townhouse": (900_000, 1_500_000)},
    "WEST RYDE":      {"Unit": (500_000, 900_000), "House": (1_400_000, 2_500_000)},
    "EASTWOOD":       {"Unit": (550_000, 950_000), "House": (1_600_000, 2_800_000)},
    "EPPING":         {"Unit": (550_000, 1_000_000), "House": (1_800_000, 3_200_000), "Townhouse": (900_000, 1_600_000)},
    "CONCORD":        {"Unit": (600_000, 1_100_000), "House": (2_000_000, 3_500_000)},
    "DRUMMOYNE":      {"Unit": (700_000, 1_300_000), "House": (2_200_000, 4_000_000)},
    "FIVE DOCK":      {"Unit": (600_000, 1_100_000), "House": (1_800_000, 3_200_000)},
    "BURWOOD":        {"Unit": (550_000, 1_000_000), "House": (1_800_000, 3_200_000)},
    "ASHFIELD":       {"Unit": (500_000, 900_000), "House": (1_500_000, 2_500_000)},
    "MARRICKVILLE":   {"Unit": (550_000, 950_000), "House": (1_400_000, 2_500_000), "Townhouse": (900_000, 1_500_000)},
    "DULWICH HILL":   {"Unit": (500_000, 900_000), "House": (1_500_000, 2_600_000)},
    "ENMORE":         {"Unit": (600_000, 1_000_000), "House": (1_500_000, 2_600_000)},
    "ERSKINEVILLE":   {"Unit": (650_000, 1_100_000), "House": (1_600_000, 2_800_000)},
    "MASCOT":         {"Unit": (550_000, 950_000), "Townhouse": (800_000, 1_400_000)},
    "ROSEBERY":       {"Unit": (600_000, 1_050_000), "Townhouse": (900_000, 1_500_000)},
    "WOLLI CREEK":    {"Unit": (450_000, 800_000), "Townhouse": (700_000, 1_200_000)},
    "ARNCLIFFE":      {"Unit": (450_000, 800_000), "House": (1_200_000, 2_000_000)},
    "CAMPSIE":        {"Unit": (400_000, 700_000), "House": (1_100_000, 1_900_000)},
    "CANTERBURY":     {"Unit": (400_000, 700_000), "House": (1_200_000, 2_000_000)},
    "GLADESVILLE":    {"Unit": (600_000, 1_100_000), "House": (1_800_000, 3_200_000)},
    "HUNTERS HILL":   {"Unit": (900_000, 1_500_000), "House": (3_000_000, 6_000_000)},
    "LIDCOMBE":       {"Unit": (450_000, 800_000), "House": (1_000_000, 1_800_000), "Townhouse": (700_000, 1_200_000)},
    "WENTWORTH POINT":{"Unit": (500_000, 900_000)},
    "CARLINGFORD":    {"Unit": (550_000, 950_000), "House": (1_600_000, 2_800_000), "Townhouse": (850_000, 1_500_000)},
    "PETERSHAM":      {"Unit": (550_000, 950_000), "House": (1_500_000, 2_500_000)},
    "STANMORE":       {"Unit": (600_000, 1_000_000), "House": (1_600_000, 2_800_000)},
    "HABERFIELD":     {"Unit": (650_000, 1_100_000), "House": (2_000_000, 3_500_000)},
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
    "ULTIMO": "2007", "PYRMONT": "2009", "SURRY HILLS": "2010",
    "NEWTOWN": "2042", "GLEBE": "2037", "LEICHHARDT": "2040",
    "BALMAIN": "2041", "ROZELLE": "2039", "ANNANDALE": "2038",
    "DARLINGHURST": "2010", "PADDINGTON": "2021", "WOOLLAHRA": "2025",
    "DOUBLE BAY": "2028", "BONDI": "2026", "BONDI BEACH": "2026",
    "BONDI JUNCTION": "2022", "COOGEE": "2034", "RANDWICK": "2031",
    "KINGSFORD": "2032", "MAROUBRA": "2035", "REDFERN": "2016",
    "WATERLOO": "2017", "ZETLAND": "2017", "ALEXANDRIA": "2015",
    "ST PETERS": "2044", "MANLY": "2095", "MOSMAN": "2088",
    "CREMORNE": "2090", "NEUTRAL BAY": "2089", "NORTH SYDNEY": "2060",
    "CHATSWOOD": "2067", "LANE COVE": "2066", "ARTARMON": "2064",
    "PARRAMATTA": "2150", "STRATHFIELD": "2135", "HOMEBUSH": "2140",
    "BANKSTOWN": "2200", "HURSTVILLE": "2220", "KOGARAH": "2217",
    "ROCKDALE": "2216", "CRONULLA": "2230", "MIRANDA": "2228",
    "CASTLE HILL": "2154", "HORNSBY": "2077", "DEE WHY": "2099",
    "BROOKVALE": "2100", "KIRRIBILLI": "2061",
    "RHODES": "2138", "MEADOWBANK": "2114", "RYDE": "2112",
    "WEST RYDE": "2114", "EASTWOOD": "2122", "EPPING": "2121",
    "CONCORD": "2137", "DRUMMOYNE": "2047", "FIVE DOCK": "2046",
    "BURWOOD": "2134", "ASHFIELD": "2131", "MARRICKVILLE": "2204",
    "DULWICH HILL": "2203", "ENMORE": "2042", "ERSKINEVILLE": "2043",
    "MASCOT": "2020", "ROSEBERY": "2018", "WOLLI CREEK": "2205",
    "ARNCLIFFE": "2205", "CAMPSIE": "2194", "CANTERBURY": "2193",
    "GLADESVILLE": "2111", "HUNTERS HILL": "2110", "LIDCOMBE": "2141",
    "WENTWORTH POINT": "2127", "CARLINGFORD": "2118",
    "PETERSHAM": "2049", "STANMORE": "2048", "HABERFIELD": "2045",
}

CENTROID_DATA = {
    "ULTIMO": (-33.8792, 151.1970),
    "PYRMONT": (-33.8694, 151.1925),
    "SURRY HILLS": (-33.8876, 151.2115),
    "NEWTOWN": (-33.8979, 151.1793),
    "GLEBE": (-33.8810, 151.1852),
    "LEICHHARDT": (-33.8839, 151.1567),
    "BALMAIN": (-33.8587, 151.1800),
    "ROZELLE": (-33.8622, 151.1720),
    "ANNANDALE": (-33.8835, 151.1658),
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
    "REDFERN": (-33.8938, 151.2041),
    "WATERLOO": (-33.8992, 151.2076),
    "ZETLAND": (-33.9070, 151.2120),
    "ALEXANDRIA": (-33.9065, 151.2035),
    "ST PETERS": (-33.9072, 151.1895),
    "MANLY": (-33.7967, 151.2872),
    "MOSMAN": (-33.8294, 151.2433),
    "CREMORNE": (-33.8327, 151.2273),
    "NEUTRAL BAY": (-33.8358, 151.2197),
    "NORTH SYDNEY": (-33.8402, 151.2073),
    "CHATSWOOD": (-33.7970, 151.1819),
    "LANE COVE": (-33.8163, 151.1661),
    "ARTARMON": (-33.8101, 151.1892),
    "PARRAMATTA": (-33.8148, 151.0042),
    "STRATHFIELD": (-33.8742, 151.0821),
    "HOMEBUSH": (-33.8629, 151.0897),
    "BANKSTOWN": (-33.9173, 151.0335),
    "HURSTVILLE": (-33.9644, 151.1033),
    "KOGARAH": (-33.9632, 151.1338),
    "ROCKDALE": (-33.9533, 151.1368),
    "CRONULLA": (-34.0555, 151.1533),
    "MIRANDA": (-34.0364, 151.1015),
    "CASTLE HILL": (-33.7300, 151.0038),
    "HORNSBY": (-33.7033, 151.0993),
    "DEE WHY": (-33.7517, 151.2893),
    "BROOKVALE": (-33.7618, 151.2618),
    "KIRRIBILLI": (-33.8481, 151.2164),
    "RHODES": (-33.8310, 151.0870),
    "MEADOWBANK": (-33.8170, 151.0900),
    "RYDE": (-33.8155, 151.1045),
    "WEST RYDE": (-33.8070, 151.0890),
    "EASTWOOD": (-33.7912, 151.0805),
    "EPPING": (-33.7730, 151.0823),
    "CONCORD": (-33.8590, 151.1030),
    "DRUMMOYNE": (-33.8530, 151.1530),
    "FIVE DOCK": (-33.8657, 151.1290),
    "BURWOOD": (-33.8774, 151.1042),
    "ASHFIELD": (-33.8880, 151.1247),
    "MARRICKVILLE": (-33.9115, 151.1552),
    "DULWICH HILL": (-33.9076, 151.1400),
    "ENMORE": (-33.9000, 151.1745),
    "ERSKINEVILLE": (-33.9032, 151.1862),
    "MASCOT": (-33.9260, 151.1925),
    "ROSEBERY": (-33.9187, 151.2043),
    "WOLLI CREEK": (-33.9338, 151.1535),
    "ARNCLIFFE": (-33.9372, 151.1470),
    "CAMPSIE": (-33.9116, 151.1024),
    "CANTERBURY": (-33.9116, 151.1180),
    "GLADESVILLE": (-33.8350, 151.1300),
    "HUNTERS HILL": (-33.8350, 151.1450),
    "LIDCOMBE": (-33.8640, 151.0475),
    "WENTWORTH POINT": (-33.8350, 151.0730),
    "CARLINGFORD": (-33.7830, 151.0490),
    "PETERSHAM": (-33.8950, 151.1545),
    "STANMORE": (-33.8960, 151.1650),
    "HABERFIELD": (-33.8820, 151.1380),
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

            # Property attributes
            bedrooms = {
                "House": random.choices([3, 4, 5], weights=[40, 45, 15])[0],
                "Unit": random.choices([1, 2, 3], weights=[25, 55, 20])[0],
                "Townhouse": random.choices([2, 3, 4], weights=[25, 55, 20])[0],
                "Land": None,
            }[prop_type]

            bathrooms = None
            if bedrooms:
                bathrooms = max(1, random.randint(bedrooms - 1, bedrooms))

            area = {
                "House": random.randint(300, 1200),
                "Unit": random.randint(55, 150),
                "Townhouse": random.randint(150, 350),
                "Land": random.randint(400, 2000),
            }[prop_type]

            # Jitter coordinates
            lat = round(lat_base + random.uniform(-0.004, 0.004), 6)
            lng = round(lng_base + random.uniform(-0.005, 0.005), 6)

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
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "area": area,
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
