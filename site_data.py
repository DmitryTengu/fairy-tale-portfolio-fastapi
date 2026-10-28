"""Данные сайта: работы, книги, герои игры, подбор картинок.

Здесь нет FastAPI, поэтому модуль можно проверять отдельно. Чтобы добавить
героев, не нужно править код: положите PNG с прозрачным фоном в
static/images/characters/ (подробнее в README).
"""
import json
import os
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

from markupsafe import Markup

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "static" / "images"
CHARACTERS_DIR = IMAGES_DIR / "characters"
MANIFEST = BASE_DIR / "characters.json"

MAGAZINE_PORTFOLIO = [
    {"image": "portfolio1.JPG", "title": "Журналы «Матуліна сонейка» и «Заикина библиотека»"},
    {"image": "portfolio2.JPG", "title": "Иллюстрации к книге «Пачастунак для Цмока»"},
    {"image": "portfolio3.JPG", "title": "Иллюстрации к книге «Падарожжа ў Новы Год»"},
    {"image": "merch.jpg", "title": "Открытки, пазлы, стикеры, календари, упаковка", "tall": True},
]

# Блок «Что я рисую»
SERVICES = [
    {"icon": "📚", "title": "Книги и журналы", "text": "Развороты, обложки и персонажи для детских книг и журналов."},
    {"icon": "🧩", "title": "Игры и головоломки", "text": "Задания, викторины и квесты, в которых картинка помогает играть."},
    {"icon": "💌", "title": "Открытки и стикеры", "text": "Серии открыток, стикеры и настольные игры."},
    {"icon": "🎁", "title": "Мерч и упаковка", "text": "Пазлы, коробки, стаканчики и другая упаковка с вашими героями."},
    {"icon": "📅", "title": "Календари", "text": "Тематические календари с иллюстрациями на каждый месяц."},
]

# Как проходит работа
STEPS = [
    {"title": "Задача", "text": "Вы рассказываете, что нужно нарисовать: формат, возраст читателей, сроки."},
    {"title": "Эскиз", "text": "Я показываю композицию и героев, пока всё можно легко поменять."},
    {"title": "Правки", "text": "Обсуждаем детали и дорабатываем рисунок вместе."},
    {"title": "Финал", "text": "Вы получаете готовые файлы в нужном формате."},
]

BOOKS = [
    {
        "title": "Пачастунак для Цмока",
        "subtitle": "Рассмотреть развороты книги",
        "pages": ["tsmok_1.jpg", "tsmok_2.jpg", "tsmok_3.jpg", "tsmok_4.jpg", "tsmok_5.jpg", "tsmok_6.jpg"]
    },
    {
        "title": "Приключения Лисёнка",
        "subtitle": "Серия детских иллюстраций",
        "pages": ["lisenok_1.jpg", "lisenok_2.jpg", "lisenok_3.jpg", "lisenok_4.jpg"]
    },
    {
        "title": "Падарожжа ў Новы Год",
        "subtitle": "Зимняя сказка",
        "pages": ["novigod_1.jpg", "novigod_2.jpg", "novigod_3.jpg", "novigod_4.jpg"]
    }
]

# Герои-заглушки (со смайликами). Используются, только пока нет ни characters.json,
# ни картинок в static/images/characters/.
DEFAULT_CHARACTERS = [
    {"id": "rabbit", "name": "Кролик-хранитель", "book": "Сказочные истории", "emoji": "🐰",
     "image": "char_rabbit.png", "section": "intro", "left": 3, "top": 84, "size": 70, "rot": -8},
    {"id": "tsmok", "name": "Цмок", "book": "Пачастунак для Цмока", "emoji": "🐲",
     "image": "char_tsmok.png", "section": "portfolio", "left": 91, "top": 4, "size": 80, "rot": 6},
    {"id": "lisenok", "name": "Лисёнок", "book": "Приключения Лисёнка", "emoji": "🦊",
     "image": "char_lisenok.png", "section": "gallery", "left": 2, "top": 20, "size": 70, "rot": -6},
    {"id": "owl", "name": "Сова-ночница", "book": "Падарожжа ў Новы Год", "emoji": "🦉",
     "image": "char_owl.png", "section": "gallery", "left": 93, "top": 62, "size": 66, "rot": 8},
    {"id": "hedgehog", "name": "Ёжик", "book": "Приключения Лисёнка", "emoji": "🦔",
     "image": "char_hedgehog.png", "section": "portfolio", "left": 3, "top": 90, "size": 62, "rot": 0},
    {"id": "snowman", "name": "Снеговик", "book": "Падарожжа ў Новы Год", "emoji": "⛄",
     "image": "char_snowman.png", "section": "contacts", "left": 46, "top": 4, "size": 66, "rot": -4},
]

HINTS = {
    "intro": "Дремлет в самом начале страницы",
    "about": "Прячется рядом с рассказом о художнице",
    "services": "Заглядывает в блок «Что я рисую»",
    "portfolio": "Выглядывает среди избранных работ",
    "gallery": "Прячется рядом с книжными проектами",
    "contacts": "Ждёт там, где можно написать художнице",
}

# Места, где могут прятаться герои (раздел, left %, top %). Каждый раз выбираются случайные.
SPOTS = [
    ("intro", 4, 84), ("gallery", 94, 32), ("contacts", 94, 84), ("portfolio", 3, 24),
    ("services", 92, 14), ("gallery", 2, 20), ("contacts", 90, 6), ("gallery", 93, 62),
    ("about", 4, 76), ("services", 3, 82), ("portfolio", 92, 44), ("contacts", 3, 88),
    ("gallery", 4, 88), ("intro", 90, 88), ("about", 60, 90), ("portfolio", 3, 62),
    ("contacts", 88, 58), ("services", 88, 93), ("about", 90, 8), ("gallery", 91, 6),
    ("portfolio", 91, 80), ("contacts", 10, 50), ("services", 40, 3), ("intro", 48, 92),
    ("portfolio", 92, 70), ("services", 3, 30), ("contacts", 92, 40), ("gallery", 3, 60),
    ("intro", 92, 20), ("about", 3, 55), ("portfolio", 4, 45), ("services", 91, 60),
    ("contacts", 4, 60), ("gallery", 93, 25), ("intro", 3, 60), ("about", 93, 70),
    ("services", 50, 4), ("services", 4, 84),
]
ROTATIONS = (-6, 5, -3, 7, 0, -8, 4)
CHAR_EXT = {".png", ".webp"}


def _image_index() -> dict:
    """Все картинки в static/images (включая подпапки): имя в нижнем регистре -> реальное имя."""
    try:
        return {
            p.relative_to(IMAGES_DIR).as_posix().lower(): p.relative_to(IMAGES_DIR).as_posix()
            for p in IMAGES_DIR.rglob("*") if p.is_file()
        }
    except OSError:
        return {}


IMAGES_MANIFEST = IMAGES_DIR / "manifest.json"


def _load_manifest() -> dict:
    """Размеры картинок (создаёт tools/optimize_images.py): имя файла в нижнем регистре -> [ширина, высота]."""
    try:
        data = json.loads(IMAGES_MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class Images:
    """Подбор картинок для шаблона.

    img("portfolio1.jpg")      -> крупная версия (для просмотра на весь экран)
    img.m("portfolio1.jpg")    -> версия для самой страницы (легче)
    img.attrs("portfolio1.jpg")-> width="..." height="..." для тега <img> (страница не «прыгает» при загрузке)

    Имя подбирается без учёта регистра (на Linux portfolio1.JPG и portfolio1.jpg разные файлы).
    Если рядом лежит WebP-версия (её делает tools/optimize_images.py), берётся она.
    """

    def __init__(self):
        self.files = _image_index()
        self.sizes = _load_manifest()

    def _find(self, name: str, mid: bool = False):
        key = str(name).lower()
        stem = key.rsplit(".", 1)[0]
        candidates = ([stem + "-m.webp"] if mid else []) + [stem + ".webp", key]
        for cand in candidates:
            if cand in self.files:
                return self.files[cand]
        return None

    def exists(self, name: str) -> bool:
        return self._find(name) is not None

    def __call__(self, name: str, mid: bool = False) -> str:
        found = self._find(name, mid)
        return "/static/images/" + quote(found or name)

    def m(self, name: str) -> str:
        return self(name, mid=True)

    def attrs(self, name: str, mid: bool = True) -> Markup:
        found = self._find(name, mid)
        size = self.sizes.get(found.lower()) if found else None
        if not size or len(size) != 2:
            return Markup("")
        return Markup('width="%d" height="%d"' % (int(size[0]), int(size[1])))


def make_img_resolver() -> Images:
    return Images()


# Блоки, которые появятся на сайте, как только вы их заполните (пока пусто, блок скрыт).
# Ничего не придумывайте за себя: только то, что правда.
#
# PRICES: ориентиры по стоимости, например
#   {"title": "Обложка книги", "price": "от 300 BYN", "note": "эскиз и 2 правки входят в цену"}
PRICES: list = []
# CLIENTS: издательства, журналы, отзывы заказчиков, например
#   {"name": "Журнал «Матуліна сонейка»", "text": "Короткий отзыв или чем занимались"}
CLIENTS: list = []

def _title(stem: str) -> str:
    text = stem.replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else "Герой"


def _normalize(chars: list) -> list:
    out, seen = [], set()
    for i, raw in enumerate(chars):
        if not isinstance(raw, dict) or not raw.get("image"):
            continue
        c = dict(raw)
        base = str(c.get("id") or Path(c["image"]).stem or f"hero{i}")
        cid, n = base, 2
        while cid in seen:
            cid, n = f"{base}{n}", n + 1
        seen.add(cid)
        section = c.get("section") if c.get("section") in HINTS else "portfolio"
        c.update({
            "id": cid,
            "name": str(c.get("name") or _title(Path(c["image"]).stem)),
            "book": str(c.get("book") or ""),
            "emoji": str(c.get("emoji") or "✨"),
            "about": str(c.get("about") or ""),
            "section": section,
            "left": c.get("left", 50), "top": c.get("top", 50),
            "size": c.get("size", 72), "rot": c.get("rot", 0),
            "hint": str(c.get("hint") or HINTS[section]),
        })
        out.append(c)
    return out


def load_characters() -> list:
    """Герои игры.

    1. Если есть characters.json, герои берутся из него.
    2. Каждая картинка из static/images/characters/, которой нет в списке,
       добавляется сама (имя из названия файла, место подбирается автоматически).
    3. Если нет ни файла, ни картинок, показываются герои-заглушки.
    """
    chars = None
    if MANIFEST.exists():
        try:
            data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            if isinstance(data, list):
                chars = data
            else:
                print("[сайт] characters.json должен быть списком героев, файл пропущен")
        except (OSError, ValueError) as e:
            print(f"[сайт] Не удалось прочитать characters.json: {e}")

    try:
        folder = sorted(p for p in CHARACTERS_DIR.iterdir() if p.suffix.lower() in CHAR_EXT)
    except OSError:
        folder = []

    if chars is None:
        chars = [] if folder else [dict(c) for c in DEFAULT_CHARACTERS]

    # Если в списке есть герой, чьей картинки уже нет в папке (файл удалили), он пропускается:
    # чтобы убрать героя, достаточно удалить его PNG.
    if folder:
        have = {f.name.lower() for f in folder}
        kept = []
        for c in chars:
            name = Path(str(c.get("image", ""))).name.lower() if isinstance(c, dict) else ""
            if name and name not in have and str(c.get("image", "")).lower().startswith("characters/"):
                print(f"[сайт] Герой {c.get('id') or name} пропущен: нет файла {name}")
                continue
            kept.append(c)
        chars = kept

    used = {Path(str(c.get("image", ""))).name.lower() for c in chars if isinstance(c, dict)}
    spot = len(chars)
    for f in folder:
        if f.name.lower() in used:
            continue
        section, left, top = SPOTS[spot % len(SPOTS)]
        chars.append({
            "image": f"characters/{f.name}", "name": _title(f.stem), "section": section,
            "left": left, "top": top, "size": 80, "rot": ROTATIONS[spot % len(ROTATIONS)],
        })
        spot += 1
    return _normalize(chars)


# ---------------------------------------------------------------------
# Игра «найди героев»: герои-стикеры лежат на сайте пятёрками. Нашёл всех пятерых,
# следующие пять появляются на следующий день. Так до конца коллекции.
# Места выбираются случайно в браузере.
# ---------------------------------------------------------------------
GAME_PER_WAVE = 5                    # сколько стикеров лежит на сайте одновременно (пятёрка дня)


def _per_wave() -> int:
    """Размер пятёрки можно изменить в .env: STICKER_BATCH=5 (старые имена GAME_PER_WAVE и GAME_PER_DAY тоже работают)."""
    raw = (os.environ.get("STICKER_BATCH") or os.environ.get("GAME_PER_WAVE") or os.environ.get("GAME_PER_DAY") or "").strip()
    if raw.isdigit() and 1 <= int(raw) <= 12:
        return int(raw)
    return GAME_PER_WAVE


def _day_gate() -> bool:
    """Ждать ли следующего дня между пятёрками. Для проверки на своём компьютере: STICKER_DAY_GATE=0 в .env
    (следующая пятёрка тогда появляется сразу)."""
    raw = (os.environ.get("STICKER_DAY_GATE") or "").strip().lower()
    return raw not in ("0", "false", "no", "off", "нет")


def game_state(chars: list, img=None) -> dict:
    """Данные игры для страницы: порядок героев (по пятёркам), места для случайной раскладки, подсказки."""
    roster = []
    for c in chars:
        item = dict(c)
        if img:
            item["url"] = img(item["image"])
        roster.append(item)
    return {
        "per_wave": _per_wave(), "total": len(roster), "roster": roster,
        "day_gate": _day_gate(),
        # Время сервера: по нему считается «следующий день», смена часов на устройстве не поможет
        "server_now": int(time.time() * 1000),
        "spots": [{"section": sec, "left": l, "top": t} for sec, l, t in SPOTS],
        "hints": HINTS,
    }


def report_missing_images():
    """При запуске пишет в консоль, каких картинок не хватает."""
    images = Images()
    wanted = ["vizitka.jpg", "anna.jpg", "paper.jpg", "fairy.png"]
    wanted += [i["image"] for i in MAGAZINE_PORTFOLIO]
    wanted += [p for b in BOOKS for p in b["pages"]]
    missing = [n for n in wanted if not images.exists(n)]
    if missing:
        print(f"[сайт] Нет картинок в {IMAGES_DIR}: " + ", ".join(missing))
    else:
        print("[сайт] Все основные картинки на месте")
    n = len(load_characters())
    print(f"[сайт] Героев в игре: {n}")
