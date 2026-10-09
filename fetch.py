#!/usr/bin/env python3
"""Fetch market quotes from Yahoo Finance or Alpaca IEX and write JSON snapshots."""
import argparse
import fcntl
import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, time as clock_time, timedelta, timezone

from alpaca_data import fetch_bars as fetch_alpaca_bars, fetch_latest_trades
from config_model import load_config
from market_calendar import early_closes, is_trading_day

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - supported Python versions include zoneinfo
    ET = timezone(timedelta(hours=-4))

BASE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


def get(url):
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def kline_filename(symbol):
    return symbol.replace("^", "_").replace(".", "_") + ".json"


def kline_cache_path(directory, symbol, timeframe, provider="yahoo"):
    """Keep each provider's cached candles separate; preserve old Yahoo paths."""
    suffix = {"5m": "", "15m": "_15m", "1d": "_1d"}[timeframe]
    filename = kline_filename(symbol)[:-5] + suffix + ".json"
    cache_dir = directory if provider == "yahoo" else os.path.join(directory, provider)
    return os.path.join(cache_dir, filename)


def fetch_candles(symbol, interval, period, provider="yahoo"):
    """Return candles [[ts, o, h, l, c, v], ...] and source metadata."""
    if provider == "alpaca_iex":
        timeframe = {"5m": "5Min", "15m": "15Min", "1d": "1Day"}.get(interval)
        days = {"2d": 5, "1mo": 35, "1y": 370}.get(period)
        if timeframe is None or days is None:
            raise ValueError("Alpaca IEX 不支持此 K 线周期")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        bars = fetch_alpaca_bars(
            symbol, timeframe,
            start.isoformat(timespec="seconds").replace("+00:00", "Z"),
            end.isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        candles = []
        for bar in bars:
            timestamp = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
            candles.append([
                int(timestamp.timestamp()), float(bar["o"]), float(bar["h"]),
                float(bar["l"]), float(bar["c"]), int(bar.get("v") or 0),
            ])
        candles.sort(key=lambda candle: candle[0])
        return candles, {"provider": provider}
    if provider != "yahoo":
        raise ValueError("未知行情数据源：%s" % provider)
    encoded = urllib.parse.quote(symbol, safe="")
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?interval=%s&range=%s&includePrePost=true" % (encoded, interval, period))
    data = get(url)
    result = data["chart"]["result"][0]
    metadata = result["meta"]
    timestamps = result["timestamp"] or []
    quote = result["indicators"]["quote"][0]
    volume = quote.get("volume") or []
    candles = []
    for index, timestamp in enumerate(timestamps):
        open_price = quote["open"][index]
        high = quote["high"][index]
        low = quote["low"][index]
        close = quote["close"][index]
        if open_price is None or high is None or low is None or close is None:
            continue
        vol = volume[index] if index < len(volume) and volume[index] is not None else 0
        candles.append([timestamp, round(open_price, 2), round(high, 2),
                        round(low, 2), round(close, 2), int(vol)])
    return candles, metadata


def _as_et(now=None):
    now = now or datetime.now(ET)
    return now.replace(tzinfo=ET) if now.tzinfo is None else now.astimezone(ET)


def _regular_close_time(day):
    return clock_time(13, 0) if day in early_closes(day.year) else clock_time(16, 0)


def _market_is_open(now):
    now = _as_et(now)
    local_time = now.time().replace(tzinfo=None)
    return (is_trading_day(now.date()) and clock_time(9, 30) <= local_time <
            _regular_close_time(now.date()))


def _quote_session(timestamp):
    """Classify a quote timestamp, including quotes retained over weekends."""
    if timestamp is None:
        return "unknown"
    quoted_at = datetime.fromtimestamp(timestamp, ET)
    if not is_trading_day(quoted_at.date()):
        return "closed"
    local_time = quoted_at.time().replace(tzinfo=None)
    close_time = _regular_close_time(quoted_at.date())
    if clock_time(4, 0) <= local_time < clock_time(9, 30):
        return "pre"
    if clock_time(9, 30) <= local_time < close_time:
        return "regular"
    if close_time <= local_time < clock_time(20, 0):
        return "after"
    return "closed"


def _completed_session_closes(candles, now=None, daily=False):
    """Return completed regular-session closes keyed by NYSE session date."""
    now = _as_et(now)
    closes_by_day = {}
    for candle in candles:
        if len(candle) < 5:
            continue
        try:
            timestamp, close = int(candle[0]), float(candle[4])
        except (TypeError, ValueError, OverflowError):
            continue
        if close <= 0:
            continue
        day = datetime.fromtimestamp(timestamp, ET).date()
        if not is_trading_day(day):
            continue
        if not daily:
            local_time = datetime.fromtimestamp(timestamp, ET).time().replace(tzinfo=None)
            if not clock_time(9, 30) <= local_time < _regular_close_time(day):
                continue
        closes_by_day[day] = close

    completed = []
    for day in sorted(closes_by_day, reverse=True):
        if day > now.date():
            continue
        if day == now.date() and now.time().replace(tzinfo=None) < _regular_close_time(day):
            continue
        completed.append((day, closes_by_day[day]))
    return completed


def _trade_timestamp(trade):
    if not isinstance(trade, dict) or not trade.get("t"):
        return None
    try:
        return datetime.fromisoformat(str(trade["t"]).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_one(symbol, name, group, provider="yahoo", latest_trade=None,
              trades_loaded=False, now=None):
    """Fetch a quote whose daily change is always anchored to regular closes."""
    candles, metadata = fetch_candles(symbol, "5m", "2d", provider=provider)
    if provider == "alpaca_iex" and not trades_loaded:
        latest_trade = fetch_latest_trades([symbol]).get(symbol)

    now_et = _as_et(now)
    closes = [candle[4] for candle in candles if len(candle) > 4]
    timestamps = [candle[0] for candle in candles if candle]
    last = closes[-1] if closes else None
    price_timestamp = timestamps[-1] if timestamps else None
    if provider == "alpaca_iex" and isinstance(latest_trade, dict):
        trade_price = latest_trade.get("p")
        if isinstance(trade_price, (int, float)) and trade_price > 0:
            last = float(trade_price)
            price_timestamp = _trade_timestamp(latest_trade) or price_timestamp
    if last is None:
        raise ValueError("行情源没有可用成交或 K 线数据")

    # Daily bars span holidays and long weekends that a two-day intraday window
    # cannot cover. Intraday regular-session bars are a fallback if daily fetch fails.
    daily_candles = []
    try:
        if provider == "yahoo":
            time.sleep(5.0)
        daily_candles, _ = fetch_candles(symbol, "1d", "1mo", provider=provider)
    except Exception:  # noqa: BLE001 - preserve quotes when the daily endpoint fails
        pass
    session_closes = {}
    for day, close in _completed_session_closes(candles, now_et, daily=False):
        session_closes[day] = close
    for day, close in _completed_session_closes(daily_candles, now_et, daily=True):
        session_closes[day] = close
    recent_closes = sorted(session_closes.items(), reverse=True)

    regular_close = recent_closes[0][1] if recent_closes else None
    previous_close = recent_closes[1][1] if len(recent_closes) > 1 else None
    metadata_previous = metadata.get("chartPreviousClose") or metadata.get("previousClose")
    if regular_close is None:
        regular_close = metadata_previous or (closes[-1] if closes else None)
    if previous_close is None and metadata_previous and metadata_previous != regular_close:
        previous_close = metadata_previous

    price_session = _quote_session(price_timestamp)
    quoted_on = (datetime.fromtimestamp(price_timestamp, ET).date()
                 if price_timestamp is not None else None)
    live_regular_quote = (
        _market_is_open(now_et) and price_session == "regular" and quoted_on == now_et.date()
    )
    if live_regular_quote and regular_close:
        change = (last / regular_close - 1) * 100
        comparison_close = regular_close
    elif regular_close and previous_close:
        change = (regular_close / previous_close - 1) * 100
        comparison_close = previous_close
    elif previous_close:
        change = (last / previous_close - 1) * 100
        comparison_close = previous_close
    else:
        change = None
        comparison_close = previous_close

    extended_change = None
    if price_session in ("pre", "after") and regular_close:
        extended_change = (last / regular_close - 1) * 100
    return {
        "symbol": symbol, "name": name, "group": group,
        "price": round(last, 2),
        "chg_pct": round(change, 2) if change is not None else None,
        "prev_close": round(comparison_close, 4) if comparison_close is not None else None,
        "regular_close": round(regular_close, 4) if regular_close is not None else None,
        "price_session": price_session,
        "extended_chg_pct": round(extended_change, 2) if extended_change is not None else None,
        "provider": provider,
    }, candles


def fetch_is_due(interval_secs, last_attempt, now=None):
    """Whether an interval-based fetch should run; missing timestamps are due."""
    now = time.time() if now is None else now
    return last_attempt is None or now - last_attempt >= interval_secs


def _atomic_json(path, payload):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".market-glance-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _last_attempt(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return float(json.load(stream)["timestamp"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch market quotes")
    parser.add_argument("--force", action="store_true", help="ignore the configured fetch interval")
    args = parser.parse_args(argv)

    config = load_config(os.path.join(BASE, "config.json"))
    data_dir = os.path.join(BASE, "data")
    klines_dir = os.path.join(data_dir, "klines")
    os.makedirs(klines_dir, exist_ok=True)
    lock_path = os.path.join(data_dir, ".fetch.lock")
    last_attempt_path = os.path.join(data_dir, ".last-fetch-at.json")

    with open(lock_path, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("skip: another fetch is already running")
            return

        now = time.time()
        if not args.force and not fetch_is_due(config["fetch_interval_secs"],
                                               _last_attempt(last_attempt_path), now):
            print("skip: next fetch is due in %d seconds" % max(
                0, int(config["fetch_interval_secs"] - (now - _last_attempt(last_attempt_path)))))
            return
        _atomic_json(last_attempt_path, {"timestamp": now})

        previous_quotes = {}
        quotes_path = os.path.join(data_dir, "quotes.json")
        if os.path.exists(quotes_path):
            try:
                with open(quotes_path, encoding="utf-8") as stream:
                    previous_quotes = {quote["symbol"]: quote
                                       for quote in json.load(stream)["quotes"]}
            except Exception:  # noqa: BLE001
                pass

        quotes = []
        provider = config["market_data_provider"]
        ticker_symbols = [ticker["symbol"] for group in config["groups"]
                          for ticker in group["tickers"]]
        latest_trades = {}
        if provider == "alpaca_iex":
            try:
                latest_trades = fetch_latest_trades(ticker_symbols)
            except Exception as exc:  # noqa: BLE001
                print("warn: Alpaca IEX latest trades unavailable: %s" % str(exc)[:160])
        for group in config["groups"]:
            for ticker in group["tickers"]:
                symbol = ticker["symbol"]
                name, group_name = ticker["name"], group["name"]
                error = None
                quote = None
                for attempt in (1, 2):
                    try:
                        quote, candles = fetch_one(
                            symbol, name, group_name, provider=provider,
                            latest_trade=latest_trades.get(symbol),
                            trades_loaded=(provider == "alpaca_iex"),
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        error = str(exc)[:120]
                        if "429" in error and attempt == 1:
                            time.sleep(30)
                        else:
                            break
                if quote is not None:
                    quote["stale"] = False
                    quote["last_success_at"] = int(now)
                    quote.pop("stale_since", None)
                    quotes.append(quote)
                    _atomic_json(kline_cache_path(klines_dir, symbol, "5m", provider),
                                 {"symbol": symbol, "tf": "5m", "provider": provider,
                                  "candles": candles})
                else:
                    old = previous_quotes.get(symbol)
                    if old and old.get("price") is not None:
                        old = dict(old)
                        old["name"], old["group"] = name, group_name
                        old["stale"] = True
                        old.setdefault("stale_since", int(now))
                        quotes.append(old)
                    else:
                        quotes.append({"symbol": symbol, "name": name, "group": group_name,
                                       "price": None, "chg_pct": None, "error": error})
                if provider == "yahoo":
                    time.sleep(5.0)

        _atomic_json(quotes_path, {"updated": int(time.time()),
                                   "anomaly_threshold_pct": config["anomaly_threshold_pct"],
                                   "provider": provider,
                                   "quotes": quotes})
        successful = sum(1 for quote in quotes if quote["price"] is not None)
        print("ok: %d/%d tickers" % (successful, len(quotes)))


if __name__ == "__main__":
    main()
