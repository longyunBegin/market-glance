#!/usr/bin/env python3
"""Small, dependency-free client for Alpaca's IEX stock market data API."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://data.alpaca.markets"


def _auth_headers():
    key = os.environ.get("APCA_API_KEY_ID", "").strip()
    secret = os.environ.get("APCA_API_SECRET_KEY", "").strip()
    if not key or not secret:
        raise RuntimeError(
            "Alpaca IEX 需要 APCA_API_KEY_ID 和 APCA_API_SECRET_KEY 环境变量"
        )
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "User-Agent": "MarketGlance/1.0",
    }


def _request_json(path, params):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        BASE_URL + path + ("?" + query if query else ""),
        headers=_auth_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", errors="replace").strip()
        suffix = (": " + detail[:240]) if detail else ""
        raise RuntimeError("Alpaca IEX API HTTP %d%s" % (exc.code, suffix)) from None


def fetch_latest_trades(symbols):
    """Return Alpaca's latest IEX trades keyed by stock symbol."""
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return {}
    if len(symbols) > 100:
        raise ValueError("Alpaca latest-trades 每次最多请求 100 个代码")
    payload = _request_json(
        "/v2/stocks/trades/latest",
        {"symbols": ",".join(symbols), "feed": "iex"},
    )
    trades = payload.get("trades", {})
    return trades if isinstance(trades, dict) else {}


def fetch_bars(symbol, timeframe, start, end):
    """Return historical IEX bars for one symbol."""
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    payload = _request_json(
        "/v2/stocks/%s/bars" % encoded_symbol,
        {
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": 10000,
            "feed": "iex",
        },
    )
    bars = payload.get("bars", [])
    return bars if isinstance(bars, list) else []
