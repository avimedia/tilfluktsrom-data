#!/usr/bin/env python3
"""Fetch Polish shelter points (punkty schronienia) and write poland_shelters.json.

Source: dane.gov.pl dataset 28058 "Punkty schronienia w Polsce" (Ministry of the Interior
and the State Fire Service, CC BY 4.0, updated weekly). Its CSV link (gdziesieukryc.pl)
blocks automated downloads, so this reads the rows through the portal's own API.

That API returns at most 100 rows per page and 10,000 rows per query, and its text match
is fuzzy ("pomorskie" also matches "kujawsko-pomorskie"). So each voivodeship is queried
on its own, sorted by id ascending, plus descending when it has more than 10,000 rows;
rows are kept only when the voivodeship matches exactly, and the total must equal the
dataset's row count before anything is written.

Most points are makeshift shelter places (miejsca doraźnego schronienia), not purpose-built
shelters. The source has no capacity, so "plasser" is 0; "dostepnosc" (availability: 24/7,
on request, set hours) is kept for the app. The object type is the same for every row
("Obiekt ochrony ludności"), so it is left out.
"""

import json
import sys
import time

import requests

API = "https://api.dane.gov.pl/1.4"
DATASET_ID = 28058
RESOURCE_ID = 1393918
HEADERS = {"Accept": "application/vnd.api+json; api-version=1.4"}
PAGE_SIZE = 100          # the API rejects larger pages
QUERY_WINDOW = 10_000    # the API fails beyond this many rows per query
OUTPUT_PATH = "poland_shelters.json"
# Refuse to publish if far fewer points than usual come back (~82,000 in October 2026).
MIN_EXPECTED_SHELTERS = 40_000

VOIVODESHIPS = [
    "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie", "małopolskie",
    "mazowieckie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "śląskie",
    "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
]

# Columns in the resource (from the API's headers map).
ID, MUNICIPALITY, COUNTY, VOIVODESHIP, LAT, LON, ADDRESS, AVAILABILITY = (
    "col1", "col5", "col6", "col7", "col8", "col9", "col10", "col11",
)
UNKNOWN_MUNICIPALITY = "Nieznana"


def get(path: str, params: dict = None, attempts: int = 5) -> dict:
    for attempt in range(attempts):
        try:
            response = requests.get(f"{API}{path}", params=params, headers=HEADERS, timeout=90)
            if response.status_code < 500:
                response.raise_for_status()
                return response.json()
        except requests.ConnectionError:
            pass
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{path} kept failing")


def value(row: dict, column: str):
    cell = row["attributes"].get(column)
    return cell.get("val") if isinstance(cell, dict) else None


def fetch_window(voivodeship: str, sort: str, limit: int) -> list:
    rows = []
    for page in range(1, limit // PAGE_SIZE + 2):
        data = get(f"/resources/{RESOURCE_ID}/data", {
            "q": f'{VOIVODESHIP}:"{voivodeship}"',
            "sort": sort,
            "per_page": PAGE_SIZE,
            "page": page,
        })["data"]
        rows += data
        if len(data) < PAGE_SIZE or len(rows) >= limit:
            break
        time.sleep(0.2)
    return rows


def fetch_voivodeship(voivodeship: str) -> dict:
    """All rows of one voivodeship, keyed by id."""
    count = get(f"/resources/{RESOURCE_ID}/data", {"q": f'{VOIVODESHIP}:"{voivodeship}"', "per_page": 1})["meta"]["count"]
    if count > 2 * QUERY_WINDOW:
        raise RuntimeError(f"{voivodeship}: {count} rows is more than two query windows")
    rows = fetch_window(voivodeship, ID, min(count, QUERY_WINDOW))
    if count > QUERY_WINDOW:
        rows += fetch_window(voivodeship, f"-{ID}", count - QUERY_WINDOW + PAGE_SIZE)
    return {value(r, ID): r for r in rows if value(r, VOIVODESHIP) == voivodeship}


def place_name(row: dict) -> str:
    """The locality after the last comma ('ul. Leszczyńska 4, Długie Stare'), else the gmina.

    Warsaw addresses end in the district ('Mokotów') and have no gmina ('Nieznana'), but
    their county is 'Warszawa'; use that, so searching for Warszawa finds them.
    """
    if (value(row, COUNTY) or "").strip() == "Warszawa":
        return "Warszawa"
    address = (value(row, ADDRESS) or "").strip()
    if "," in address:
        locality = address.rsplit(",", 1)[1].strip()
        if locality and not locality[0].isdigit():
            return locality
    municipality = (value(row, MUNICIPALITY) or "").strip()
    return "" if municipality == UNKNOWN_MUNICIPALITY else municipality


def to_feature(row: dict, date: str):
    lat, lon = value(row, LAT), value(row, LON)
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    identifier = value(row, ID) or ""
    try:
        number = int(identifier.rsplit("-", 1)[-1], 16)
    except ValueError:
        number = 0
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": {
            "romnr": number,
            "plasser": 0,
            "adresse": (value(row, ADDRESS) or "").strip(),
            "adresse_avstand": None,
            "sted": place_name(row),
            "datauttaksdato": date,
            "dostepnosc": (value(row, AVAILABILITY) or "").strip(),
        },
    }


def main() -> int:
    dataset = get(f"/datasets/{DATASET_ID}")["data"]["attributes"]
    date = str(dataset.get("modified") or "")[:10]
    total = get(f"/resources/{RESOURCE_ID}/data", {"per_page": 1})["meta"]["count"]
    print(f"Dataset updated {date}, {total} rows", flush=True)

    rows = {}
    for voivodeship in VOIVODESHIPS:
        found = fetch_voivodeship(voivodeship)
        print(f"  {voivodeship}: {len(found)}", flush=True)
        rows.update(found)

    if len(rows) != total:
        print(f"❌ Got {len(rows)} rows but the dataset has {total}; not publishing.")
        return 1
    features = [f for f in (to_feature(r, date) for r in rows.values()) if f]
    features.sort(key=lambda f: f["properties"]["romnr"])  # stable order, so unchanged data gives an unchanged file
    if len(features) < MIN_EXPECTED_SHELTERS:
        print(f"❌ Only {len(features)} points with a position (expected at least {MIN_EXPECTED_SHELTERS}); not publishing.")
        return 1

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        # Compact JSON: this is the largest file on GitHub Pages, and every deployment counts
        # against the account's Actions storage.
        json.dump({"type": "FeatureCollection", "name": "Punkty schronienia w Polsce", "features": features},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"✓ Saved {len(features)} points to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
