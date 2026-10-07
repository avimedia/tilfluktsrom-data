#!/usr/bin/env python3
"""Fetch Estonian public shelters (avalikud varjumiskohad) and write estonia_shelters.json.

Source: the Rescue Board's open data ("SMIT. Päästeameti avaandmed"), published as
the WFS layer huvipunkt:varjumiskoht on the Ministry of Climate's open GeoServer.
No API key is needed. Until 2026 this used Maa-amet's xgis2/service/205arpl
(layer ms:VARJEKOHT), which now refuses requests.

The source has no capacity, so "plasser" is 0 (as it was with the old source).
"""

import json
import sys
from datetime import datetime

import requests

WFS_URL = "https://gsavalik.envir.ee/geoserver/wfs"
LAYER = "huvipunkt:varjumiskoht"
OUTPUT_PATH = "estonia_shelters.json"
# Refuse to publish if far fewer shelters than usual come back (~300 in 2026).
MIN_EXPECTED_SHELTERS = 150


def source_date(andmeseis: str) -> str:
    """'23.09.2026' -> '2026-09-23' (the app expects yyyy-MM-dd)."""
    try:
        return datetime.strptime(andmeseis.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return datetime.now().strftime("%Y-%m-%d")


def place_name(properties: dict) -> str:
    """Settlement, or the municipality for Tallinn's districts ('Haabersti linnaosa' -> 'Tallinn')."""
    settlement = (properties.get("ay") or "").strip()
    municipality = (properties.get("ov") or "").strip()
    if not settlement or settlement.endswith("linnaosa"):
        return municipality
    return settlement


def fetch() -> list:
    response = requests.get(
        WFS_URL,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": LAYER,
            "outputFormat": "application/json",
        },
        timeout=120,
    )
    response.raise_for_status()
    features = []
    for feature in response.json().get("features", []):
        p = feature.get("properties", {})
        lon, lat = p.get("pikkus"), p.get("laius")
        if lon is None or lat is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {
                "romnr": int(p.get("poi_id") or p.get("fid") or 0),
                "plasser": 0,
                "adresse": (p.get("aadress") or "").strip(),
                "adresse_avstand": None,
                "sted": place_name(p),
                "datauttaksdato": source_date(p.get("andmeseis")),
            },
        })
    return features


def main() -> int:
    print(f"Fetching {LAYER} from {WFS_URL}")
    features = fetch()
    print(f"Found {len(features)} shelters")
    if len(features) < MIN_EXPECTED_SHELTERS:
        print(f"❌ Only {len(features)} shelters (expected at least {MIN_EXPECTED_SHELTERS}); not publishing.")
        return 1

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "name": "Avalikud varjumiskohad (Estonia)", "features": features}, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved {len(features)} shelters to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
