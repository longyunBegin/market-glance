# Market Glance 盘前哨

个人行情看板：查看跨市场行情、观察池、异动扫描和 K 线。桌面端为三栏布局，窄屏会自动改为双栏或单栏。基准行情带、观察池和异动区会分配显示标的，避免同一标的在多个区重复出现。

## 功能与架构

```text
Yahoo Finance（非官方接口，约 1～3 分钟延迟）
    │
fetch.py ── 读取 config.json 的抓取间隔 ──→ data/quotes.json + data/klines/*.json
    │                                             ↑
    └── systemd timer 每分钟检查一次；未到配置间隔时不访问行情源
                                                  │
server.py ── 页面服务 + /api/config + /api/klines + /api/market-status
    │
index.html ── 同源单页看板（lightweight-charts 内联，无外部运行时依赖）
```

- **K 线**：5 分钟、15 分钟、日线；包括盘前盘后、成交量、MA20/50 和前收参考线。浏览器 K 线缓存会过期，刷新按钮可跳过缓存；过期请求不会覆盖后来选中的标的。
- **市场状态**：按美东时区识别周末、NYSE 常规假日、盘前/盘中/盘后和常见提前收市日。特殊临时休市不在年度规则表内。
- **安全渲染**：可编辑分组名和显示名通过 DOM 文本/表单属性渲染，不拼接到 HTML。
- **失败回退**：抓取失败时保留最后成功行情并标记旧数据。

## 安装

需要 Linux、Python 3.9+ 和 systemd，无第三方 Python 依赖。建议将仓库放在不含空格的目录中；安装脚本会从当前仓库目录生成 systemd 单元，不依赖某个固定用户或路径。

```bash
git clone https://github.com/longyunBegin/market-glance.git
cd market-glance
cp config.example.json config.json
# 按需编辑 config.json
sudo bash systemd/install.sh
```

默认网页服务只监听 `127.0.0.1`，可在本机打开 `http://127.0.0.1:8090`。需要从另一台机器访问时，建议配置 SSH 隧道；如需直接暴露网络端口，应自行配置防火墙和访问控制。

### 可选 SSH 隧道

安装脚本默认不会启用隧道。需要隧道时，先在系统本机配置命令：

```bash
sudo install -m 600 /dev/null /etc/default/market-glance-tunnel
sudoedit /etc/default/market-glance-tunnel
```

文件内容示例（把地址和参数改成自己的环境）：

```ini
TUNNEL_CMD="ssh -N -T -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -R 8090:localhost:8090 user@your-host"
```

之后执行 `sudo ENABLE_TUNNEL=1 bash systemd/install.sh`。隧道断开后脚本会重试；不再需要时可运行 `sudo systemctl disable --now market-glance-tunnel.service`。

## 配置

`config.json` 是每台机器自己的配置，已加入 Git 忽略规则；仓库只保存 `config.example.json`。页面右上角齿轮可编辑分组、代码、显示名、异动阈值和抓取间隔。

```json
{
  "anomaly_threshold_pct": 3.0,
  "fetch_interval_secs": 300,
  "www_port": 8090,
  "groups": [
    {"name": "观察池", "tickers": [{"name": "显示名", "symbol": "AAPL"}]}
  ]
}
```

- `anomaly_threshold_pct`：异动区阈值，范围 `0.1`～`50`。
- `fetch_interval_secs`：实际行情抓取间隔，范围 `60`～`86400` 秒；timer 每分钟唤醒一次，脚本依据该值决定是否访问 Yahoo。
- `www_port`：网页服务端口，范围 `1024`～`65535`。若手动修改端口，需重启网页服务：`sudo systemctl restart market-glance-www.service`。
- `symbol` 使用 Yahoo Finance 代码，例如美股 `AAPL`、斯德哥尔摩 `SIVE.ST`、指数 `^NDX` / `^IXIC`、美债 `^TNX`、波动率 `^VIX`。

页面保存观察池后会立即触发一次抓取；只改阈值或抓取间隔不会额外访问行情源。也可手动强制抓取：

```bash
python3 fetch.py --force
```

## 数据说明

- 涨跌幅相对上一个常规收盘价；Yahoo 的含盘前数据时 `chartPreviousClose` 不可靠，因此优先从 K 线计算前收。
- Yahoo 对突发请求敏感；抓取脚本使用 5 秒 pacing，并在 429 时退避重试。
- 15 分钟 K 线缓存 15 分钟，日线缓存 1 小时；5 分钟 K 线由定时抓取任务更新，浏览器每 30 秒检查一次文件。
- 图表库为 TradingView 开源 [lightweight-charts](https://github.com/tradingview/lightweight-charts) v4.2.0（Apache-2.0），已内联到 `assets/`。

## systemd 服务

| 单元 | 作用 |
|---|---|
| `market-glance-fetch.timer` | 每分钟检查是否到达配置中的抓取间隔 |
| `market-glance-www.service` | 页面和 API 服务 |
| `market-glance-tunnel.service` | 可选 SSH 隧道，默认不启用 |
| `market-glance-healthcheck.timer` | 每 10 分钟检查网页端口并在无响应时重启服务 |

迁移或重建安装目录后，在新目录重新运行 `bash systemd/install.sh` 即可重新生成带有实际路径的 unit。代理环境变量由安装脚本注入 systemd manager 环境，不会写入仓库文件。

## 测试

运行标准库测试：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖配置边界、抓取间隔门控、K 线缓存 TTL、安装路径生成、前端安全渲染和市场假日/时段计算。

## 目录结构

```text
market-glance/
├── index.html          单页看板
├── fetch.py            行情抓取及间隔门控
├── server.py           静态页面和 JSON API
├── config_model.py     配置默认值与校验
├── market_calendar.py  美股常规假日与交易时段
├── config.example.json 配置示例
├── assets/             内联图表库
├── data/               运行时行情数据（Git 忽略）
├── systemd/            unit 模板与安装脚本
├── tests/              回归测试
├── healthcheck.sh      本机网页健康检查
└── tunnel.sh           可选 SSH 隧道
```

## License

MIT
