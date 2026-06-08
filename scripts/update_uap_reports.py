#!/usr/bin/env python3
"""Daily UAP report updater for UAP Global Map.

This script appends candidate UAP/disclosure reports to data/uap_reports.json.
It is designed to be conservative but useful:
- It never overwrites existing reports.
- It appends new candidates from Reddit RSS, Google News RSS, and public search RSS feeds.
- It pins a report only when a known location term is detected.
- It clearly marks low-confidence/social reports.
- It stores unpinned reports too, so the map dashboard can show backlog count.

Important: this is not proof that a report is real. It is an intelligence-intake
pipeline for review, mapping, and later verification.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "uap_reports.json"
MAX_NEW_PER_RUN = 40

KEYWORDS = [
    "uap", "ufo", "unidentified aerial", "unidentified anomalous",
    "orb", "sphere", "tic tac", "tictac", "triangle", "cigar", "saucer",
    "flying object", "strange lights", "anomalous object",
    "pentagon", "aaro", "pursue", "disclosure", "declassified",
]

FEEDS = [
    {"name": "Reddit r/UFOs new", "url": "https://www.reddit.com/r/UFOs/new/.rss", "source_type": "reddit", "confidence": "low"},
    {"name": "Reddit r/UAP new", "url": "https://www.reddit.com/r/UAP/new/.rss", "source_type": "reddit", "confidence": "low"},
    {"name": "Reddit r/aliens new", "url": "https://www.reddit.com/r/aliens/new/.rss", "source_type": "reddit", "confidence": "low"},
    {"name": "Google News UAP sightings", "url": "https://news.google.com/rss/search?q=UAP%20OR%20UFO%20sighting%20OR%20unidentified%20aerial%20phenomenon&hl=en-US&gl=US&ceid=US:en", "source_type": "news_search", "confidence": "low"},
    {"name": "Google News UAP disclosure", "url": "https://news.google.com/rss/search?q=Pentagon%20UAP%20OR%20UFO%20disclosure%20OR%20AARO%20OR%20declassified%20UAP&hl=en-US&gl=US&ceid=US:en", "source_type": "news_search", "confidence": "medium"},
    {"name": "Bing News UFO", "url": "https://www.bing.com/news/search?q=UFO%20sighting%20UAP&format=rss", "source_type": "news_search", "confidence": "low"},
    {"name": "Bing News disclosure", "url": "https://www.bing.com/news/search?q=Pentagon%20UAP%20disclosure%20declassified&format=rss", "source_type": "news_search", "confidence": "medium"},
]

# Conservative gazetteer for regional/exact pinning. Expand over time.
GAZETTEER = {
    "sandia": (35.0540, -106.5400, "Sandia, New Mexico, USA", "approximate_facility_area"),
    "albuquerque": (35.0844, -106.6504, "Albuquerque, New Mexico, USA", "city_centroid"),
    "new mexico": (34.5199, -105.8701, "New Mexico, USA", "state_centroid"),
    "seven cabins": (35.7800, -106.4500, "Seven Cabins area, New Mexico, USA", "regional"),
    "lake huron": (44.8000, -82.4000, "Lake Huron", "regional_lake"),
    "southeastern united states": (32.8000, -83.6000, "Southeastern United States", "regional"),
    "western united states": (39.0000, -112.0000, "Western United States", "regional"),
    "oregon": (43.8041, -120.5542, "Oregon, USA", "state_centroid"),
    "california": (36.7783, -119.4179, "California, USA", "state_centroid"),
    "arizona": (34.0489, -111.0937, "Arizona, USA", "state_centroid"),
    "nevada": (38.8026, -116.4194, "Nevada, USA", "state_centroid"),
    "area 51": (37.2431, -115.7930, "Area 51 / Groom Lake, Nevada, USA", "landmark"),
    "tikaboo": (37.3472, -115.3578, "Tikaboo Peak, Nevada, USA", "landmark"),
    "jersey city": (40.7178, -74.0431, "Jersey City, New Jersey, USA", "city_centroid"),
    "new jersey": (40.0583, -74.4057, "New Jersey, USA", "state_centroid"),
    "syria": (34.8021, 38.9968, "Syria", "country_centroid_unverified"),
    "iran": (32.4279, 53.6880, "Iran", "country_centroid_unverified"),
    "iraq": (33.2232, 43.6793, "Iraq", "country_centroid_unverified"),
    "united arab emirates": (23.4241, 53.8478, "United Arab Emirates", "country_centroid_unverified"),
    "uae": (23.4241, 53.8478, "United Arab Emirates", "country_centroid_unverified"),
    "east china sea": (29.5000, 126.0000, "East China Sea", "regional_maritime"),
    "japan": (36.2048, 138.2529, "Japan", "country_centroid_unverified"),
    "okinawa": (26.3344, 127.8056, "Okinawa, Japan", "regional"),
    "indopacom": (7.0000, 150.0000, "Indo-Pacific region", "regional_maritime"),
    "indo-pacific": (7.0000, 150.0000, "Indo-Pacific region", "regional_maritime"),
    "athens": (37.9838, 23.7275, "Athens, Greece", "city_centroid"),
    "greece": (39.0742, 21.8243, "Greece", "country_centroid_unverified"),
    "crete": (35.2401, 24.8093, "Crete, Greece", "island_centroid"),
    "peckham": (51.4746, -0.0698, "Peckham, London, UK", "city_area"),
    "london": (51.5072, -0.1276, "London, UK", "city_centroid"),
    "germany": (51.1657, 10.4515, "Germany", "country_centroid_unverified"),
    "mayon": (13.2570, 123.6856, "Mount Mayon, Albay, Philippines", "exact_landmark"),
    "philippines": (12.8797, 121.7740, "Philippines", "country_centroid_unverified"),
    "mecheda": (22.4050, 87.8530, "Mecheda, West Bengal, India", "city_centroid"),
    "west bengal": (22.9868, 87.8550, "West Bengal, India", "state_centroid"),
    "india": (20.5937, 78.9629, "India", "country_centroid_unverified"),
    "ukraine": (48.3794, 31.1656, "Ukraine", "country_centroid_unverified"),
    "donetsk": (48.0159, 37.8028, "Donetsk region, Ukraine", "regional"),
    "china": (35.8617, 104.1954, "China", "country_centroid_unverified"),
    "mexico": (23.6345, -102.5528, "Mexico", "country_centroid_unverified"),
    "brazil": (-14.2350, -51.9253, "Brazil", "country_centroid_unverified"),
    "australia": (-25.2744, 133.7751, "Australia", "country_centroid_unverified"),
    "canada": (56.1304, -106.3468, "Canada", "country_centroid_unverified"),
    "united states": (39.8283, -98.5795, "United States", "country_centroid_unverified"),
    "usa": (39.8283, -98.5795, "United States", "country_centroid_unverified"),
}

COORD_RE = re.compile(r"(?P<lat>-?\d{1,2}\.\d{3,})\s*,\s*(?P<lon>-?\d{1,3}\.\d{3,})")

@dataclass
class FeedItem:
    title: str
    url: str
    published: str | None
    summary: str
    source_name: str
    source_type: str
    confidence: str


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def stable_id(text: str) -> str:
    return "auto-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load_existing() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_reports(reports: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "UAP-Global-Map/0.2 (+https://github.com/qshaiya/UAP-Global-Map)"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def parse_feed(feed: dict) -> list[FeedItem]:
    try:
        root = ET.fromstring(fetch_url(feed["url"]))
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: failed to fetch/parse {feed['name']}: {exc}", file=sys.stderr)
        return []

    items: list[FeedItem] = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        pub = clean_text(item.findtext("pubDate")) or None
        desc = clean_text(item.findtext("description"))
        if title and link:
            items.append(FeedItem(title, link, pub, desc, feed["name"], feed["source_type"], feed["confidence"]))

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = clean_text(entry.findtext("atom:title", namespaces=ns))
        link = ""
        for link_el in entry.findall("atom:link", ns):
            if link_el.attrib.get("href"):
                link = link_el.attrib["href"]
                break
        pub = clean_text(entry.findtext("atom:updated", namespaces=ns)) or None
        summary = clean_text(entry.findtext("atom:content", namespaces=ns) or entry.findtext("atom:summary", namespaces=ns))
        if title and link:
            items.append(FeedItem(title, link, pub, summary, feed["name"], feed["source_type"], feed["confidence"]))
    return items


def relevant(item: FeedItem) -> bool:
    haystack = f"{item.title} {item.summary}".lower()
    return any(k in haystack for k in KEYWORDS)


def find_location(item: FeedItem) -> tuple[float | None, float | None, str, str, str]:
    haystack = f"{item.title} {item.summary}".lower()

    match = COORD_RE.search(haystack)
    if match:
        lat, lon = float(match.group("lat")), float(match.group("lon"))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon, f"Coordinates {lat}, {lon}", "exact_coordinates_from_text", "pinned"

    for key, (lat, lon, name, precision) in sorted(GAZETTEER.items(), key=lambda x: len(x[0]), reverse=True):
        if key in haystack:
            return lat, lon, name, precision, "pinned"
    return None, None, "Unknown", "unknown", "not_pinned_missing_coordinates"


def normalize_date(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except Exception:  # noqa: BLE001
        return value


def strengthen_confidence(item: FeedItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if any(term in text for term in ["official", "pentagon", "aaro", "declassified", "department of defense", "dod", "military"]):
        return "medium"
    return item.confidence


def build_report(item: FeedItem) -> dict:
    lat, lon, location, precision, pin_status = find_location(item)
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "id": stable_id(item.url or item.title),
        "title": item.title[:220],
        "event_date": normalize_date(item.published),
        "discovered_or_released_date": today,
        "location_name": location,
        "latitude": lat,
        "longitude": lon,
        "location_precision": precision,
        "source_type": item.source_type,
        "source_url": item.url,
        "summary": item.summary[:900] if item.summary else f"Candidate item from {item.source_name}.",
        "pin_status": pin_status,
        "confidence": strengthen_confidence(item),
        "notes": "Auto-ingested candidate. Treat as unverified until reviewed. Regional/country pins are approximate.",
    }


def dedupe(existing: list[dict], candidates: Iterable[dict]) -> list[dict]:
    seen_ids = {str(r.get("id")) for r in existing}
    seen_urls = {str(r.get("source_url")) for r in existing if r.get("source_url")}
    out = []
    for report in candidates:
        if report["id"] in seen_ids or report.get("source_url") in seen_urls:
            continue
        seen_ids.add(report["id"])
        if report.get("source_url"):
            seen_urls.add(report["source_url"])
        out.append(report)
        if len(out) >= MAX_NEW_PER_RUN:
            break
    return out


def main() -> int:
    existing = load_existing()
    candidates = []
    for feed in FEEDS:
        for item in parse_feed(feed):
            if relevant(item):
                candidates.append(build_report(item))

    new_reports = dedupe(existing, candidates)
    if not new_reports:
        print("No new UAP candidate reports found.")
        return 0

    existing.extend(new_reports)
    save_reports(existing)
    print(f"Added {len(new_reports)} new candidate reports.")
    for r in new_reports:
        print(f"- {r['title']} | {r['location_name']} | {r['pin_status']} | {r['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
