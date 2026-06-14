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

Any record with valid `latitude` and `longitude` values can appear as a map pin.

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
  "event_date": "YYYY-MM-DD or historical/unknown",
  "discovered_or_released_date": "YYYY-MM-DD",
  "location_name": "Readable location name",
  "latitude": 0.0,
  "longitude": 0.0,
  "location_precision": "exact | city | regional | country_centroid_unverified | unknown | non_earth_location",
  "source_type": "official_disclosure | government_disclosure_news_report | news | reddit | x | public_web",
  "source_url": "https://example.com/source",
  "summary": "Brief summary of the report and why it matters.",
  "pin_status": "pinned | needs_better_coordinates | not_pinned_missing_coordinates | not_pinned_region_too_broad | not_pinned_non_earth",
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
9. Review newly pinned locations on the map.

The dataset should accumulate over time. Daily updates should never replace the whole dataset with only the latest search results.

## Deduplication Rules

Before adding a new record, compare it against existing records using:

- `source_url`
- `title`
- `event_date`
- `location_name`
- approximate latitude/longitude

If the new item describes the same event but has better metadata, update the existing record instead of creating a duplicate.

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
- Add review status such as `pending_review`, `verified_source`, and `rejected_natural_explanation`.
- Add daily intake files under `data/daily_intake/`.
- Add separate rejected/explained event records.
- Add CI checks for JSON validity.
- Add filters for source type, confidence, date range, and pin precision.

## Disclaimer

The data in this project may include official records, news reports, social media posts, historical claims, and unverified public submissions. Each item should be interpreted according to its confidence level, source type, and review notes.
