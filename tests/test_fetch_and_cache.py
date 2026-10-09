import os
import tempfile
import unittest

from fetch import fetch_is_due
from server import cache_is_fresh


class FetchIntervalTests(unittest.TestCase):
    def test_fetch_interval_uses_configured_seconds(self):
        self.assertTrue(fetch_is_due(300, None, now=1000))
        self.assertFalse(fetch_is_due(300, 800, now=1000))
        self.assertTrue(fetch_is_due(300, 700, now=1000))
        self.assertTrue(fetch_is_due(60, 900, now=1000))


class KlineCacheTests(unittest.TestCase):
    def test_cache_ttl_expires_and_missing_files_are_stale(self):
        with tempfile.NamedTemporaryFile(delete=False) as stream:
            path = stream.name
        try:
            os.utime(path, (1000, 1000))
            self.assertTrue(cache_is_fresh(path, 900, now=1899))
            self.assertFalse(cache_is_fresh(path, 900, now=1900))
            self.assertFalse(cache_is_fresh(path, 900, now=999))
        finally:
            os.unlink(path)
        self.assertFalse(cache_is_fresh(path, 60, now=1000))


if __name__ == "__main__":
    unittest.main()
