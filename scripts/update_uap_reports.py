#!/usr/bin/env python3
"""Daily UAP report updater.

This script is a safe first-stage ingestion pipeline for the UAP Global Map.
It reads public RSS/search-style feeds, extracts candidate UAP items, tries to
identify locations from titles/snippets, geocodes known locations from a small
curated gazetteer, and appends new records to data/uap_reports.json.

The goal is reliability-first automation:
- Do not invent coordinates.
- Do not overwrite existing records.
- Mark low-confidence social/web reports clearly.
- Only pin when latitude and longitude are available.

You can expand FEEDS and GAZETTEER over time.
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
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "uap_reports.json"

KEYWORDS = [
    "uap",
    "ufo",
    "unidentified aerial",
    "unidentified anomalous",
    "orb",
    "tic tac",
    "flying saucer",
    "pentagon",
    "pursue",
    "disclosure",
]

# RSS-style sources. Reddit exposes RSS through .rss endpoints.
FEEDS = [
    {
        "name": "Reddit r/UFOs new",
        "url": "https://www.reddit.com/r/UFOs/new/.rss",
        "source_type": "reddit",
        "confidence": "low",
    },
    {
        "name": "Reddit r/UAP new",
        "url": "https://www.reddit.com/r/UAP/new/.rss",
        "source_type": "reddit",
        "confidence": "low",
    },
    {
        "name": "Google News UAP RSS",
        "url": "https://news.google.com/rss/search?q=UAP%20OR%20UFO%20sighting%20OR%20Pentagon%20UAP%20disclosure&hl=en-US&gl=US&ceid=US:en",
        "source_type": "news_search",
        "confidence": "low",
    },
    {
        "name": "Google News Pentagon UAP RSS",
        "url": "https://news.google.com/rss/search?q=Pentagon%20UAP%20files%20OR%20UFO%20disclosure&hl=en-US&gl=US&ceid=US:en",
        "source_type": "news_search",
        "confidence": "medium",
    },
]

# Conservative location matching. Add more places as the map grows.
GAZETTEER = {
    "sandia": (35.0540, -106.5400, "Sandia, New Mexico, USA", "approximate_facility_area"),
    "new mexico": (34.5199, -105.8701, "New Mexico, USA", "state_centroid"),
    "lake huron": (44.8000, -82.4000, "Lake Huron", "regional_lake"),
    "syria": (34.8021, 38.9968, "Syria", "country_centroid_unverified"),
    "iran": (32.4279, 53.6880, "Iran", "country_centroid_unverified"),
    "iraq": (33.2232, 43.6793, "Iraq", "country_centroid_unverified"),
    "united arab emirates": (23.4241, 53.8478, "United Arab Emirates", "country_centroid_unverified"),
    "uae": (23.4241, 53.8478, "United Arab Emirates", "country_centroid_unverified"),
    "east china sea": (29.5000, 126.0000, "East China Sea", "regional_maritime"),
    "japan": (36.2048, 138.2529, "Japan", "country_centroid_unverified"),
    "indopacom": (7.0000, 150.0000, "Indo-Pacific region", "regional_maritime"),
    "indo-pacific": (7.0000, 150.0000, "Indo-Pacific region", "regional_maritime"),
    "oregon": (43.8041, -120.5542, "Oregon, USA", "state_centroid"),
    "jersey city": (40.7178, -74.0431, "Jersey City, New Jersey, USA", "city_centroid"),
    "athens": (37.9838, 23.7275, "Athens, Greece", "city_centroid"),
    "greece": (39.0742, 21.8243, "Greece", "country_centroid_unverified"),
    "crete": (35.2401, 24.8093, "Crete, Greece", "island_centroid"),
    "peckham": (51.4746, -0.0698, "Peckham, London, UK", "city_area"),
    "london": (51.5072, -0.1276, "London, UK", "city_centroid"),
    "mayon": (13.2570, 123.6856, "Mount Mayon, Albay, Philippines", "exact_landmark"),
    "philippines": (12.8797, 121.7740, "Philippines", "country_centroid_unverified"),
    "mecheda": (22.4050, 87.8530, "Mecheda, West Bengal, India", "city_centroid"),
    "west bengal": (22.9868, 87.8550, "West Bengal, India", "state_centroid"),
    "ukraine": (48.3794, 31.1656, "Ukraine", "country_centroid_unverified"),
    "donetsk": (48.0159, 37.8028, "Donetsk region, Ukraine", "regional"),
    "china": (35.8617, 104.1954, "China", "country_centroid_unverified"),
}

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
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"auto-{digest}"


def load_existing() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_reports(reports: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "UAP-Global-Map/0.1 (+https://github.com/qshaiya/UAP-Global-Map)",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def parse_feed(feed: dict) -> list[FeedItem]:
    try:
        raw = fetch_url(feed["url"])
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: failed to fetch {feed['name']}: {exc}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"WARN: failed to parse {feed['name']}: {exc}", file=sys.stderr)
        return []

    items: list[FeedItem] = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        pub = clean_text(item.findtext("pubDate")) or None
        desc = clean_text(item.findtext("description"))
        if title and link:
            items.append(FeedItem(title, link, pub, desc, feed["name"], feed["source_type"], feed["confidence"]))

    # Atom, used by Reddit RSS
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
    return any(keyword in haystack for keyword in KEYWORDS)


def find_location(item: FeedItem) -> tuple[float | None, float | None, str, str, str]:
    haystack = f"{item.title} {item.summary}".lower()
    for key, (lat, lon, name, precision) in GAZETTEER.items():
        if key in haystack:
            return lat, lon, name, precision, "pinned" if precision else "needs_better_coordinates"
    return None, None, "Unknown", "unknown", "not_pinned_missing_coordinates"


def normalize_date(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    # Keep feed date as text because feeds use several formats.
    return value


def build_report(item: FeedItem) -> dict:
    lat, lon, location, precision, pin_status = find_location(item)
    item_id = stable_id(item.url or item.title)
    today = datetime.now(timezone.utc).date().isoformat()

    return {
        "id": item_id,
        "title": item.title[:180],
        "event_date": normalize_date(item.published),
        "discovered_or_released_date": today,
        "location_name": location,
        "latitude": lat,
        "longitude": lon,
        "location_precision": precision,
        "source_type": item.source_type,
        "source_url": item.url,
        "summary": item.summary[:700] if item.summary else f"Candidate item from {item.source_name}.",
        "pin_status": pin_status,
        "confidence": item.confidence,
        "notes": "Auto-ingested candidate. Review source before treating as reliable evidence.",
    }


def dedupe(existing: list[dict], candidates: Iterable[dict]) -> list[dict]:
    seen_ids = {str(report.get("id")) for report in existing}
    seen_urls = {str(report.get("source_url")) for report in existing if report.get("source_url")}
    new_reports = []

    for report in candidates:
        if report["id"] in seen_ids or report.get("source_url") in seen_urls:
            continue
        seen_ids.add(report["id"])
        if report.get("source_url"):
            seen_urls.add(report["source_url"])
        new_reports.append(report)

    return new_reports


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
    for report in new_reports:
        print(f"- {report['title']} | {report['location_name']} | {report['pin_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
