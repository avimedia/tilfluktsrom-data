# Tilfluktsrom Data Repository

This repository contains scripts and data for shelter locations in Norway, Denmark, and Sweden.

## Data Files

The shelter data is available via GitHub Pages:

- **Norway**: `https://avimedia.github.io/tilfluktsrom-data/norway_shelters.json`
- **Denmark**: `https://avimedia.github.io/tilfluktsrom-data/denmark_shelters.json`
- **Sweden**: `https://avimedia.github.io/tilfluktsrom-data/sweden_shelters.json`

## Automated Updates

GitHub Actions workflows automatically update the data:

- **Norwegian shelters**: Weekly on Mondays at 2:00 AM UTC (from GeoNorge)
- **Danish shelters**: Weekly on Tuesdays at 2:10 AM UTC (from BBR GraphQL API)
- **Swedish shelters**: Daily at 3:00 AM UTC (from MSB ArcGIS API)

## Data Statistics

| Country | Shelters | File Size | Update Frequency |
|---------|----------|-----------|------------------|
| 🇳🇴 Norway | ~560 | 0.3 MB | Weekly (Mondays) |
| 🇩🇰 Denmark | ~10,500 | 3.6 MB | Weekly (Tuesdays) |
| 🇸🇪 Sweden | ~63,500 | 21 MB | Daily |

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
export BBR_API_KEY="your-bbr-api-key"
export DATAFORSYNINGEN_TOKEN="your-dataforsyningen-token"
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
        "datauttaksdato": "2026-01-11"
      }
    }
  ]
}
```

**Note**: Norwegian data uses UTM33 (EPSG:25833) coordinates, which need to be converted to WGS84 by the app.

## Data Sources

- **Norway**: DSB (Direktoratet for samfunnssikkerhet og beredskap) via GeoNorge
- **Denmark**: BBR (Bygnings- og Boligregistret) via Datafordeler.dk
- **Sweden**: MSB (Myndigheten för samhällsskydd och beredskap) via ArcGIS Feature Service

## Manual Workflow Triggers

You can manually trigger the workflows from GitHub Actions:

1. Go to: https://github.com/avimedia/tilfluktsrom-data/actions
2. Select the workflow (Norway, Denmark, or Sweden)
3. Click "Run workflow"
4. Wait for completion

## License

The data is provided by government agencies and is subject to their respective licenses.
