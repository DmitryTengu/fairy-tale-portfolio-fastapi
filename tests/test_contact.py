import unittest

import contact


class ValidateTests(unittest.TestCase):
    def test_ok(self):
        data, err = contact.validate({"name": "  Анна ", "contact": "a@b.by", "message": "Привет!\nКак дела?"})
        self.assertIsNone(err)
        self.assertEqual(data["name"], "Анна")
        self.assertIn("\n", data["message"])

    def test_honeypot(self):
        self.assertEqual(contact.validate({"name": "a", "contact": "b", "message": "c", "website": "spam"}), (None, "spam"))

    def test_empty_and_wrong_type(self):
        self.assertEqual(contact.validate({"name": "", "contact": "b", "message": "c"})[1], "empty_fields")
        self.assertEqual(contact.validate([])[1], "bad_request")
        self.assertEqual(contact.validate({"name": 5, "contact": "b", "message": "c"})[1], "empty_fields")

    def test_header_injection_is_removed(self):
        data, _ = contact.validate({"name": "Имя\r\nBcc: evil@x.com", "contact": "a@b.by", "message": "m"})
        self.assertNotIn("\n", data["name"])
        self.assertNotIn("\r", data["name"])

    def test_length_limits(self):
        data, _ = contact.validate({"name": "n" * 1000, "contact": "c" * 1000, "message": "m" * 10000})
        self.assertLessEqual(len(data["name"]), contact.MAX_NAME)
        self.assertLessEqual(len(data["message"]), contact.MAX_MESSAGE)


class MessageTests(unittest.TestCase):
    CFG = {"from": "site@x.by", "to": "artist@x.by"}

    def test_reply_to_only_for_real_email(self):
        msg = contact.build_message(self.CFG, {"name": "A", "contact": "a@b.by", "message": "m"})
        self.assertEqual(msg["Reply-To"], "a@b.by")
        msg = contact.build_message(self.CFG, {"name": "A", "contact": "@telegram_name", "message": "m"})
        self.assertIsNone(msg["Reply-To"])


class LimiterTests(unittest.TestCase):
    def test_per_ip_and_total(self):
        lim = contact.ContactLimiter(per_ip=2, window=600, total=3, total_window=3600)
        self.assertEqual([lim.allow("a", now=0) for _ in range(3)], [True, True, False])
        self.assertTrue(lim.allow("b", now=1))
        self.assertFalse(lim.allow("c", now=2))   # общий потолок сайта
        self.assertTrue(lim.allow("a", now=4000))  # окна истекли


if __name__ == "__main__":
    unittest.main()
