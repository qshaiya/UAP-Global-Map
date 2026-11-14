#!/usr/bin/env python3
"""Daily UAP report updater for UAP Global Map.

This script appends candidate UAP/disclosure reports to data/uap_reports.json.
It is designed to be conservative but useful:
- It never overwrites existing reports.
- It appends new candidates from Reddit RSS, Google News RSS, and public search RSS feeds.
- New candidates remain pending review and never become automatic map pins.
- It separates publication, ingestion, and explicitly stated event dates.
- It stores unpinned reports too, so the map dashboard can show backlog count.

Important: this is not proof that a report is real. It is an intelligence-intake
pipeline for review, mapping, and later verification.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

COORD_RE = re.compile(r"(?<![\d.])(?P<lat>-?\d{1,2}\.\d{3,})\s*,\s*(?P<lon>-?\d{1,3}\.\d{3,})(?![\d.])")

@dataclass
class FeedItem:
    title: str
    url: str
    published: str | None
    summary: str
    source_name: str
    source_type: str
    confidence: str
    raw_title: str | None = None
    raw_content: str | None = None


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    # Reddit RSS footer is attribution, not report content.
    return re.split(r"\s*submitted by\s+/?u/", value, maxsplit=1, flags=re.I)[0].strip()


def canonical_source_url(url: str) -> str:
    """Unwrap Bing RSS redirects; preserve identifiers and non-tracking queries."""
    for _ in range(3):
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname in {"bing.com", "www.bing.com"} and parsed.path.lower() == "/news/apiclick.aspx":
            target = urllib.parse.parse_qs(parsed.query).get("url", [None])[0]
            if target and urllib.parse.urlsplit(target).scheme in {"http", "https"}:
                url = target
                continue
        break
    parsed = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "msclkid"}]
    host = parsed.netloc.lower()
    path = parsed.path
    if parsed.hostname in {"reddit.com", "www.reddit.com", "old.reddit.com"}:
        post = re.match(r"/r/([^/]+)/comments/([a-z0-9]+)(?:/|$)", path, re.I)
        if post:
            host = "www.reddit.com"
            path = f"/r/{post[1].lower()}/comments/{post[2].lower()}/"
            query = []
    scheme = "https" if host == "www.reddit.com" else parsed.scheme.lower()
    return urllib.parse.urlunsplit((scheme, host, path, urllib.parse.urlencode(sorted(query)), ""))


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
        raw_title = item.findtext("title")
        title = clean_text(raw_title)
        link = clean_text(item.findtext("link"))
        pub = clean_text(item.findtext("pubDate")) or None
        raw_content = item.findtext("description")
        desc = clean_text(raw_content)
        if title and link:
            items.append(FeedItem(title, link, pub, desc, feed["name"], feed["source_type"], feed["confidence"], raw_title, raw_content))

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        raw_title = entry.findtext("atom:title", namespaces=ns)
        title = clean_text(raw_title)
        link = ""
        for link_el in entry.findall("atom:link", ns):
            if link_el.attrib.get("href") and link_el.attrib.get("rel", "alternate") == "alternate":
                link = link_el.attrib["href"]
                break
        pub = clean_text(entry.findtext("atom:published", namespaces=ns) or entry.findtext("atom:updated", namespaces=ns)) or None
        raw_content = entry.findtext("atom:content", namespaces=ns) or entry.findtext("atom:summary", namespaces=ns)
        summary = clean_text(raw_content)
        if title and link:
            items.append(FeedItem(title, link, pub, summary, feed["name"], feed["source_type"], feed["confidence"], raw_title, raw_content))
    return items


def relevant(item: FeedItem) -> bool:
    haystack = f"{item.title} {item.summary}".lower()
    return any(k in haystack for k in KEYWORDS)


def classify_record(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if re.search(r"\b(?:ten|[2-9]) (?:\w+ )?(?:encounters|cases)\b|4 uap encounters", text):
        return "multi_event"
    if "time:" in text and "location:" in text:
        return "sighting_candidate"
    if re.search(r"—\s*[a-z]{3,9}\.?\s+\d{1,2},\s*\d{4}", title, re.I):
        return "sighting_candidate"
    if any(k in text for k in ("workshop", "waiver", "advisory council", "disclosure rules")):
        return "policy_news"
    if any(k in text for k in ("intelligence file", "assessment written", "declassified file")):
        return "document_analysis"
    if "larry king" in text or "sts-80" in text:
        return "media_archive"
    return "topic_candidate"


def location_evidence(item: FeedItem) -> str:
    """Only extract location proposals from sighting context, never all article text."""
    structured = re.search(r"\bLocation:\s*(.+?)(?=\s+Detail\b|\s+Reported Objects\b|$)", item.summary, re.I)
    if structured:
        return structured[1].strip()
    # Dated sighting titles such as '... over Visalia, CA — Dec 31, 2012'.
    if classify_record(item.title, item.summary) == "sighting_candidate":
        match = re.search(r"\b(?:over|near|in|at)\s+(.+?)\s*—", item.title, re.I)
        if match:
            return match[1].strip()
    return ""


def find_location(item: FeedItem) -> tuple[float | None, float | None, str, str, str]:
    evidence = location_evidence(item)
    if not evidence:
        return None, None, "Unknown", "unknown", "not_pinned_missing_coordinates"
    match = COORD_RE.search(evidence)
    if match:
        lat, lon = float(match["lat"]), float(match["lon"])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon, evidence, "coordinates_from_text_unverified", "needs_review"
    # Specific places outrank countries even when a country name is longer.
    priority = {"exact_landmark": 0, "landmark": 0, "approximate_facility_area": 1,
                "city_centroid": 2, "city_area": 2, "island_centroid": 3,
                "state_centroid": 4, "regional_lake": 5, "regional": 5,
                "regional_maritime": 6, "country_centroid_unverified": 7}
    for key, (lat, lon, name, precision) in sorted(
            GAZETTEER.items(), key=lambda x: (priority[x[1][3]], -len(x[0]))):
        if re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", evidence, re.I):
            # Broad regions remain searchable metadata, never proposed point coordinates.
            if priority[precision] >= 4:
                return None, None, evidence, precision, "not_pinned_region_too_broad"
            return lat, lon, evidence, precision, "needs_review"
    return None, None, evidence, "unknown", "needs_better_coordinates"


def publication_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return datetime.fromisoformat(value).date().isoformat()
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if dt.tzinfo is None:
        return dt.isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def normalize_date(value: str | None) -> str | None:
    published = publication_time(value)
    return published[:10] if published else None


def event_fields(item: FeedItem) -> dict:
    """Extract only explicit structured/datetime sighting text, not feed timestamps."""
    fields = {"event_date": None, "event_at": None, "event_time_text": None}
    if classify_record(item.title, item.summary) != "sighting_candidate":
        return fields
    match = re.search(r"\bTime:\s*(.+?)(?=\s+Location:|$)", item.summary, re.I)
    value = match[1] if match else item.title.split("—", 1)[-1]
    pattern = r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})(?:,?\s+(\d{1,2}):(\d{2})\s*(AM|PM)(?:\s+(UTC|EDT|EST|CDT|CST|MDT|MST|PDT|PST))?)?"
    match = re.search(pattern, value, re.I)
    if not match:
        return fields
    month, day, year, hour, minute, ampm, zone = match.groups()
    months = {name: i + 1 for i, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
    try:
        month_number = months[month[:3].lower()]
        dt = datetime(int(year), month_number, int(day))
        fields.update(event_date=dt.date().isoformat(), event_time_text=match[0])
        if hour:
            h = int(hour)
            if not 1 <= h <= 12:
                raise ValueError("Invalid 12-hour time")
            dt = dt.replace(hour=h % 12 + (12 if ampm.upper() == "PM" else 0), minute=int(minute))
            if zone:
                offsets = {"UTC": 0, "EDT": -4, "EST": -5, "CDT": -5, "CST": -6,
                           "MDT": -6, "MST": -7, "PDT": -7, "PST": -8}
                fields["event_at"] = dt.replace(tzinfo=timezone(timedelta(hours=offsets[zone.upper()]))).astimezone(timezone.utc).isoformat()
    except (KeyError, ValueError):
        return {"event_date": None, "event_at": None, "event_time_text": None}
    return fields


def build_report(item: FeedItem) -> dict:
    title = clean_text(item.title)
    summary = clean_text(item.summary)
    cleaned = FeedItem(title, item.url, item.published, summary,
                       item.source_name, item.source_type, item.confidence)
    lat, lon, location, precision, pin_status = find_location(cleaned)
    now = datetime.now(timezone.utc).isoformat()
    canonical = canonical_source_url(item.url)
    raw_content = item.raw_content if item.raw_content is not None else item.summary
    return {
        "id": stable_id(canonical),
        "title": title,
        "raw_title": item.raw_title if item.raw_title is not None else item.title,
        **event_fields(cleaned),
        "source_published_at": publication_time(item.published),
        "source_published_raw": item.published,
        "ingested_at": now,
        "discovered_or_released_date": None,
        "record_type": classify_record(title, summary),
        "review_status": "pending_review",
        "content_status": "available" if summary else "missing",
        "location_name": location,
        "latitude": lat,
        "longitude": lon,
        "location_precision": precision,
        "location_evidence": location_evidence(cleaned),
        "source_type": item.source_type,
        "source_name": item.source_name,
        "source_url": canonical,
        "raw_source_url": item.url,
        "canonical_source_url": canonical,
        "summary": summary[:900],
        "summary_truncated": len(summary) > 900,
        "raw_content": raw_content,
        "pin_status": pin_status,
        "confidence": "low",
        "confidence_basis": "Unreviewed candidate; topic keywords do not verify evidence.",
        "notes": "Auto-ingested candidate. Source content, event date and location require review before pinning.",
    }


def dedupe(existing: list[dict], candidates: Iterable[dict]) -> list[dict]:
    seen_ids = {str(r.get("id")) for r in existing}
    seen_urls = {canonical_source_url(r["source_url"]) for r in existing if r.get("source_url")}
    out = []
    for report in candidates:
        canonical = canonical_source_url(report["source_url"])
        if report["id"] in seen_ids or canonical in seen_urls:
            continue
        seen_ids.add(report["id"])
        if report.get("source_url"):
            seen_urls.add(canonical)
        out.append(report)
        if len(out) >= MAX_NEW_PER_RUN:
            break
    return out


def validate_reports(reports: list[dict]) -> None:
    ids = [r["id"] for r in reports]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate record IDs")
    known_ids = set(ids)
    for report in reports:
        if not report.get("review_status"):
            continue  # Unmigrated legacy rows are outside this repair's scope.
        if report.get("duplicate_of") and (report["duplicate_of"] not in known_ids or report["duplicate_of"] == report["id"]):
            raise ValueError(f"Invalid duplicate reference: {report['id']}")
        if report.get("pin_status") == "pinned" and (report["review_status"] != "reviewed" or report.get("duplicate_of")):
            raise ValueError(f"Unreviewed/duplicate map pin: {report['id']}")
        date = report.get("event_date")
        if date is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                raise ValueError(f"Invalid event date: {report['id']}")
            datetime.fromisoformat(date)
        lat, lon = report.get("latitude"), report.get("longitude")
        if (lat is None) != (lon is None):
            raise ValueError(f"Incomplete coordinates: {report['id']}")
        if lat is not None and (not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
                                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            raise ValueError(f"Invalid coordinates: {report['id']}")
        if report.get("pin_status") == "pinned" and lat is None:
            raise ValueError(f"Pinned without coordinates: {report['id']}")


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
    validate_reports(existing)
    save_reports(existing)
    print(f"Added {len(new_reports)} new candidate reports.")
    for r in new_reports:
        print(f"- {r['title']} | {r['location_name']} | {r['pin_status']} | {r['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
