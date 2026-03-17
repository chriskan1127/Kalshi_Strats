#!/usr/bin/env python3
"""Post DraftKings NHL player-prop offers on Kalshi with added vig.

Reads today's NHL props CSV (MM-DD-YY_nhl_props.csv), finds matching Kalshi
markets, and posts a limit buy-NO order at:
    offer_price = max(MIN_OFFER, min(99, round(dk_implied_prob_pct + EDGE_ON_OFFER)))
at OFFER_SIZE contracts.  Markets not found on Kalshi are silently skipped.

Also posts a buy-YES bid at BID_FROM_OFFER cents below the offer, capped at MAX_BID.

Kalshi rate limit: 30 reads + writes per second combined.

NOTE: Verify NHL series tickers against live Kalshi markets before first run.
"""

import base64
import csv
import datetime
import os
import re
import sys
import time
import uuid

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from params import EDGE_ON_OFFER, MIN_OFFER, OFFER_SIZE, BID_SIZE, MAX_BID, BID_FROM_OFFER, public_api_key  # noqa: E402

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
_today   = datetime.date.today().strftime("%m-%d-%y")
CSV_PATH = os.path.join(
    SCRIPT_DIR,
    f"../../Draftkings-Scraper/hockey-props-pregame/props/{_today}_nhl_props.csv",
)
KEY_PATH  = os.path.join(SCRIPT_DIR, "../chris_mm.txt")
LOGS_DIR  = os.path.join(SCRIPT_DIR, "logs")

# Kalshi NHL series tickers — verify against live Kalshi markets before running
# Format mirrors NBA: KXNHL + stat abbreviation
PROP_TO_SERIES = {
    "Goals":   "KXNHLFIRSTGOAL",   # DK scrapes First Goalscorer for this category
    "Points":  "KXNHLPTS",
    "Assists": "KXNHLAST",
}

# Stay well under the 30 req/s combined read+write limit
READ_SLEEP  = 1 / 25
WRITE_SLEEP = 1 / 25


# ── Auth ──────────────────────────────────────────────────────────────────────

def load_private_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def make_headers(private_key, api_key: str, method: str, path: str) -> dict:
    ts  = str(int(time.time() * 1000))
    msg = ts + method.upper() + path
    sig = private_key.sign(
        msg.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "Content-Type":            "application/json",
        "KALSHI-ACCESS-KEY":       api_key,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode("utf-8"),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }


# ── Market fetch ──────────────────────────────────────────────────────────────

def get_markets_for_series(private_key, api_key: str, series_ticker: str) -> list[dict]:
    """Fetch all open markets for a series, handling pagination."""
    api_path = "/trade-api/v2/markets"
    markets: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "series_ticker": series_ticker,
            "status": "open",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor

        headers = make_headers(private_key, api_key, "GET", api_path)
        resp    = requests.get(f"{BASE_URL}/markets", headers=headers, params=params)

        if resp.status_code != 200:
            print(f"  [warn] {series_ticker} fetch → {resp.status_code}: {resp.text[:150]}")
            break

        data = resp.json()
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break

        time.sleep(READ_SLEEP)

    return markets


def build_title_index(markets: list[dict]) -> dict[str, dict]:
    """Build lowercase-title → market dict for O(1) lookup."""
    return {(m.get("title") or "").lower(): m for m in markets}


# ── Market matching ───────────────────────────────────────────────────────────

def find_market(
    title_index: dict[str, dict],
    player_name: str,
    threshold: int,
) -> dict | None:
    """Threshold-based props: title like '{Name}: 1+ goals'. Match on prefix."""
    name_lower = player_name.lower()
    prefix = f"{name_lower}: {threshold}+"
    for title, market in title_index.items():
        if title.startswith(prefix):
            return market
    tag = f": {threshold}+"
    for title, market in title_index.items():
        if name_lower in title and tag in title:
            return market
    return None


def find_first_goalscorer_market(
    title_index: dict[str, dict],
    player_name: str,
) -> dict | None:
    """Match Kalshi 'First Goalscorer' markets: title = '{Name}: First Goalscorer'."""
    name_lower = player_name.lower()
    target = f"{name_lower}: first goalscorer"
    if target in title_index:
        return title_index[target]
    # Fallback: name substring anywhere in title
    for title, market in title_index.items():
        if name_lower in title and "first goalscorer" in title:
            return market
    return None


# ── Order posting ─────────────────────────────────────────────────────────────

def post_offer(private_key, api_key: str, ticker: str, yes_price: int, count: int) -> requests.Response:
    """Buy NO at (100 - yes_price) — equivalent to selling YES at yes_price."""
    api_path = "/trade-api/v2/portfolio/orders"
    body = {
        "ticker":          ticker,
        "client_order_id": str(uuid.uuid4()),
        "type":            "limit",
        "action":          "buy",
        "side":            "no",
        "no_price":        100 - yes_price,
        "count":           count,
    }
    headers = make_headers(private_key, api_key, "POST", api_path)
    return requests.post(f"{BASE_URL}/portfolio/orders", headers=headers, json=body)


def post_bid(private_key, api_key: str, ticker: str, yes_price: int, count: int) -> requests.Response:
    """Buy YES at yes_price cents."""
    api_path = "/trade-api/v2/portfolio/orders"
    body = {
        "ticker":          ticker,
        "client_order_id": str(uuid.uuid4()),
        "type":            "limit",
        "action":          "buy",
        "side":            "yes",
        "yes_price":       yes_price,
        "count":           count,
    }
    headers = make_headers(private_key, api_key, "POST", api_path)
    return requests.post(f"{BASE_URL}/portfolio/orders", headers=headers, json=body)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{_today}_pregame_dk_nhl_playerprop.log")
    log_fh   = open(log_path, "a", encoding="utf-8")

    class _Tee:
        def __init__(self, *streams): self._s = streams
        def write(self, t):
            for s in self._s: s.write(t)
            return len(t)
        def flush(self):
            for s in self._s: s.flush()

    sys.stdout = _Tee(sys.__stdout__, log_fh)

    try:
        _run()
    finally:
        sys.stdout = sys.__stdout__
        log_fh.close()


def _run() -> None:
    private_key = load_private_key(KEY_PATH)

    # Pre-fetch markets for each supported prop type
    print("Fetching Kalshi NHL markets …")
    series_index: dict[str, dict[str, dict]] = {}
    for prop_type, series in PROP_TO_SERIES.items():
        markets = get_markets_for_series(private_key, public_api_key, series)
        series_index[prop_type] = build_title_index(markets)
        print(f"  {series:12s} → {len(markets):4d} open markets")
        time.sleep(READ_SLEEP)
    print()

    placed = skipped = errors = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            player       = row["player_name"]
            prop_type    = row["prop_type"]
            player_prop  = row["player_prop"]        # e.g. "Goals 1+"
            implied_prob = float(row["implied_probability"])

            title_index = series_index.get(prop_type)
            if title_index is None:
                skipped += 1
                continue

            offer_price = max(MIN_OFFER, min(99, round(implied_prob * 100 + EDGE_ON_OFFER)))

            if "First Goalscorer" in player_prop:
                market     = find_first_goalscorer_market(title_index, player)
                thresh_str = "1st goal"
            else:
                m = re.search(r"(\d+)\+", player_prop)
                if not m:
                    skipped += 1
                    continue
                threshold  = int(m.group(1))
                market     = find_market(title_index, player, threshold)
                thresh_str = f"{threshold}+"

            if not market:
                print(f"  SKIP   {player:<26} {prop_type:<16} {thresh_str}")
                skipped += 1
                continue

            ticker = market["ticker"]
            resp   = post_offer(private_key, public_api_key, ticker, offer_price, OFFER_SIZE)

            dk_pct = implied_prob * 100
            if resp.status_code in (200, 201):
                print(
                    f"  OK     {player:<26} {prop_type:<16} {thresh_str:<5}  "
                    f"DK={dk_pct:.1f}¢ → offer={offer_price}¢  [{ticker}]"
                )
                placed += 1
            else:
                print(
                    f"  ERROR  {player:<26} {prop_type:<16} {thresh_str:<5}  "
                    f"[{ticker}] {resp.status_code}: {resp.text[:120]}"
                )
                errors += 1

            time.sleep(WRITE_SLEEP)

            # Post bid BID_FROM_OFFER points below our offer, capped at MAX_BID
            bid_price = min(MAX_BID, offer_price - BID_FROM_OFFER)
            if bid_price >= 1:
                resp_bid = post_bid(private_key, public_api_key, ticker, bid_price, BID_SIZE)
                if resp_bid.status_code in (200, 201):
                    print(
                        f"  BID    {player:<26} {prop_type:<16} {thresh_str:<5}  "
                        f"bid={bid_price}¢  [{ticker}]"
                    )
                    placed += 1
                else:
                    print(
                        f"  BDERR  {player:<26} {prop_type:<16} {thresh_str:<5}  "
                        f"[{ticker}] {resp_bid.status_code}: {resp_bid.text[:120]}"
                    )
                    errors += 1
                time.sleep(WRITE_SLEEP)

    print(f"\n{'─' * 65}")
    print(f"Placed: {placed}  |  Skipped (no market): {skipped}  |  Errors: {errors}")


if __name__ == "__main__":
    main()
