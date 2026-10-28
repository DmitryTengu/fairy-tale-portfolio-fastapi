"""Защита сервера: проверка источника WebSocket, адрес посетителя за прокси, лимиты подключений.

Модуль не зависит от FastAPI, поэтому его легко проверять отдельно (см. tests/).
"""
import ipaddress
import os
from collections import defaultdict
from typing import Iterable, Mapping, Optional
from urllib.parse import urlsplit


def _split_env(name: str, default: str = "") -> list:
    return [p.strip() for p in os.environ.get(name, default).split(",") if p.strip()]


def trusted_proxies() -> set:
    """Адреса прокси (Nginx и т.п.), которым можно верить в заголовке X-Forwarded-For.
    Настраивается в .env: TRUSTED_PROXIES=127.0.0.1,::1"""
    return set(_split_env("TRUSTED_PROXIES", "127.0.0.1,::1"))


def client_ip(headers: Mapping, peer: Optional[str], trusted: Optional[Iterable[str]] = None) -> str:
    """Настоящий адрес посетителя. За прокси request.client.host всегда адрес самого прокси,
    поэтому лимиты считались бы на всех посетителей сразу."""
    trusted = set(trusted if trusted is not None else trusted_proxies())
    peer = peer or "unknown"
    if peer not in trusted:
        return peer
    forwarded = headers.get("x-forwarded-for", "")
    chain = [p.strip() for p in forwarded.split(",") if p.strip()]
    for addr in reversed(chain):            # идём справа налево, пропуская свои прокси
        if addr in trusted:
            continue
        try:
            ipaddress.ip_address(addr)
        except ValueError:
            continue
        return addr
    return peer


def origin_allowed(origin: Optional[str], host: Optional[str], extra: Optional[Iterable[str]] = None) -> bool:
    """Подключаться к WebSocket можно только со страниц этого же сайта (или из ALLOWED_ORIGINS).
    Браузер всегда присылает Origin; без него подключаются скрипты, поэтому такие запросы отклоняем
    (разрешить: WS_ALLOW_NO_ORIGIN=1)."""
    if not origin:
        return os.environ.get("WS_ALLOW_NO_ORIGIN", "").strip() == "1"
    netloc = urlsplit(origin).netloc.lower()
    if not netloc:
        return False
    if host and netloc == host.strip().lower():
        return True
    allowed = {a.lower() for a in (extra if extra is not None else _split_env("ALLOWED_ORIGINS"))}
    return netloc in allowed or origin.lower() in allowed


class ConnectionLimiter:
    """Не больше N одновременных подключений с одного адреса и M на весь сайт."""

    def __init__(self, per_ip: int = 8, total: int = 300):
        self.per_ip, self.total = per_ip, total
        self._by_ip = defaultdict(int)
        self._all = 0

    def acquire(self, ip: str) -> bool:
        if self._all >= self.total or self._by_ip[ip] >= self.per_ip:
            return False
        self._by_ip[ip] += 1
        self._all += 1
        return True

    def active(self, ip: str) -> int:
        return self._by_ip.get(ip, 0)

    def release(self, ip: str) -> None:
        if self._by_ip.get(ip, 0) > 0:
            self._by_ip[ip] -= 1
            self._all = max(0, self._all - 1)
            if self._by_ip[ip] == 0:
                del self._by_ip[ip]
