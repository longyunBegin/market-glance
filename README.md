# Market Glance 盘前哨

个人行情看板：一眼看完跨市场行情、观察池异动扫描、一键切换 K 线。

![三栏布局](docs/screenshot.png)

三栏布局（类似 r/wallstreetbets 的盘前 widget）：

- **跨市场一眼**（左栏）：观察池 + 基准指数，价格、涨跌幅、相对上个常规收盘价的涨跌
- **异动扫描**（中栏）：按绝对涨跌幅阈值（默认 3%，页面可改）筛出异动标的
- **K 线**（右栏）：点击任意 ticker 切换；支持 5分（近2日）/ 15分（近1月）/ 日K（近1年），含盘前盘后，均线（MA20/50）、成交量、前收参考线

架构三层，各司其职，纯标准库零依赖：

```
Yahoo Finance（非官方接口，延迟约 1~3 分钟）
    │
fetch.py ── 每 5 分钟抓一次 ──→ data/quotes.json + data/klines/*.json
    │（systemd timer 驱动；失败保留最后成功值并标 stale）
server.py ── 静态页面 + /api/config（读写观察列表）+ /api/klines（按需抓 15m/日K 并缓存）
    │
index.html ── 单页三栏看板（lightweight-charts 内联，无外部依赖）
```

## 安装

需要一台 Linux 机器（或云主机 / VM），Python 3.8+ 即可，无其他依赖。

```bash
git clone https://github.com/longyunBegin/market-glance.git
cd market-glance

# 1) 准备配置：复制示例，填上你想看的代码
cp config.example.json config.json

# 2) 装 systemd 服务（抓取 timer + 页面服务 + 健康检查）
bash systemd/install.sh

# 3) 在浏览器打开（默认端口 8090，可在 config.json 改 www_port）
#    http://<你的机器IP>:8090
```

如果你想和作者一样"云主机跑服务、Mac 本地浏览器看"，把页面端口经 SSH 反向隧道映射到桌面机器即可：

```bash
# 在云主机上（隧道断线自动重连）
bash tunnel.sh   # 默认命令按 Tailscale 场景写死，可用 TUNNEL_CMD 环境变量覆盖
# 然后在 Mac 浏览器打开 http://localhost:8090
```

## 配置

观察列表有两种改法：

1. **页面上直接改**：打开页面点右上角 ⚙️，分组 / ticker 都可增删，保存后服务端立刻重抓。
2. **改 config.json**：编辑后等下一轮 5 分钟抓取，或手动 `systemctl start market-glance-fetch.service`。

```json
{
  "anomaly_threshold_pct": 3.0,
  "fetch_interval_secs": 300,
  "www_port": 8090,
  "groups": [
    { "name": "观察池", "tickers": [{ "name": "显示名", "symbol": "AAPL" }] }
  ]
}
```

- `symbol` 是 Yahoo Finance 代码：美股 `AAPL`、斯德哥尔摩 `SIVE.ST`、指数 `^NDX` / `^IXIC`、美债 `^TNX`、波动率 `^VIX`
- `anomaly_threshold_pct`：异动阈值（绝对涨跌幅 ≥ 该值进中栏）
- `fetch_interval_secs`：抓取间隔（秒），timer 按此值调度

## 数据说明

- 数据源：Yahoo Finance 非官方 chart 接口（无需 API key），延迟约 1~3 分钟，含盘前盘后
- 涨跌幅基准：按美东上一个常规交易日 16:00 前最后一根 K 线计算前收（`chartPreviousClose` 在含盘前数据时不可靠，未采用）
- 抓取失败时保留最后一次成功值并标记 `stale`，页面上会灰显并带"旧"标记；连续失败也不会清空
- Yahoo 对突发请求敏感（共享出口 IP 容易 429）：已内置 5 秒 pacing + 429 退避 30 秒重试
- 图表库：TradingView 开源 [lightweight-charts](https://github.com/tradingview/lightweight-charts) v4.2.0（Apache-2.0），已内联到 `assets/`，页面全同源无外部依赖

## 服务清单（systemd）

| 服务 | 作用 |
|---|---|
| `market-glance-fetch.timer` | 每 5 分钟驱动 `fetch.py` 抓行情 |
| `market-glance-www.service` | 页面服务（:8090，静态 + API） |
| `market-glance-tunnel.service` | SSH 反向隧道（可选，桌面本地看时用） |
| `market-glance-healthcheck.timer` | 每 10 分钟自检：:8090 无响应则重启 www |

VM 整体重建后重跑一次 `bash systemd/install.sh` 即可恢复全部服务。

## 目录结构

```
market-glance/
├── index.html          单页看板（前端）
├── fetch.py            行情抓取（stdlib 零依赖）
├── server.py           页面服务 + API（stdlib 零依赖）
├── config.json         观察列表配置（复制 config.example.json 生成）
├── config.example.json 配置示例
├── assets/             内联的 lightweight-charts v4.2.0
├── data/               运行时数据（gitignore，不提交）
├── systemd/            systemd 服务定义 + install.sh
├── healthcheck.sh      健康检查
└── tunnel.sh           SSH 反向隧道（可选）
```

## License

MIT
