import re
import unittest
from pathlib import Path


HTML = Path(__file__).resolve().parents[1] / "index.html"


class FrontendGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_user_text_is_rendered_through_text_content_and_values(self):
        self.assertIn("name.textContent = q.name", self.html)
        self.assertIn("heading.textContent=groupName", self.html)
        self.assertIn("name.value=group.name||''", self.html)
        self.assertNotRegex(self.html, re.compile(r"innerHTML\s*=\s*`[^`]*\$\{"))

    def test_chart_requests_expire_and_ignore_old_responses(self):
        self.assertIn("expiresAt>Date.now()", self.html)
        self.assertIn("if(requestId!==chartRequestId) return", self.html)
        self.assertIn("setInterval(()=>showChart(curSym,curTf),60000)", self.html)
        self.assertIn("&refresh=1", self.html)

    def test_layout_has_tablet_and_phone_breakpoints(self):
        self.assertIn('@media (min-width: 701px) and (max-width: 1120px)', self.html)
        self.assertIn("@media (max-width: 700px)", self.html)
        self.assertIn("main > .panel.mobile-active", self.html)
        self.assertIn('grid-template-areas: "overview chart anomalies"', self.html)
        self.assertIn("minmax(560px, 1fr) minmax(260px, 300px)", self.html)
        self.assertIn('grid-template-areas: "overview chart" "anomalies anomalies"', self.html)

    def test_watchlist_keeps_quotes_visible_even_when_repeated_elsewhere(self):
        self.assertIn("displayQuotes.forEach(q=>{", self.html)
        self.assertIn("const anomalies = displayQuotes.filter(q=>!BENCHMARKS.has(q.symbol)", self.html)
        self.assertNotIn("if(excluded.has(q.symbol)) return;", self.html)
        self.assertIn("观察池暂无可显示的代码", self.html)

    def test_tape_includes_every_configured_watchlist_ticker(self):
        self.assertIn('aria-label="观察池行情带"', self.html)
        self.assertIn("const tapeQuotes = displayQuotes;", self.html)
        self.assertNotIn("const TAPE_BASES", self.html)
        self.assertIn("配置观察池代码后会显示在这里", self.html)

    def test_extended_session_prices_are_distinguished_from_regular_close_change(self):
        self.assertIn("function quoteSessionLabel(q)", self.html)
        self.assertIn("q.price_session==='pre'?'盘前'", self.html)
        self.assertIn("q.price_session==='after'?'盘后'", self.html)
        self.assertIn("return session?session+'价':''", self.html)
        self.assertIn("q.price_timestamp", self.html)
        self.assertIn("quoteDate!==today?'上次':''", self.html)
        self.assertIn("quoteSessionPrefix(q)+' '+formatPercent(q.extended_chg_pct)", self.html)
        self.assertIn("q.extended_chg_pct", self.html)
        self.assertIn("较收盘", self.html)
        self.assertIn("(sessionLabel?'收盘 ':'')+formatPercent(change)", self.html)

    def test_configured_tickers_remain_visible_without_quote_snapshot(self):
        self.assertIn("function dashboardQuotes()", self.html)
        self.assertIn("pending:true", self.html)
        self.assertIn("if(q.pending)", self.html)
        self.assertIn("const configResponse=await fetch('/api/config'", self.html)
        self.assertIn("configuredGroups=pendingConfig.groups", self.html)
        self.assertIn("行情快照尚未生成；已显示已保存的观察代码", self.html)

    def test_selection_and_chart_title_follow_successful_data(self):
        self.assertIn("function ensureSelectedSymbol()", self.html)
        self.assertIn("if(requestId!==chartRequestId) return", self.html)
        show_chart = self.html[self.html.index("async function showChart"):self.html.index("function bindClicks")]
        self.assertLess(show_chart.index("syncChartHeader(symbol)"), show_chart.index("const data=await loadKlines"))
        self.assertIn("loadedChartSymbol=symbol; loadedChartTimeframe=timeframe", show_chart)
        self.assertIn("$('chart').setAttribute('aria-busy','true')", self.html)
        self.assertIn("图表数据未更新：'+symbol", self.html)
        self.assertIn("if(selectionChanged||timeframeChanged||providerChanged)clearChartData()", show_chart)
        self.assertIn("不会显示其他标的的 K 线", show_chart)
        self.assertNotIn("图中仍显示", show_chart)
        self.assertIn("function clearChartData()", self.html)

    def test_watchlist_search_sort_and_anomaly_direction_filters(self):
        self.assertIn('id="watchSearch" type="search"', self.html)
        self.assertIn('id="watchSort" aria-label="观察池排序"', self.html)
        self.assertIn("const searchable=[q.symbol,q.name||'',q.group||'']", self.html)
        self.assertIn("sortMode==='pct-desc'", self.html)
        self.assertIn('data-anomaly-filter="all"', self.html)
        self.assertIn('data-anomaly-filter="up"', self.html)
        self.assertIn('data-anomaly-filter="down"', self.html)
        self.assertIn("anomalyFilter==='up'?anomalies.filter(q=>q.chg_pct>0)", self.html)
        self.assertIn("anomalyFilter==='down'?anomalies.filter(q=>q.chg_pct<0)", self.html)

    def test_chart_has_selected_name_quote_and_color_legend(self):
        self.assertIn('id="cname"', self.html)
        self.assertIn("$('cname').textContent=quote?[quote.name,providerLabel(quote.provider)].filter(Boolean).join(' · '):''", self.html)
        self.assertIn("font-variant-numeric: tabular-nums; font-family: ui-monospace", self.html)
        self.assertIn('aria-label="K 线图例"', self.html)
        self.assertIn('K 线数据更新时间 ', self.html)
        self.assertIn("syncChartHeader(curSym)", self.html)

    def test_chart_offers_daily_and_latest_intraday_session_only(self):
        chart_periods = re.findall(r'<button class="tfbtn[^\"]*" data-tf="([^\"]+)"', self.html)
        self.assertEqual(chart_periods, ["5m", "1d"])
        self.assertIn('data-tf="5m" title="休市时显示最近一个有数据的交易日">当日走势</button>', self.html)
        self.assertIn('data-tf="1d">日K</button>', self.html)
        self.assertIn("function latestIntradaySession(bars)", self.html)
        self.assertIn("bars.filter(bar=>etDateKey(bar.time)===latestDate)", self.html)
        self.assertIn("走势日期 ", self.html)
        self.assertIn('id="sessionCoverage"', self.html)
        self.assertIn("04:00–09:30 ET", self.html)
        self.assertIn("function setPremarketStatus(bars,timeframe,state='loaded',provider=providerForChartSymbol(curSym))", self.html)
        self.assertIn("Alpaca IEX 的盘前从 08:00 ET 开始", self.html)
        self.assertIn("const hasToday=bars.some(bar=>etDateKey(bar.time)===today)", self.html)

    def test_mobile_tabs_and_config_editor_validate_before_preview(self):
        self.assertIn('data-panel-tab="overview"', self.html)
        self.assertIn('data-panel-tab="anomalies"', self.html)
        self.assertIn('data-panel-tab="chart"', self.html)
        self.assertIn('data-panel-tab="overview" class="on" aria-pressed="true">观察池</button>', self.html)
        self.assertIn('data-panel-tab="anomalies" aria-pressed="false">异动</button>', self.html)
        self.assertIn('data-panel-tab="chart" aria-pressed="false">图表</button>', self.html)
        self.assertIn('id="manageWatchlist" aria-label="新增分组或代码"', self.html)
        self.assertIn("$('manageWatchlist').onclick=()=>openCfg('watchlist')", self.html)
        self.assertIn('data-cfg-pane="watchlist"', self.html)
        self.assertIn('data-cfg-pane="settings"', self.html)
        self.assertIn('class="cfg-guide"><strong>新增观察代码</strong>', self.html)
        self.assertIn('添加分组并命名', self.html)
        self.assertIn('预览后确认保存', self.html)
        self.assertIn("group.querySelector('.ticker-symbol').focus()", self.html)
        self.assertIn(r"const symbolPattern=/^[A-Z0-9^.=\-]{1,12}$/", self.html)
        self.assertIn("代码重复：", self.html)
        self.assertIn("变更预览", self.html)
        self.assertIn("waitForUpdatedQuotes(pendingConfig", self.html)
        self.assertNotIn("element.querySelector('textarea')", self.html)

    def test_sources_are_auto_routed_and_disclosed_per_ticker(self):
        self.assertIn("function providerLabel(provider)", self.html)
        self.assertIn("source.textContent = providerLabel(q.provider); source.title", self.html)
        self.assertIn("item.append(symbol, source, price)", self.html)
        self.assertIn("q.price==null?'失败':'旧'", self.html)
        self.assertIn("每只代码都可单独选择", self.html)
        self.assertIn("自动模式下普通美股代码默认走 IEX", self.html)
        self.assertIn("provider_mode:row.querySelector('.ticker-provider').value", self.html)
        self.assertIn("providerForChartSymbol(symbol)", self.html)
        self.assertNotIn('id="cfgProvider"', self.html)
        self.assertIn("APCA_API_KEY_ID / APCA_API_SECRET_KEY", self.html)
        self.assertIn("不是全市场 SIP 汇总", self.html)
        self.assertIn("数据源变更：", self.html)
        self.assertNotIn("Twelve Data", self.html)

    def test_desktop_panel_controls_and_theme_preferences_are_persistent(self):
        self.assertIn('data-layout-toggle="overview"', self.html)
        self.assertIn('data-layout-toggle="anomalies"', self.html)
        self.assertIn('id="themeToggle"', self.html)
        self.assertIn("localStorage.getItem(UI_PREF_KEY)", self.html)
        self.assertIn("localStorage.setItem(UI_PREF_KEY", self.html)
        self.assertIn('<option value="light">浅色模式</option>', self.html)
        self.assertIn('<option value="dark">深色模式</option>', self.html)
        self.assertIn('<option value="system">系统模式</option>', self.html)
        self.assertIn("['light','dark','system'].includes(saved.theme)", self.html)
        self.assertIn("window.matchMedia('(prefers-color-scheme: dark)')", self.html)
        self.assertIn("function effectiveTheme()", self.html)
        self.assertIn("systemThemeMedia.addEventListener('change',handleSystemThemeChange)", self.html)
        self.assertIn('[data-theme="dark"] body', self.html)
        self.assertIn('title="主题模式会自动保存到此浏览器"', self.html)
        self.assertIn("localStorage.setItem(UI_PREF_KEY,JSON.stringify(uiPreferences))", self.html)
        self.assertIn("main.hide-overview", self.html)
        self.assertIn("main.hide-anomalies", self.html)

    def test_dark_theme_uses_pure_black_surfaces_and_chart(self):
        self.assertIn('[data-theme="dark"] { color-scheme: dark; background: #000; }', self.html)
        self.assertIn('[data-theme="dark"] body { background: #000; color: #ededed; }', self.html)
        self.assertIn('[data-theme="dark"] header, [data-theme="dark"] .tape, [data-theme="dark"] .panel, [data-theme="dark"] .modal { background: #000;', self.html)
        self.assertIn("? {background:'#000000'", self.html)

    def test_market_session_is_dynamic_and_displays_new_york_time(self):
        self.assertIn('id="marketClock"', self.html)
        self.assertIn("timeZone:'America/New_York'", self.html)
        self.assertIn("fmtEtClock.format(new Date(status.as_of))", self.html)
        self.assertIn("setInterval(updateMarketStage,30000)", self.html)
        self.assertNotIn("盘前哨", self.html)


if __name__ == "__main__":
    unittest.main()
