#!/usr/bin/env python3
"""Shared configuration defaults and validation for Market Glance."""
import math
import re

DEFAULT_CONFIG = {
    "anomaly_threshold_pct": 3.0,
    "fetch_interval_secs": 300,
    "www_port": 8090,
}
SYMBOL_RE = re.compile(r"^[A-Z0-9^.\-=]{1,12}$")
MAX_GROUPS = 10
MAX_TICKERS_PER_GROUP = 30
MAX_TICKERS_TOTAL = 60


def provider_for_symbol(symbol):
    """Route plain US stock symbols to IEX and market-qualified symbols to Yahoo."""
    normalized = str(symbol).strip().upper()
    return "yahoo" if not re.fullmatch(r"[A-Z0-9]+", normalized) else "alpaca_iex"


def _label(value, fallback, limit):
    if value is None:
        value = ""
    elif not isinstance(value, str):
        value = str(value)
    cleaned = "".join(ch for ch in value.strip() if ch.isprintable())
    return (cleaned or fallback)[:limit]


def validate_config(payload):
    """Return a normalized configuration or raise ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("配置必须是 JSON 对象")

    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("至少需要一个分组")
    if len(groups) > MAX_GROUPS:
        raise ValueError("分组太多（最多 %d 个）" % MAX_GROUPS)

    out, total, seen = [], 0, set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("分组格式错误")
        group_name = _label(group.get("name"), "未命名", 24)
        tickers = group.get("tickers")
        if not isinstance(tickers, list) or not tickers:
            raise ValueError("分组「%s」至少需要一个代码" % group_name)
        if len(tickers) > MAX_TICKERS_PER_GROUP:
            raise ValueError("分组「%s」代码太多（最多 %d 个）" % (group_name, MAX_TICKERS_PER_GROUP))

        normalized_tickers = []
        for ticker in tickers:
            if not isinstance(ticker, dict):
                raise ValueError("代码格式错误")
            raw_symbol = ticker.get("symbol", "")
            symbol = str(raw_symbol).strip().upper()
            if not SYMBOL_RE.fullmatch(symbol):
                raise ValueError("代码格式不对：%r（只允许字母、数字、^ . - =）" % raw_symbol)
            if symbol in seen:
                raise ValueError("代码重复：%s" % symbol)
            seen.add(symbol)
            name = _label(ticker.get("name"), symbol, 24)
            normalized_tickers.append({
                "symbol": symbol, "name": name,
                "provider": provider_for_symbol(symbol),
            })
        total += len(normalized_tickers)
        out.append({"name": group_name, "tickers": normalized_tickers})

    if total > MAX_TICKERS_TOTAL:
        raise ValueError("代码总数太多（最多 %d 个），行情源可能限流" % MAX_TICKERS_TOTAL)

    threshold = payload.get("anomaly_threshold_pct", DEFAULT_CONFIG["anomaly_threshold_pct"])
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("异动阈值必须是数字")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.1 <= threshold <= 50:
        raise ValueError("异动阈值必须在 0.1 到 50 之间")

    interval = payload.get("fetch_interval_secs", DEFAULT_CONFIG["fetch_interval_secs"])
    if isinstance(interval, bool) or not isinstance(interval, int) or not 60 <= interval <= 86400:
        raise ValueError("抓取间隔必须是 60 到 86400 秒之间的整数")

    port = payload.get("www_port", DEFAULT_CONFIG["www_port"])
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("网页端口必须是 1024 到 65535 之间的整数")

    return {
        "anomaly_threshold_pct": threshold,
        "fetch_interval_secs": interval,
        "www_port": port,
        "groups": out,
    }


def load_config(path):
    import json

    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    return validate_config(payload)
