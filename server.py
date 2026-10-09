#!/usr/bin/env python3
"""Market Glance web server: static files and small JSON APIs."""
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config.json")
FETCH = os.path.join(BASE, "fetch.py")
DATA = os.path.join(BASE, "data")
KL_DIR = os.path.join(DATA, "klines")

sys.path.insert(0, BASE)
from config_model import load_config, provider_for_symbol, validate_config  # noqa: E402
from fetch import fetch_candles, kline_cache_path  # noqa: E402
from market_calendar import market_status  # noqa: E402

SYM_RE = re.compile(r"^[A-Z0-9^.=\-]{1,12}$")
TF_MAP = {
    "5m": ("5m", "2d", None),
    "15m": ("15m", "1mo", 900),
    "1d": ("1d", "1y", 3600),
}
_KLINE_LOCKS = {}
_KLINE_LOCKS_GUARD = threading.Lock()


def cache_is_fresh(path, ttl, now=None):
    """Return whether a cache file is younger than ttl seconds."""
    try:
        age = (time.time() if now is None else now) - os.path.getmtime(path)
        return 0 <= age < ttl
    except OSError:
        return False


def _kline_lock(key):
    with _KLINE_LOCKS_GUARD:
        return _KLINE_LOCKS.setdefault(key, threading.Lock())


def _atomic_json(path, value):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".market-glance-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_path(self):
        return self.path.split("?", 1)[0]

    def do_GET(self):
        path = self._api_path()
        if path == "/api/config":
            try:
                self._json(load_config(CONFIG))
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)[:200]}, 500)
            return
        if path == "/api/market-status":
            self._json(market_status())
            return
        if path == "/api/klines":
            self._serve_klines()
            return
        return super().do_GET()

    def _serve_klines(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        symbol = (query.get("symbol") or [""])[0].strip().upper()
        timeframe = (query.get("tf") or ["5m"])[0]
        force = (query.get("refresh") or ["0"])[0] == "1"
        if not SYM_RE.fullmatch(symbol):
            self._json({"ok": False, "error": "代码格式不对"}, 400)
            return
        if timeframe not in TF_MAP:
            self._json({"ok": False, "error": "周期只支持 5m / 15m / 1d"}, 400)
            return

        config = load_config(CONFIG)
        provider = provider_for_symbol(symbol)
        interval, yahoo_range, ttl = TF_MAP[timeframe]
        path = kline_cache_path(KL_DIR, symbol, timeframe, provider)

        def cached_response(stale=False, max_age=0):
            with open(path, encoding="utf-8") as stream:
                payload = json.load(stream)
            updated = int(os.path.getmtime(path))
            return {"ok": True, "symbol": symbol, "tf": timeframe,
                    "candles": payload["candles"], "cached": True,
                    "stale": bool(stale), "updated_at": updated,
                    "max_age": max(1, int(max_age)), "provider": provider}

        if ttl is None:
            try:
                stale_after = max(120, config["fetch_interval_secs"] * 2)
                age = max(0, time.time() - os.path.getmtime(path))
                self._json(cached_response(stale=age > stale_after, max_age=30))
            except FileNotFoundError:
                self._json({"ok": False, "error": "暂无该代码的 5 分钟数据"}, 404)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": "读取 K 线缓存失败：%s" % str(exc)[:100]}, 500)
            return

        key = provider + "_" + symbol + "_" + timeframe
        with _kline_lock(key):
            if not force and cache_is_fresh(path, ttl):
                try:
                    remaining = ttl - (time.time() - os.path.getmtime(path))
                    self._json(cached_response(max_age=remaining))
                    return
                except Exception:  # noqa: BLE001
                    pass

            error = None
            for attempt in (1, 2):
                try:
                    candles, _meta = fetch_candles(
                        symbol, interval, yahoo_range, provider=provider)
                    if not candles:
                        raise ValueError("行情数据源返回空 K 线")
                    _atomic_json(path, {"symbol": symbol, "tf": timeframe,
                                        "provider": provider, "candles": candles})
                    self._json({"ok": True, "symbol": symbol, "tf": timeframe,
                                "candles": candles, "cached": False,
                                "stale": False, "updated_at": int(time.time()),
                                "max_age": ttl, "provider": provider})
                    return
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)[:120]
                    if "429" in error and attempt == 1:
                        time.sleep(10)

            try:
                self._json(cached_response(stale=True, max_age=30))
            except Exception:  # noqa: BLE001
                self._json({"ok": False, "error": "抓取失败：%s" % (error or "未知错误")}, 502)

    def do_POST(self):
        if self._api_path() != "/api/config":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0 or length > 1_000_000:
                raise ValueError("配置内容过大")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("配置必须是 JSON 对象")
            current = load_config(CONFIG)
            candidate = dict(current)
            candidate.update(payload)
            normalized = validate_config(candidate)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
            return
        except Exception:  # noqa: BLE001
            self._json({"ok": False, "error": "配置读取或 JSON 解析失败"}, 400)
            return

        groups_changed = normalized["groups"] != current["groups"]
        try:
            if os.path.exists(CONFIG):
                shutil.copy2(CONFIG, CONFIG + ".bak")
            _atomic_json(CONFIG, normalized)
        except OSError as exc:
            self._json({"ok": False, "error": "写入配置失败：%s" % str(exc)[:120]}, 500)
            return

        if groups_changed:
            try:
                subprocess.Popen([sys.executable, FETCH, "--force"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 cwd=BASE, start_new_session=True)
            except OSError:
                pass
        self._json({"ok": True,
                    "tickers": sum(len(group["tickers"]) for group in normalized["groups"]),
                    "fetch_interval_secs": normalized["fetch_interval_secs"],
                    "groups_changed": groups_changed})


def main():
    config = load_config(CONFIG)
    port = config["www_port"]
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
