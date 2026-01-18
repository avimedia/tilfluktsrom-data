#!/usr/bin/env python3
"""
Lithuanian Shelter Data Scraper
Extracts public shelter data from Geoportal.lt WFS service
"""

import json
import re
from datetime import datetime
from typing import List, Dict, Any
import requests

class LithuaniaShelterScraper:
    def __init__(self):
        # WFS endpoint from Lithuanian Geoportal
        self.wfs_url = "https://www.geoportal.lt/geoportal/wfs"
        self.layer_name = "prieglobos_vietos"  # Public shelter locations layer
        
    def download_shelters(self):
        """Download shelter data from WFS"""
        print(f"Downloading Lithuanian shelters from WFS...")
        print(f"Service: {self.wfs_url}")
        print(f"Layer: {self.layer_name}\n")
        
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetFeature',
            'typeName': self.layer_name,
            'outputFormat': 'application/json'
        }
        
        try:
            print(f"Requesting shelter data...")
            response = requests.get(self.wfs_url, params=params, timeout=30)
            
            print(f"Response status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")
            print(f"Response size: {len(response.content)} bytes")
            
            if response.status_code == 200:
                with open('lithuania_raw_response.json', 'wb') as f:
                    f.write(response.content)
                print("Saved raw response to lithuania_raw_response.json\n")
                
                shelters = self._parse_geojson_data(response.json())
                
                if shelters:
                    print(f"\n✓ Successfully parsed {len(shelters)} shelters!")
                    return shelters
                else:
                    print("\n✗ No shelters found in response")
            else:
                print(f"\n✗ HTTP error: {response.status_code}")
                print(response.text[:500])
        
        except Exception as e:
            print(f"\n✗ Error downloading shelters: {e}")
            import traceback
            traceback.print_exc()
        
        return []
    
    def _parse_geojson_data(self, geojson_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse GeoJSON shelter data"""
        shelters = []
        
        try:
            print("Parsing GeoJSON response...")
            
            if 'features' not in geojson_data:
                print("No 'features' key in GeoJSON")
                return []
            
            features = geojson_data['features']
            print(f"Found {len(features)} features\n")
            
            for idx, feature in enumerate(features):
                try:
                    # Extract coordinates
                    if 'geometry' not in feature or 'coordinates' not in feature['geometry']:
                        continue
                    
                    coords = feature['geometry']['coordinates']
                    lon, lat = coords[0], coords[1]
                    
                    # Extract properties
                    props = feature.get('properties', {})
                    
                    if idx < 3:
                        print(f"Shelter {idx + 1}:")
                        print(f"  Address: {props.get('address', 'N/A')}")
                        print(f"  Municipality: {props.get('municipality', 'N/A')}")
                        print(f"  Coordinates: ({lon:.6f}, {lat:.6f})\n")
                    
                    # Generate unique romnr from ID or hash
                    shelter_id = props.get('id', props.get('objectid', str(idx)))
                    try:
                        romnr = int(''.join(filter(str.isdigit, str(shelter_id)))[:9]) % 1000000
                    except:
                        romnr = abs(hash(str(shelter_id))) % 1000000
                    
                    # Extract capacity
                    capacity = 0
                    capacity_field = props.get('capacity', props.get('talpa', 0))
                    try:
                        capacity = int(capacity_field) if capacity_field else 0
                    except (ValueError, TypeError):
                        capacity = 0
                    
                    # Get address
                    address = props.get('address', props.get('adresas', ''))
                    if not address:
                        # Try to construct from municipality
                        municipality = props.get('municipality', props.get('savivaldybe', ''))
                        address = municipality if municipality else 'Unknown address'
                    
                    # Get update date
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    date_field = props.get('updated', props.get('atnaujinta', ''))
                    if date_field:
                        try:
                            # Try to parse and convert to YYYY-MM-DD
                            if '-' in date_field:
                                date_str = date_field.split('T')[0]  # Remove time if present
                        except:
                            pass
                    
                    # Create feature matching the Swift model format
                    shelter = {
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
                    shelters.append(shelter)
                
                except Exception as e:
                    print(f"Error parsing feature {idx}: {e}")
                    continue
            
            print(f"\nSuccessfully parsed {len(shelters)} shelters")
        
        except Exception as e:
            print(f"Error parsing GeoJSON: {e}")
            import traceback
            traceback.print_exc()
        
        return shelters
    
    def save_to_geojson(self, shelters: List[Dict[str, Any]], output_file: str):
        """Save shelters to GeoJSON file"""
        geojson = {
            "type": "FeatureCollection",
            "name": "Būstinės apsaugos prieglobos vietos (Lithuania)",
            "features": shelters
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Saved {len(shelters)} shelters to {output_file}")


def main():
    print("="*70)
    print("Lithuanian Public Shelter Data Downloader")
    print("="*70)
    print("\nDownloading from official Geoportal WFS service:")
    print("  Service: geoportal.lt/geoportal/wfs")
    print("  Layer: prieglobos_vietos")
    print("="*70)
    print()
    
    scraper = LithuaniaShelterScraper()
    
    try:
        shelters = scraper.download_shelters()
        
        if shelters:
            output_file = "lithuania_shelters.json"
            scraper.save_to_geojson(shelters, output_file)
            
            print("\n" + "="*70)
            print(f"SUCCESS! Downloaded {len(shelters)} shelters")
            print("="*70)
            
            # Show sample
            print("\nFirst 3 shelters:")
            for i, shelter in enumerate(shelters[:3]):
                props = shelter['properties']
                coords = shelter['geometry']['coordinates']
                print(f"\n#{i+1}:")
                print(f"  Room number: {props['romnr']}")
                print(f"  Address: {props['adresse']}")
                print(f"  Capacity: {props['plasser']}")
                print(f"  Coordinates: [{coords[0]:.6f}, {coords[1]:.6f}]")
                print(f"  Updated: {props['datauttaksdato']}")
        else:
            print("\n✗ No shelters downloaded")
            print("\nCheck lithuania_raw_response.json to see what was returned")
    
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
