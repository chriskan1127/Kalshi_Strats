"""
Find today's NBA game start times using the NBA schedule API.
"""

import urllib.request
import json
from datetime import datetime, timezone


def _fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        print(f"Error fetching {url}: {e}")
        return None


def _format_utc(utc_str: str) -> str:
    try:
        utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return utc_dt.astimezone().strftime("%I:%M %p %Z")
    except ValueError:
        return utc_str


def _team_name(team: dict) -> str:
    return f"{team.get('teamCity', '')} {team.get('teamName', '')}".strip()


def _print_games(games: list, time_key: str, show_location: bool = False):
    print(f"Found {len(games)} game(s):\n")
    for i, game in enumerate(games, 1):
        away = _team_name(game.get("awayTeam", {}))
        home = _team_name(game.get("homeTeam", {}))
        time_str = _format_utc(game.get(time_key, "")) if game.get(time_key) else "TBD"
        print(f"  Game {i}:")
        print(f"    {away} @ {home}")
        print(f"    Time:   {time_str}")
        print(f"    Status: {game.get('gameStatusText', '')}")
        if show_location:
            arena, city, state = game.get("arenaName", ""), game.get("arenaCity", ""), game.get("arenaState", "")
            print(f"    Location: {', '.join(filter(None, [arena, city, state]))}")
        print()


def get_todays_nba_games():
    """Fetch and display today's NBA game start times."""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print(f"NBA Games for {today.strftime('%A, %B %d, %Y')}")
    print("=" * 55)

    # Primary: scoreboard endpoint (today-only, fast)
    data = _fetch_json("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json")
    if data:
        games = data.get("scoreboard", {}).get("games", [])
        if games:
            return _print_games(games, "gameTimeUTC")
        print("No games found for today.")
        return

    # Fallback: full season schedule (slower, has arena details)
    print("Falling back to the schedule API...")
    data = _fetch_json("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
    if not data:
        print("Could not reach the NBA API. Check your internet connection.")
        return

    games = next(
        (gd.get("games", []) for gd in data.get("leagueSchedule", {}).get("gameDates", [])
         if gd.get("gameDate", "").split(" ")[0] and
         datetime.strptime(gd["gameDate"].split(" ")[0], "%m/%d/%Y").strftime("%Y-%m-%d") == date_str),
        []
    )
    if games:
        _print_games(games, "gameDateTimeUTC", show_location=True)
    else:
        print("No games found for today.")


if __name__ == "__main__":
    get_todays_nba_games()