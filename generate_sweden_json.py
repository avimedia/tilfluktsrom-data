#!/usr/bin/env python3
"""
Generate Swedish shelters GeoJSON from MSB ArcGIS Feature Service
Run this script to create the JSON file with proper Swedish characters
"""

import requests
import json
from datetime import datetime

def fetch_all_shelters():
    """Fetch all Swedish shelter data from MSB's ArcGIS Feature Service"""
    
    print("📥 Downloading Swedish shelter data from MSB ArcGIS Service...")
    
    # MSB's official ArcGIS Feature Service for shelters
    base_url = "https://services6.arcgis.com/NThLsKaeOKhGxBBE/arcgis/rest/services/Skyddsrum_220225/FeatureServer/1/query"
    
    all_features = []
    offset = 0
    page_size = 2000  # ArcGIS max record count
    
    while True:
        params = {
            "where": "1=1",  # Get all records
            "outFields": "Gatuadress,AntalPlatser,Skyddsrumsnr,Kommunnamn,XKoordinat,YKoordinat",
            "returnGeometry": "true",
            "outSR": "4326",  # WGS84 (lat/lon)
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
            
            # Check if we got all records
            if len(features) < page_size:
                break
                
            offset += page_size
            
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            break
    
    print(f"\n✅ Downloaded {len(all_features)} shelters total")
    return all_features

def convert_to_app_format(arcgis_features):
    """Convert ArcGIS features to our app's GeoJSON format"""
    
    print("🔄 Converting to app format...")
    
    features = []
    swedish_char_count = 0
    
    for idx, arcgis_feature in enumerate(arcgis_features):
        attrs = arcgis_feature.get("attributes", {})
        geom = arcgis_feature.get("geometry", {})
        
        # Extract coordinates
        if "x" in geom and "y" in geom:
            lon, lat = geom["x"], geom["y"]
        else:
            print(f"⚠️ Skipping feature {idx} - no geometry")
            continue
        
        # Extract fields with proper Swedish characters
        address = attrs.get("Gatuadress", "Okänd adress")
        if address:
            address = str(address).strip()
            # Count entries with Swedish characters
            if any(char in address for char in ['å', 'ä', 'ö', 'Å', 'Ä', 'Ö']):
                swedish_char_count += 1
        
        capacity = attrs.get("AntalPlatser", 0)
        if capacity is None:
            capacity = 0
        
        shelter_nr = attrs.get("Skyddsrumsnr", idx)
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "romnr": idx,
                "plasser": int(capacity) if capacity else 0,
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
    
    # Fetch data from MSB's ArcGIS service
    arcgis_features = fetch_all_shelters()
    
    if not arcgis_features:
        print("\n❌ FAILED to download data")
        exit(1)
    
    # Convert to our format
    geojson = convert_to_app_format(arcgis_features)
    
    # Save to file with explicit UTF-8 encoding
    output_file = "sweden_shelters.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ SUCCESS! File saved as: {output_file}")
    
    # Calculate file size
    file_size_mb = len(json.dumps(geojson, ensure_ascii=False)) / 1024 / 1024
    print(f"📊 File size: {file_size_mb:.2f} MB")
    
    # Verify Swedish characters
    with open(output_file, "r", encoding="utf-8") as f:
        content = f.read()
        swedish_chars = ['å', 'ä', 'ö', 'Å', 'Ä', 'Ö']
        found_chars = [char for char in swedish_chars if char in content]
        if found_chars:
            print(f"✅ Swedish characters preserved correctly: {', '.join(sorted(set(found_chars)))}")
            # Show a few example addresses with Swedish characters
            import re
            matches = re.findall(r'"adresse": "([^"]*[åäöÅÄÖ][^"]*)"', content)
            if matches:
                print(f"\n📋 Sample addresses with Swedish characters:")
                for addr in matches[:5]:
                    print(f"   - {addr}")
        else:
            print("⚠️ Warning: No Swedish characters found in output")
    
    print(f"\n📝 Next steps:")
    print(f"1. Copy {output_file} to your GitHub repository")
    print(f"2. Commit and push the changes")
    print(f"3. The app will download the updated data from GitHub Pages")