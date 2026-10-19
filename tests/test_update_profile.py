from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import update_profile as profile


def snapshot():
    return {
        "team": {"id": 447690}, "season": 2026,
        "synced_at": "2026-10-19T12:00:00+00:00",
        "ranking": {"country_place": 4, "world_place": 356, "rating_points": 191.6797128},
        "summary": {}, "upcoming": [],
        "results": [
            {"event_id": i, "title": f"CTF {i}", "place": place, "points": str(100 * i), "rating_points": 2.5}
            for i, place in enumerate([52, 18, 4, 21, 38, 63], 1)
        ],
    }


class ProfileUpdaterTests(unittest.TestCase):
    def test_selects_five_best_finishes_deduplicates_and_breaks_ties_by_score(self):
        payload = snapshot()
        payload["results"] += [
            {"event_id": 3, "title": "Duplicate", "place": 70, "points": "1"},
            {"event_id": 7, "title": "Tie", "place": 18, "points": "900"},
            {"event_id": 8, "place": 0}, {"event_id": 9, "place": "NaN"},
        ]
        rows = profile.top_results(payload)
        self.assertEqual([row["event_id"] for row in rows], [3, 7, 2, 4, 5])

    def test_changes_refresh_the_table_and_stats_without_touching_other_content(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "README.md"
            path.write_text(f"Branding\n{profile.START}\nOld data\n{profile.END}\nManaged by Spydomain\n")
            payload = snapshot()
            self.assertTrue(profile.update_readme(path, payload))
            self.assertIn("CTF 3](https://ctftime.org/event/3/)", path.read_text())
            payload["results"].append({"event_id": 99, "title": "New best", "place": 1, "points": 3000})
            payload["ranking"]["world_place"] = 300
            profile.update_readme(path, payload)
            content = path.read_text()
            self.assertTrue(content.startswith("Branding\n"))
            self.assertTrue(content.endswith("Managed by Spydomain\n"))
            self.assertIn("**01** | [New best]", content)
            self.assertIn('alt="WORLDWIDE: #300"', content)

    def test_timestamp_only_changes_do_not_rewrite_identical_daily_stats(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "README.md"
            path.write_text(f"{profile.START}\n{profile.END}")
            payload = snapshot()
            profile.update_readme(path, payload)
            payload["synced_at"] = "2026-10-19T12:15:00+00:00"
            self.assertFalse(profile.update_readme(path, payload))

    def test_escapes_external_titles_and_uses_official_event_urls(self):
        payload = snapshot()
        payload["results"][2]["title"] = "<script>alert(1)</script> | [bad](evil)\n**bold**"
        payload["results"][2]["url"] = "javascript:alert(1)"
        output = profile.render(payload)
        self.assertNotIn("<script>", output)
        self.assertNotIn("javascript:", output)
        self.assertIn("&#124;", output)
        self.assertIn("https://ctftime.org/event/3/", output)

    def test_new_season_without_results_is_not_filled_with_old_records(self):
        payload = snapshot()
        payload.update(season=2027, results=[], ranking={})
        output = profile.render(payload)
        self.assertIn("No ranked finishes", output)
        self.assertIn('alt="WORLDWIDE: Unranked"', output)
        self.assertNotIn("CTF 3", output)

    def test_invalid_snapshot_preserves_the_readme(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "README.md"
            content = f"Keep this\n{profile.START}\nValid saved records\n{profile.END}"
            path.write_text(content)
            payload = snapshot()
            payload["team"]["id"] = 1
            with self.assertRaises(ValueError):
                profile.update_readme(path, payload)
            self.assertEqual(path.read_text(), content)

    def test_feed_outage_keeps_saved_content_and_fallback_is_attempted(self):
        with patch.object(profile, "urlopen", side_effect=OSError("offline")) as request:
            with self.assertRaises(RuntimeError):
                profile.fetch_snapshot()
            self.assertEqual(request.call_count, 2)

    def test_saved_snapshot_is_used_if_live_endpoint_is_unavailable(self):
        payload = snapshot()
        import io
        import json
        response = io.StringIO(json.dumps(payload))
        with patch.object(profile, "urlopen", side_effect=[OSError("offline"), response]):
            self.assertEqual(profile.fetch_snapshot()["team"]["id"], 447690)


if __name__ == "__main__":
    unittest.main()
