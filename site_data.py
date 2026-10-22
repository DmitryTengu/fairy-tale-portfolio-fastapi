"""Данные сайта: работы, книги, герои игры, подбор картинок.

Здесь нет FastAPI, поэтому модуль можно проверять отдельно. Чтобы добавить
героев, не нужно править код: положите PNG с прозрачным фоном в
static/images/characters/ (подробнее в README).
"""
import json
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "static" / "images"
CHARACTERS_DIR = IMAGES_DIR / "characters"
MANIFEST = BASE_DIR / "characters.json"

MAGAZINE_PORTFOLIO = [
    {"image": "portfolio1.JPG", "title": "Журналы «Матуліна сонейка» и «Заикина библиотека»"},
    {"image": "portfolio2.JPG", "title": "Иллюстрации к книге «Пачастунак для Цмока»"},
    {"image": "portfolio3.JPG", "title": "Иллюстрации к книге «Падарожжа ў Новы Год»"},
    {"image": "portfolio4.JPG", "title": "Проявление заботы"},
    {"image": "shapoklyak_foxes.jpg", "title": "Журнал «Шапокляк»: головоломка с лисятами", "thumb": "t_shapoklyak_foxes.jpg", "tall": True},
    {"image": "shapoklyak_potion.jpg", "title": "Журнал «Шапокляк»: зельеварение", "thumb": "t_shapoklyak_potion.jpg", "tall": True},
    {"image": "gustav.jpg", "title": "Журнал «Шапокляк»: портрет Густава Окрылённого", "thumb": "t_gustav.jpg", "tall": True},
    {"image": "quiz.jpg", "title": "Журнал «Шапокляк»: викторина на воздушном шаре", "thumb": "t_quiz.jpg", "tall": True},
    {"image": "easter_rabbit.jpg", "title": "Пасхальный кролик: рецепт для журнала", "thumb": "t_easter_rabbit.jpg", "tall": True},
    {"image": "cookies.jpg", "title": "Шедевр на скорую руку: рецепт с зайчиками", "thumb": "t_cookies.jpg", "tall": True},
    {"image": "charlotte.jpg", "title": "Царская шарлотка: египетский разворот", "thumb": "t_charlotte.jpg", "tall": True},
    {"image": "merch.jpg", "title": "Открытки, пазлы, стикеры, календари, упаковка", "thumb": "t_merch.jpg", "tall": True},
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
        "title": "Приключения Lисёнка",
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
    {"id": "lisenok", "name": "Лисёнок", "book": "Приключения Lисёнка", "emoji": "🦊",
     "image": "char_lisenok.png", "section": "gallery", "left": 2, "top": 20, "size": 70, "rot": -6},
    {"id": "owl", "name": "Сова-ночница", "book": "Падарожжа ў Новы Год", "emoji": "🦉",
     "image": "char_owl.png", "section": "gallery", "left": 93, "top": 62, "size": 66, "rot": 8},
    {"id": "hedgehog", "name": "Ёжик", "book": "Приключения Lисёнка", "emoji": "🦔",
     "image": "char_hedgehog.png", "section": "portfolio", "left": 3, "top": 90, "size": 62, "rot": 0},
    {"id": "snowman", "name": "Снеговик", "book": "Падарожжа ў Новы Год", "emoji": "⛄",
     "image": "char_snowman.png", "section": "contacts", "left": 46, "top": 4, "size": 66, "rot": -4},
]

HINTS = {
    "intro": "Дремлет в самом начале страницы",
    "portfolio": "Выглядывает среди избранных работ",
    "gallery": "Прячется рядом с книжными проектами",
    "contacts": "Ждёт там, где можно написать художнице",
}

# Места, куда автоматически раскладываются герои из папки characters/
SPOTS = [
    ("intro", 3, 84), ("portfolio", 91, 4), ("gallery", 2, 20), ("gallery", 93, 62),
    ("portfolio", 3, 90), ("contacts", 46, 4), ("intro", 90, 88), ("gallery", 4, 88),
    ("contacts", 90, 8), ("portfolio", 50, 2),
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


def make_img_resolver():
    """Возвращает функцию img(имя) -> адрес картинки.

    Хостинги на Linux различают регистр: portfolio1.JPG и portfolio1.jpg для них разные
    файлы. Из-за этого картинки «не грузятся», хотя на Windows всё работало. Здесь имя
    подбирается без учёта регистра по тому, что реально лежит в static/images.
    """
    files = _image_index()

    def img(name: str) -> str:
        return "/static/images/" + quote(files.get(name.lower(), name))

    return img


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


def report_missing_images():
    """При запуске пишет в консоль, каких картинок не хватает."""
    present = set(_image_index())
    wanted = ["photo.jpg", "paper.jpg", "character1.png"]
    wanted += [i["image"] for i in MAGAZINE_PORTFOLIO]
    wanted += [p for b in BOOKS for p in b["pages"]]
    missing = [n for n in wanted if n.lower() not in present]
    if missing:
        print(f"[сайт] Нет картинок в {IMAGES_DIR}: " + ", ".join(missing))
    else:
        print("[сайт] Все основные картинки на месте")
    n = len(load_characters())
    print(f"[сайт] Героев в игре: {n}")
