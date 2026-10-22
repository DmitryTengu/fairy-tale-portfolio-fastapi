import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import List, Optional

from datetime import datetime

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import contact
from drawing import ADD_PER_REMOVED, RateLimiter, is_clear, parse_cut, parse_line, valid_cid
from site_data import (
    BOOKS, IMAGES_DIR, MAGAZINE_PORTFOLIO, SERVICES, STEPS, load_characters, make_img_resolver,
    report_missing_images,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "drawings.db"
STATIC_DIR = BASE_DIR / "static"

LINE_LIFETIME = 1800     # секунд: мазки старше 30 минут стираются
MAX_LINES_IN_DB = 20000  # страховка от разрастания базы

# Папка static нужна приложению при старте: если её нет, создаём пустую,
# иначе сервер падает с ошибкой, ещё не показав страницу.
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def connect_db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# Инициализация базы данных SQLite
def init_db():
    with closing(connect_db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prevX REAL, prevY REAL, currX REAL, currY REAL,
                color TEXT, size REAL, timestamp REAL,
                lid TEXT DEFAULT '', cid TEXT DEFAULT '', brush TEXT DEFAULT 'w'
            )
        """)
        # Старая база без колонок lid/cid: добавляем их
        columns = {row[1] for row in conn.execute("PRAGMA table_info(lines)")}
        for name in ("lid", "cid", "brush"):
            if name not in columns:
                default = "w" if name == "brush" else ""
                conn.execute(f"ALTER TABLE lines ADD COLUMN {name} TEXT DEFAULT '{default}'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lines_lid ON lines(lid)")
        conn.commit()


init_db()
report_missing_images()


def insert_line(conn: sqlite3.Connection, line: dict, cid: str):
    conn.execute(
        "INSERT INTO lines (prevX, prevY, currX, currY, color, size, timestamp, lid, cid, brush) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (line["prevX"], line["prevY"], line["currX"], line["currY"],
         line["color"], line["size"], time.time(), line["lid"], cid, line["brush"])
    )


# =====================================================================
# МЕНЕДЖЕР ВЕБ-СОКЕТОВ ДЛЯ МГНОВЕННОЙ РАССЫЛКИ ЛИНЕЙНЫХ МАЗКОВ
# =====================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str, exclude: Optional[WebSocket] = None):
        # Рассылаем мазок всем, кроме автора (он уже нарисовал его у себя)
        for connection in list(self.active_connections):
            if connection is exclude:
                continue
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


# =====================================================================
# МАРШРУТЫ И ЭНДПОИНТЫ СЕРВЕРА
# =====================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Очистка базы: старые линии и всё, что сверх лимита
    with closing(connect_db()) as conn:
        conn.execute("DELETE FROM lines WHERE ? - timestamp > ?", (time.time(), LINE_LIFETIME))
        conn.execute(
            "DELETE FROM lines WHERE id NOT IN (SELECT id FROM lines ORDER BY id DESC LIMIT ?)",
            (MAX_LINES_IN_DB,),
        )
        conn.commit()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "portfolio": MAGAZINE_PORTFOLIO,
            "books": BOOKS,
            "services": SERVICES,
            "steps": STEPS,
            "characters": load_characters(),
            "contact_email": contact.contact_email(),
            "year": datetime.now().year,
            "studio": "Bellunium",
            "img": make_img_resolver(),
        }
    )


# Этот эндпоинт нужен только для первоначальной загрузки истории при входе на сайт.
# cid посетителя нужен, чтобы пометить его собственные штрихи (их он может стирать).
@app.get("/api/get_lines")
async def get_lines(cid: str = ""):
    me = cid if valid_cid(cid) else None
    with closing(connect_db()) as conn:
        rows = conn.execute(
            "SELECT prevX, prevY, currX, currY, color, size, lid, cid, brush FROM lines"
        ).fetchall()

    lines = [
        {"prevX": r[0], "prevY": r[1], "currX": r[2], "currY": r[3], "color": r[4], "size": r[5],
         "lid": r[6] or "", "mine": bool(me) and r[7] == me, "brush": r[8] or "w"}
        for r in rows
    ]
    return JSONResponse(content={"lines": lines})


# ---------------------------------------------------------------------
# ФОРМА СВЯЗИ: письмо на почту художницы
# ---------------------------------------------------------------------
contact_limiter = contact.ContactLimiter()


@app.post("/api/contact")
async def contact_api(request: Request):
    cfg = contact.smtp_config()
    if cfg is None:
        # Почта на сервере не настроена: страница сама предложит отправить письмо из почтовой программы
        return JSONResponse({"error": "smtp_not_configured"}, status_code=503)
    try:
        data = await request.json()
    except ValueError:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    cleaned, error = contact.validate(data)
    if error == "spam":
        return JSONResponse({"ok": True})   # бота не расстраиваем, письмо просто не уходит
    if error:
        return JSONResponse({"error": error}, status_code=400)
    ip = request.client.host if request.client else "unknown"
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
@app.websocket("/ws/draw")
async def websocket_endpoint(websocket: WebSocket):
    # Личный id посетителя из браузера. Он нужен только серверу и другим не рассылается.
    cid = websocket.query_params.get("cid", "")
    if not valid_cid(cid):
        cid = secrets.token_hex(8)  # без нормального id стирать свои штрихи после перезагрузки не получится

    await manager.connect(websocket)
    limiter = RateLimiter()
    try:
        while True:
            raw = await websocket.receive_text()

            # Слишком частые сообщения и мусор молча отбрасываем
            if not limiter.allow():
                continue

            # Ластик: убрать свои отрезки и добавить их уцелевшие части
            cut = parse_cut(raw)
            if cut is not None:
                remove, add = cut
                owned = []
                if remove:
                    marks = ",".join("?" * len(remove))
                    with closing(connect_db()) as conn:
                        # Удаляем и рассылаем только то, что действительно принадлежит этому посетителю
                        owned = [r[0] for r in conn.execute(
                            f"SELECT lid FROM lines WHERE cid = ? AND lid IN ({marks})", [cid, *remove])]
                        if owned:
                            conn.execute(f"DELETE FROM lines WHERE cid = ? AND lid IN ({marks})", [cid, *remove])
                            conn.commit()
                # Новых кусочков не больше, чем уместно для убранных линий (защита от спама)
                add = add[: ADD_PER_REMOVED * len(owned)]
                if owned or add:
                    with closing(connect_db()) as conn:
                        for item in add:
                            insert_line(conn, item, cid)
                        conn.commit()
                    await manager.broadcast(json.dumps({"cut": {"remove": owned, "add": add}}), exclude=websocket)
                continue

            # Стереть все свои рисунки
            if is_clear(raw):
                with closing(connect_db()) as conn:
                    lids = [r[0] for r in conn.execute(
                        "SELECT lid FROM lines WHERE cid = ? AND lid != ''", (cid,))]
                    conn.execute("DELETE FROM lines WHERE cid = ?", (cid,))
                    conn.commit()
                for i in range(0, len(lids), 500):
                    await manager.broadcast(
                        json.dumps({"cut": {"remove": lids[i:i + 500], "add": []}}), exclude=websocket)
                continue

            line = parse_line(raw)
            if line is None:
                continue

            # Сохраняем проверенную линию в SQLite, чтобы она не пропала
            with closing(connect_db()) as conn:
                insert_line(conn, line, cid)
                conn.commit()

            # Мгновенно пересылаем всем остальным (очищенные данные, без личного id)
            await manager.broadcast(json.dumps(line), exclude=websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Ошибка сокета: {e}")
        manager.disconnect(websocket)
