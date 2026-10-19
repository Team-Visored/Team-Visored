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
        "members": [
            {"id": 10, "name": "Operator One", "role": "CTF Operator", "specialization": []},
            {"id": 20, "name": "Operator Two", "specialization": ["Web Security"], "avatar_img": "https://ctftime.org/media/user.png", "portfolio_url": "https://example.com/"},
        ],
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

    def test_members_join_leave_rename_and_profile_changes_update_automatically(self):
        payload = snapshot()
        first = profile.render(payload)
        self.assertIn("Operator One", first)
        self.assertIn('alt="MEMBERS: 2"', first)
        payload["members"] = [
            {"id": 20, "name": "Renamed Operator", "specialization": ["Forensics"], "avatar_img": "https://ctftime.org/media/new.png", "portfolio_url": "https://new.example/"},
            {"id": 30, "name": "New Operator", "specialization": []},
            {"id": 40, "name": "Another Operator", "specialization": []},
        ]
        updated = profile.render(payload)
        self.assertNotIn("Operator One", updated)
        self.assertNotIn("Operator Two", updated)
        self.assertIn("Renamed Operator", updated)
        self.assertIn("New Operator", updated)
        self.assertIn("Forensics", updated)
        self.assertIn("https://ctftime.org/media/new.png", updated)
        self.assertIn("https://new.example/", updated)
        self.assertIn('alt="MEMBERS: 3"', updated)

    def test_duplicate_members_use_fresh_profile_and_sort_stably(self):
        payload = snapshot()
        payload["members"] += [
            {"id": 20, "name": "Old stale name", "_stale": True},
            {"id": 30, "name": "Previously stale", "_stale": True},
            {"id": 30, "name": "Fresh profile", "_stale": False},
        ]
        members = profile.team_members(payload)
        self.assertEqual([member["id"] for member in members], [30, 10, 20])
        self.assertNotIn("Old stale name", profile.render(payload))
        self.assertIn('alt="MEMBERS: 3"', profile.render(payload))

    def test_invalid_or_missing_roster_preserves_saved_readme(self):
        for members in (None, "unavailable", [{"id": 20}], [{"id": "invalid", "name": "Name"}]):
            with self.subTest(members=members), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "README.md"
                original = f"{profile.START}\nSaved members\n{profile.END}"
                path.write_text(original)
                payload = snapshot()
                payload["members"] = members
                with self.assertRaises(ValueError):
                    profile.update_readme(path, payload)
                self.assertEqual(path.read_text(), original)

    def test_empty_roster_and_missing_member_fields_have_honest_fallbacks(self):
        payload = snapshot()
        output = profile.render(payload)
        self.assertIn("assets/team-logo.png", output)
        self.assertIn("https://ctftime.org/user/10/", output)
        payload["members"] = []
        output = profile.render(payload)
        self.assertIn('alt="MEMBERS: 0"', output)
        self.assertIn("No public members", output)

    def test_member_content_and_links_cannot_inject_markup(self):
        payload = snapshot()
        payload["members"] = [{
            "id": 30, "name": '<img src=x onerror="alert(1)">',
            "specialization": ["<script>bad</script>", "Web | Crypto"],
            "avatar_img": 'javascript:alert(1)', "portfolio_url": 'javascript:alert(1)',
            "url": "https://evil.example/", "_stale": True,
        }]
        output = profile.render(payload)
        self.assertNotIn("<script>", output)
        self.assertNotIn("javascript:", output)
        self.assertNotIn("https://evil.example/", output)
        self.assertIn("https://ctftime.org/user/30/", output)
        self.assertIn("Profile refresh pending", output)
        self.assertIn("&#124;", output)
        self.assertEqual(profile.public_url("assets/portrait.jpg", image=True), "https://team-visored.vercel.app/assets/portrait.jpg")
        self.assertIsNone(profile.public_url("https://user:password@example.com/"))

    def test_all_displayed_stats_follow_the_snapshot(self):
        payload = snapshot()
        payload.update(season=2027, upcoming=[{"event_id": 901}, {"event_id": 902}])
        payload["ranking"] = {"country_place": 2, "world_place": 100, "rating_points": 250.5}
        payload["results"] = [{"event_id": 99, "title": "New season", "place": 1, "points": 1000, "rating_points": 12.25}]
        output = profile.render(payload)
        for label in ["NEPAL: #2", "WORLDWIDE: #100", "SEASON: 2027", "BEST FINISH: #1", "CTF FINISHES: 1", "RATING: 250.500", "PLANNED EVENTS: 2", "MEMBERS: 2"]:
            self.assertIn(f'alt="{label}"', output)
        self.assertIn("1,000.00 | 12.250", output)


if __name__ == "__main__":
    unittest.main()
