#!/usr/bin/env python3
"""Write docs/manifest.json describing every docs/<country>_shelters.json.

The iOS app reads the manifest to skip downloading files that haven't changed
(by comparing sha256) and to show "newer data available" (by comparing
latestExtractDate). The app works without the manifest, so a missing or stale
manifest only costs an extra download, never a missed update.

Dates are compared on their first 10 characters (YYYY-MM-DD) because Norway's
source uses "YYYY-MM-DDTHH:MM:SS" while the other countries use "YYYY-MM-DD".
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DOCS = Path(__file__).resolve().parent / "docs"
COUNTRIES = ["norway", "sweden", "denmark", "estonia", "lithuania"]


def describe(path: Path) -> dict:
    raw = path.read_bytes()
    collection = json.loads(raw)
    features = collection.get("features", [])
    dates = [
        f.get("properties", {}).get("datauttaksdato")
        for f in features
        if isinstance(f.get("properties", {}).get("datauttaksdato"), str)
    ]
    latest = max(dates, key=lambda d: d[:10]) if dates else None
    return {
        "file": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "count": len(features),
        "latestExtractDate": latest,
    }


def main() -> None:
    countries = {}
    for country in COUNTRIES:
        path = DOCS / f"{country}_shelters.json"
        if not path.exists():
            print(f"skipping {country}: {path.name} not found")
            continue
        countries[country] = describe(path)
        entry = countries[country]
        print(f"{country}: {entry['count']} shelters, latest {entry['latestExtractDate']}")

    manifest = {
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "countries": countries,
    }
    (DOCS / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
