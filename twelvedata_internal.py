#!/usr/bin/env python3
"""Collect Twelve Data series for private, non-display internal use only.

This module is intentionally not wired into the dashboard, quote API, charts,
widgets, or browser extension. Basic-plan data must remain non-display.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = "https://api.twelvedata.com/time_series"
BASE = os.path.dirname(os.path.abspath(__file__))
SUPPORTED_INTERVALS = {
    "1min", "5min", "15min", "30min", "45min", "1h", "2h", "4h",
    "8h", "1day", "1week", "1month",
}
SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./=_:-]{0,31}$")
CREDITS_PER_MINUTE = 8
CREDITS_PER_UTC_DAY = 800
WINDOW_SECONDS = 60


class TwelveDataError(RuntimeError):
    """An API or local safety-limit error without credential-bearing details."""


def _key_file_path(home=None):
    return Path(home or Path.home()) / ".config" / "market-glance" / "twelvedata.env"


def _read_key_file(path):
    path = Path(path)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise TwelveDataError(
                "Twelve Data key file permissions are too broad; run chmod 600 on it."
            )
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise TwelveDataError("Unable to read the Twelve Data key file.") from exc

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, value = stripped.partition("=")
        if separator and name.strip() == "TWELVE_DATA_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                return value
    return None


def load_api_key(env=None, home=None):
    """Read the API key from the environment or a mode-600 user config file."""
    env = os.environ if env is None else env
    value = env.get("TWELVE_DATA_API_KEY", "").strip()
    if value:
        return value
    value = _read_key_file(_key_file_path(home))
    if not value:
        raise TwelveDataError(
            "Missing TWELVE_DATA_API_KEY; set it in the environment or in "
            "~/.config/market-glance/twelvedata.env."
        )
    return value


def private_state_dir(home=None, xdg_state_home=None, app_dir=None):
    """Return a private state path outside the app's HTTP-served directory."""
    home_path = Path(home or Path.home())
    root = Path(xdg_state_home or os.environ.get("XDG_STATE_HOME") or home_path / ".local" / "state")
    path = (root / "market-glance" / "twelvedata").resolve()
    app_root = Path(app_dir or BASE).resolve()
    try:
        inside_app = os.path.commonpath((str(path), str(app_root))) == str(app_root)
    except ValueError:
        inside_app = False
    if inside_app:
        raise TwelveDataError("Private Twelve Data storage must be outside the app's served directory.")
    return path


def _request_json(symbol, interval, outputsize, api_key):
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "timezone": "UTC",
        "apikey": api_key,
    })
    request = urllib.request.Request(
        API_URL + "?" + params,
        headers={"User-Agent": "Market-Glance-Internal-Collector/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not include the exception text: urllib's message may contain the URL and API key.
        raise TwelveDataError("Twelve Data request failed (HTTP %d)." % exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise TwelveDataError("Twelve Data request failed due to a network or response error.") from None

    if not isinstance(payload, dict) or payload.get("status") == "error":
        raise TwelveDataError("Twelve Data rejected the request; check the symbol, plan, and key.")
    values = payload.get("values")
    if not isinstance(values, list):
        raise TwelveDataError("Twelve Data returned no time-series values.")

    normalized = []
    for item in values:
        if not isinstance(item, dict) or not item.get("datetime"):
            continue
        row = {"datetime": str(item["datetime"])}
        valid = True
        for field in ("open", "high", "low", "close", "volume"):
            value = item.get(field)
            if value is None:
                continue
            try:
                number = float(value)
                if not (number == number and abs(number) != float("inf")):
                    valid = False
                    break
            except (TypeError, ValueError, OverflowError):
                valid = False
                break
            row[field] = str(value)
        if valid and all(field in row for field in ("open", "high", "low", "close")):
            normalized.append(row)

    if not normalized:
        raise TwelveDataError("Twelve Data returned no usable time-series values.")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    safe_meta = {key: meta[key] for key in (
        "symbol", "interval", "currency", "exchange_timezone", "exchange", "mic_code", "type"
    ) if key in meta}
    return {
        "symbol": symbol,
        "interval": interval,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "meta": safe_meta,
        "values": normalized,
    }


def _atomic_private_json(directory, filename, payload):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    path = os.path.join(directory, filename)
    fd, temporary = tempfile.mkstemp(prefix=".twelvedata-", suffix=".tmp", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as stream:
            result = json.load(stream)
        return result if isinstance(result, dict) else fallback
    except FileNotFoundError:
        return fallback
    except (OSError, json.JSONDecodeError):
        raise TwelveDataError("Unable to read the private Twelve Data state file.") from None


def _utc_day(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date().isoformat()


def _quota_wait(ledger, now):
    """Return required wait; retain the rolling minute window across UTC midnight."""
    today = _utc_day(now)
    recent = [float(value) for value in ledger.get("recent_timestamps", [])
              if 0 <= now - float(value) < WINDOW_SECONDS]
    ledger["recent_timestamps"] = recent
    if ledger.get("utc_day") != today:
        ledger["utc_day"] = today
        ledger["daily_count"] = 0
    if int(ledger.get("daily_count", 0)) >= CREDITS_PER_UTC_DAY:
        raise TwelveDataError("Local Basic-plan safety cap reached: 800 requests for this UTC day.")
    if len(recent) >= CREDITS_PER_MINUTE:
        return max(0.0, recent[0] + WINDOW_SECONDS - now + 0.05)
    return 0.0


def collect(symbols, interval="1day", outputsize=30, *, api_key=None,
            state_dir=None, request_func=None, wait=True, clock=None, sleeper=None):
    """Fetch one time_series request per unique symbol into private local state."""
    if interval not in SUPPORTED_INTERVALS:
        raise TwelveDataError("Unsupported Twelve Data interval.")
    if isinstance(outputsize, bool) or not isinstance(outputsize, int) or not 1 <= outputsize <= 5000:
        raise TwelveDataError("outputsize must be an integer from 1 to 5000.")
    normalized_symbols = []
    seen = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        if not SYMBOL_RE.fullmatch(symbol):
            raise TwelveDataError("Invalid Twelve Data symbol.")
        if symbol not in seen:
            seen.add(symbol)
            normalized_symbols.append(symbol)
    if not normalized_symbols:
        raise TwelveDataError("Provide at least one symbol.")
    if len(normalized_symbols) > CREDITS_PER_UTC_DAY:
        raise TwelveDataError("One run cannot request more than 800 symbols.")

    key = api_key if api_key is not None else load_api_key()
    if not key:
        raise TwelveDataError("Missing Twelve Data API key.")
    request_func = request_func or _request_json
    clock = clock or time.time
    sleeper = sleeper or time.sleep
    directory = Path(state_dir) if state_dir else private_state_dir()
    directory = directory.resolve()
    app_root = Path(BASE).resolve()
    try:
        inside_app = os.path.commonpath((str(directory), str(app_root))) == str(app_root)
    except ValueError:
        inside_app = False
    if inside_app:
        raise TwelveDataError("Private Twelve Data storage must be outside the app's served directory.")

    os.makedirs(directory, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    lock_path = directory / ".collector.lock"
    ledger_path = directory / "credits.json"
    results_path = directory / "series.json"
    saved = 0
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        ledger = _read_json(ledger_path, {"utc_day": None, "daily_count": 0,
                                         "recent_timestamps": []})
        snapshot = _read_json(results_path, {"updated_at": None, "series": {}})
        if not isinstance(snapshot.get("series"), dict):
            snapshot["series"] = {}

        for symbol in normalized_symbols:
            while True:
                now = clock()
                delay = _quota_wait(ledger, now)
                if delay <= 0:
                    break
                if not wait:
                    raise TwelveDataError("Local rate cap reached: at most 8 requests in a rolling minute.")
                sleeper(delay)

            now = clock()
            ledger["recent_timestamps"].append(now)
            ledger["daily_count"] = int(ledger.get("daily_count", 0)) + 1
            ledger["utc_day"] = _utc_day(now)
            _atomic_private_json(str(directory), "credits.json", ledger)

            record = request_func(symbol, interval, outputsize, api_key=key)
            if not isinstance(record, dict) or not isinstance(record.get("values"), list):
                raise TwelveDataError("Twelve Data returned an invalid internal record.")
            snapshot["series"][symbol + "|" + interval] = record
            snapshot["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            _atomic_private_json(str(directory), "series.json", snapshot)
            saved += 1
    return {"saved": saved, "path": str(results_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Collect Twelve Data for private, non-display internal use only."
    )
    parser.add_argument("--symbols", required=True,
                        help="comma-separated symbols; one API credit is reserved per symbol")
    parser.add_argument("--interval", default="1day", choices=sorted(SUPPORTED_INTERVALS))
    parser.add_argument("--outputsize", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        result = collect(args.symbols.split(","), args.interval, args.outputsize)
    except TwelveDataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print("Saved %d private internal series; no quote or chart output was changed." % result["saved"])
    print("Private local file: %s" % result["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
