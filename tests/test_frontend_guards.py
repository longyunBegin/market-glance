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

    def test_quote_panels_partition_benchmarks_and_anomalies(self):
        self.assertIn("const excluded = new Set(benchmarks.map(q=>q.symbol))", self.html)
        self.assertIn("anomalies.forEach(q=>excluded.add(q.symbol))", self.html)


if __name__ == "__main__":
    unittest.main()
