#!/usr/bin/env python3
"""Refresh only the CTFtime section of the Team Visored profile README."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape, unescape
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
START = "<!-- CTFTIME:START -->"
END = "<!-- CTFTIME:END -->"
SOURCES = (
    "https://team-visored.vercel.app/api/ctftime",
    "https://team-visored.vercel.app/data/ctftime.json",
)
TEAM_URL = "https://ctftime.org/team/447690"
ARCHIVE_URL = "https://team-visored.vercel.app/achievements.html"


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def positive_int(value):
    result = number(value)
    return int(result) if result is not None and result > 0 and result == result.to_integral_value() else None


def rank(value):
    result = positive_int(value)
    return f"#{result:,}" if result is not None else "Unranked"


def formatted(value, places=0):
    result = number(value)
    return f"{result:,.{places}f}" if result is not None else "—"


def text(value):
    value = " ".join(unescape(str(value)).split())
    return escape(value, quote=True).replace("|", "&#124;").replace("[", "&#91;").replace("]", "&#93;").replace("*", "&#42;").replace("_", "&#95;").replace("`", "&#96;").replace("\\", "&#92;")


def validate(payload):
    if not isinstance(payload, dict) or payload.get("_error"):
        raise ValueError("The source did not return a valid CTFtime snapshot")
    if not isinstance(payload.get("team"), dict) or positive_int(payload["team"].get("id")) != 447690:
        raise ValueError("The snapshot belongs to a different team")
    if not positive_int(payload.get("season")) or not isinstance(payload.get("ranking"), dict):
        raise ValueError("Season or ranking data is missing")
    for key in ("results", "upcoming"):
        if not isinstance(payload.get(key), list) or not all(isinstance(row, dict) for row in payload[key]):
            raise ValueError(f"Invalid {key} data")
    if not isinstance(payload.get("summary"), dict):
        raise ValueError("Summary data is missing")
    datetime.fromisoformat(payload["synced_at"].replace("Z", "+00:00"))
    return payload


def fetch_snapshot():
    for source in SOURCES:
        try:
            request = Request(source, headers={
                "User-Agent": "Team-Visored-profile-updater/1.0",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            })
            with urlopen(request, timeout=60) as response:
                payload = validate(json.load(response))
            print(f"Using CTFtime snapshot from {source}")
            return payload
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            print(f"Could not refresh from {source}: {error}", file=sys.stderr)
    raise RuntimeError("All CTFtime sources failed; the existing README has been kept")


def top_results(payload):
    """Keep the best entry per event, then rank by place and score."""
    ordered = sorted(
        (row for row in payload["results"] if positive_int(row.get("place")) and positive_int(row.get("event_id"))),
        key=lambda row: (positive_int(row["place"]), -(number(row.get("points")) or Decimal(0)), positive_int(row["event_id"])),
    )
    unique = {}
    for row in ordered:
        unique.setdefault(positive_int(row["event_id"]), row)
    return list(unique.values())[:5]


def badge(label, value, color, destination):
    query = urlencode({
        "label": label, "message": str(value), "color": color,
        "labelColor": "0D1117", "style": "for-the-badge",
    })
    image = escape("https://img.shields.io/static/v1?" + query, quote=True)
    alt = escape(f"{label}: {value}", quote=True)
    return f'  <a href="{destination}"><img src="{image}" alt="{alt}" /></a>'


def render(payload):
    validate(payload)
    ranking = payload["ranking"]
    results = top_results(payload)
    best = results[0]["place"] if results else None
    badges = [
        badge("NEPAL", rank(ranking.get("country_place")), "A8C8FF", TEAM_URL),
        badge("WORLDWIDE", rank(ranking.get("world_place")), "818CF8", TEAM_URL),
        badge("SEASON", payload["season"], "38BDF8", ARCHIVE_URL),
        badge("BEST FINISH", rank(best), "C4B5FD", ARCHIVE_URL),
        badge("CTF FINISHES", len({row.get("event_id") for row in payload["results"]}), "67E8F9", ARCHIVE_URL),
        badge("RATING", formatted(ranking.get("rating_points"), 3), "A8C8FF", TEAM_URL),
        badge("PLANNED EVENTS", len({row.get("event_id") for row in payload["upcoming"]}), "818CF8", "https://team-visored.vercel.app/upcoming.html"),
    ]
    lines = ["<p align=\"center\">", *badges[:3], "</p>", "", "<p align=\"center\">", *badges[3:], "</p>", "", "### Five strongest finishes", ""]
    if results:
        lines += ["| Record | Event | Global finish | CTF score | Rating points |", "|:------:|:------|:-------------:|----------:|--------------:|"]
        for index, row in enumerate(results, 1):
            event_url = f"https://ctftime.org/event/{positive_int(row['event_id'])}/"
            title = text(row.get("title") or "CTF event")
            lines.append(f"| **{index:02}** | [{title}]({event_url}) | **{rank(row['place'])}** | {formatted(row.get('points'), 2)} | {formatted(row.get('rating_points'), 3)} |")
    else:
        lines.append("No ranked finishes have been published for this season yet.")
    stamp = datetime.fromisoformat(payload["synced_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    source_date = stamp.astimezone(timezone.utc).strftime("%d %b %Y")
    lines += ["", "<p align=\"center\">", f"  <sub>Source snapshot: {source_date} (UTC). Rankings and results synchronize from CTFtime; checks are scheduled every 15 minutes.</sub>", "</p>"]
    if payload.get("_sync", {}).get("status") == "partial":
        lines += ["", "<p align=\"center\"><sub>Some source data is temporarily unavailable; the feed retains its last available records.</sub></p>"]
    return "\n".join(lines)


def update_readme(path, payload):
    original = path.read_text(encoding="utf-8")
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("README must contain exactly one CTFtime start marker and end marker")
    before, rest = original.split(START, 1)
    _, after = rest.split(END, 1)
    updated = f"{before}{START}\n\n{render(payload)}\n\n{END}{after}"
    if updated == original:
        print("No public stats changed; README is already up to date")
        return False
    path.write_text(updated, encoding="utf-8")
    print(f"Updated {path} with the five strongest CTFtime finishes")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    parser.add_argument("--snapshot", type=Path, help="Read a saved JSON snapshot instead of the live feed")
    args = parser.parse_args()
    try:
        payload = validate(json.loads(args.snapshot.read_text(encoding="utf-8"))) if args.snapshot else fetch_snapshot()
        update_readme(args.readme, payload)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as error:
        print(f"Refresh stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
