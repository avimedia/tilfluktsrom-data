import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Any
from tqdm import tqdm
import concurrent.futures
import os

def load_partial_shelters(path="partial_denmark_shelters.json"):
    if os.path.exists(path):
        print(f"Loading previous partial results from {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("shelters", []), set(data.get("processed_kommuner", []))
    return [], set()

def save_partial_shelters(shelters, processed_kommuner, path="partial_denmark_shelters.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "shelters": shelters,
            "processed_kommuner": list(processed_kommuner)
        }, f, ensure_ascii=False, indent=2)

class DenmarkShelterFetcher:
    def __init__(self, api_key: str, dataforsyningen_token: str = None):
        self.api_key = api_key
        self.dataforsyningen_token = dataforsyningen_token
        self.base_url = "https://graphql.datafordeler.dk/BBR/v1"
        self.dawa_base_url = "https://api.dataforsyningen.dk"
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/graphql-response+json"
        }
        
        # Try to import pyproj for accurate coordinate conversion
        try:
            from pyproj import Transformer
            # EPSG:25832 (ETRS89/UTM Zone 32N) to EPSG:4326 (WGS84)
            self.transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
            self.use_pyproj = True
            print("✓ Using pyproj for accurate coordinate conversion")
        except ImportError:
            self.transformer = None
            self.use_pyproj = False
            print("⚠ pyproj not available, using fallback conversion (install with: pip install pyproj)")
        
        # Check if Dataforsyningen token is provided
        if dataforsyningen_token:
            print("✓ Using Dataforsyningen.dk token for address lookups")
        else:
            print("⚠ No Dataforsyningen.dk token provided - address lookups may be limited")
        
        # Danish municipality codes (all 98 municipalities)
        self.municipality_codes = [
            "0101", "0147", "0151", "0153", "0155", "0157", "0159", "0161", "0163", "0165",
            "0167", "0169", "0173", "0175", "0183", "0185", "0187", "0190", "0201", "0210",
            "0217", "0219", "0223", "0230", "0240", "0250", "0253", "0259", "0260", "0265",
            "0269", "0270", "0306", "0316", "0320", "0326", "0329", "0330", "0336", "0340",
            "0350", "0360", "0370", "0376", "0390", "0400", "0410", "0411", "0420", "0430",
            "0440", "0450", "0461", "0479", "0480", "0482", "0492", "0510", "0530", "0540",
            "0550", "0561", "0563", "0573", "0575", "0580", "0607", "0615", "0621", "0630",
            "0657", "0661", "0665", "0671", "0706", "0707", "0710", "0727", "0730", "0740",
            "0741", "0746", "0751", "0756", "0760", "0766", "0773", "0779", "0787", "0791",
            "0810", "0813", "0820", "0825", "0840", "0846", "0849", "0851"
        ]
        
        # Cache for DAWA address lookups
        self.address_cache = {}
        self.address_lookup_count = 0
        self.address_success_count = 0
    
    def fetch_shelters(self, batch_size: int = 500, max_retries: int = 3) -> List[Dict[str, Any]]:
        all_shelters, processed_kommuner = load_partial_shelters()
        start_time = time.time()
        
        print("\nStarting GraphQL query for Danish shelters... (partial results loaded, {} shelters from {} kommuner)".format(
            len(all_shelters), len(processed_kommuner)))
        print(f"Processing {len(self.municipality_codes)} municipalities...\n")
        
        try:
            for idx, kommune_code in enumerate(tqdm(self.municipality_codes, desc="Municipalities", ncols=80), 1):
                if kommune_code in processed_kommuner:
                    print(f"⏩ Skipping kommune {kommune_code} (already processed)")
                    continue
                kommune_name = "København (Copenhagen)" if kommune_code == "0101" else f"Kommune {kommune_code}"
                success = False
                retry_count = 0
                kommune_shelters = []
                
                while retry_count < max_retries and not success:
                    try:
                        kommune_shelters = self._fetch_kommune_shelters(kommune_code, batch_size)
                        all_shelters.extend(kommune_shelters)
                        success = True
                    except requests.exceptions.Timeout:
                        retry_count += 1
                        print(f"\ntimeout, retrying {kommune_name} ({retry_count}/{max_retries})...", end=" ", flush=True)
                        time.sleep(2)
                    except Exception as e:
                        print(f"\n✗ error with {kommune_name}: {str(e)[:50]}")
                        retry_count += 1
                        time.sleep(2)
                
                processed_kommuner.add(kommune_code)
                # Save partial after each completed kommune to file
                save_partial_shelters(all_shelters, processed_kommuner)
                
                # Progress print
                elapsed = time.time() - start_time
                est_total = elapsed / idx * len(self.municipality_codes)
                print(f"\n✓ Progress: {idx}/{len(self.municipality_codes)}: {kommune_name} done. {len(all_shelters)} shelters so far.")
                print(f"Elapsed: {elapsed/60:.1f} min | Estimated total: {est_total/60:.1f} min\n")

        except Exception as outer_e:
            print(f"\n💥 Unhandled error: {str(outer_e)}")
            print("Partial results saved. You can re-run the script to resume.")

        print(f"\n{'='*60}")
        print(f"Total shelters found: {len(all_shelters)}")
        print(f"{'='*60}")
        return all_shelters
    
    def _fetch_kommune_shelters(self, kommune_code: str, batch_size: int) -> List[Dict[str, Any]]:
        """
        Fetch shelters for a specific municipality ― now with parallel address lookup!
        """
        shelters = []
        has_next_page = True
        after_cursor = None
        page_count = 0
        max_pages = 50
        total_buildings = 0

        print(f"\n--- Starting kommune {kommune_code} ---")

        buildings_to_process = []

        while has_next_page and page_count < max_pages:
            page_count += 1
            query = self._build_query(kommune_code, batch_size, after_cursor)
            
            response = requests.post(
                f"{self.base_url}?apiKey={self.api_key}",
                headers=self.headers,
                json={"query": query},
                timeout=60
            )
            
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            
            data = response.json()
            
            if "errors" in data:
                error_msg = data['errors'][0].get('message', 'Unknown error')
                raise Exception(error_msg)
            
            buildings_data = data.get("data", {}).get("BBR_Bygning", {})
            nodes = buildings_data.get("nodes", [])
            page_info = buildings_data.get("pageInfo", {})

            total_buildings += len(nodes)

            for b_idx, building in enumerate(nodes, 1):
                shelter_capacity = building.get("byg069Sikringsrumpladser")
                if shelter_capacity and shelter_capacity >= 30:
                    buildings_to_process.append(building)
                if b_idx % 100 == 0 or b_idx == len(nodes):
                    print(f"   ...Queued {b_idx}/{len(nodes)} buildings for parallel address lookup in kommune {kommune_code}")
            
            has_next_page = page_info.get("hasNextPage", False)
            after_cursor = page_info.get("endCursor")
            
            if not nodes:
                break

        # Process buildings in parallel for address lookup!
        shelters = self._process_buildings_parallel(buildings_to_process, kommune_code=kommune_code)
        print(f"--- Finished kommune {kommune_code}: found {len(shelters)} shelters out of {total_buildings} buildings checked ---\n")
        return shelters
    
    def _process_buildings_parallel(self, buildings: List[Dict[str, Any]], kommune_code: str = "") -> List[Dict[str, Any]]:
        """
        Process buildings in parallel using ThreadPoolExecutor for fast DAWA lookups.
        """
        shelters = []
        max_workers = min(16, (concurrent.futures.thread._MAX_WORKERS if hasattr(concurrent.futures.thread, '_MAX_WORKERS') else 16))
        print(f"--> Running parallel DAWA lookups for {len(buildings)} buildings in kommune {kommune_code} (workers={max_workers})")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for building in buildings:
                futures.append(executor.submit(self._process_building, building))
            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                shelter = future.result()
                if shelter: shelters.append(shelter)
                if idx % 100 == 0 or idx == len(futures):
                    print(f"      ...processed {idx}/{len(futures)} shelters")
        return shelters
    
    def _build_query(self, kommune_code: str, first: int, after_cursor: str = None) -> str:
        """
        Build the GraphQL query for BBR buildings in a specific municipality.
        """
        after_param = f', after: "{after_cursor}"' if after_cursor else ""
        
        # Get current timestamp for bitemporal query (required by API)
        current_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Simplified query - only fetch fields we know work
        query = f"""
        query {{
          BBR_Bygning(
            first: {first}{after_param}
            registreringstid: "{current_time}"
            virkningstid: "{current_time}"
            where: {{
              kommunekode: {{ eq: "{kommune_code}" }}
              status: {{ eq: "6" }}
            }}
          ) {{
            pageInfo {{
              hasNextPage
              endCursor
            }}
            nodes {{
              id_lokalId
              byg069Sikringsrumpladser
              kommunekode
              byg404Koordinat {{
                wkt
              }}
            }}
          }}
        }}
        """
        return query
    
    def _process_building(self, building: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single building record and convert to GeoJSON feature format.
        Fully safe for parallel usage.
        """
        try:
            # Extract coordinates from byg404Koordinat
            koordinat = building.get("byg404Koordinat")
            if not koordinat:
                return None
            
            # Extract WKT and parse coordinates
            wkt = koordinat.get("wkt")
            if not wkt:
                return None
            
            coordinates = self._extract_coordinates_from_wkt(wkt)
            if not coordinates:
                return None
            
            # Look up nearest address by coordinates (within 200m)
            lon, lat = coordinates
            try:
                # Catch DAWA lookup error very tightly
                address, distance = self._lookup_address_by_coordinates(lon, lat, max_distance=200)
            except Exception:
                address, distance = ("", None)
            
            # If no address found within 200m, use empty string (shelter will still be included)
            if not address:
                address = ""
                distance = None
            
            # Get shelter capacity
            shelter_capacity = building.get("byg069Sikringsrumpladser", 0)
            
            # Create unique room number from id_lokalId
            id_lokalid = building.get("id_lokalId", "")
            try:
                # Extract numbers from UUID-like id
                romnr = int(''.join(filter(str.isdigit, id_lokalid))[:9]) % 1000000
            except:
                romnr = hash(id_lokalid) % 1000000
            
            # Create GeoJSON feature
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": coordinates
                },
                "properties": {
                    "romnr": romnr,
                    "plasser": shelter_capacity,
                    "adresse": address,
                    "adresse_avstand": distance,
                    "datauttaksdato": datetime.now().strftime("%Y-%m-%d")
                }
            }
            
            return feature
            
        except Exception as e:
            return None
    
    def _build_fallback_address(self, building: Dict[str, Any]) -> str:
        return ""
    
    def _extract_coordinates_from_wkt(self, wkt_string: str) -> List[float]:
        """
        Extract coordinates from WKT (Well-Known Text) format.
        Expected format: "POINT (easting northing)" in EPSG:25832
        We need to convert to WGS84 (lon, lat) for GeoJSON
        """
        if not wkt_string:
            return None
        
        try:
            # Remove "POINT (" prefix and ")" suffix
            coords_str = wkt_string.replace("POINT (", "").replace("POINT(", "").replace(")", "").strip()
            parts = coords_str.split()
            
            if len(parts) >= 2:
                easting = float(parts[0])
                northing = float(parts[1])
                
                # Convert from EPSG:25832 (UTM Zone 32N) to WGS84
                lon, lat = self._convert_utm32_to_wgs84(easting, northing)
                
                # REMOVE verbose debug print, only print on first 2 for safety
                if hasattr(self, "_coord_debug_count"):
                    self._coord_debug_count += 1
                else:
                    self._coord_debug_count = 1

                if self._coord_debug_count <= 2:
                    print(f"Converted UTM32 ({easting},{northing}) → WGS84 (lon={lon}, lat={lat}) [Check at https://epsg.io/transform]")
                
                return [lon, lat]
        except Exception as e:
            print(f"Coordinate conversion error: {e}")
        
        return None
    
    def _convert_utm32_to_wgs84(self, easting: float, northing: float) -> tuple:
        """
        Convert from EPSG:25832 (ETRS89/UTM Zone 32N) to EPSG:4326 (WGS84 lon, lat).
        """
        if self.use_pyproj and self.transformer:
            # Use pyproj for accurate conversion
            lon, lat = self.transformer.transform(easting, northing)
            return (lon, lat)
        else:
            # Fallback: Use proper UTM Zone 32N conversion formulas
            return self._utm32_to_wgs84_fallback(easting, northing)
    
    def _utm32_to_wgs84_fallback(self, easting: float, northing: float) -> tuple:
        """
        Fallback UTM to WGS84 conversion using proper formulas.
        Based on the Karney-Krüger transverse Mercator projection.
        """
        import math
        
        # WGS84 ellipsoid parameters
        a = 6378137.0  # Semi-major axis
        f = 1/298.257223563  # Flattening
        
        # UTM Zone 32N parameters
        k0 = 0.9996  # Scale factor
        lon0 = 9.0 * math.pi / 180.0  # Central meridian (9°E)
        E0 = 500000.0  # False easting
        N0 = 0.0  # False northing (0 for northern hemisphere)
        
        # Remove false easting/northing
        x = easting - E0
        y = northing - N0
        
        # Derived constants
        n = f / (2 - f)
        n2 = n * n
        n3 = n2 * n
        n4 = n3 * n
        
        A = (a / (1 + n)) * (1 + n2/4 + n4/64)
        
        # Coefficients for inverse formulas
        alpha = [
            None,
            n/2 - 2*n2/3 + 5*n3/16,
            13*n2/48 - 3*n3/5,
            61*n3/240
        ]
        
        beta = [
            None,
            n/2 - 2*n2/3 + 37*n3/96,
            n2/48 + n3/15,
            17*n3/480
        ]
        
        # Calculate footpoint latitude
        xi = y / (k0 * A)
        
        xi_prime = xi
        for j in range(1, 4):
            xi_prime -= beta[j] * math.sin(2*j*xi) * math.cosh(2*j*x/(k0*A))
        
        eta_prime = x / (k0 * A)
        for j in range(1, 4):
            eta_prime -= beta[j] * math.cos(2*j*xi) * math.sinh(2*j*x/(k0*A))
        
        # Calculate latitude and longitude
        chi = math.asin(math.sin(xi_prime) / math.cosh(eta_prime))
        
        lat = chi
        for j in range(1, 4):
            lat += alpha[j] * math.sin(2*j*chi)
        
        lon = lon0 + math.atan(math.sinh(eta_prime) / math.cos(xi_prime))
        
        # Convert to degrees
        lat_deg = lat * 180.0 / math.pi
        lon_deg = lon * 180.0 / math.pi
        
        return (lon_deg, lat_deg)
    
    def _lookup_address_by_coordinates(self, lon: float, lat: float, max_distance: int = 100) -> tuple:
        """
        Look up nearest address by coordinates using DAWA circle search.
        Uses WGS84 coordinates (EPSG:4326).
        
        Args:
            lon: Longitude in WGS84
            lat: Latitude in WGS84  
            max_distance: Maximum acceptable distance in meters (default 100m)
            
        Returns:
            tuple: (address_string, distance_in_meters) or (None, None) if not found
        """
        cache_key = f"{lon:.6f},{lat:.6f}"
        
        # Check cache first
        if cache_key in self.address_cache:
            cached = self.address_cache.get(cache_key)
            return (cached, None) if cached else (None, None)
        
        self.address_lookup_count += 1
        
        # Only show debug for first few
        debug = self.address_lookup_count <= 3
        
        if debug:
            print(f"\n  [DEBUG] Looking up nearest address for: {lat:.6f}°N, {lon:.6f}°E")
            print(f"  [DEBUG] Max acceptable distance: {max_distance}m")
        
        try:
            # Use DAWA's circle search with a larger search radius
            # We'll filter by distance ourselves
            search_radius = 500  # Search in a 500m radius
            url = f"{self.dawa_base_url}/adgangsadresser"
            params = {
                "cirkel": f"{lon},{lat},{search_radius}",
                "srid": "4326",
                "struktur": "mini"
            }
            
            if self.dataforsyningen_token:
                params["token"] = self.dataforsyningen_token
            
            response = requests.get(url, params=params, timeout=5)
            
            if debug:
                print(f"  [DEBUG] Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    # Calculate distance to first (closest) address
                    addr_data = data[0]
                    addr_lon = addr_data.get("x", 0)
                    addr_lat = addr_data.get("y", 0)
                    
                    # Calculate approximate distance in meters
                    # Simple haversine for small distances
                    import math
                    dlat = math.radians(addr_lat - lat)
                    dlon = math.radians(addr_lon - lon)
                    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(addr_lat)) * math.sin(dlon/2)**2
                    c = 2 * math.asin(math.sqrt(a))
                    distance = 6371000 * c  # Earth radius in meters
                    
                    if debug:
                        print(f"  [DEBUG] Nearest address distance: {distance:.1f}m")
                    
                    # Only accept if within max_distance
                    if distance > max_distance:
                        if debug:
                            print(f"  [DEBUG] ✗ Address too far ({distance:.1f}m > {max_distance}m)\n")
                        self.address_cache[cache_key] = None
                        return (None, None)
                    
                    vejnavn = addr_data.get("vejnavn", "")
                    husnr = addr_data.get("husnr", "")
                    postnr = addr_data.get("postnr", "")
                    postnrnavn = addr_data.get("postnrnavn", "")
                    
                    if vejnavn and husnr:
                        address = f"{vejnavn} {husnr}"
                        if postnr and postnrnavn:
                            address += f", {postnr} {postnrnavn}"
                        
                        self.address_cache[cache_key] = address
                        self.address_success_count += 1
                        
                        if debug:
                            print(f"  [DEBUG] ✓ Resolved to: {address} (distance: {distance:.1f}m)\n")
                        
                        return (address, round(distance))
                
        except Exception as e:
            if debug:
                print(f"  [DEBUG] ✗ Error: {str(e)}\n")
        
        self.address_cache[cache_key] = None
        return (None, None)

    def _lookup_dar_address(self, husnummer_id: str) -> str:
        """
        Look up actual street address from DAWA (Danish Address Web API).
        NOTE: This method is kept for compatibility but BBR husnummer IDs
        don't match DAWA address IDs. Use _lookup_address_by_coordinates instead.
        """
        return None

    def _lookup_address_by_husnummer_id(self, husnummer_id: str) -> str:
        """
        This method is kept for compatibility but BBR doesn't provide husnummer IDs.
        """
        return None

    def _build_address(self, building: Dict[str, Any]) -> str:
        """
        Build a human-readable address from building data.
        NOTE: This is no longer used - addresses are now resolved in _process_building.
        """
        kommune = building.get("kommunekode", "")
        husnummer_id = building.get("husnummer", "")
        
        parts = []
        if kommune:
            parts.append(f"Kommune {kommune}")
        if husnummer_id:
            parts.append(f"Husnummer: {husnummer_id}")
        
        return ", ".join(parts) if parts else "Ukendt adresse"
    
    def save_to_geojson(self, shelters: List[Dict[str, Any]], output_file: str):
        geojson = {
            "type": "FeatureCollection",
            "name": "Beskyttelsesrum Danmark",
            "features": shelters
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Saved {len(shelters)} shelters to {output_file}")

        # Remove partial on full success
        try:
            os.remove("partial_denmark_shelters.json")
            print("Removed partial progress file (full run completed)")
        except Exception:
            pass
        
        # Show address lookup statistics
        if self.address_lookup_count > 0:
            success_rate = (self.address_success_count / self.address_lookup_count) * 100
            print(f"\nAddress resolution statistics:")
            print(f"  Total lookups:     {self.address_lookup_count}")
            print(f"  Successful:        {self.address_success_count} ({success_rate:.1f}%)")
            print(f"  Failed/Not found:  {self.address_lookup_count - self.address_success_count}")


def main():
    # API keys
    BBR_API_KEY = "n31WJRdIAq7lmpRalX5svlz1rzSQeXuPZoXnnv8r41O4OtzdxfcSETQJ8bU7ppYF9lclkQzFGxfxT8mIPda82GMgy6YVMdGaZ"
    DATAFORSYNINGEN_TOKEN = "71b18ff9d7fa03229a141a394acef6cb"
    
    print("="*60)
    print("Danish Shelter Data Fetcher (BBR GraphQL)")
    print("="*60)
    print("\nThis will fetch real shelter data from Denmark's BBR registry.")
    print("It will take approximately 5-10 minutes to process all")
    print("98 municipalities...\n")
    
    # Create fetcher instance
    fetcher = DenmarkShelterFetcher(BBR_API_KEY, DATAFORSYNINGEN_TOKEN)
    
    # Fetch all shelters
    shelters = fetcher.fetch_shelters(batch_size=500, max_retries=3)
    
    if shelters:
        # Save to file
        output_file = "denmark_shelters.json"
        fetcher.save_to_geojson(shelters, output_file)
        print("\n" + "="*60)
        print(f"SUCCESS! Found {len(shelters)} shelters with 40+ capacity")
        print("="*60)
    else:
        print("\n⚠ No shelters found.")


if __name__ == "__main__":
    main()