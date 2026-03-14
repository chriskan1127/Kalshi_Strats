#!/usr/bin/env python3
"""Cancel all resting Kalshi orders for a specific game at tip-off.

Usage:
    python cancel_game.py ORLMIN

The game code (e.g. ORLMIN) is matched as a substring against each open
order's ticker.  Orders for other games are not touched.
"""

import base64
import datetime
import os
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from params import public_api_key  # noqa: E402

BASE_URL   = "https://api.elections.kalshi.com/trade-api/v2"
KEY_PATH   = os.path.join(SCRIPT_DIR, "chris_mm.txt")
LOGS_DIR   = os.path.join(SCRIPT_DIR, "logs")
_today     = datetime.date.today().strftime("%m-%d-%y")

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
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "Content-Type":            "application/json",
        "KALSHI-ACCESS-KEY":       api_key,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode("utf-8"),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }


# ── Kalshi order management ───────────────────────────────────────────────────

def get_resting_orders(private_key) -> list[dict]:
    """Fetch all resting orders, handling pagination."""
    api_path = "/trade-api/v2/portfolio/orders"
    orders: list[dict] = []
    cursor = None

    while True:
        params: dict = {"status": "resting", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        headers = make_headers(private_key, public_api_key, "GET", api_path)
        resp    = requests.get(f"{BASE_URL}/portfolio/orders", headers=headers, params=params)

        if resp.status_code != 200:
            print(f"  [warn] orders fetch → {resp.status_code}: {resp.text[:150]}")
            break

        data   = resp.json()
        orders.extend(data.get("orders", []))
        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(READ_SLEEP)

    return orders


def cancel_order(private_key, order_id: str) -> bool:
    api_path = f"/trade-api/v2/portfolio/orders/{order_id}"
    headers  = make_headers(private_key, public_api_key, "DELETE", api_path)
    resp     = requests.delete(f"{BASE_URL}/portfolio/orders/{order_id}", headers=headers)
    return resp.status_code in (200, 204)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python cancel_game.py <GAME_CODE>  e.g. ORLMIN")
        sys.exit(1)

    game_code = sys.argv[1].upper()
    # Also try reversed in case away/home ordering differs
    game_code2 = game_code[3:] + game_code[:3]

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path    = os.path.join(LOGS_DIR, f"{_today}_cancel_at_gametime.log")
    private_key = load_private_key(KEY_PATH)

    with open(log_path, "a", encoding="utf-8") as lf:
        def log(msg: str):
            ts   = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {msg}"
            print(line)
            lf.write(line + "\n")
            lf.flush()

        log(f"TIP-OFF  game={game_code} — fetching resting orders …")
        orders = get_resting_orders(private_key)

        game_orders = [
            o for o in orders
            if game_code in o.get("ticker", "") or game_code2 in o.get("ticker", "")
        ]

        log(f"  {len(orders)} total resting orders | {len(game_orders)} for {game_code}")

        cancelled = errors = 0
        for o in game_orders:
            ticker   = o.get("ticker", "")
            order_id = o.get("order_id", "")
            if cancel_order(private_key, order_id):
                log(f"  CANCELLED  [{ticker}]")
                cancelled += 1
            else:
                log(f"  ERROR      [{ticker}]  id={order_id}")
                errors += 1
            time.sleep(WRITE_SLEEP)

        log(f"  Done — cancelled={cancelled}  errors={errors}")


if __name__ == "__main__":
    main()
