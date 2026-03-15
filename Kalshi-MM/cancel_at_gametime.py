#!/usr/bin/env python3
"""Fetch today's NBA games for use by scheduler.py.

get_todays_games() is imported by scheduler.py, which registers
APScheduler DateTrigger jobs to cancel Kalshi orders at tip-off.
"""

import json
import urllib.request
from datetime import datetime, timezone

_log_fh = None


def log(msg: str) -> None:
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


# ── NBA schedule ───────────────────────────────────────────────────────────────

def _parse_games(raw_games: list[dict], time_key: str) -> list[dict]:
    result = []
    for g in raw_games:
        away    = g.get("awayTeam", {}).get("teamTricode", "")
        home    = g.get("homeTeam", {}).get("teamTricode", "")
        utc_str = g.get(time_key, "")
        if not (away and home and utc_str):
            continue
        try:
            start_utc = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        result.append({
            "game_code":  away + home,
            "game_code2": home + away,
            "start_utc":  start_utc,
            "label":      f"{away} @ {home}",
        })
    return result


def _fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"[ERROR] Could not fetch {url}: {e}")
        return None


def get_todays_games() -> list[dict]:
    """Return list of {game_code, game_code2, start_utc, label} for today's future games.

    Tries the live scoreboard first.  If it still shows yesterday's games
    (all in the past — common before ~11 AM ET), falls back to the full
    season schedule filtered by today's local date.
    """
    now = datetime.now(timezone.utc)

    # --- Primary: live scoreboard ---
    data = _fetch_json("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json")
    if data:
        games  = _parse_games(data.get("scoreboard", {}).get("games", []), "gameTimeUTC")
        future = [g for g in games if g["start_utc"] > now]
        if future:
            log(f"[source] live scoreboard ({len(future)} future game(s))")
            return future
        log("[source] scoreboard has no future games — falling back to season schedule")

    # --- Fallback: full season schedule ---
    data = _fetch_json("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
    if not data:
        return []

    today_str = datetime.now().strftime("%m/%d/%Y")
    raw = next(
        (gd.get("games", [])
         for gd in data.get("leagueSchedule", {}).get("gameDates", [])
         if gd.get("gameDate", "").startswith(today_str)),
        []
    )
    games  = _parse_games(raw, "gameDateTimeUTC")
    future = [g for g in games if g["start_utc"] > now]
    log(f"[source] season schedule ({len(future)} future game(s) on {today_str})")
    return future
