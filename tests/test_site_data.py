import tempfile
import unittest
from pathlib import Path
from unittest import mock

import site_data


class ImagesTests(unittest.TestCase):
    def make(self, names, manifest=None):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        for n in names:
            (root / n).parent.mkdir(parents=True, exist_ok=True)
            (root / n).write_bytes(b"x")
        with mock.patch.object(site_data, "IMAGES_DIR", root), \
             mock.patch.object(site_data, "_load_manifest", return_value=manifest or {}):
            return site_data.Images()

    def test_prefers_webp_and_ignores_case(self):
        img = self.make(["portfolio1.webp", "portfolio1-m.webp", "portfolio1.JPG"])
        self.assertEqual(img("Portfolio1.jpg"), "/static/images/portfolio1.webp")
        self.assertEqual(img.m("portfolio1.jpg"), "/static/images/portfolio1-m.webp")

    def test_falls_back_to_original_and_to_name(self):
        img = self.make(["only.jpg"])
        self.assertEqual(img("only.jpg"), "/static/images/only.jpg")
        self.assertEqual(img.m("only.jpg"), "/static/images/only.jpg")
        self.assertEqual(img("missing.jpg"), "/static/images/missing.jpg")
        self.assertFalse(img.exists("missing.jpg"))

    def test_width_height_attrs(self):
        img = self.make(["a.webp", "a-m.webp"], manifest={"a-m.webp": [1600, 900]})
        self.assertEqual(str(img.attrs("a.jpg")), 'width="1600" height="900"')
        self.assertEqual(str(img.attrs("nothing.jpg")), "")

    def test_characters_in_subfolder(self):
        img = self.make(["characters/cub.webp"])
        self.assertEqual(img("characters/cub.webp"), "/static/images/characters/cub.webp")


class GameSettingsTests(unittest.TestCase):
    def test_default_batch_is_five(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(site_data.game_state([])["per_wave"], 5)

    def test_batch_size_setting_and_old_names(self):
        for env, value, expected in (("STICKER_BATCH", "3", 3), ("GAME_PER_WAVE", "4", 4), ("GAME_PER_DAY", "6", 6),
                                     ("STICKER_BATCH", "abc", 5), ("STICKER_BATCH", "0", 5), ("STICKER_BATCH", "13", 5),
                                     ("STICKER_BATCH", "12", 12)):
            with mock.patch.dict("os.environ", {env: value}, clear=True):
                self.assertEqual(site_data.game_state([])["per_wave"], expected, (env, value))

    def test_day_gate_on_by_default_and_can_be_switched_off(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertTrue(site_data.game_state([])["day_gate"])
        for value in ("0", "false", "OFF", "no"):
            with mock.patch.dict("os.environ", {"STICKER_DAY_GATE": value}, clear=True):
                self.assertFalse(site_data.game_state([])["day_gate"], value)
        with mock.patch.dict("os.environ", {"STICKER_DAY_GATE": "1"}, clear=True):
            self.assertTrue(site_data.game_state([])["day_gate"])

    def test_game_state_has_server_time(self):
        state = site_data.game_state([])
        self.assertGreater(state["server_now"], 1_700_000_000_000)


class LoaderTests(unittest.TestCase):
    def test_heroes_from_folder_and_optional_description(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            chars = root / "characters"
            chars.mkdir()
            (chars / "fox.webp").write_bytes(b"x")
            (chars / "owl.webp").write_bytes(b"x")
            manifest = root / "characters.json"
            manifest.write_text('[{"image": "characters/owl.webp", "name": "Сова", "about": "Любит чай"}]', encoding="utf-8")
            with mock.patch.object(site_data, "CHARACTERS_DIR", chars), mock.patch.object(site_data, "MANIFEST", manifest):
                result = site_data.load_characters()
        self.assertEqual([c["name"] for c in result], ["Сова", "Fox"])
        self.assertEqual(result[0]["about"], "Любит чай")
        self.assertEqual(result[1]["about"], "")


class DataTests(unittest.TestCase):
    def test_no_latin_letter_in_cyrillic_title(self):
        for book in site_data.BOOKS:
            self.assertNotIn("Lис", book["title"])

    def test_game_state(self):
        game = site_data.game_state(site_data.load_characters())
        self.assertEqual(game["total"], len(game["roster"]))
        self.assertGreaterEqual(game["per_wave"], 1)


if __name__ == "__main__":
    unittest.main()
