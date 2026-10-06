#!/usr/bin/env python3
"""Fetch Danish public shelters (sikringsrum) from Datafordeler and write denmark_shelters.json.

1. BBR (Bygnings- og Boligregistret) GraphQL v2: buildings per municipality with
   shelter capacity (byg069Sikringsrumpladser), position and their DAR address id
   (husnummer).
2. DAR (Danmarks Adresseregister) GraphQL v2: the official address of each of those
   buildings, looked up in batches ("Bakken 1, 2600 Glostrup").
3. "sted" is the postal town from that address, or the municipality name.

History: until 2026 this used BBR v1 (now HTTP 404) and the DAWA API for a
nearest-address search (now HTTP 410 Gone), which left ~90% of addresses empty.

Requires BBR_API_KEY (a Datafordeler API key with access to BBR and DAR).
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from pyproj import Transformer

from place_names import DENMARK_MUNICIPALITIES, denmark_place

BBR_URL = "https://graphql.datafordeler.dk/BBR/v2"
DAR_URL = "https://graphql.datafordeler.dk/DAR/v2"
# Buildings per page when scanning a municipality. Datafordeler aborts queries after 60 s,
# so a page that times out is retried at half the size (down to MIN_PAGE_SIZE).
PAGE_SIZE = 1000
MIN_PAGE_SIZE = 100
# Ids per request when fetching details (BBR) and addresses (DAR).
DETAIL_BATCH = 100
DAR_BATCH = 100
# Progress older than this is discarded rather than resumed (data would be inconsistent).
PARTIAL_MAX_AGE_SECONDS = 7 * 24 * 3600
# Every building BBR lists with shelter places. Most are sikringsrum (for the people who
# live or work in the building); the app says so on every Danish shelter.
MIN_CAPACITY = 1
# Refuse to publish if far fewer shelters than usual come back (an API change, not reality).
MIN_EXPECTED_SHELTERS = 5000
PARTIAL_PATH = "partial_denmark_shelters.json"
OUTPUT_PATH = "denmark_shelters.json"


class QueryTimeout(RuntimeError):
    """Datafordeler aborted the query after its 60-second limit (HC0045)."""


class DatafordelerClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def _clean(self, text: str) -> str:
        """Never let the API key reach logs (it is part of the URL)."""
        return text.replace(self.api_key, "<api-key>")

    def query(self, url: str, query: str, attempts: int = 5) -> Dict[str, Any]:
        service = url.rstrip("/").rsplit("/", 2)[-2]
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.post(f"{url}?apiKey={self.api_key}", json={"query": query}, timeout=(20, 120))
                data = response.json() if response.headers.get("content-type", "").startswith("application") else {}
                errors = data.get("errors") or []
                if any(e.get("extensions", {}).get("code") == "HC0045" for e in errors):
                    raise QueryTimeout(f"{service} query timed out")
                if response.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"{service} HTTP {response.status_code}")
                if response.status_code != 200:
                    raise RuntimeError(f"{service} HTTP {response.status_code} (not retried)")
                if errors:
                    raise RuntimeError(f"{service}: {errors[0].get('message', 'GraphQL error')}")
                return data["data"]
            except QueryTimeout:
                raise  # the caller can retry with a smaller query
            except (requests.RequestException, RuntimeError, ValueError) as error:
                message = self._clean(str(error))
                if "not retried" in message or attempt == attempts:
                    raise RuntimeError(message) from None
                wait = min(60, 5 * 2 ** (attempt - 1))
                print(f"   ↻ {message[:120]}; retrying in {wait}s", flush=True)
                time.sleep(wait)
        raise RuntimeError("unreachable")


class DenmarkShelterFetcher:
    def __init__(self, api_key: str):
        self.client = DatafordelerClient(api_key)
        # EPSG:25832 (ETRS89 / UTM 32N) -> WGS84 lon/lat
        self.transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
        self.now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.addresses_found = 0
        self.addresses_missing = 0

    def fetch_all(self) -> List[Dict[str, Any]]:
        shelters, done = self._load_partial()
        codes = sorted(DENMARK_MUNICIPALITIES)
        failures = []
        start = time.time()

        # Stop starting new municipalities before the workflow's time limit, so progress is
        # saved and cached for the next run instead of being lost when the job is killed.
        deadline = start + float(os.environ.get("FETCH_DEADLINE_MINUTES", "0")) * 60
        for index, code in enumerate(codes, 1):
            if code in done:
                continue
            if deadline > start and time.time() > deadline:
                failures.append("deadline")
                print(f"⏱ Time limit reached after {len(done)} municipalities; progress saved for the next run", flush=True)
                break
            name = DENMARK_MUNICIPALITIES[code]
            try:
                found = self.fetch_municipality(code)
            except Exception as error:  # keep going; failures are reported and fail the run
                failures.append(code)
                print(f"✗ {code} {name}: {error}", flush=True)
                continue
            shelters.extend(found)
            done.add(code)
            self._save_partial(shelters, done)
            print(f"✓ {index}/{len(codes)} {code} {name}: {len(found)} shelters ({len(shelters)} total, {(time.time() - start) / 60:.1f} min)", flush=True)

        if failures:
            print(f"\n⚠ Municipalities that failed: {', '.join(failures)} (re-run to resume)")
        self.failures = failures
        return shelters

    def fetch_municipality(self, code: str) -> List[Dict[str, Any]]:
        shelter_ids = self.scan_for_shelters(code)
        buildings = self.lookup_buildings(shelter_ids)
        addresses = self.lookup_addresses([b["husnummer"] for b in buildings if b.get("husnummer")])
        features = []
        for building in buildings:
            feature = self.make_feature(building, addresses.get(building.get("husnummer") or ""), code)
            if feature:
                features.append(feature)
        return features

    def scan_for_shelters(self, code: str) -> List[str]:
        """Ids of the municipality's buildings with shelter places.

        Only id and capacity are fetched while paging through every building (under 1% have
        shelters), which keeps each page small for Datafordeler's 60-second query limit.
        """
        ids: List[str] = []
        after = None
        page_size = PAGE_SIZE
        while True:
            cursor = f', after: "{after}"' if after else ""
            try:
                data = self.client.query(BBR_URL, f"""
                {{
                  BBR_Bygning(first: {page_size}{cursor}, registreringstid: "{self.now}", virkningstid: "{self.now}",
                              where: {{ kommunekode: {{ eq: "{code}" }}, status: {{ eq: "6" }} }}) {{
                    pageInfo {{ hasNextPage endCursor }}
                    nodes {{ id_lokalId byg069Sikringsrumpladser }}
                  }}
                }}""")["BBR_Bygning"]
            except QueryTimeout:
                if page_size <= MIN_PAGE_SIZE:
                    raise RuntimeError(f"BBR timed out even at {page_size} buildings per page")
                page_size = max(MIN_PAGE_SIZE, page_size // 2)
                print(f"   ↻ BBR page timed out; retrying with {page_size} per page", flush=True)
                continue
            ids += [b["id_lokalId"] for b in data["nodes"] if (b.get("byg069Sikringsrumpladser") or 0) >= MIN_CAPACITY]
            if not data["pageInfo"]["hasNextPage"] or not data["nodes"]:
                return ids
            after = data["pageInfo"]["endCursor"]
            page_size = min(PAGE_SIZE, page_size * 2) if page_size < PAGE_SIZE else page_size

    def lookup_buildings(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Capacity, position and DAR address id for the given buildings, in batches."""
        buildings: List[Dict[str, Any]] = []
        for start in range(0, len(ids), DETAIL_BATCH):
            batch = ids[start:start + DETAIL_BATCH]
            id_list = ", ".join(json.dumps(i) for i in batch)
            buildings += self.client.query(BBR_URL, f"""
            {{
              BBR_Bygning(first: {len(batch)}, registreringstid: "{self.now}", virkningstid: "{self.now}",
                          where: {{ id_lokalId: {{ in: [{id_list}] }} }}) {{
                nodes {{ id_lokalId husnummer byg069Sikringsrumpladser byg404Koordinat {{ wkt }} }}
              }}
            }}""")["BBR_Bygning"]["nodes"]
        return buildings

    def lookup_addresses(self, husnummer_ids: List[str]) -> Dict[str, str]:
        """DAR husnummer id -> "Vej 1, 1234 By"."""
        result: Dict[str, str] = {}
        unique = sorted(set(husnummer_ids))
        for start in range(0, len(unique), DAR_BATCH):
            batch = unique[start:start + DAR_BATCH]
            ids = ", ".join(json.dumps(i) for i in batch)
            nodes = self.client.query(DAR_URL, f"""
            {{
              DAR_Husnummer(first: {len(batch)}, registreringstid: "{self.now}", virkningstid: "{self.now}",
                            where: {{ id_lokalId: {{ in: [{ids}] }} }}) {{
                nodes {{ id_lokalId adgangsadressebetegnelse }}
              }}
            }}""")["DAR_Husnummer"]["nodes"]
            for node in nodes:
                if node.get("adgangsadressebetegnelse"):
                    result[node["id_lokalId"]] = node["adgangsadressebetegnelse"].strip()
        return result

    def make_feature(self, building: Dict[str, Any], address: Optional[str], code: str) -> Optional[Dict[str, Any]]:
        wkt = (building.get("byg404Koordinat") or {}).get("wkt") or ""
        try:
            easting, northing = (float(v) for v in wkt.replace("POINT", "").strip(" ()").split()[:2])
        except ValueError:
            return None
        lon, lat = self.transformer.transform(easting, northing)

        if address:
            self.addresses_found += 1
        else:
            self.addresses_missing += 1
            address = ""

        lokal_id = building.get("id_lokalId", "")
        digits = "".join(filter(str.isdigit, lokal_id))
        romnr = int(digits[:9]) % 1_000_000 if digits else abs(hash(lokal_id)) % 1_000_000

        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "romnr": romnr,
                "plasser": building["byg069Sikringsrumpladser"],
                "adresse": address,
                # The address is the building's own, so there is no distance to report.
                "adresse_avstand": None,
                "sted": denmark_place(address, code),
                "datauttaksdato": self.today,
            },
        }

    @staticmethod
    def _load_partial():
        if os.path.exists(PARTIAL_PATH):
            with open(PARTIAL_PATH, encoding="utf-8") as f:
                data = json.load(f)
            age = time.time() - data.get("saved_at", 0)
            if age > PARTIAL_MAX_AGE_SECONDS:
                print(f"Ignoring progress from {age / 86400:.0f} days ago; starting over")
                return [], set()
            print(f"Resuming: {len(data.get('shelters', []))} shelters from {len(data.get('processed_kommuner', []))} municipalities")
            return data.get("shelters", []), set(data.get("processed_kommuner", []))
        return [], set()

    @staticmethod
    def _save_partial(shelters, done):
        with open(PARTIAL_PATH, "w", encoding="utf-8") as f:
            json.dump({"saved_at": time.time(), "shelters": shelters, "processed_kommuner": sorted(done)}, f, ensure_ascii=False)


def main() -> int:
    api_key = os.environ.get("BBR_API_KEY")
    if not api_key:
        print("❌ BBR_API_KEY is not set")
        return 1

    fetcher = DenmarkShelterFetcher(api_key)
    shelters = fetcher.fetch_all()

    total = fetcher.addresses_found + fetcher.addresses_missing
    if total:
        print(f"\nAddresses: {fetcher.addresses_found}/{total} resolved via DAR ({100 * fetcher.addresses_found / total:.1f}%)")

    if fetcher.failures:
        print("❌ Some municipalities failed; not publishing an incomplete file.")
        return 1
    if len(shelters) < MIN_EXPECTED_SHELTERS:
        print(f"❌ Only {len(shelters)} shelters (expected at least {MIN_EXPECTED_SHELTERS}); not publishing.")
        return 1

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "name": "Beskyttelsesrum Danmark", "features": shelters}, f, ensure_ascii=False, indent=2)
    if os.path.exists(PARTIAL_PATH):
        os.remove(PARTIAL_PATH)
    print(f"✓ Saved {len(shelters)} shelters to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
