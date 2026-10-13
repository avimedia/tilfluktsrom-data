#!/usr/bin/env python3
"""
Generate Swedish shelters GeoJSON from MSB ArcGIS Feature Service
For GitHub Actions: always outputs docs/sweden_shelters.json and requires no manual steps.
"""

import os
import requests
import json
from datetime import datetime

def fetch_all_shelters():
    print("📥 Downloading Swedish shelter data from MSB ArcGIS Service...")
    base_url = "https://services6.arcgis.com/NThLsKaeOKhGxBBE/arcgis/rest/services/Skyddsrum_220225/FeatureServer/1/query"
    all_features = []
    offset = 0
    page_size = 2000

    while True:
        params = {
            "where": "1=1",
            "outFields": "Gatuadress,AntalPlatser,Skyddsrumsnr,Kommunnamn,XKoordinat,YKoordinat",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": page_size
        }
        try:
            print(f"  Fetching records {offset} to {offset + page_size}...")
            response = requests.get(base_url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                print(f"❌ API Error: {data['error']}")
                break
            features = data.get("features", [])
            if not features:
                break
            all_features.extend(features)
            print(f"    Got {len(features)} shelters")
            if len(features) < page_size:
                break
            offset += page_size
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            break

    print(f"\n✅ Downloaded {len(all_features)} shelters total")
    return all_features

def convert_to_app_format(arcgis_features):
    print("🔄 Converting to app format...")
    features = []
    swedish_char_count = 0

    for idx, arcgis_feature in enumerate(arcgis_features):
        attrs = arcgis_feature.get("attributes", {})
        geom = arcgis_feature.get("geometry", {})
        if "x" in geom and "y" in geom:
            lon, lat = geom["x"], geom["y"]
        else:
            print(f"⚠️ Skipping feature {idx} - no geometry")
            continue
        address = attrs.get("Gatuadress", "") or ""
        address = str(address).strip()
        if address in ("", None):
            address = ""
        if any(char in address for char in ['å', 'ä', 'ö', 'Å', 'Ä', 'Ö']):
            swedish_char_count += 1
        capacity = attrs.get("AntalPlatser", 0) or 0
        municipality = str(attrs.get("Kommunnamn") or "").strip()

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "romnr": idx,
                "plasser": int(capacity),
                "adresse": address,
                "sted": municipality,
                "datauttaksdato": datetime.now().strftime("%Y-%m-%d")
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "name": "Skyddsrum Sverige",
        "features": features
    }

    print(f"✅ Converted {len(features)} shelters")
    print(f"📝 Found {swedish_char_count} addresses with Swedish characters")
    return geojson

def without_dates(features):
    return [
        {**f, "properties": {k: v for k, v in f["properties"].items() if k != "datauttaksdato"}}
        for f in features
    ]


def unchanged_date(geojson, path):
    """The previous file's date if its shelters equal the new ones apart from the date, else None."""
    try:
        with open(path, encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        return None
    old_features = previous.get("features", [])
    if without_dates(old_features) != without_dates(geojson["features"]):
        return None
    dates = [f["properties"].get("datauttaksdato") for f in old_features if f["properties"].get("datauttaksdato")]
    return max(dates) if dates else None


if __name__ == "__main__":
    print("🇸🇪 Swedish Shelter Data Converter (ArcGIS)")
    print("=" * 50)
    arcgis_features = fetch_all_shelters()
    if not arcgis_features:
        print("\n❌ FAILED to download data")
        exit(1)
    geojson = convert_to_app_format(arcgis_features)
    output_dir = "docs"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "sweden_shelters.json")
    previous_date = unchanged_date(geojson, output_file)
    if previous_date:
        # Same shelters as last time: keep the old date, so the app doesn't report
        # "newer data" every day for a file where only the date changed.
        print(f"\n= Shelters unchanged since {previous_date}; keeping that date")
        for feature in geojson["features"]:
            feature["properties"]["datauttaksdato"] = previous_date
    with open(output_file, "w", encoding="utf-8") as f:
        # Compact JSON: GitHub Pages redeploys on every change, and each deployment
        # counts against the account's Actions storage.
        json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n✅ SUCCESS! File saved as: {output_file}")
    file_size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"📊 File size: {file_size_mb:.2f} MB")
    with open(output_file, "r", encoding="utf-8") as f:
        content = f.read()
        swedish_chars = ['å', 'ä', 'ö', 'Å', 'Ä', 'Ö']
        found_chars = [char for char in swedish_chars if char in content]
        if found_chars:
            print(f"✅ Swedish characters preserved correctly: {', '.join(sorted(set(found_chars)))}")
            import re
            matches = re.findall(r'"adresse": ?"([^"]*[åäöÅÄÖ][^"]*)"', content)
            if matches:
                print(f"\n📋 Sample addresses with Swedish characters:")
                for addr in matches[:5]:
                    print(f"   - {addr}")
        else:
            print("⚠️ Warning: No Swedish characters found in output")