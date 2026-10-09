#!/usr/bin/env python3
"""market-glance fetcher: Yahoo Finance -> data/quotes.json + data/klines/<SYM>.json.

只干一件事：拉行情，写 JSON。不做任何计算、不推送、不发通知。
纯标准库，零依赖。由 systemd timer 每 5 分钟调用一次。
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001
    ET = timezone(timedelta(hours=-4))

BASE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def kline_filename(symbol):
    return symbol.replace("^", "_").replace(".", "_") + ".json"


def fetch_candles(sym, interval, rng):
    """拉 Yahoo chart 接口，返回 (candles, meta)。
    candles 为 [ts, o, h, l, c, v] 列表（ts 为秒级时间戳），meta 为原样返回的元信息。
    """
    enc = urllib.parse.quote(sym, safe="")
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?interval=%s&range=%s&includePrePost=true" % (enc, interval, rng))
    d = get(url)
    r = d["chart"]["result"][0]
    m = r["meta"]
    ts = r["timestamp"] or []
    q = r["indicators"]["quote"][0]
    vol = q.get("volume") or []
    candles = []
    for i, tt in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if o is None or h is None or l is None or c is None:
            continue
        v = vol[i] if i < len(vol) and vol[i] is not None else 0
        candles.append([tt, round(o, 2), round(h, 2), round(l, 2), round(c, 2), int(v)])
    return candles, m


def fetch_one(sym, name, group):
    """拉单个 ticker，返回 quote dict；失败抛异常。"""
    candles, m = fetch_candles(sym, "5m", "2d")
    ts = [c[0] for c in candles]
    # 前收：上一个常规交易时段收盘价（昨日美东 16:00 前最后一根），
    # chartPreviousClose 在含盘前数据时不可靠，不用它。
    midnight_et = datetime.now(ET).replace(hour=0, minute=0, second=0, microsecond=0)
    yday_close_ts = int(midnight_et.timestamp()) - 8 * 3600  # 昨日 16:00 ET
    day_start_ts = int(midnight_et.timestamp())
    prev = None
    closes = [c[4] for c in candles]
    for i in range(len(ts) - 1, -1, -1):
        if ts[i] <= yday_close_ts and closes[i]:
            prev = closes[i]
            break
    if prev is None:  # 周末/假日兜底：今日 00:00 ET 之前最后一根
        for i in range(len(ts) - 1, -1, -1):
            if ts[i] < day_start_ts and closes[i]:
                prev = closes[i]
                break
    if prev is None:
        prev = m.get("chartPreviousClose") or m.get("previousClose")
    last = closes[-1] if closes else None
    chg = (last / prev - 1) * 100 if (last and prev) else None
    return {
        "symbol": sym, "name": name, "group": group,
        "price": round(last, 2) if last is not None else None,
        "chg_pct": round(chg, 2) if chg is not None else None,
        "prev_close": prev,
    }, candles


def main():
    cfg = json.load(open(os.path.join(BASE, "config.json")))
    data_dir = os.path.join(BASE, "data")
    kl_dir = os.path.join(data_dir, "klines")
    os.makedirs(kl_dir, exist_ok=True)

    # 上次成功的数据：本轮失败时保留旧值（标 stale），不拿 null 覆盖
    prev_quotes = {}
    pq_path = os.path.join(data_dir, "quotes.json")
    if os.path.exists(pq_path):
        try:
            prev_quotes = {q["symbol"]: q for q in json.load(open(pq_path))["quotes"]}
        except Exception:  # noqa: BLE001
            pass

    quotes = []
    now = int(time.time())
    for group in cfg["groups"]:
        for t in group["tickers"]:
            sym = t["symbol"]
            name, gname = t.get("name", sym), group["name"]
            err = None
            quote = None
            for attempt in (1, 2):
                try:
                    quote, candles = fetch_one(sym, name, gname)
                    break
                except Exception as e:  # noqa: BLE001
                    err = str(e)[:120]
                    if "429" in err and attempt == 1:
                        time.sleep(30)  # 限流退避后重试一次（出口 IP 是共享的，温柔一点）
                    else:
                        break
            if quote is not None:
                quote["stale"] = False
                quote["last_success_at"] = now
                quote.pop("stale_since", None)
                quotes.append(quote)
                json.dump({"symbol": sym, "candles": candles},
                          open(os.path.join(kl_dir, kline_filename(sym)), "w"))
            else:
                # 失败时保留最后一次成功值（连续失败也不丢），标 stale + stale_since
                old = prev_quotes.get(sym)
                if old and old.get("price") is not None:
                    old = dict(old)
                    old["name"], old["group"] = name, gname
                    old["stale"] = True
                    old.setdefault("stale_since", now)
                    quotes.append(old)
                else:
                    quotes.append({
                        "symbol": sym, "name": name, "group": gname,
                        "price": None, "chg_pct": None, "error": err,
                    })
            time.sleep(5.0)  # 轻 pacing，别触发限流（出口 IP 是共享的，Yahoo 对突发很敏感）

    json.dump({"updated": int(time.time()),
               "anomaly_threshold_pct": cfg.get("anomaly_threshold_pct", 3.0),
               "quotes": quotes},
              open(os.path.join(data_dir, "quotes.json"), "w"))
    ok = sum(1 for x in quotes if x["price"] is not None)
    print("ok: %d/%d tickers" % (ok, len(quotes)))


if __name__ == "__main__":
    main()
