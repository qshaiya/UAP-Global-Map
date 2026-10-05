#!/usr/bin/env python3
"""Idempotent, non-destructive repair of the 73 records audited on 2026-10-05.

Only these IDs may change. Original fields are retained in audit_original.
No RSS requests or inferred full-content reconstruction are performed.
"""
from __future__ import annotations

import json
from pathlib import Path

from update_uap_reports import FeedItem, build_report, canonical_source_url

AUDITED_IDS = set([
    "auto-51eb4ca185c2",
    "auto-8386a9180573",
    "auto-d6b00de4136c",
    "auto-2287fa6b0c06",
    "auto-736d04df91ff",
    "auto-5a40babc38e9",
    "auto-195c90734349",
    "auto-09c012909c85",
    "auto-e3db0954e672",
    "auto-4a19462c944f",
    "auto-f1c03d374366",
    "auto-2b999aae8f45",
    "auto-8a7fe82cc3d5",
    "auto-f887892b7abd",
    "auto-c57a47eeb6a6",
    "auto-c51d46e1a333",
    "auto-30296b621e9e",
    "auto-8d34ddf0d1c0",
    "auto-0ebddf85f161",
    "auto-714f97998222",
    "auto-dd7b5e4b4eb2",
    "auto-c89933fca978",
    "auto-de471bb61112",
    "auto-b05e008255a4",
    "auto-ce142996f65e",
    "auto-989372ba75c9",
    "auto-505560499500",
    "auto-0aaa2984a12c",
    "auto-39239a906865",
    "auto-2b514124514c",
    "auto-2450f4eb2dd5",
    "auto-1fee33900a28",
    "auto-a8ae419c3259",
    "auto-99f25fc894fd",
    "auto-c428d66c4695",
    "auto-1f76d178abbc",
    "auto-e43fd1213dc1",
    "auto-60ff71c74ef3",
    "auto-8322345edf4b",
    "auto-1c89b540654d",
    "auto-a8e81c784ae5",
    "auto-9d64d01c6347",
    "auto-a3ff5d4b8db6",
    "auto-f7d2ec2a3d9c",
    "auto-acb83de679a5",
    "auto-0e02e8668fe5",
    "auto-48e52a2815e3",
    "auto-5a35bf2c4c12",
    "auto-066cb970bb9f",
    "auto-dc9adc0a72bf",
    "auto-9762b3d84cae",
    "auto-74e1b9af2e85",
    "auto-d2e93f215963",
    "auto-0abff05257c3",
    "auto-c5a12ded2a21",
    "auto-6135fb8324be",
    "auto-d1ca0f4b4e46",
    "auto-1d83cbd471ec",
    "auto-18dda8518ba1",
    "auto-aae8a0d31671",
    "auto-ef7b33416b11",
    "auto-9c00f540b47a",
    "auto-48fd4175567d",
    "auto-75752b1604a3",
    "auto-ce1f1c87c18f",
    "auto-15b5a181f3a6",
    "auto-17a5cf5c5442",
    "auto-0b42b0e1bf8a",
    "auto-ce3331920cb4",
    "auto-eaf1a6256fe3",
    "auto-028eec107914",
    "auto-cb1ffe0dcd12",
    "auto-ae9cea514f02"
])
REPAIR_VERSION = "2026-10-05-v1"
NON_EVENT_TYPES = {
    "auto-736d04df91ff": "media_archive",
    "auto-c51d46e1a333": "document_analysis",
    "auto-c428d66c4695": "policy_news",
    "auto-d2e93f215963": "media_archive",
    "auto-60ff71c74ef3": "multi_event",
    "auto-066cb970bb9f": "multi_event",
    "auto-2b999aae8f45": "discussion",
    "auto-a3ff5d4b8db6": "discussion",
    "auto-f887892b7abd": "policy_news",
    "auto-9762b3d84cae": "discussion",
}


def repair_reports(reports: list[dict]) -> int:
    seen: dict[str, str] = {}
    changed = 0
    for report in reports:
        canonical = canonical_source_url(report.get("source_url", ""))
        if report["id"] in AUDITED_IDS and report.get("audit_repair_version") != REPAIR_VERSION:
            original = dict(report)
            item = FeedItem(original["title"], original["source_url"], original["event_date"],
                            original["summary"], "Historical RSS snapshot", original["source_type"], original["confidence"])
            replacement = build_report(item)
            # Preserve IDs, original URL and every original field for traceability.
            replacement["id"] = original["id"]
            replacement["source_url"] = original["source_url"]
            replacement["audit_original"] = original
            replacement["audit_repair_version"] = REPAIR_VERSION
            # Exact ingestion timestamp/full RSS content were not recorded historically.
            replacement["ingested_at"] = None
            replacement["ingested_date"] = original.get("discovered_or_released_date")
            replacement["raw_content"] = None
            replacement["raw_title"] = None
            replacement["content_snapshot"] = original["summary"]
            replacement["source_content_complete"] = False
            replacement["summary_truncated"] = len(original["summary"]) == 900
            replacement["title_may_be_truncated"] = len(original["title"]) == 220
            replacement["source_published_basis"] = "Legacy feed timestamp previously stored in event_date; published vs updated unknown."
            if original["id"] in NON_EVENT_TYPES:
                replacement["record_type"] = NON_EVENT_TYPES[original["id"]]
            if original["pin_status"] == "pinned":
                replacement["latitude"] = replacement["longitude"] = None
                replacement["pin_status"] = "needs_review"
                if original["id"] in NON_EVENT_TYPES:
                    replacement["location_name"] = "Unknown"
                    replacement["location_precision"] = "non_earth_location" if original["id"] == "auto-736d04df91ff" else "unknown"
                    replacement["pin_status"] = "not_pinned_non_earth" if original["id"] == "auto-736d04df91ff" else "not_pinned_not_single_sighting"
                else:
                    replacement["pin_status"] = "needs_better_coordinates"
            if canonical in seen:
                replacement["duplicate_of"] = seen[canonical]
                replacement["review_status"] = "duplicate"
                replacement["pin_status"] = "not_pinned_duplicate"
                replacement["latitude"] = replacement["longitude"] = None
            replacement["notes"] = "Audited RSS candidate: pending source/event/location review. Original values retained in audit_original; no missing source content reconstructed."
            report.clear()
            report.update(replacement)
            changed += 1
        if canonical:
            seen.setdefault(canonical, report["id"])
    return changed


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "uap_reports.json"
    reports = json.loads(path.read_text(encoding="utf-8"))
    changed = repair_reports(reports)
    if changed:
        path.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Repaired {changed} audited records; no records deleted.")


if __name__ == "__main__":
    main()
