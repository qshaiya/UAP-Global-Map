import copy
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
u = importlib.import_module("update_uap_reports")
repair = importlib.import_module("repair_audited_reports")


def item(title="UFO report", summary="", published="2026-10-04T02:00:00Z", url="https://example.com/report"):
    return u.FeedItem(title, url, published, summary, "test", "reddit", "medium")


class IngestionTests(unittest.TestCase):
    def test_reddit_footer_is_not_content(self):
        self.assertEqual(u.clean_text("&#32; submitted by &#32; /u/name [link] [comments]"), "")
        self.assertEqual(u.clean_text("<p>A &quot;triangle&quot;</p> submitted by /u/name [link]"), 'A "triangle"')
        report = u.build_report(item(summary="&#32; submitted by &#32; /u/name [link] [comments]"))
        self.assertEqual(report["content_status"], "missing")
        self.assertEqual(report["summary"], "")

    def test_full_feed_content_survives_summary_truncation(self):
        text = "UFO " + "a" * 1000
        report = u.build_report(item(title="x" * 230, summary=text))
        self.assertEqual(report["raw_content"], text)
        self.assertEqual(len(report["title"]), 230)
        self.assertTrue(report["summary_truncated"])
        self.assertEqual(len(report["summary"]), 900)

    def test_keyword_does_not_raise_confidence(self):
        report = u.build_report(item("Pentagon official military disclosure"))
        self.assertEqual(report["confidence"], "low")
        self.assertEqual(report["review_status"], "pending_review")

    def test_usaf_not_country(self):
        candidate = item("Triangle over USAF — Oct 2, 2026, 8:11 PM")
        self.assertEqual(u.find_location(candidate)[3], "unknown")
        self.assertIsNone(u.find_location(candidate)[0])

    def test_specific_location_outranks_country(self):
        candidate = item(summary="Time: December 31, 2012, 11:57 PM PST Location: Visalia, California, United States Detail Reported Objects 5")
        lat, lon, name, precision, status = u.find_location(candidate)
        self.assertIn("Visalia", name)
        self.assertEqual(precision, "state_centroid")
        self.assertEqual(status, "not_pinned_region_too_broad")
        self.assertIsNone(lat)
        self.assertIsNone(lon)

    def test_document_country_not_sighting(self):
        for title, summary in [("Australia AARO workshop", "Australian Government"),
                               ("STS-80 footage", "Recorder lived in Canada"),
                               ("Aliens think differently", "USA and China"),
                               ("Larry King: live from Area 51 (1994)", "")]:
            with self.subTest(title=title):
                self.assertEqual(u.find_location(item(title, summary))[2], "Unknown")

    def test_city_proposal_needs_review(self):
        report = u.build_report(item("Triangle over Jersey City — Oct 2, 2026, 8:11 PM"))
        self.assertEqual(report["location_precision"], "city_centroid")
        self.assertEqual(report["pin_status"], "needs_review")
        self.assertNotEqual(report["pin_status"], "pinned")

    def test_coordinates_only_in_sighting_location_context(self):
        report = u.build_report(item(summary="Time: Oct 2, 2026, 8:11 PM Location: 35.1234, -106.1234 Detail Reported Objects 1"))
        self.assertEqual(report["latitude"], 35.1234)
        self.assertEqual(report["pin_status"], "needs_review")
        for text in ["Article about 35.1234, -106.1234", "Time: Oct 2, 2026 Location: 99.1234, -106.1234", "Time: Oct 2, 2026 Location: 135.1234, -106.1234"]:
            self.assertIsNone(u.build_report(item(summary=text))["latitude"])

    def test_historical_sighting_date_not_post_date(self):
        report = u.build_report(item("Orange-red lights over Visalia, CA — Dec 31, 2012, 11:57 PM",
                                    "Time: December 31, 2012, 11:57 PM PST Location: Visalia, California, United States Detail"))
        self.assertEqual(report["event_date"], "2012-12-31")
        self.assertEqual(report["event_at"], "2013-01-01T07:57:00+00:00")
        self.assertEqual(report["source_published_at"], "2026-10-04T02:00:00+00:00")
        self.assertIsNone(report["discovered_or_released_date"])

    def test_cdt_sighting_time(self):
        report = u.build_report(item(summary="Time: October 2, 2026, 8:11 PM CDT Location: Springfield, Missouri, United States Detail"))
        self.assertEqual(report["event_date"], "2026-10-02")
        self.assertEqual(report["event_at"], "2026-10-03T01:11:00+00:00")

    def test_unknown_timezone_not_invented(self):
        report = u.build_report(item("Triangle over Parrish, FL — Oct 2, 2026, 9:26 PM"))
        self.assertEqual(report["event_date"], "2026-10-02")
        self.assertIsNone(report["event_at"])

    def test_publication_parsing_and_invalid_dates(self):
        self.assertEqual(u.normalize_date("2026-10-04T02:00:00Z"), "2026-10-04")
        self.assertEqual(u.publication_time("Fri, 02 Oct 2026 08:11:00 -0500"), "2026-10-02T13:11:00+00:00")
        self.assertEqual(u.publication_time("2026-10-04"), "2026-10-04")
        for value in [None, "invalid", "2026-13-55"]:
            self.assertIsNone(u.publication_time(value))
        self.assertIsNone(u.build_report(item("UFO published today"))["event_date"])
        self.assertIsNone(u.build_report(item("Triangle over London — Feb 31, 2026, 2:00 AM"))["event_date"])

    def test_canonical_url_unwraps_bing_and_preserves_identifiers(self):
        first = "http://www.bing.com/news/apiclick.aspx?tid=old&url=https%3A%2F%2Fexample.com%2Farticle%3Fid%3D12%26utm_source%3Dbing"
        second = "http://www.bing.com/news/apiclick.aspx?tid=new&url=https%3A%2F%2Fexample.com%2Farticle%3Fid%3D12"
        self.assertEqual(u.canonical_source_url(first), "https://example.com/article?id=12")
        self.assertEqual(u.canonical_source_url(first), u.canonical_source_url(second))
        existing = [{"id": "old-id", "source_url": first}]
        self.assertEqual(u.dedupe(existing, [u.build_report(item(url=second))]), [])
        self.assertEqual(len(u.dedupe([], [u.build_report(item(url=first)), u.build_report(item(url=second))])), 1)

    def test_reddit_post_identity(self):
        self.assertEqual(u.canonical_source_url("https://old.reddit.com/r/UFOs/comments/abc123/old_slug/?utm_source=share"),
                         u.canonical_source_url("https://www.reddit.com/r/UFOs/comments/abc123/new_slug/"))

    def test_atom_uses_alternate_link_and_publication_time(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>UFO triangle</title><link rel="self" href="https://feed.example/self"/><link rel="alternate" href="https://example.com/post"/><published>2026-10-02T01:00:00Z</published><updated>2026-10-04T01:00:00Z</updated><content>&lt;p&gt;A triangle&lt;/p&gt; submitted by /u/name [link]</content></entry></feed>'
        feed = {"name": "test", "url": "https://feed.example", "source_type": "reddit", "confidence": "low"}
        with patch.object(u, "fetch_url", return_value=xml):
            parsed = u.parse_feed(feed)
        self.assertEqual(parsed[0].url, "https://example.com/post")
        self.assertEqual(parsed[0].published, "2026-10-02T01:00:00Z")
        self.assertEqual(parsed[0].summary, "A triangle")
        self.assertIn("submitted by", parsed[0].raw_content)

    def test_validation_rejects_pending_pin(self):
        report = u.build_report(item())
        report.update(pin_status="pinned", latitude=35.0, longitude=-106.0)
        with self.assertRaises(ValueError):
            u.validate_reports([report])
        report["review_status"] = "reviewed"
        u.validate_reports([report])


class RepairTests(unittest.TestCase):
    def test_actual_repair_preserves_all_other_rows_and_is_idempotent(self):
        repaired = json.loads((ROOT / "data/uap_reports.json").read_text())
        original = [copy.deepcopy(r.get("audit_original", r)) for r in repaired]
        self.assertEqual(repair.repair_reports(original), 73)
        u.validate_reports(original)
        count = 0
        for before, after in zip(repaired, original):
            if after["id"] not in repair.AUDITED_IDS:
                self.assertEqual(before, after)
            else:
                count += 1
                self.assertEqual(after["audit_original"], before["audit_original"])
                self.assertNotEqual(after["pin_status"], "pinned")
                self.assertEqual(after["event_date"], before["event_date"])
                self.assertEqual(after.get("duplicate_of"), before.get("duplicate_of"))
        self.assertEqual(count, 73)
        self.assertEqual(sum(bool(r.get("duplicate_of")) for r in original if r["id"] in repair.AUDITED_IDS), 25)
        snapshot = copy.deepcopy(original)
        self.assertEqual(repair.repair_reports(original), 0)
        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main()
