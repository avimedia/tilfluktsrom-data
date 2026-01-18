#!/usr/bin/env python3
"""
Convert Lithuanian shelter geodatabase to GeoJSON format
Source: https://www.geoportal.lt/download/opendata/PAGD/PAGD_civiline_sauga.zip
"""

import geopandas as gpd
import json
from datetime import datetime
import pandas as pd

def convert_lithuania_shelters():
    print("="*70)
    print("Lithuanian Shelter Data Converter")
    print("="*70)
    print()
    
    # Read the geodatabase
    gdb_path = "PAGD_civiline_sauga.gdb"
    print(f"Reading {gdb_path}...")
    gdf = gpd.read_file(gdb_path, layer="Priedangos")
    
    print(f"Found {len(gdf)} shelters\n")
    
    # Convert to WGS84 (EPSG:4326)
    print("Converting coordinates to WGS84...")
    gdf = gdf.to_crs("EPSG:4326")
    
    # Create GeoJSON features
    features = []
    
    for idx, row in gdf.iterrows():
        try:
            # Get coordinates
            lon, lat = row.geometry.x, row.geometry.y
            
            # Build address
            address_parts = []
            if row['gatve']:
                address_parts.append(str(row['gatve']))
            if row['namo_numeris']:
                address_parts.append(str(row['namo_numeris']))
            if row['gyvenviete']:
                address_parts.append(str(row['gyvenviete']))
            if row['savivaldybe']:
                address_parts.append(str(row['savivaldybe']))
            
            address = ", ".join(address_parts) if address_parts else "Unknown address"
            
            # Get capacity
            capacity = 0
            if row['gyventoju_skaicius'] and not pd.isna(row['gyventoju_skaicius']):
                capacity = int(row['gyventoju_skaicius'])
            
            # Get update date
            date_str = datetime.now().strftime("%Y-%m-%d")
            if row['atnaujinimo_data'] and not pd.isna(row['atnaujinimo_data']):
                date_str = row['atnaujinimo_data'].strftime("%Y-%m-%d")
            
            # Generate unique romnr from index
            romnr = idx + 100000  # Start from 100000 to avoid conflicts
            
            # Create feature
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                },
                "properties": {
                    "romnr": romnr,
                    "plasser": capacity,
                    "adresse": address,
                    "adresse_avstand": None,
                    "datauttaksdato": date_str
                }
            }
            
            features.append(feature)
            
            if idx < 3:
                print(f"Shelter {idx + 1}:")
                print(f"  Address: {address}")
                print(f"  Capacity: {capacity}")
                print(f"  Coordinates: ({lon:.6f}, {lat:.6f})\n")
        
        except Exception as e:
            print(f"Error processing shelter {idx}: {e}")
            continue
    
    # Create GeoJSON FeatureCollection
    geojson = {
        "type": "FeatureCollection",
        "name": "Būstinės apsaugos prieglobos vietos (Lithuania)",
        "features": features
    }
    
    # Save to file
    output_file = "lithuania_shelters.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*70)
    print(f"SUCCESS! Converted {len(features)} shelters")
    print(f"Output: {output_file}")
    print("="*70)
    
    return features

if __name__ == "__main__":
    shelters = convert_lithuania_shelters()
