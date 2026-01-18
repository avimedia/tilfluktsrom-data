#!/usr/bin/env python3
"""
Estonian Shelter Data Scraper
Extracts public shelter data from Maa-amet's WFS service
"""

import json
import re
from datetime import datetime
from typing import List, Dict, Any
import requests

class EstoniaShelterScraper:
    def __init__(self):
        # Direct WFS endpoint with correct layer name
        self.wfs_url = "https://xgis.maaamet.ee/xgis2/service/205arpl"
        self.layer_name = "ms:VARJEKOHT"
        
    def download_shelters(self):
        """Download shelter data directly from WFS"""
        print(f"Downloading Estonian shelters from WFS...")
        print(f"Service: {self.wfs_url}")
        print(f"Layer: {self.layer_name}\n")
        
        params = {
            'service': 'WFS',
            'version': '1.0.0',
            'request': 'GetFeature',
            'typeName': self.layer_name,
            'outputFormat': 'GML2'
        }
        
        try:
            print(f"Requesting shelter data...")
            response = requests.get(self.wfs_url, params=params, timeout=30)
            
            print(f"Response status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")
            print(f"Response size: {len(response.content)} bytes")
            
            if response.status_code == 200:
                with open('estonia_raw_response.xml', 'wb') as f:
                    f.write(response.content)
                print("Saved raw response to estonia_raw_response.xml\n")
                
                shelters = self._parse_gml_data(response.text)
                
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
    
    def _parse_gml_data(self, gml_xml: str) -> List[Dict[str, Any]]:
        """Parse GML/XML shelter data"""
        import xml.etree.ElementTree as ET
        
        shelters = []
        
        try:
            print("Parsing GML response...")
            root = ET.fromstring(gml_xml)
            
            namespaces = {
                'gml': 'http://www.opengis.net/gml',
                'ms': 'http://mapserver.gis.umn.edu/mapserver',
                'wfs': 'http://www.opengis.net/wfs'
            }
            
            feature_members = root.findall('.//gml:featureMember', namespaces)
            print(f"Found {len(feature_members)} feature members\n")
            
            for idx, member in enumerate(feature_members):
                shelter_data = {}
                
                # Extract all ms: prefixed elements (shelter properties)
                for child in member.iter():
                    tag = child.tag.split('}')[-1]
                    if child.text and child.text.strip():
                        shelter_data[tag.lower()] = child.text.strip()
                
                # Find coordinates - they're in <gml:coordinates> inside <gml:Point>
                coords_elem = member.find('.//gml:coordinates', namespaces)
                
                if coords_elem is not None and coords_elem.text:
                    # Parse "easting,northing" or "easting northing"
                    coords_text = coords_elem.text.strip().replace(',', ' ')
                    coords_parts = coords_text.split()
                    
                    if len(coords_parts) >= 2:
                        try:
                            x = float(coords_parts[0])
                            y = float(coords_parts[1])
                            
                            # Convert from EPSG:3301 to WGS84
                            lon, lat = self._convert_estonian_grid_to_wgs84(x, y)
                            
                            if idx < 3:
                                print(f"Shelter {idx + 1}:")
                                print(f"  Name: {shelter_data.get('nimi', 'N/A')}")
                                print(f"  Address: {shelter_data.get('aadress', 'N/A')}")
                                print(f"  EPSG:3301: ({x}, {y}) → WGS84: ({lon:.6f}, {lat:.6f})\n")
                            
                            # Generate romnr from ID
                            shelter_id = shelter_data.get('id', '')
                            try:
                                # Extract numbers from ID and create unique room number
                                romnr = int(''.join(filter(str.isdigit, shelter_id))[:9]) % 1000000
                            except:
                                romnr = abs(hash(shelter_id)) % 1000000
                            
                            # Extract capacity (mahutavus field)
                            capacity = 0
                            mahutavus_str = shelter_data.get('mahutavus', '0')
                            try:
                                capacity = int(mahutavus_str) if mahutavus_str else 0
                            except (ValueError, TypeError):
                                capacity = 0
                            
                            # Convert date format from DD.MM.YYYY to YYYY-MM-DD
                            date_str = shelter_data.get('andmeseis', datetime.now().strftime("%d.%m.%Y"))
                            try:
                                # Try to parse Estonian date format
                                if '.' in date_str:
                                    parts = date_str.split('.')
                                    if len(parts) == 3:
                                        date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
                            except:
                                date_str = datetime.now().strftime("%Y-%m-%d")
                            
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
                                    "adresse": shelter_data.get('aadress', ''),
                                    "adresse_avstand": None,
                                    "datauttaksdato": date_str
                                }
                            }
                            shelters.append(shelter)
                        
                        except Exception as e:
                            print(f"Error parsing coordinates for feature {idx}: {e}")
            
            print(f"\nSuccessfully parsed {len(shelters)} shelters with coordinates")
        
        except Exception as e:
            print(f"Error parsing GML: {e}")
            import traceback
            traceback.print_exc()
        
        return shelters
    
    def _convert_estonian_grid_to_wgs84(self, x: float, y: float) -> tuple:
        """Convert Estonian coordinate system (EPSG:3301) to WGS84"""
        try:
            from pyproj import Transformer
            transformer = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)
            lon, lat = transformer.transform(x, y)
            return (lon, lat)
        except ImportError:
            print("Warning: pyproj not installed, using approximate conversion")
            print("Install with: pip install pyproj")
            lon = 24.0 + (x - 500000) / 111000
            lat = 58.5 + (y - 6500000) / 111000
            return (lon, lat)
        except Exception as e:
            print(f"Coordinate conversion error for ({x}, {y}): {e}")
            return (None, None)
    
    def save_to_geojson(self, shelters: List[Dict[str, Any]], output_file: str):
        """Save shelters to GeoJSON file"""
        geojson = {
            "type": "FeatureCollection",
            "name": "Avalikud varjumiskohad (Estonia)",
            "features": shelters
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Saved {len(shelters)} shelters to {output_file}")


def main():
    print("="*70)
    print("Estonian Public Shelter Data Downloader")
    print("="*70)
    print("\nDownloading from official WFS service:")
    print("  Service: xgis2/service/205arpl")
    print("  Layer: ms:VARJEKOHT")
    print("="*70)
    print()
    
    scraper = EstoniaShelterScraper()
    
    try:
        shelters = scraper.download_shelters()
        
        if shelters:
            output_file = "estonia_shelters.json"
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
                print(f"  Coordinates: [{coords[0]:.6f}, {coords[1]:.6f}]")
                print(f"  Updated: {props['datauttaksdato']}")
        else:
            print("\n✗ No shelters downloaded")
            print("\nCheck estonia_raw_response.xml to see what was returned")
    
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()