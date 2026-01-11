# Tilfluktsrom Data Repository

This repository contains scripts and data for shelter locations in Norway, Denmark, and Sweden.

## Data Files

The shelter data is available via GitHub Pages:

- Norway: `https://avimedia.github.io/tilfluktsrom-data/tilfluktsrom.json`
- Denmark: `https://avimedia.github.io/tilfluktsrom-data/denmark_shelters.json`
- Sweden: `https://avimedia.github.io/tilfluktsrom-data/sweden_shelters.json`

## Automated Updates

GitHub Actions workflows automatically update the data:

- **Swedish shelters**: Daily at 3:00 AM UTC (from MSB ArcGIS API)
- **Danish shelters**: Weekly on Tuesdays at 2:10 AM UTC (from BBR GraphQL API)

## Running Scripts Locally

### Prerequisites

Install required Python packages: