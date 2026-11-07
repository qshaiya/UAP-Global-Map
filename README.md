# UAP Global Map

An interactive global map for collecting, reviewing, and visualizing public UAP sighting reports and disclosure-related records.

The project stores UAP records in a JSON dataset and renders Earth-map pins automatically when a record has valid latitude and longitude coordinates.

## Live Concept

The map is designed to answer one practical question:

> Where are newly reported UAP sightings or disclosure-linked cases appearing, and which ones are reliable enough to pin?

Reports may come from official disclosures, government archives, news coverage, Reddit, X, and other public internet sources. Each item is treated as a record first. Only records with usable coordinates become visible pins.

## Current Structure

```text
.
├── index.html
└── data/
    └── uap_reports.json
```

### `index.html`

The frontend uses Leaflet to render the global map. It loads records from:

```js
const DATA_URL = './data/uap_reports.json';
```

New records require `review_status="reviewed"`, `pin_status="pinned"`, valid coordinates, and no `duplicate_of` before appearing as a map pin. Legacy records without review metadata retain their previous behavior.

### `data/uap_reports.json`

This is the accumulated master dataset. New records should be appended to this file after deduplication. Old records should not be deleted simply because a newer search was performed.

## Data Philosophy

This project separates three ideas:

1. **Record** — a sighting, disclosure document, news report, or public claim that should be tracked.
2. **Pin** — a record with enough location information to appear on the map.
3. **Review status** — the confidence level and quality of the source/location data.

A record can exist in the dataset without being pinned.

For example:

- A government disclosure document with no coordinates should be stored but not pinned.
- A Reddit sighting with only a country name should usually be marked as approximate or not pinned.
- A report with a city, facility, airport, or precise coordinates may be pinned.

## Record Schema

Each record should follow this structure:

```json
{
  "id": "unique-record-id",
  "title": "Short report title",
  "event_date": null,
  "event_at": null,
  "event_time_text": null,
  "source_published_at": "2026-10-05T00:00:00+00:00",
  "ingested_at": "2026-10-05T01:00:00+00:00",
  "review_status": "pending_review",
  "record_type": "sighting_candidate",
  "discovered_or_released_date": null,
  "location_name": "Readable location name",
  "latitude": null,
  "longitude": null,
  "location_precision": "exact | city | regional | country_centroid_unverified | unknown | non_earth_location",
  "source_type": "official_disclosure | government_disclosure_news_report | news | reddit | x | public_web",
  "source_url": "https://example.com/source",
  "summary": "Brief summary of the report and why it matters.",
  "pin_status": "not_pinned_missing_coordinates",
  "confidence": "low | medium | medium-high | high",
  "notes": "Review notes, caveats, or geolocation explanation."
}
```

## Pinning Rules

A record should be pinned only when:

- `latitude` is a valid number between `-90` and `90`.
- `longitude` is a valid number between `-180` and `180`.
- The location is specific enough to be meaningful on a map.
- `pin_status` is set to `pinned`.
- New/repaired records have `review_status="reviewed"` and no `duplicate_of`.
- Source content, event context, and location evidence have been reviewed.

A record should not be pinned when:

- The location is unknown.
- The only known location is too broad, such as "Western United States".
- The event is not Earth-based, such as a Moon or space-only anomaly.
- The coordinates are only guessed and could mislead viewers.

## Confidence Levels

Suggested confidence meanings:

| Confidence | Meaning |
|---|---|
| `high` | Strong official source, precise location, and reliable metadata. |
| `medium-high` | Strong source but some missing details. |
| `medium` | Plausible report from a known source, but location or evidence is incomplete. |
| `low` | Unverified public report, social media post, approximate location, or unclear evidence. |
| `unknown` | Not enough information to classify yet. |

## Source Types

Suggested source categories:

| Source type | Meaning |
|---|---|
| `official_disclosure` | Direct government or official archive/document source. |
| `government_disclosure_news_report` | News report about government disclosure material. |
| `news` | Standard news source. |
| `reddit` | Reddit-sourced public report or discussion. |
| `x` | X/Twitter-sourced public report. |
| `public_web` | Other public internet source. |

## Daily Update Workflow

The intended daily workflow is:

1. Search public sources for new UAP sighting reports and disclosure documents.
2. Extract candidate records.
3. Normalize fields into the project schema.
4. Deduplicate against existing records.
5. Append only new unique records.
6. Improve existing records when better coordinates or better sources are found.
7. Validate `data/uap_reports.json` as valid JSON.
8. Commit the updated dataset.
9. Review candidates before setting `review_status="reviewed"` and `pin_status="pinned"`.

The dataset should accumulate over time. Daily updates should never replace the whole dataset with only the latest search results.

## Deduplication Rules

The updater deduplicates exact source identity using `canonical_source_url` (including unwrapped Bing RSS destinations and stable Reddit post paths). It preserves `raw_source_url` for provenance. New IDs use the canonical URL; existing IDs are never rewritten.

When reviewing whether different sources describe the same event, also compare:

- `source_url`
- `title`
- `event_date`
- `location_name`
- approximate latitude/longitude

Different articles about the same event may remain separate source records; do not delete a different source just because its title is similar. Known same-source duplicates are retained with `duplicate_of` and excluded from the displayed source-record count. This count is not a unique sighting count.

## Local Development

Because the map fetches a local JSON file, run a simple local server instead of opening `index.html` directly from the filesystem.

```bash
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

## JSON Validation

Before committing data changes, validate the dataset:

```bash
python3 -m json.tool data/uap_reports.json > /tmp/uap_reports_validated.json
```

If the command succeeds, the JSON syntax is valid.

## Review Notes

This project does not claim that every report is extraterrestrial, anomalous, or unexplained. It is a structured collection and visualization tool for UAP-related reports and disclosure material.

Low-confidence reports should remain clearly labeled. Natural explanations such as meteors, satellites, aircraft, drones, balloons, flares, and camera artifacts should be noted when likely.

## Roadmap

Planned improvements:

- Add automated source ingestion.
- Add stronger geocoding for city/facility-level locations.
- Extend the implemented `pending_review` / `reviewed` / `duplicate` workflow with review tooling.
- Add daily intake files under `data/daily_intake/`.
- Add separate rejected/explained event records.
- Expand the ingestion regression tests and semantic data validation.
- Add filters for source type, confidence, date range, and pin precision.

## Disclaimer

The data in this project may include official records, news reports, social media posts, historical claims, and unverified public submissions. Each item should be interpreted according to its confidence level, source type, and review notes.


## Ingestion quality safeguards

The updater always creates **pending review** candidates. A matching place name,
legal coordinate pair, source keyword, or mention of an official agency never
automatically creates a map pin or raises confidence. `confidence` starts at
`low`; this is a review state, not a judgement that every claim is false.

- `event_date`: explicitly stated local event date, `YYYY-MM-DD`, or `null`.
- `event_at`: UTC timestamp only when the source explicitly supplies a supported
  timezone (UTC / US standard or daylight abbreviation); otherwise `null`.
- `event_time_text`: the original matched time phrase, preserving unknown timezone.
- `source_published_at`: feed publication time, preferring Atom `published`;
  Atom `updated` is only a fallback. A date-only legacy value stays date-only.
  `source_published_raw` preserves the exact input.
- `ingested_at`: when this collector ran. Historical repaired records have only
  `ingested_date`, because an exact collection timestamp was not saved.
- `discovered_or_released_date`: `null` until original discovery/release is known;
  it is never filled from the collector's current date.
- `record_type`: conservative candidate classification, not an assertion of truth.
  Multi-event collections, policy news, documents and discussions need separate
  review before any event-level mapping.
- `location_evidence`: the structured `Location:` value or a dated sighting title's
  location phrase. Other article mentions are not used for geolocation. Word
  boundaries prevent `USA` inside `USAF` from matching; geographic precision
  outranks string length. Country/state/broad-region mentions never supply point
  coordinates. City/coordinate proposals stay `needs_review`.
- `raw_title` / `raw_content`: complete text delivered by the RSS feed, **not**
  necessarily the full linked article. `summary_truncated` records the display
  excerpt limit. HTML entities and Reddit attribution footers are removed from
  display excerpts. Footer-only content is explicitly `content_status="missing"`.

After reviewing an individual sighting's source, date and location, provide
specific justified coordinates, update its precision and review notes, then set
`review_status="reviewed"` and `pin_status="pinned"`. Missing content or a broad
country label alone is insufficient. Reviewed source metadata does not establish
that the observed object is extraterrestrial.

### Scoped historical repair

`python -B scripts/repair_audited_reports.py` repairs only the 73 IDs added by
`f514c27` and `a78f69b`. It is idempotent, preserves all original fields in
`audit_original`, retains every record and ID, and marks 25 same-source duplicates.
All 12 old map points in that scope are withdrawn pending review. The 2012 Visalia
sighting and other explicitly dated sighting titles/structured reports have their
event dates separated from feed timestamps. No original RSS body is reconstructed:
repaired records preserve `content_snapshot`, mark `source_content_complete=false`,
and expose possible title/summary truncation.

Records outside those two commits are not retrospectively repaired; legacy source
counts can still include unmarked duplicates, and legacy pins may be unreviewed.
The 26 records appended on 2026-10-05 remain intact. A future historical audit can
apply the same rules with explicit provenance rather than guessing missing content.

### Offline checks

```bash
python -B -m unittest discover -s tests -v
node tests/test_frontend.js
python -B -c 'import sys; sys.path.insert(0, "scripts"); from update_uap_reports import load_existing, validate_reports; validate_reports(load_existing())'
```

The daily workflow runs the regression tests before fetching feeds; the updater
validates record IDs, repaired/new dates, duplicate references, coordinates and
review gating before writing the master dataset. Existing legacy rows without
review metadata are not silently rewritten by validation.
