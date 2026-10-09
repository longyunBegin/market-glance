#!/usr/bin/env python3
"""market-glance web 服务器。

两件事，各司其职：
  1. 静态文件服务（页面 + data/*.json，同源）
  2. /api/config 接口：页面上的 ⚙️ 配置弹窗读写 config.json，
     保存后立刻在后台跑一次 fetch.py（新代码不用等 5 分钟）

纯标准库，零依赖。由 market-glance-www.service 启动。
"""
import http.server
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config.json")
FETCH = os.path.join(BASE, "fetch.py")

# fetch_candles 复用抓取逻辑（纯标准库，无额外依赖）
sys.path.insert(0, BASE)
from fetch import fetch_candles, kline_filename  # noqa: E402

# 允许的代码字符：字母数字 + ^ . - =（覆盖 ^VIX、SIVE.ST、BRK-B 这类）
SYM_RE = re.compile(r"^[A-Z0-9^.\-=]{1,12}$")
MAX_GROUPS = 10
MAX_TICKERS_PER_GROUP = 30
MAX_TICKERS_TOTAL = 60

# K 线周期：tf -> (yahoo interval, yahoo range, 本地缓存文件名后缀, 缓存秒数)
TF_MAP = {
    "5m": ("5m", "2d", "", None),        # 5 分钟走定时任务写的文件
    "15m": ("15m", "1mo", "_15m", 900),  # 15 分钟走按需抓取，缓存 15 分钟
    "1d": ("1d", "1y", "_1d", 3600),     # 日 K 走按需抓取，缓存 1 小时
}


def validate(payload):
    """校验并规范化前端提交的配置，返回 groups 列表；不合法抛 ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("配置必须是 JSON 对象")
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("至少需要一个分组")
    if len(groups) > MAX_GROUPS:
        raise ValueError("分组太多（最多 %d 个）" % MAX_GROUPS)
    out, total, seen = [], 0, set()
    for g in groups:
        if not isinstance(g, dict):
            raise ValueError("分组格式错误")
        name = str(g.get("name", "")).strip() or "未命名"
        tickers = g.get("tickers")
        if not isinstance(tickers, list) or not tickers:
            raise ValueError("分组「%s」至少需要一个代码" % name[:20])
        if len(tickers) > MAX_TICKERS_PER_GROUP:
            raise ValueError("分组「%s」代码太多（最多 %d 个）" % (name[:20], MAX_TICKERS_PER_GROUP))
        ts = []
        for t in tickers:
            if not isinstance(t, dict):
                raise ValueError("代码格式错误")
            sym = str(t.get("symbol", "")).strip().upper()
            if not SYM_RE.match(sym):
                raise ValueError("代码格式不对：%r（只允许字母、数字、^ . - =）" % t.get("symbol"))
            if sym in seen:
                raise ValueError("代码重复：%s" % sym)
            seen.add(sym)
            disp = str(t.get("name", "")).strip() or sym
            ts.append({"symbol": sym, "name": disp[:24]})
        out.append({"name": name[:24], "tickers": ts})
        total += len(ts)
    if total > MAX_TICKERS_TOTAL:
        raise ValueError("代码总数太多（最多 %d 个），Yahoo 会限流" % MAX_TICKERS_TOTAL)
    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def log_message(self, *a):
        pass  # 日志走 journal 就够了，不刷屏

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_path(self):
        return self.path.split("?", 1)[0]

    def do_GET(self):
        path = self._api_path()
        if path == "/api/config":
            try:
                self._json(json.load(open(CONFIG, encoding="utf-8")))
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "error": str(e)[:200]}, 500)
            return
        if path == "/api/klines":
            self._serve_klines()
            return
        return super().do_GET()

    def _serve_klines(self):
        """K 线按需接口：/api/klines?symbol=AAOI&tf=5m|15m|1d。

        5m 直接读定时任务写的文件；15m / 1d 按需抓 Yahoo，写缓存文件，
        缓存期内直接读文件，不打扰 Yahoo（限流时也尽量少请求）。
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        sym = (qs.get("symbol") or [""])[0].strip().upper()
        tf = (qs.get("tf") or ["5m"])[0]
        if not SYM_RE.match(sym):
            self._json({"ok": False, "error": "代码格式不对"}, 400)
            return
        if tf not in TF_MAP:
            self._json({"ok": False, "error": "周期只支持 5m / 15m / 1d"}, 400)
            return
        interval, rng, suffix, ttl = TF_MAP[tf]
        kl_dir = os.path.join(BASE, "data", "klines")
        fp = os.path.join(kl_dir, kline_filename(sym)[:-5] + suffix + ".json")
        # 5m 固定读定时任务文件；其他周期缓存期内读缓存
        if ttl is not None and os.path.exists(fp):
            try:
                age = time.time() - os.path.getmtime(fp)
                if age < ttl:
                    self._json({"ok": True, "symbol": sym, "tf": tf,
                                "candles": json.load(open(fp, encoding="utf-8"))["candles"],
                                "cached": True})
                    return
            except Exception:  # noqa: BLE001
                pass
        if ttl is None:
            if os.path.exists(fp):
                try:
                    self._json({"ok": True, "symbol": sym, "tf": tf,
                                "candles": json.load(open(fp, encoding="utf-8"))["candles"],
                                "cached": True})
                    return
                except Exception:  # noqa: BLE001
                    pass
            self._json({"ok": False, "error": "暂无该代码的 5 分钟数据"}, 404)
            return
        # 缓存过期或没有：按需抓一次 Yahoo
        err = None
        for attempt in (1, 2):
            try:
                candles, _meta = fetch_candles(sym, interval, rng)
                if not candles:
                    raise ValueError("Yahoo 返回空数据")
                os.makedirs(kl_dir, exist_ok=True)
                json.dump({"symbol": sym, "tf": tf, "candles": candles},
                          open(fp, "w", encoding="utf-8"))
                self._json({"ok": True, "symbol": sym, "tf": tf,
                            "candles": candles, "cached": False})
                return
            except Exception as e:  # noqa: BLE001
                err = str(e)[:120]
                if "429" in err and attempt == 1:
                    time.sleep(10)
        # 抓失败：有旧缓存就给旧的（标 stale），没有就报错，前端保持原图
        if os.path.exists(fp):
            try:
                self._json({"ok": True, "symbol": sym, "tf": tf,
                            "candles": json.load(open(fp, encoding="utf-8"))["candles"],
                            "cached": True, "stale": True})
                return
            except Exception:  # noqa: BLE001
                pass
        self._json({"ok": False, "error": "抓取失败：%s" % (err or "未知错误")}, 502)

    def do_POST(self):
        if self._api_path() != "/api/config":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            groups = validate(payload)
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)
            return
        except Exception:  # noqa: BLE001
            self._json({"ok": False, "error": "JSON 解析失败"}, 400)
            return
        cur = json.load(open(CONFIG, encoding="utf-8"))
        try:
            os.replace(CONFIG, CONFIG + ".bak")  # 旧配置留一份，出问题可回滚
        except FileNotFoundError:
            pass
        cur["groups"] = groups
        tmp = CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG)
        # 后台立刻抓一次新表，页面不用等下一个 5 分钟周期
        subprocess.Popen([sys.executable, FETCH],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         cwd=BASE, start_new_session=True)
        self._json({"ok": True, "tickers": sum(len(g["tickers"]) for g in groups)})


def main():
    port = 8090
    try:
        port = int(json.load(open(CONFIG, encoding="utf-8")).get("www_port", 8090))
    except Exception:  # noqa: BLE001
        pass
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
