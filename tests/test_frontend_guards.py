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
        self.assertIn("@media (max-width: 1120px)", self.html)
        self.assertIn("@media (max-width: 700px)", self.html)
        self.assertIn("main > .panel.mobile-active", self.html)

    def test_quote_panels_partition_benchmarks_and_anomalies(self):
        self.assertIn("const excluded = new Set(tapeQuotes.map(q=>q.symbol))", self.html)
        self.assertIn("anomalies.forEach(q=>excluded.add(q.symbol))", self.html)

    def test_selection_and_chart_title_follow_successful_data(self):
        self.assertIn("if(!quotes.some(q=>q.symbol===curSym)) curSym=", self.html)
        self.assertIn("if(requestId!==chartRequestId) return", self.html)
        self.assertLess(self.html.index("series.setData(bars)"), self.html.index("$('csym').textContent=symbol"))
        self.assertIn("$('chart').setAttribute('aria-busy','true')", self.html)
        self.assertIn("K 线加载失败（", self.html)

    def test_mobile_tabs_and_config_editor_validate_before_preview(self):
        self.assertIn('data-panel-tab="overview"', self.html)
        self.assertIn('data-panel-tab="anomalies"', self.html)
        self.assertIn('data-panel-tab="chart"', self.html)
        self.assertIn(r"const symbolPattern=/^[A-Z0-9^.=\-]{1,12}$/", self.html)
        self.assertIn("代码重复：", self.html)
        self.assertIn("变更预览", self.html)
        self.assertIn("waitForUpdatedQuotes(pendingConfig", self.html)
        self.assertNotIn("element.querySelector('textarea')", self.html)

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

    def test_market_session_is_dynamic_and_displays_new_york_time(self):
        self.assertIn('id="marketClock"', self.html)
        self.assertIn("timeZone:'America/New_York'", self.html)
        self.assertIn("fmtEtClock.format(new Date(status.as_of))", self.html)
        self.assertIn("setInterval(updateMarketStage,30000)", self.html)
        self.assertNotIn("盘前哨", self.html)


if __name__ == "__main__":
    unittest.main()
