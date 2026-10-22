"""Отправка сообщений из формы связи на почту художницы.

Настройки берутся из переменных окружения или из файла .env рядом с main.py
(см. .env.example). Если почта не настроена, сайт сам предложит отправить
письмо через почтовую программу посетителя. Модуль не зависит от FastAPI.
"""
import os
import re
import smtplib
import ssl
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_NAME, MAX_CONTACT, MAX_MESSAGE = 120, 160, 4000


def load_env_file(path: Path) -> None:
    """Читает простой файл .env (строки KEY=VALUE). Уже заданные переменные не трогает."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(Path(__file__).resolve().parent / ".env")


DEFAULT_CONTACT_EMAIL = "angry.miu@gmail.com"


def contact_email() -> str:
    """Адрес художницы (куда приходят письма). Пусто, если не задан."""
    value = os.environ.get("CONTACT_EMAIL", DEFAULT_CONTACT_EMAIL).strip()
    return value if EMAIL_RE.match(value) else ""


def smtp_config() -> Optional[dict]:
    """Настройки почтового сервера или None, если отправка с сайта не настроена."""
    host, to = os.environ.get("SMTP_HOST", "").strip(), contact_email()
    if not host or not to:
        return None
    security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    if security not in ("starttls", "ssl", "none"):
        security = "starttls"
    default_port = {"starttls": 587, "ssl": 465, "none": 25}[security]
    try:
        port = int(os.environ.get("SMTP_PORT", default_port))
    except ValueError:
        port = default_port
    user = os.environ.get("SMTP_USER", "").strip()
    return {
        "host": host, "port": port, "security": security, "user": user,
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from": os.environ.get("CONTACT_FROM", "").strip() or user or to,
        "to": to,
    }


def _clean(value, limit: int, multiline: bool) -> str:
    if not isinstance(value, str):
        return ""
    value = CONTROL_RE.sub("", value).strip()
    if not multiline:
        value = " ".join(value.split())
    return value[:limit]


def validate(data) -> tuple:
    """Проверяет данные формы. Возвращает (чистые данные, None) или (None, код ошибки)."""
    if not isinstance(data, dict):
        return None, "bad_request"
    if data.get("website"):          # скрытое поле-ловушка для ботов
        return None, "spam"
    cleaned = {
        "name": _clean(data.get("name"), MAX_NAME, False),
        "contact": _clean(data.get("contact"), MAX_CONTACT, False),
        "message": _clean(data.get("message"), MAX_MESSAGE, True),
    }
    if not all(cleaned.values()):
        return None, "empty_fields"
    return cleaned, None


def build_message(cfg: dict, data: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Сообщение с сайта от " + data["name"][:60]
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    if EMAIL_RE.match(data["contact"]):
        msg["Reply-To"] = data["contact"]   # ответ уйдёт сразу автору сообщения
    msg.set_content(
        f"Новое сообщение с сайта.\n\n"
        f"Имя или издательство: {data['name']}\n"
        f"Как связаться: {data['contact']}\n\n"
        f"Сообщение:\n{data['message']}\n"
    )
    return msg


def send(cfg: dict, data: dict) -> None:
    msg = build_message(cfg, data)
    if cfg["security"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
    with server:
        if cfg["security"] == "starttls":
            server.starttls(context=ssl.create_default_context())
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"])
        server.send_message(msg)


class ContactLimiter:
    """Не больше N сообщений с одного адреса за период, и общий потолок на весь сайт."""

    def __init__(self, per_ip: int = 3, window: float = 600, total: int = 30, total_window: float = 3600):
        self.per_ip, self.window = per_ip, window
        self.total, self.total_window = total, total_window
        self._ip = defaultdict(deque)
        self._all = deque()

    def allow(self, ip: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._ip[ip]
        while q and now - q[0] > self.window:
            q.popleft()
        while self._all and now - self._all[0] > self.total_window:
            self._all.popleft()
        if len(q) >= self.per_ip or len(self._all) >= self.total:
            return False
        q.append(now)
        self._all.append(now)
        return True
