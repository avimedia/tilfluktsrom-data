#!/usr/bin/env python3
"""Town/municipality names ("sted") for shelters.

Each country's source carries the place differently, so each has its own rule:

- Norway: reverse lookup at Kartverket (postal town; municipality as fallback).
- Sweden: MSB's Kommunnamn field (handled in fetch_sweden_shelters.py).
- Denmark: postal town from the address ("Bakken 1, 2600 Glostrup"), else the
  municipality the shelter was fetched for.
- Estonia: settlement from "County, Municipality, Settlement, Street".
- Lithuania: town from "Street, Number, Town, Municipality".

The iOS app reads the optional "sted" property and falls back to the same
parsing (and on-device geocoding) when it is missing, so older files keep working.

Usage: python3 place_names.py docs/norway_shelters.json norway
"""

import json
import re
import sys
import time

import requests

# Danish municipality codes -> names (source: Wikidata P1168, CC0; 98 municipalities).
DENMARK_MUNICIPALITIES = {
    "0101": "København", "0147": "Frederiksberg", "0151": "Ballerup", "0153": "Brøndby",
    "0155": "Dragør", "0157": "Gentofte", "0159": "Gladsaxe", "0161": "Glostrup",
    "0163": "Herlev", "0165": "Albertslund", "0167": "Hvidovre", "0169": "Høje-Taastrup",
    "0173": "Lyngby-Taarbæk", "0175": "Rødovre", "0183": "Ishøj", "0185": "Tårnby",
    "0187": "Vallensbæk", "0190": "Furesø", "0201": "Allerød", "0210": "Fredensborg",
    "0217": "Helsingør", "0219": "Hillerød", "0223": "Hørsholm", "0230": "Rudersdal",
    "0240": "Egedal", "0250": "Frederikssund", "0253": "Greve", "0259": "Køge",
    "0260": "Halsnæs", "0265": "Roskilde", "0269": "Solrød", "0270": "Gribskov",
    "0306": "Odsherred", "0316": "Holbæk", "0320": "Faxe", "0326": "Kalundborg",
    "0329": "Ringsted", "0330": "Slagelse", "0336": "Stevns", "0340": "Sorø",
    "0350": "Lejre", "0360": "Lolland", "0370": "Næstved", "0376": "Guldborgsund",
    "0390": "Vordingborg", "0400": "Bornholm", "0410": "Middelfart", "0411": "Christiansø",
    "0420": "Assens", "0430": "Faaborg-Midtfyn", "0440": "Kerteminde", "0450": "Nyborg",
    "0461": "Odense", "0479": "Svendborg", "0480": "Nordfyns", "0482": "Langeland",
    "0492": "Ærø", "0510": "Haderslev", "0530": "Billund", "0540": "Sønderborg",
    "0550": "Tønder", "0561": "Esbjerg", "0563": "Fanø", "0573": "Varde",
    "0575": "Vejen", "0580": "Aabenraa", "0607": "Fredericia", "0615": "Horsens",
    "0621": "Kolding", "0630": "Vejle", "0657": "Herning", "0661": "Holstebro",
    "0665": "Lemvig", "0671": "Struer", "0706": "Syddjurs", "0707": "Norddjurs",
    "0710": "Favrskov", "0727": "Odder", "0730": "Randers", "0740": "Silkeborg",
    "0741": "Samsø", "0746": "Skanderborg", "0751": "Aarhus", "0756": "Ikast-Brande",
    "0760": "Ringkøbing-Skjern", "0766": "Hedensted", "0773": "Morsø", "0779": "Skive",
    "0787": "Thisted", "0791": "Viborg", "0810": "Brønderslev", "0813": "Frederikshavn",
    "0820": "Vesthimmerlands", "0825": "Læsø", "0840": "Rebild", "0846": "Mariagerfjord",
    "0849": "Jammerbugt", "0851": "Aalborg", "0860": "Hjørring",
}

_SMALL_WORDS = {"i", "på", "og", "ved", "under", "over"}


def title_case_no(name: str) -> str:
    """'MO I RANA' -> 'Mo i Rana', 'BØ I TELEMARK' -> 'Bø i Telemark'."""
    if not name:
        return name
    words = name.lower().split()
    result = []
    for index, word in enumerate(words):
        if index > 0 and word in _SMALL_WORDS:
            result.append(word)
        else:
            result.append("-".join(part[:1].upper() + part[1:] for part in word.split("-")))
    return " ".join(result)


def norway_place(easting: float, northing: float, session: requests.Session) -> str:
    """Postal town near a UTM33 point; municipality name when no address is within 1 km."""
    try:
        response = session.get(
            "https://ws.geonorge.no/adresser/v1/punktsok",
            params={"lat": northing, "lon": easting, "koordsys": 25833, "radius": 1000, "treffPerSide": 1},
            timeout=20,
        )
        if response.ok:
            addresses = response.json().get("adresser") or []
            if addresses and addresses[0].get("poststed"):
                return title_case_no(addresses[0]["poststed"])
    except requests.RequestException:
        pass

    try:
        response = session.get(
            "https://ws.geonorge.no/kommuneinfo/v1/punkt",
            params={"nord": northing, "ost": easting, "koordsys": 25833},
            timeout=20,
        )
        if response.ok:
            return response.json().get("kommunenavn") or ""
    except requests.RequestException:
        pass
    return ""


_DK_POSTAL = re.compile(r",\s*\d{4}\s+(.+?)\s*$")


def denmark_place(address: str, kommune_code: str = "") -> str:
    match = _DK_POSTAL.search(address or "")
    if match:
        return match.group(1)
    return DENMARK_MUNICIPALITIES.get(kommune_code, "")


def estonia_place(address: str) -> str:
    parts = [p.strip() for p in (address or "").split(",")]
    return parts[2] if len(parts) >= 4 else ""


def lithuania_place(address: str) -> str:
    parts = [p.strip() for p in (address or "").split(",")]
    return parts[2] if len(parts) >= 4 else ""


def _coordinate_key(feature: dict) -> str:
    coordinates = feature.get("geometry", {}).get("coordinates", [])
    return f"{coordinates[0]:.2f},{coordinates[1]:.2f}" if len(coordinates) >= 2 else ""


def enrich_collection(collection: dict, country: str, previous: dict = None) -> int:
    """Add "sted" to features that lack it; returns how many were filled.

    `previous` is last run's collection: places are reused for shelters at the same
    position, so Norway only queries Kartverket for new or moved shelters.
    """
    known = {}
    for feature in (previous or {}).get("features", []):
        place = feature.get("properties", {}).get("sted")
        if place:
            known[_coordinate_key(feature)] = place

    session = requests.Session()
    session.headers["User-Agent"] = "tilfluktsrom-data (https://github.com/avimedia/tilfluktsrom-data)"
    filled = 0
    for feature in collection.get("features", []):
        properties = feature.setdefault("properties", {})
        if properties.get("sted"):
            continue
        address = properties.get("adresse") or ""
        if country == "norway":
            place = known.get(_coordinate_key(feature))
            if not place:
                easting, northing = feature["geometry"]["coordinates"][:2]
                place = norway_place(easting, northing, session)
                time.sleep(0.05)  # be gentle with Kartverket
        elif country == "denmark":
            place = denmark_place(address)
        elif country == "estonia":
            place = estonia_place(address)
        elif country == "lithuania":
            place = lithuania_place(address)
        else:
            raise ValueError(f"No enrichment rule for {country}")
        if place:
            properties["sted"] = place
            filled += 1
    return filled


def enrich_file(path: str, country: str) -> None:
    """Add "sted" to every feature in an existing GeoJSON file that lacks it."""
    with open(path, encoding="utf-8") as f:
        collection = json.load(f)
    filled = enrich_collection(collection, country)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2)
    print(f"{country}: added sted to {filled} of {len(collection.get('features', []))} shelters")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    enrich_file(sys.argv[1], sys.argv[2])
