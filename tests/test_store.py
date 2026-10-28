import os
import tempfile
import unittest

from store import LineStore

LINE = {"prevX": 1, "prevY": 2, "currX": 3, "currY": 4, "color": "#fff", "size": 3, "lid": "abcd1", "brush": "w"}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = LineStore(os.path.join(self.dir.name, "t.db"))

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def test_insert_and_recent_order(self):
        for i in range(5):
            self.store.insert({**LINE, "lid": f"line{i}"}, "cid00001")
        rows = self.store.recent(3)
        self.assertEqual([r[6] for r in rows], ["line2", "line3", "line4"])   # последние три, по порядку рисования

    def test_only_owner_can_delete(self):
        self.store.insert(LINE, "owner001")
        self.assertEqual(self.store.delete_owned("other001", ["abcd1"]), [])
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.delete_owned("owner001", ["abcd1"]), ["abcd1"])
        self.assertEqual(self.store.count(), 0)

    def test_clear_owned_keeps_foreign_lines(self):
        self.store.insert({**LINE, "lid": "mine1"}, "owner001")
        self.store.insert({**LINE, "lid": "other1"}, "other001")
        self.assertEqual(self.store.clear_owned("owner001"), ["mine1"])
        self.assertEqual(self.store.count(), 1)

    def test_purge_old_and_over_limit(self):
        self.store.insert_many([{**LINE, "lid": f"ln{i}x"} for i in range(10)], "cid00001")
        self.assertEqual(self.store.purge(lifetime=1800, max_lines=4), 6)       # сверх лимита
        self.assertEqual(self.store.purge(lifetime=1800, max_lines=100, now=10 ** 10), 4)   # всё устарело
        self.assertEqual(self.store.count(), 0)

    def test_recent_respects_lifetime(self):
        self.store.insert(LINE, "cid00001")
        self.assertEqual(len(self.store.recent(10, lifetime=60)), 1)
        self.assertEqual(len(self.store.recent(10, lifetime=-1)), 0)

    def test_old_database_gets_new_columns(self):
        import sqlite3
        path = os.path.join(self.dir.name, "old.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE lines (id INTEGER PRIMARY KEY AUTOINCREMENT, prevX REAL, prevY REAL, currX REAL, currY REAL, color TEXT, size REAL, timestamp REAL)")
        conn.commit(); conn.close()
        store = LineStore(path)
        store.insert(LINE, "cid00001")
        self.assertEqual(store.count(), 1)
        store.close()


if __name__ == "__main__":
    unittest.main()
