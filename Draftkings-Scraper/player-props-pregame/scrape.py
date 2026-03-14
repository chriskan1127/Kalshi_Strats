"""DraftKings NBA Player Props Scraper"""

import requests
import random
import time
import json
import os
from datetime import datetime

BASE_URL = "https://sportsbook-nash.draftkings.com/sites/US-PA-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets"
NBA_LEAGUE_ID = "42648"

SUBCATEGORIES = {
    "points": "16477",
    "rebounds": "16479",
    "assists": "16478",
    "threes": "16480",
    "double_double": "13762",
    "triple_double": "13759",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Referer": "https://sportsbook.draftkings.com/",
        "Origin": "https://sportsbook.draftkings.com",
    }


def fetch_props(subcategory_id):
    """Fetch player props for a given subcategory."""
    params = {
        "isBatchable": "false",
        "templateVars": f"{NBA_LEAGUE_ID},{subcategory_id}",
        "eventsQuery": f"$filter=leagueId eq '{NBA_LEAGUE_ID}' AND clientMetadata/Subcategories/any(s: s/Id eq '{subcategory_id}')",
        "marketsQuery": f"$filter=clientMetadata/subCategoryId eq '{subcategory_id}' AND tags/all(t: t ne 'SportcastBetBuilder')",
        "include": "Events",
        "entity": "events",
    }
    resp = requests.get(BASE_URL, params=params, headers=get_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_all():
    """Fetch all subcategories with polite delays."""
    results = {}
    for name, sub_id in SUBCATEGORIES.items():
        try:
            print(f"Fetching {name}...")
            results[name] = fetch_props(sub_id)
            time.sleep(random.uniform(2, 4))  # polite delay between requests
        except requests.RequestException as e:
            print(f"  Error fetching {name}: {e}")
            results[name] = None
    return results


if __name__ == "__main__":
    data = fetch_all()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Save timestamped archive copy
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(script_dir, f"dk_props_{timestamp}.json")
    with open(archive_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved archive: {archive_path}")

    # Save fixed "latest" file for build_csv.js to consume
    latest_path = os.path.join(script_dir, "dk_props_latest.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved latest:  {latest_path}")

    # Summary
    for name, props in data.items():
        count = len(props.get("selections", [])) if props else 0
        print(f"  {name}: {count} selections")