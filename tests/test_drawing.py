import json
import unittest

from drawing import RateLimiter, is_clear, parse_cut, parse_line, valid_cid

GOOD = {"prevX": 10, "prevY": 20, "currX": 30, "currY": 40, "size": 5, "color": "#0d9488", "lid": "abc123", "brush": "o"}


class ParseLineTests(unittest.TestCase):
    def test_valid_line(self):
        line = parse_line(json.dumps(GOOD))
        self.assertEqual(line["brush"], "o")
        self.assertEqual(line["lid"], "abc123")

    def test_rejects_garbage(self):
        for raw in ("", "not json", "[]", "null", json.dumps({**GOOD, "color": "red; drop"}),
                    json.dumps({**GOOD, "size": 9999}), json.dumps({**GOOD, "prevX": float("inf")}),
                    json.dumps({**GOOD, "prevX": True}), json.dumps({**GOOD, "currY": -1})):
            self.assertIsNone(parse_line(raw), raw)

    def test_too_long_message(self):
        self.assertIsNone(parse_line(json.dumps({**GOOD, "pad": "x" * 500})))

    def test_unknown_brush_falls_back(self):
        self.assertEqual(parse_line(json.dumps({**GOOD, "brush": "evil"}))["brush"], "w")

    def test_bad_lid_is_dropped(self):
        self.assertEqual(parse_line(json.dumps({**GOOD, "lid": "bad id!"}))["lid"], "")


class CutAndClearTests(unittest.TestCase):
    def test_cut_ok(self):
        raw = json.dumps({"cut": {"remove": ["abc123", "zz"], "add": [GOOD]}})
        remove, add = parse_cut(raw)
        self.assertEqual(remove, ["abc123"])      # "zz" короче 4 символов и не принимается
        self.assertEqual(len(add), 1)

    def test_cut_requires_lid_in_added_lines(self):
        raw = json.dumps({"cut": {"remove": [], "add": [{**GOOD, "lid": ""}]}})
        self.assertEqual(parse_cut(raw), ([], []))

    def test_not_a_cut(self):
        self.assertIsNone(parse_cut(json.dumps(GOOD)))
        self.assertIsNone(parse_cut("{bad"))

    def test_clear(self):
        self.assertTrue(is_clear('{"clear": true}'))
        self.assertFalse(is_clear('{"clear": 1}'))
        self.assertFalse(is_clear("x" * 200))


class OtherTests(unittest.TestCase):
    def test_cid(self):
        self.assertTrue(valid_cid("abcdef12"))
        for bad in ("", "short", "UPPERCASE1", "a b c d e f", None, 12345678):
            self.assertFalse(valid_cid(bad), bad)

    def test_rate_limiter(self):
        rl = RateLimiter(limit=3)
        self.assertEqual([rl.allow(now=0.0) for _ in range(4)], [True, True, True, False])
        self.assertTrue(rl.allow(now=2.0))        # через секунду окно очистилось


if __name__ == "__main__":
    unittest.main()
