#!/usr/bin/env python3
"""Fetch today's NHL games for use by scheduler.py.

get_todays_games() is imported by scheduler.py, which registers
APScheduler DateTrigger jobs to cancel Kalshi orders at puck drop.

Reads game start times from the DK scraper's dk_nhl_latest.json
(run scraper.py first to generate it).
"""

import json
import os
from datetime import datetime, timezone

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SCRAPER_JSON = os.path.join(
    SCRIPT_DIR, "../../Draftkings-Scraper/hockey-props-pregame/dk_nhl_latest.json"
)

_log_fh = None


def log(msg: str) -> None:
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


# ── NHL schedule from DK scraper JSON ─────────────────────────────────────────

def get_todays_games() -> list[dict]:
    """Parse game schedule from dk_nhl_latest.json.

    Returns list of {game_code, game_code2, start_utc, label} for future games.
    """
    if not os.path.exists(SCRAPER_JSON):
        log(f"[ERROR] Scraper JSON not found: {SCRAPER_JSON}")
        log("  Run scraper.py first to generate dk_nhl_latest.json")
        return []

    with open(SCRAPER_JSON, encoding="utf-8") as f:
        data = json.load(f)

    scraped_at = data.get("scraped_at", "unknown")
    log(f"[source] dk_nhl_latest.json (scraped {scraped_at})")

    now   = datetime.now(timezone.utc)
    games = []

    for g in data.get("schedule", []):
        utc_str = g.get("start_utc", "")
        if not utc_str:
            continue
        try:
            start_utc = datetime.fromisoformat(utc_str)
            if start_utc.tzinfo is None:
                start_utc = start_utc.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if start_utc <= now:
            continue

        away = g.get("away_abbrev", g.get("away_team", "???")[:3].upper())
        home = g.get("home_abbrev", g.get("home_team", "???")[:3].upper())

        games.append({
            "game_code":  away + home,
            "game_code2": home + away,
            "start_utc":  start_utc,
            "label":      f"{away} @ {home}",
        })

    return games
