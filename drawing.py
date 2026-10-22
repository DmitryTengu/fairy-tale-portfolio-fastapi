"""Проверка мазков, которые приходят от браузеров по WebSocket.

Без этой проверки любой посетитель мог бы прислать на сервер что угодно:
гигантские числа, мусор вместо цвета, тысячи сообщений в секунду.
Модуль не зависит от FastAPI, поэтому его легко тестировать отдельно.
"""
import json
import math
import re
import time
from collections import deque
from typing import Optional

# Допустимый цвет: #rgb, #rrggbb или rgb()/rgba() с числами
COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}"
    r"|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*\d*\.?\d+\s*)?\))$"
)

MAX_MESSAGE_LEN = 400      # символов в одном сообщении
MAX_X = 10_000             # px, шире экрана не бывает
MAX_Y = 100_000            # px, высота всей страницы со скроллом
MIN_SIZE, MAX_SIZE = 1.0, 30.0
MAX_MESSAGES_PER_SECOND = 240
MAX_CUT_REMOVE = 30        # линий, которые можно убрать одним сообщением ластика
MAX_CUT_ADD = 180          # новых кусочков в одном сообщении ластика
MAX_CUT_LEN = 40_000       # символов в сообщении ластика
ADD_PER_REMOVED = 6        # сколько кусочков разрешено на одну убранную линию

BRUSHES = ("w", "o")       # w: акварель, o: масло

LID_RE = re.compile(r"^[a-z0-9]{4,24}$")    # id одного отрезка линии
CID_RE = re.compile(r"^[a-z0-9]{8,40}$")    # id посетителя (хранится у него в браузере)


def valid_cid(value) -> bool:
    return isinstance(value, str) and CID_RE.match(value) is not None


def _number(value, low: float, high: float) -> Optional[float]:
    """Число в пределах [low, high] или None (bool и NaN/inf не принимаем)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < low or value > high:
        return None
    return float(value)


def parse_line(raw: str) -> Optional[dict]:
    """Разбирает сообщение клиента. Возвращает чистый словарь мазка или None."""
    if not isinstance(raw, str) or len(raw) > MAX_MESSAGE_LEN:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    line = {
        "prevX": _number(data.get("prevX"), 0, MAX_X),
        "prevY": _number(data.get("prevY"), 0, MAX_Y),
        "currX": _number(data.get("currX"), 0, MAX_X),
        "currY": _number(data.get("currY"), 0, MAX_Y),
        "size": _number(data.get("size"), MIN_SIZE, MAX_SIZE),
    }
    color = data.get("color")
    if any(v is None for v in line.values()):
        return None
    if not isinstance(color, str) or not COLOR_RE.match(color):
        return None
    line["color"] = color
    lid = data.get("lid", "")
    line["lid"] = lid if isinstance(lid, str) and LID_RE.match(lid) else ""
    brush = data.get("brush", "w")
    line["brush"] = brush if brush in BRUSHES else "w"
    return line


def parse_cut(raw: str) -> Optional[tuple]:
    """Сообщение ластика: {"cut": {"remove": [id, ...], "add": [линия, ...]}}.

    Ластик стирает как в Paint: старые отрезки убираются, а их уцелевшие части
    добавляются заново. Возвращает (список id на удаление, список новых линий)
    или None, если это не такое сообщение."""
    if not isinstance(raw, str) or len(raw) > MAX_CUT_LEN or '"cut"' not in raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    cut = data.get("cut") if isinstance(data, dict) else None
    if not isinstance(cut, dict) or not isinstance(cut.get("remove"), list) or not isinstance(cut.get("add"), list):
        return None
    remove = [x for x in cut["remove"] if isinstance(x, str) and LID_RE.match(x)][:MAX_CUT_REMOVE]
    add = []
    for item in cut["add"][:MAX_CUT_ADD]:
        line = parse_line(json.dumps(item)) if isinstance(item, dict) else None
        if line and line["lid"]:
            add.append(line)
    return remove, add


def is_clear(raw: str) -> bool:
    """Сообщение «стереть все мои рисунки»: {"clear": true}."""
    if not isinstance(raw, str) or len(raw) > 100 or '"clear"' not in raw:
        return False
    try:
        data = json.loads(raw)
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("clear") is True


class RateLimiter:
    """Не больше N сообщений в секунду с одного подключения."""

    def __init__(self, limit: int = MAX_MESSAGES_PER_SECOND):
        self.limit = limit
        self._stamps: deque = deque()

    def allow(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        while self._stamps and now - self._stamps[0] > 1.0:
            self._stamps.popleft()
        if len(self._stamps) >= self.limit:
            return False
        self._stamps.append(now)
        return True
