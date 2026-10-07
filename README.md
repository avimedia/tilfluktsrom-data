# Tilfluktsrom Data Repository

This repository contains scripts and data for shelter locations in Norway, Sweden, Denmark, Estonia, Lithuania and Poland.

## Data Files

The shelter data is available via GitHub Pages as `https://avimedia.github.io/tilfluktsrom-data/<country>_shelters.json`, where `<country>` is `norway`, `sweden`, `denmark`, `estonia`, `lithuania` or `poland`. `manifest.json` lists the sha256, count and latest extraction date of each file.

## Automated Updates

| Country | Source | Workflow schedule |
|---------|--------|-------------------|
| 🇳🇴 Norway | GeoNorge (DSB) | Weekly |
| 🇸🇪 Sweden | MCF (formerly MSB) ArcGIS API | Daily |
| 🇩🇰 Denmark | Datafordeler BBR v2 + DAR v2 GraphQL | Weekly |
| 🇪🇪 Estonia | Päästeamet open data (WFS) | Weekly |
| 🇱🇹 Lithuania | PAGD via Geoportal.lt | Manual |
| 🇵🇱 Poland | dane.gov.pl dataset 28058 (PSP/MSWiA, CC BY 4.0) via the portal API | Weekly (Tuesdays) |

Every push to `docs/` redeploys GitHub Pages, and each deployment counts against the account's Actions storage, so new sources should update weekly at most and write compact JSON (as `fetch_poland_shelters.py` does).

## Running Scripts Locally

### Prerequisites

Install required Python packages:

```bash
pip install requests
```

### Norwegian Shelters

```bash
python3 fetch_norway_shelters.py
```

Downloads ZIP from GeoNorge, extracts GeoJSON, and saves to `docs/norway_shelters.json`.

### Swedish Shelters

```bash
python3 fetch_sweden_shelters.py
```

Fetches data from MSB ArcGIS API and saves to `docs/sweden_shelters.json`.

### Danish Shelters

The Danish shelter script requires API keys from Datafordeler.dk:

1. Set environment variables:

```bash
export BBR_API_KEY="your-datafordeler-api-key"   # needs access to BBR and DAR
```

2. Run the script:

```bash
python3 fetch_denmark_shelters_graphql.py
```

## Security

**IMPORTANT**: Never commit API keys to the repository!

- API keys are stored in GitHub Secrets
- Local development should use environment variables
- The `.gitignore` file prevents accidental commits of sensitive files

## Data Format

All shelter data follows the GeoJSON format:

```json
{
  "type": "FeatureCollection",
  "name": "Shelter Name",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [longitude, latitude]
      },
      "properties": {
        "romnr": 12345,
        "plasser": 150,
        "adresse": "Street Name 123",
        "sted": "Town",
        "datauttaksdato": "2026-01-11"
      }
    }
  ]
}
```

**Note**: Norwegian data uses UTM33 (EPSG:25833) coordinates, which need to be converted to WGS84 by the app.

`sted` (town or municipality) is optional; older files don't have it and the app handles both. Sources (see `place_names.py`):

| Country | `sted` from |
|---|---|
| Norway | Kartverket address API (postal town), municipality if no address within 1 km |
| Sweden | MSB `Kommunnamn` |
| Denmark | Postal town from the DAR address, else the municipality |
| Estonia | Settlement part of the address |
| Lithuania | Settlement (`gyvenviete`) |
| Poland | Locality after the last comma of the address, else the gmina |

## Data Sources

- **Norway**: DSB (Direktoratet for samfunnssikkerhet og beredskap) via GeoNorge
- **Denmark**: BBR (Bygnings- og Boligregistret) for all buildings with shelter capacity (mostly *sikringsrum*, meant for the building's occupants; BBR can't distinguish public *offentlige beskyttelsesrum*), and DAR (Danmarks Adresseregister) for each building's official address, both via Datafordeler.dk GraphQL v2. (The v1 endpoint and the DAWA address API used until 2026 have been shut down.)
- **Sweden**: MSB (Myndigheten för samhällsskydd och beredskap) via ArcGIS Feature Service

## Manual Workflow Triggers

You can manually trigger the workflows from GitHub Actions:

1. Go to: https://github.com/avimedia/tilfluktsrom-data/actions
2. Select the workflow (Norway, Denmark, or Sweden)
3. Click "Run workflow"
4. Wait for completion

## License

The data is provided by government agencies and is subject to their respective licenses.
