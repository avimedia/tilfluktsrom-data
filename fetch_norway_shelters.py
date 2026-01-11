#!/usr/bin/env python3
"""
Generate Norwegian shelters GeoJSON from DSB/GeoNorge
For GitHub Actions: always outputs docs/norway_shelters.json and requires no manual steps.
"""

import os
import requests
import zipfile
import json
import io
from datetime import datetime

def fetch_norwegian_shelters():
    print("🇳🇴 Norwegian Shelter Data Fetcher (GeoNorge)")
    print("=" * 60)
    
    # GeoNorge URL for Norwegian shelter data
    base_url = "https://nedlasting.geonorge.no/geonorge/Samfunnssikkerhet/TilfluktsromOffentlige/GeoJSON/"
    file_name = "Samfunnssikkerhet_0000_Norge_25833_TilfluktsromOffentlige_GeoJSON.zip"
    download_url = base_url + file_name
    
    print(f"📥 Downloading Norwegian shelter data from GeoNorge...")
    print(f"   URL: {download_url}")
    
    try:
        # Download the ZIP file
        response = requests.get(download_url, timeout=120)
        response.raise_for_status()
        
        print(f"✅ Downloaded {len(response.content)} bytes")
        
        # Extract JSON from ZIP
        print("📦 Extracting JSON from ZIP file...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            # Find the JSON file in the ZIP
            json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
            
            if not json_files:
                print("❌ No JSON file found in ZIP")
                return None
            
            json_filename = json_files[0]
            print(f"   Found: {json_filename}")
            
            # Read the JSON content
            with zip_file.open(json_filename) as json_file:
                geojson = json.load(json_file)
        
        print(f"✅ Successfully loaded GeoJSON")
        print(f"   Features: {len(geojson.get('features', []))}")
        
        # Update datauttaksdato for all features to today
        today = datetime.now().strftime("%Y-%m-%d")
        for feature in geojson.get('features', []):
            if 'properties' in feature:
                feature['properties']['datauttaksdato'] = today
        
        return geojson
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error downloading data: {e}")
        return None
    except zipfile.BadZipFile as e:
        print(f"❌ Error extracting ZIP: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def save_geojson(geojson, output_path="docs/norway_shelters.json"):
    """Save GeoJSON to file"""
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        file_size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"\n✅ SUCCESS! File saved as: {output_path}")
        print(f"📊 File size: {file_size_mb:.2f} MB")
        print(f"📊 Total shelters: {len(geojson.get('features', []))}")
        
        # Show sample data
        if geojson.get('features'):
            sample = geojson['features'][0]
            print(f"\n📋 Sample shelter:")
            print(f"   Address: {sample['properties'].get('adresse', 'N/A')}")
            print(f"   Capacity: {sample['properties'].get('plasser', 'N/A')}")
            print(f"   Date: {sample['properties'].get('datauttaksdato', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return False

if __name__ == "__main__":
    geojson = fetch_norwegian_shelters()
    
    if geojson:
        success = save_geojson(geojson)
        exit(0 if success else 1)
    else:
        print("\n❌ FAILED to fetch Norwegian shelter data")
        exit(1)