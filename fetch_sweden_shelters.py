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
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, indent=2)
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
            matches = re.findall(r'"adresse": "([^"]*[åäöÅÄÖ][^"]*)"', content)
            if matches:
                print(f"\n📋 Sample addresses with Swedish characters:")
                for addr in matches[:5]:
                    print(f"   - {addr}")
        else:
            print("⚠️ Warning: No Swedish characters found in output")
