import os
import unittest
from unittest import mock

from security import ConnectionLimiter, client_ip, origin_allowed


class ClientIpTests(unittest.TestCase):
    def test_direct_visitor_cannot_fake_header(self):
        self.assertEqual(client_ip({"x-forwarded-for": "6.6.6.6"}, "1.2.3.4", trusted=["127.0.0.1"]), "1.2.3.4")

    def test_behind_proxy(self):
        self.assertEqual(client_ip({"x-forwarded-for": "8.8.8.8"}, "127.0.0.1", trusted=["127.0.0.1"]), "8.8.8.8")

    def test_chain_skips_own_proxies_and_garbage(self):
        headers = {"x-forwarded-for": "9.9.9.9, evil-text, 10.0.0.5, 127.0.0.1"}
        self.assertEqual(client_ip(headers, "127.0.0.1", trusted=["127.0.0.1", "10.0.0.5"]), "9.9.9.9")

    def test_no_peer(self):
        self.assertEqual(client_ip({}, None, trusted=[]), "unknown")


class OriginTests(unittest.TestCase):
    def test_same_site(self):
        self.assertTrue(origin_allowed("https://site.by", "site.by", extra=[]))
        self.assertTrue(origin_allowed("http://127.0.0.1:8000", "127.0.0.1:8000", extra=[]))

    def test_other_site_and_garbage(self):
        self.assertFalse(origin_allowed("https://evil.com", "site.by", extra=[]))
        self.assertFalse(origin_allowed("null", "site.by", extra=[]))
        self.assertFalse(origin_allowed("https://site.by.evil.com", "site.by", extra=[]))

    def test_extra_allowed(self):
        self.assertTrue(origin_allowed("https://www.site.by", "site.by", extra=["www.site.by"]))

    def test_missing_origin(self):
        with mock.patch.dict(os.environ, {"WS_ALLOW_NO_ORIGIN": ""}):
            self.assertFalse(origin_allowed(None, "site.by", extra=[]))
        with mock.patch.dict(os.environ, {"WS_ALLOW_NO_ORIGIN": "1"}):
            self.assertTrue(origin_allowed(None, "site.by", extra=[]))


class LimiterTests(unittest.TestCase):
    def test_per_ip_and_total(self):
        lim = ConnectionLimiter(per_ip=2, total=3)
        self.assertEqual([lim.acquire("a") for _ in range(3)], [True, True, False])
        self.assertTrue(lim.acquire("b"))
        self.assertFalse(lim.acquire("c"))        # общий потолок
        lim.release("a")
        self.assertTrue(lim.acquire("c"))

    def test_release_cleans_up(self):
        lim = ConnectionLimiter(per_ip=1, total=5)
        lim.acquire("a"); lim.release("a"); lim.release("a")
        self.assertEqual(lim.active("a"), 0)


if __name__ == "__main__":
    unittest.main()
