#!/usr/bin/env python3
"""Verify NHL Kalshi series tickers and market title format.

Run this before the first live trading day to confirm:
  1. Each PROP_TO_SERIES ticker returns open markets.
  2. Market titles follow the expected format for find_market() matching.

Usage:
    python check_markets.py
"""

import base64
import os
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MM_HOCKEY  = os.path.join(SCRIPT_DIR, "../../Kalshi-MM/hockey")
KEY_PATH   = os.path.join(SCRIPT_DIR, "../../Kalshi-MM/chris_mm.txt")

sys.path.insert(0, MM_HOCKEY)
from params import public_api_key  # noqa: E402

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Must match pregame_dk_nhl_playerprop.py exactly
PROP_TO_SERIES = {
    "Goals":         "KXNHLGOAL",
    "Shots on Goal": "KXNHLSOG",
    "Points":        "KXNHLPTS",
    "Assists":       "KXNHLAST",
}

SAMPLE_SIZE = 5   # titles to print per series
READ_SLEEP  = 1 / 25


def load_private_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def make_headers(private_key, api_key: str, method: str, path: str) -> dict:
    ts  = str(int(time.time() * 1000))
    msg = ts + method.upper() + path
    sig = private_key.sign(
        msg.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "Content-Type":            "application/json",
        "KALSHI-ACCESS-KEY":       api_key,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode("utf-8"),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }


def fetch_markets(private_key, series_ticker: str) -> list[dict]:
    api_path = "/trade-api/v2/markets"
    markets  = []
    cursor   = None
    while True:
        params: dict = {"series_ticker": series_ticker, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        headers = make_headers(private_key, public_api_key, "GET", api_path)
        resp    = requests.get(f"{BASE_URL}/markets", headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(READ_SLEEP)
    return markets


def main() -> None:
    if not os.path.exists(KEY_PATH):
        print(f"ERROR: private key not found at {KEY_PATH}")
        sys.exit(1)

    private_key = load_private_key(KEY_PATH)
    issues      = []

    print(f"{'='*65}")
    print("Kalshi NHL Series Ticker Check")
    print(f"{'='*65}\n")

    for prop_type, series in PROP_TO_SERIES.items():
        print(f"[{prop_type}]  series={series}")
        markets = fetch_markets(private_key, series)

        if not markets:
            print(f"  *** NO OPEN MARKETS — ticker may be wrong ***\n")
            issues.append(f"{prop_type}: {series} returned 0 markets")
            time.sleep(READ_SLEEP)
            continue

        print(f"  {len(markets)} open markets")
        print(f"  Sample titles (first {min(SAMPLE_SIZE, len(markets))}):")
        for m in markets[:SAMPLE_SIZE]:
            print(f"    \"{m.get('title', '')}\"  [{m.get('ticker', '')}]")

        # Spot-check: verify title contains ": N+" pattern (threshold format)
        sample_titles = [m.get("title", "") for m in markets[:20]]
        threshold_ok  = any(": " in t and "+" in t for t in sample_titles)
        if not threshold_ok:
            print(f"  *** WARNING: titles may not match expected '{{name}}: {{N}}+' format ***")
            issues.append(f"{prop_type}: unexpected title format — check find_market() logic")
        else:
            print(f"  Title format looks correct (contains ': N+' pattern)")
        print()
        time.sleep(READ_SLEEP)

    print(f"{'='*65}")
    if issues:
        print(f"ISSUES FOUND ({len(issues)}):")
        for i in issues:
            print(f"  - {i}")
        print("\nUpdate PROP_TO_SERIES in pregame_dk_nhl_playerprop.py with correct tickers.")
    else:
        print("All series tickers verified — ready to trade.")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
