# Market Glance 美股行情看板

个人美股行情看板，覆盖常规交易时段及盘前、盘后行情：查看观察池、异动扫描、K 线和跨市场参考。休市、隔夜、周末和假日继续显示最近完整交易日的收盘涨跌幅；若有盘前或盘后价格，会单独标注，并显示相对最近常规收盘价的变化。桌面端为“观察池—中央图表—异动”三栏；平板端优先展示观察池与图表，异动栏可收起；手机端可在观察池、异动和图表间切换。观察池支持按代码、名称或分组搜索，以及按代码或涨跌幅排序；异动榜可按全部、涨幅或跌幅筛选。顶部行情带按观察池配置顺序显示全部代码，可直接点击切换图表。

![Market Glance 深色模式界面](docs/screenshot.png)

> 截图展示深色模式、收盘涨跌幅与盘后价格的区分；报价为界面演示样例，不代表实时行情。

## 功能与架构

```text
行情源（默认 Yahoo Finance；可选 Alpaca IEX）
    │
fetch.py ── 读取 config.json 的数据源与抓取间隔 ──→ data/quotes.json + data/klines/*.json
    │                                             ↑
    └── systemd timer 每分钟检查一次；未到配置间隔时不访问行情源
                                                  │
server.py ── 页面服务 + /api/config + /api/klines + /api/market-status
    │
index.html ── 同源单页看板（lightweight-charts 内联，无外部运行时依赖）
```

- **K 线**：提供日K和当日走势（5 分钟粒度）；当日走势只显示最近一个有数据的交易日，周末、休市时自然显示上一交易日，并标注图表日期。图表包括成交量、MA20/50 和前收参考线。换标时标题和报价立即跟随选择，图表显示加载状态；若暂时保留旧图，会明确标出旧图所属标的，失败时提示“图表数据未更新”，不会把旧图伪装成新标的。过期请求不会覆盖后来选中的标的。
- **市场状态**：按纽约当地时间识别周末、NYSE 常规假日、盘前/盘中/盘后和常见提前收市日，每 30 秒更新一次并显示纽约时间；倒计时指向下一个真实时段。市场状态与行情快照的最后更新时间分开展示。特殊临时休市不在年度规则表内。
- **涨跌幅口径**：盘中按实时成交价相对最近常规收盘价计算；盘前、盘后及休市时按最近完整交易日收盘价对前一交易日收盘价计算。扩展时段价格及其相对常规收盘的变化会单独标注。
- **主题与布局**：可在页面顶部选择浅色、深色或系统模式；主题和桌面面板显示偏好自动保存在当前浏览器。
- **安全渲染**：可编辑分组名和显示名通过 DOM 文本/表单属性渲染，不拼接到 HTML。
- **失败回退**：抓取失败时保留最后成功行情并标记旧数据。
- **数据源**：默认使用 Yahoo Finance；可在设置中切换 Alpaca IEX，支持 IEX 最新成交及 5 分钟、日线 K 线。Alpaca IEX 只含 IEX 单一交易所的成交，并非 SIP 全市场汇总。

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

### 从旧版升级

旧提交曾将 `config.json` 纳入 Git。升级到忽略本地配置的版本前，先在仓库目录备份并从工作区恢复旧的跟踪版本，避免本地观察列表阻止 `git pull` 或被删除：

```bash
backup="../market-glance-config.$(date +%Y%m%d%H%M%S).json"
cp config.json "$backup"
git checkout -- config.json
git pull
cp "$backup" config.json
sudo bash systemd/install.sh
```

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

`config.json` 是每台机器自己的配置，已加入 Git 忽略规则；仓库只保存 `config.example.json`。可在观察池标题旁点“新增”，直接进入分组与代码编辑；配置窗口会按步骤提示创建分组、填写代码，并在保存前校验重复/无效代码、预览差异。右上角齿轮用于调整异动阈值和抓取间隔。行情源按代码格式自动路由，行情列表会标出每个代码本轮使用的来源。观察池保存后页面会持续显示更新状态，直到新行情快照实际到达。

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
- 行情源自动路由：普通字母/数字美股代码（如 `AAPL`）使用 Alpaca IEX；指数代码（如 `^NDX`）及含市场后缀或其他标点的代码（如 `SIVE.ST`）使用 Yahoo Finance。旧配置中的 `market_data_provider` 字段会被忽略。
- `fetch_interval_secs`：实际行情抓取间隔，范围 `60`～`86400` 秒；timer 每分钟唤醒一次，脚本依据该值决定是否访问行情源。
- `www_port`：网页服务端口，范围 `1024`～`65535`。若手动修改端口，需重启网页服务：`sudo systemctl restart market-glance-www.service`。
- Alpaca IEX 仅适用于其支持的美国股票代码，且数据为 IEX feed、不是 SIP 全市场汇总；路由到 Alpaca 的代码需要有效凭据。Yahoo Finance 使用非官方接口。

使用 Alpaca IEX 前，先在服务器上创建仅 root 可读的凭据文件；不要把 API 密钥放进 `config.json` 或提交到 Git：

```bash
sudo install -m 600 /dev/null /etc/default/market-glance-fetch
sudoedit /etc/default/market-glance-fetch
```

文件内容（填入 Alpaca API dashboard 的数据密钥）：

```ini
APCA_API_KEY_ID=your_key_id
APCA_API_SECRET_KEY=your_secret_key
```

安装/更新 systemd 单元后，执行以下命令让网页服务和抓取服务重新读取凭据；符合格式的普通美股代码将自动使用 **Alpaca IEX**，无需手动选择数据源：

```bash
sudo systemctl daemon-reload
sudo systemctl restart market-glance-www.service
sudo systemctl start market-glance-fetch.service
```

抓取器通过 Alpaca 官方股票行情 API 显式请求 `feed=iex`。更多说明见 [Alpaca Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)、[最新成交 API](https://docs.alpaca.markets/us/reference/stocklatesttrades-1) 和 [历史 K 线 API](https://docs.alpaca.markets/us/reference/stockbars)。

页面保存观察池后会立即触发一次抓取；只改阈值或抓取间隔不会额外访问行情源。也可手动强制抓取；使用 Alpaca 时请确保当前 shell 已设置 `APCA_API_KEY_ID` 和 `APCA_API_SECRET_KEY`，systemd 服务会从上面的凭据文件读取：

```bash
python3 fetch.py --force
```

## 数据说明

- 常规时段内的涨跌幅以实时价对最近完整常规收盘价计算；盘前、盘后及休市期间保持最近完整交易日的收盘价对前一交易日收盘价变化，不会因跨夜、周末或假日归零。盘前/盘后价格如有显示，会标出扩展时段，并另列其相对最近常规收盘价的变化。每个代码的现价、涨跌基准和 K 线均来自同一行情源；Alpaca IEX 的最新价格取最新 IEX 成交，K 线和收盘基准也仅基于 IEX 数据。请求失败时仅复用同一来源的旧报价并标记过期，不会静默切换数据源。
- Yahoo 对突发请求敏感；抓取脚本使用 5 秒 pacing，并在 429 时退避重试。
- IEX 是单一交易所行情，成交量/报价可能少于 SIP 汇总；标普或纳指等指数符号不属于股票 IEX 行情。
- 15 分钟 K 线缓存 15 分钟，日线缓存 1 小时；5 分钟 K 线由定时抓取任务更新，浏览器每 30 秒检查一次文件。
- 图表库为 TradingView 开源 [lightweight-charts](https://github.com/tradingview/lightweight-charts) v4.2.0（Apache-2.0），已内联到 `assets/`。

## systemd 服务

| 单元 | 作用 |
|---|---|
| `market-glance-fetch.timer` | 每分钟检查是否到达配置中的抓取间隔 |
| `market-glance-www.service` | 页面和 API 服务 |
| `market-glance-tunnel.service` | 可选 SSH 隧道，默认不启用 |
| `market-glance-healthcheck.timer` | 每 10 分钟检查网页端口并在无响应时重启服务 |

迁移或重建安装目录后，在新目录重新运行 `bash systemd/install.sh` 即可重新生成带有实际路径的 unit。代理环境变量由安装脚本注入 systemd manager 环境，不会写入仓库文件。抓取服务会可选读取 `/etc/default/market-glance-fetch`；该文件由运维者以 `0600` 权限创建，避免密钥进入仓库。

## 测试

运行标准库测试：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖配置边界、抓取间隔门控、K 线缓存 TTL、安装路径生成、前端安全渲染、市场假日/时段计算，以及周末、假日和盘前盘后的收盘涨跌幅口径。

## 目录结构

```text
market-glance/
├── index.html          单页看板
├── fetch.py            行情抓取及间隔门控
├── alpaca_data.py     Alpaca IEX 行情 API 适配器
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
