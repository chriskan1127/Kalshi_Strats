#!/usr/bin/env python3
"""Debug: inspect what Kalshi returns for various NBA series tickers."""

import base64
import os
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from params import public_api_key  # noqa: E402

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
KEY_PATH = os.path.join(SCRIPT_DIR, "chris_mm.txt")


def load_private_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def make_headers(private_key, api_key, method, path):
    ts = str(int(time.time() * 1000))
    msg = ts + method.upper() + path
    sig = private_key.sign(
        msg.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode("utf-8"),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }


def main():
    pk = load_private_key(KEY_PATH)

    import json

    # 1) Is /markets public? Try with NO auth headers
    print("=== GET /markets WITHOUT auth ===")
    resp = requests.get(f"{BASE_URL}/markets", params={"series_ticker": "KXNBAPTS", "limit": 1})
    print(f"  {resp.status_code}: {resp.text[:120]}")

    # 2) Portfolio balance — requires real auth
    print("\n=== GET /portfolio/balance WITH auth ===")
    path = "/trade-api/v2/portfolio/balance"
    resp = requests.get(f"{BASE_URL}/portfolio/balance", headers=make_headers(pk, public_api_key, "GET", path))
    print(f"  {resp.status_code}: {resp.text[:300]}")


if __name__ == "__main__":
    main()
