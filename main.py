import asyncio
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import contact
from drawing import ADD_PER_REMOVED, RateLimiter, is_clear, parse_cut, parse_line, valid_cid
from security import ConnectionLimiter, client_ip, origin_allowed
from site_data import (
    BOOKS, CLIENTS, IMAGES_DIR, MAGAZINE_PORTFOLIO, PRICES, SERVICES, STEPS, game_state, load_characters,
    make_img_resolver,
    report_missing_images,
)
from store import LineStore

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "drawings.db"
STATIC_DIR = BASE_DIR / "static"

LINE_LIFETIME = 1800      # секунд: мазки старше 30 минут стираются
MAX_LINES_IN_DB = 20000   # страховка от разрастания базы
MAX_LINES_SENT = 6000     # сколько последних мазков отдаём новому посетителю
PURGE_EVERY = 60          # секунд между очистками старых мазков
MAX_BODY = 20_000         # байт: больше форма связи не принимает
IP_MESSAGES_PER_SECOND = 400   # все подключения одного адреса вместе (дополняет лимит на одно подключение)

# Папка static нужна приложению при старте: если её нет, создаём пустую,
# иначе сервер падает с ошибкой, ещё не показав страницу.
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

store = LineStore(DB_PATH)
report_missing_images()


async def purge_loop():
    """Раз в минуту убирает старые мазки (раньше это происходило только при заходе на главную)."""
    while True:
        try:
            await run_in_threadpool(store.purge, LINE_LIFETIME, MAX_LINES_IN_DB)
        except Exception as e:
            print(f"[сайт] Не удалось очистить старые мазки: {e}")
        await asyncio.sleep(PURGE_EVERY)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(purge_loop())
    yield
    task.cancel()
    store.close()


class CachedStatic(StaticFiles):
    """Статика с кешем на 30 дней: картинки не перекачиваются при каждом заходе.
    Для CSS и JS в шаблоне стоит ?v=<время изменения>, поэтому правки подхватываются сразу."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.setdefault("Cache-Control", "public, max-age=2592000")
        return response


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", CachedStatic(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


def site_url(request: Request) -> str:
    """Адрес сайта для canonical, og:url и sitemap. Лучше задать SITE_URL в .env (https://ваш-домен)."""
    env = os.environ.get("SITE_URL", "").strip().rstrip("/")
    return env or str(request.base_url).rstrip("/")


def asset_version(*parts: str) -> str:
    """Номер версии для CSS и JS: время последнего изменения файлов."""
    stamp = 0
    for part in parts:
        try:
            stamp = max(stamp, int((STATIC_DIR / part).stat().st_mtime))
        except OSError:
            pass
    return str(stamp)


# =====================================================================
# МЕНЕДЖЕР ВЕБ-СОКЕТОВ ДЛЯ МГНОВЕННОЙ РАССЫЛКИ ЛИНЕЙНЫХ МАЗКОВ
# =====================================================================
class ConnectionManager:
    SEND_TIMEOUT = 2.0   # секунд: медленный посетитель не должен задерживать остальных

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def _send(self, connection: WebSocket, message: str):
        try:
            await asyncio.wait_for(connection.send_text(message), timeout=self.SEND_TIMEOUT)
        except Exception:
            self.disconnect(connection)

    async def broadcast(self, message: str, exclude: Optional[WebSocket] = None):
        # Рассылаем мазок всем, кроме автора (он уже нарисовал его у себя), одновременно
        targets = [c for c in list(self.active_connections) if c is not exclude]
        if targets:
            await asyncio.gather(*(self._send(c, message) for c in targets))


manager = ConnectionManager()
connection_limiter = ConnectionLimiter()
ip_rates: dict = {}


# =====================================================================
# МАРШРУТЫ И ЭНДПОИНТЫ СЕРВЕРА
# =====================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    img = make_img_resolver()
    game = game_state(load_characters(), img=img)
    base = site_url(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "portfolio": MAGAZINE_PORTFOLIO,
            "books": BOOKS,
            "services": SERVICES,
            "steps": STEPS,
            "prices": PRICES,
            "clients": CLIENTS,
            "game": game,
            "characters": game["roster"],
            "contact_email": contact.contact_email(),
            "year": datetime.now().year,
            "studio": "Bellunium",
            "img": img,
            "canonical": base + "/",
            "og_image": base + img("og.jpg"),
            "ver": asset_version("css/main.css", "js/main.js"),
        },
        # В страницу вшито время сервера (по нему считается «следующий день» для стикеров), кешировать её нельзя
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/robots.txt")
async def robots(request: Request):
    body = f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {site_url(request)}/sitemap.xml\n"
    return Response(body, media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml")
async def sitemap(request: Request):
    try:
        lastmod = datetime.fromtimestamp((BASE_DIR / "templates" / "index.html").stat().st_mtime).date().isoformat()
    except OSError:
        lastmod = datetime.now().date().isoformat()
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"  <url><loc>{site_url(request)}/</loc><lastmod>{lastmod}</lastmod></url>\n"
           "</urlset>\n")
    return Response(xml, media_type="application/xml")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")


# Этот эндпоинт нужен только для первоначальной загрузки истории при входе на сайт.
# cid посетителя нужен, чтобы пометить его собственные штрихи (их он может стирать).
@app.get("/api/get_lines")
async def get_lines(cid: str = ""):
    me = cid if valid_cid(cid) else None
    rows = await run_in_threadpool(store.recent, MAX_LINES_SENT, LINE_LIFETIME)
    lines = [
        {"prevX": r[0], "prevY": r[1], "currX": r[2], "currY": r[3], "color": r[4], "size": r[5],
         "lid": r[6] or "", "mine": bool(me) and r[7] == me, "brush": r[8] or "w"}
        for r in rows
    ]
    return JSONResponse(content={"lines": lines}, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------
# ФОРМА СВЯЗИ: письмо на почту художницы
# ---------------------------------------------------------------------
contact_limiter = contact.ContactLimiter()


async def read_limited_json(request: Request):
    """Читает JSON не больше MAX_BODY байт (иначе None)."""
    try:
        if int(request.headers.get("content-length") or 0) > MAX_BODY:
            return None
    except ValueError:
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


@app.post("/api/contact")
async def contact_api(request: Request):
    cfg = contact.smtp_config()
    if cfg is None:
        # Почта на сервере не настроена: страница сама предложит отправить письмо из почтовой программы
        return JSONResponse({"error": "smtp_not_configured"}, status_code=503)
    data = await read_limited_json(request)
    if data is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    cleaned, error = contact.validate(data)
    if error == "spam":
        return JSONResponse({"ok": True})   # бота не расстраиваем, письмо просто не уходит
    if error:
        return JSONResponse({"error": error}, status_code=400)
    ip = client_ip(request.headers, request.client.host if request.client else None)
    if not contact_limiter.allow(ip):
        return JSONResponse({"error": "too_many"}, status_code=429)
    try:
        await run_in_threadpool(contact.send, cfg, cleaned)
    except Exception as e:
        print(f"[сайт] Не удалось отправить письмо: {e}")
        return JSONResponse({"error": "send_failed"}, status_code=502)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------
# ЖИВОЙ ТУННЕЛЬ WEBSOCKET
# ---------------------------------------------------------------------
async def persist(fn, *args):
    """Запись в базу не должна ронять соединение: ошибку пишем в консоль и идём дальше."""
    try:
        return await run_in_threadpool(fn, *args)
    except Exception as e:
        print(f"[сайт] Ошибка базы: {e}")
        return None


@app.websocket("/ws/draw")
async def websocket_endpoint(websocket: WebSocket):
    # Подключаться можно только со страниц этого сайта (проверка Origin)
    if not origin_allowed(websocket.headers.get("origin"), websocket.headers.get("host")):
        await websocket.close(code=1008)
        return

    ip = client_ip(websocket.headers, websocket.client.host if websocket.client else None)
    if not connection_limiter.acquire(ip):
        await websocket.close(code=1013)   # слишком много подключений
        return
    ip_limiter = ip_rates.setdefault(ip, RateLimiter(limit=IP_MESSAGES_PER_SECOND))

    # Личный id посетителя из браузера. Он нужен только серверу и другим не рассылается.
    cid = websocket.query_params.get("cid", "")
    if not valid_cid(cid):
        cid = secrets.token_hex(8)  # без нормального id стирать свои штрихи после перезагрузки не получится

    await manager.connect(websocket)
    limiter = RateLimiter()
    try:
        while True:
            raw = await websocket.receive_text()

            # Слишком частые сообщения (с этого подключения или со всех подключений адреса) и мусор молча отбрасываем
            if not limiter.allow() or not ip_limiter.allow():
                continue

            # Ластик: убрать свои отрезки и добавить их уцелевшие части
            cut = parse_cut(raw)
            if cut is not None:
                remove, add = cut
                # Удаляем и рассылаем только то, что действительно принадлежит этому посетителю
                owned = (await persist(store.delete_owned, cid, remove) or []) if remove else []
                # Новых кусочков не больше, чем уместно для убранных линий (защита от спама)
                add = add[: ADD_PER_REMOVED * len(owned)]
                if owned or add:
                    if add:
                        await persist(store.insert_many, add, cid)
                    await manager.broadcast(json.dumps({"cut": {"remove": owned, "add": add}}), exclude=websocket)
                continue

            # Стереть все свои рисунки
            if is_clear(raw):
                lids = await persist(store.clear_owned, cid) or []
                for i in range(0, len(lids), 500):
                    await manager.broadcast(
                        json.dumps({"cut": {"remove": lids[i:i + 500], "add": []}}), exclude=websocket)
                continue

            line = parse_line(raw)
            if line is None:
                continue

            # Сначала пересылаем всем остальным (очищенные данные, без личного id), потом сохраняем в SQLite
            await manager.broadcast(json.dumps(line), exclude=websocket)
            await persist(store.insert, line, cid)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Ошибка сокета: {e}")
    finally:
        manager.disconnect(websocket)
        connection_limiter.release(ip)
        if not connection_limiter.active(ip):
            ip_rates.pop(ip, None)
