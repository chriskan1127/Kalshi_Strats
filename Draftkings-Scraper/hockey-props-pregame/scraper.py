"""DraftKings NHL Player Props Scraper

Fetches schedule + player props (goals, points, assists).
Saves raw DK API responses so build_csv.js can parse selections/events/markets.
Also embeds game schedule (with team abbreviations) for cancel_at_gametime_nhl.py.
"""

import requests
import random
import time
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BASE_URL = (
    "https://sportsbook-nash.draftkings.com/sites/US-PA-SB"
    "/api/sportscontent/controldata/league/leagueSubcategory/v1/markets"
)

NHL_LEAGUE_ID = "42133"
GAME_LINES_SUBCATEGORY = "4525"  # returns schedule + event data

PROP_SUBCATEGORIES = {
    "goals":   "14496",
    "points":  "16545",
    "assists": "16546",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

EASTERN = ZoneInfo("America/New_York")

# Full NHL team name → 3-letter abbreviation
NHL_ABBREV = {
    "Anaheim Ducks":         "ANA",
    "Boston Bruins":         "BOS",
    "Buffalo Sabres":        "BUF",
    "Calgary Flames":        "CGY",
    "Carolina Hurricanes":   "CAR",
    "Chicago Blackhawks":    "CHI",
    "Colorado Avalanche":    "COL",
    "Columbus Blue Jackets": "CBJ",
    "Dallas Stars":          "DAL",
    "Detroit Red Wings":     "DET",
    "Edmonton Oilers":       "EDM",
    "Florida Panthers":      "FLA",
    "Los Angeles Kings":     "LAK",
    "Minnesota Wild":        "MIN",
    "Montreal Canadiens":    "MTL",
    "Nashville Predators":   "NSH",
    "New Jersey Devils":     "NJD",
    "New York Islanders":    "NYI",
    "New York Rangers":      "NYR",
    "Ottawa Senators":       "OTT",
    "Philadelphia Flyers":   "PHI",
    "Pittsburgh Penguins":   "PIT",
    "San Jose Sharks":       "SJS",
    "Seattle Kraken":        "SEA",
    "St. Louis Blues":       "STL",
    "Tampa Bay Lightning":   "TBL",
    "Toronto Maple Leafs":   "TOR",
    "Utah Hockey Club":      "UTA",
    "Vancouver Canucks":     "VAN",
    "Vegas Golden Knights":  "VGK",
    "Washington Capitals":   "WSH",
    "Winnipeg Jets":         "WPG",
}


def team_abbrev(name: str) -> str:
    """Return 3-letter abbreviation for a team name, or first 3 chars as fallback."""
    if name in NHL_ABBREV:
        return NHL_ABBREV[name]
    # Already an abbreviation (≤4 chars)
    if len(name) <= 4:
        return name.upper()
    # Last-resort: first 3 letters uppercased
    return name[:3].upper()


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://sportsbook.draftkings.com/",
        "Origin": "https://sportsbook.draftkings.com",
    }


def polite_delay():
    time.sleep(random.uniform(2, 4))


def fetch_league_data(subcategory_id):
    """Fetch raw DK API response for a subcategory."""
    params = {
        "isBatchable": "false",
        "templateVars": f"{NHL_LEAGUE_ID},{subcategory_id}",
        "eventsQuery": (
            f"$filter=leagueId eq '{NHL_LEAGUE_ID}' AND "
            f"clientMetadata/Subcategories/any(s: s/Id eq '{subcategory_id}')"
        ),
        "marketsQuery": (
            f"$filter=clientMetadata/subCategoryId eq '{subcategory_id}' "
            "AND tags/all(t: t ne 'SportcastBetBuilder')"
        ),
        "include": "Events",
        "entity": "events",
    }
    resp = requests.get(BASE_URL, params=params, headers=get_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_schedule(data):
    """Extract game schedule with team abbreviations from event data."""
    events = data.get("events", [])
    games = []
    for event in events:
        start_utc = datetime.fromisoformat(
            event["startEventDate"].replace("Z", "+00:00")
        )
        start_et = start_utc.astimezone(EASTERN)

        participants = event.get("participants", [])
        away_p = next((p for p in participants if p.get("venueRole") == "Away"), {})
        home_p = next((p for p in participants if p.get("venueRole") == "Home"), {})

        away_name = away_p.get("name", "Unknown")
        home_name = home_p.get("name", "Unknown")

        games.append({
            "event_id":    event["id"],
            "name":        event.get("name", f"{away_name} @ {home_name}"),
            "away_team":   away_name,
            "home_team":   home_name,
            "away_abbrev": team_abbrev(away_name),
            "home_abbrev": team_abbrev(home_name),
            "start_utc":   start_utc.isoformat(),
            "start_et":    start_et.strftime("%Y-%m-%d %I:%M %p ET"),
            "status":      event.get("status", "Unknown"),
        })

    games.sort(key=lambda g: g["start_utc"])
    return games


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Fetch schedule via game lines endpoint
    print("Fetching today's NHL schedule...")
    try:
        schedule_data = fetch_league_data(GAME_LINES_SUBCATEGORY)
        games = parse_schedule(schedule_data)
        print(f"  Found {len(games)} game(s)")
        for g in games:
            print(f"  {g['start_et']}  {g['away_abbrev']} @ {g['home_abbrev']}  [{g['status']}]")
    except requests.RequestException as e:
        print(f"  Schedule fetch failed: {e}")
        games = []

    polite_delay()

    # 2. Fetch each prop category (raw DK API response preserved for build_csv.js)
    props = {}
    for name, sub_id in PROP_SUBCATEGORIES.items():
        polite_delay()
        print(f"Fetching {name}...")
        try:
            props[name] = fetch_league_data(sub_id)
            count = len(props[name].get("selections", []))
            print(f"  {name}: {count} selections")
        except requests.RequestException as e:
            print(f"  {name} failed: {e}")
            props[name] = None

    # 3. Build output: flat dict with each prop category + schedule
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "schedule":   games,
        **props,
    }

    # Save timestamped archive
    archive_path = os.path.join(script_dir, f"dk_nhl_{timestamp}.json")
    with open(archive_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Saved archive: {archive_path}")

    # Save fixed latest file for build_csv.js and cancel_at_gametime_nhl.py
    latest_path = os.path.join(script_dir, "dk_nhl_latest.json")
    with open(latest_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Saved latest:  {latest_path}")

    # 4. Print cancellation deadlines
    print("\n" + "=" * 60)
    print("KALSHI CANCELLATION DEADLINES")
    print("=" * 60)
    for g in games:
        if g["status"] != "STARTED":
            print(f"  {g['away_abbrev']} @ {g['home_abbrev']}")
            print(f"    Puck drop: {g['start_et']}")
            print(f"    Cancel Kalshi orders before this time")
            print()
