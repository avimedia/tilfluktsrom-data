#!/usr/bin/env python3
"""
Convert Lithuanian shelter geodatabase to GeoJSON format
Source: https://www.geoportal.lt/download/opendata/PAGD/PAGD_civiline_sauga.zip
"""

import geopandas as gpd
import json
from datetime import datetime
import pandas as pd
import os
import fiona

def convert_lithuania_shelters():
    print("="*70)
    print("Lithuanian Shelter Data Converter")
    print("="*70)
    
    # Find the .gdb directory
    gdb_path = None
    for root, dirs, files in os.walk("."):
        for d in dirs:
            if d.endswith(".gdb"):
                gdb_path = os.path.join(root, d)
                break
        if gdb_path:
            break
    
    if not gdb_path:
        print("ERROR: Could not find .gdb directory")
        print("Current directory contents:")
        os.system("ls -la")
        exit(1)
    
    print(f"Found GDB: {gdb_path}")
    
    # List available layers
    print("\nAvailable layers:")
    layers = fiona.listlayers(gdb_path)
    for layer in layers:
        print(f"  - {layer}")
    
    # Try to find the shelter layer
    shelter_layer = None
    for layer in layers:
        if 'priedang' in layer.lower() or 'prieglob' in layer.lower() or 'shelter' in layer.lower():
            shelter_layer = layer
            break
    
    if not shelter_layer:
        print("\nWARNING: Could not find shelter layer by name. Using first layer.")
        shelter_layer = layers[0] if layers else None
    
    if not shelter_layer:
        print("ERROR: No layers found in GDB")
        exit(1)
    
    print(f"\nReading layer: {shelter_layer}")
    gdf = gpd.read_file(gdb_path, layer=shelter_layer)
    print(f"Found {len(gdf)} features")
    
    print("\nColumn names:")
    print(gdf.columns.tolist())
    
    print("\nFirst row sample:")
    if len(gdf) > 0:
        print(gdf.head(1))
    
    # Convert to WGS84 (EPSG:4326)
    print("\nConverting coordinates to WGS84...")
    gdf = gdf.to_crs("EPSG:4326")
    
    # Create GeoJSON features
    features = []
    
    for idx, row in gdf.iterrows():
        try:
            # Get coordinates
            lon, lat = row.geometry.x, row.geometry.y
            
            # Try different possible field names for address
            address_parts = []
            
            # Street
            for field in ['gatve', 'GATVE', 'street', 'Street']:
                if field in row.index and row.get(field) and not pd.isna(row[field]):
                    address_parts.append(str(row[field]))
                    break
            
            # House number
            for field in ['namo_numeris', 'NAMO_NUMERIS', 'house_number', 'HouseNumber']:
                if field in row.index and row.get(field) and not pd.isna(row[field]):
                    address_parts.append(str(row[field]))
                    break
            
            # City/Settlement
            for field in ['gyvenviete', 'GYVENVIETE', 'city', 'miestas', 'MIESTAS', 'City']:
                if field in row.index and row.get(field) and not pd.isna(row[field]):
                    address_parts.append(str(row[field]))
                    break
            
            # Municipality
            for field in ['savivaldybe', 'SAVIVALDYBE', 'municipality', 'Municipality']:
                if field in row.index and row.get(field) and not pd.isna(row[field]):
                    address_parts.append(str(row[field]))
                    break
            
            address = ", ".join(address_parts) if address_parts else f"Shelter location {idx+1}"
            
            # Get capacity - try multiple field names
            capacity = 0
            for field in ['gyventoju_skaicius', 'GYVENTOJU_SKAICIUS', 'capacity', 'Capacity', 'talpa', 'TALPA', 'plasser', 'PLASSER']:
                if field in row.index and row.get(field) and not pd.isna(row[field]):
                    try:
                        capacity = int(row[field])
                        break
                    except (ValueError, TypeError):
                        pass
            
            # Get update date
            date_str = datetime.now().strftime("%Y-%m-%d")
            for field in ['atnaujinimo_data', 'ATNAUJINIMO_DATA', 'updated', 'Updated', 'date', 'Date']:
                if field in row.index and row.get(field) and not pd.isna(row[field]):
                    try:
                        date_str = pd.to_datetime(row[field]).strftime("%Y-%m-%d")
                        break
                    except:
                        pass
            
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
                print(f"\nShelter {idx + 1}:")
                print(f"  Address: {address}")
                print(f"  Capacity: {capacity}")
                print(f"  Coordinates: ({lon:.6f}, {lat:.6f})")
        
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