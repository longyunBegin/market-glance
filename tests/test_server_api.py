import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


ROOT = Path(__file__).resolve().parents[1]


class ServerApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tempdir.name) / "config.json"
        self.config_path.write_text((ROOT / "config.example.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.original_config = server.CONFIG
        server.CONFIG = str(self.config_path)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.CONFIG = self.original_config
        self.tempdir.cleanup()

    def test_config_round_trip_and_interval_validation(self):
        with urlopen(self.base_url + "/api/config") as response:
            current = json.load(response)
        self.assertEqual(current["fetch_interval_secs"], 300)
        current["fetch_interval_secs"] = 60
        current["anomaly_threshold_pct"] = 4.5
        request = Request(self.base_url + "/api/config", data=json.dumps(current).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request) as response:
            saved = json.load(response)
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["fetch_interval_secs"], 60)
        with urlopen(self.base_url + "/api/config") as response:
            updated = json.load(response)
        self.assertEqual(updated["anomaly_threshold_pct"], 4.5)
        self.assertEqual(updated["fetch_interval_secs"], 60)

        current["fetch_interval_secs"] = 5
        invalid = Request(self.base_url + "/api/config", data=json.dumps(current).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(HTTPError) as error:
            urlopen(invalid)
        self.assertEqual(error.exception.code, 400)

    def test_market_status_endpoint_returns_calendar_fields(self):
        with urlopen(self.base_url + "/api/market-status") as response:
            status = json.load(response)
        self.assertIn("label", status)
        self.assertIn("class", status)
        self.assertIn("countdown", status)


if __name__ == "__main__":
    unittest.main()
