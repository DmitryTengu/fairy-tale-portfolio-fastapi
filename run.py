"""Запуск сервера с безопасными настройками для публикации: python run.py

Что здесь важно (в обычной команде `uvicorn main:app` этого нет):
  * ws_max_size: WebSocket-сообщение больше 64 КБ отклоняется ещё до разбора (по умолчанию было 16 МБ);
  * proxy_headers: за Nginx / на Render настоящий адрес посетителя берётся из X-Forwarded-For;
  * порт и адрес берутся из переменных окружения HOST и PORT (так просят многие хостинги).
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        ws_max_size=65536,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
