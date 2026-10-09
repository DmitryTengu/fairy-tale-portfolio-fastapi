import sqlite3
import time
import json
from typing import List
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()

# Монтируем статику и шаблоны
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Модель данных для сохранения (оставляем для совместимости, если нужна)
class DrawingLine(BaseModel):
    prevX: float
    prevY: float
    currX: float
    currY: float
    color: str
    size: float


# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect("drawings.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prevX REAL, prevY REAL, currX REAL, currY REAL,
            color TEXT, size REAL, timestamp REAL
        )
    """)
    conn.commit()
    conn.close()


init_db()


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
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # Рассылаем мазок абсолютно всем подключенным пользователям
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Если кто-то отвалился, не ломаем рассылку остальным
                pass


manager = ConnectionManager()


# =====================================================================
# МАРШРУТЫ И ЭНДПОИНТЫ СЕРВЕРА
# =====================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Очистка базы от линий старше 30 минут
    conn = sqlite3.connect("drawings.db")
    cursor = conn.cursor()
    now = time.time()
    cursor.execute("DELETE FROM lines WHERE ? - timestamp > 1800", (now,))
    conn.commit()
    conn.close()

    magazine_portfolio = [
        {"image": "portfolio1.JPG", "title": "Журналы «Матуліна сонейка» и «Заикина библиотека»"},
        {"image": "portfolio2.JPG", "title": "Иллюстрации к книге «Пачастунак для Цмока»"},
        {"image": "portfolio3.JPG", "title": "Иллюстрации к книге «Падарожжа ў Новы Год»"},
        {"image": "portfolio4.JPG", "title": "Проявление заботы"}
    ]

    books = [
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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"portfolio": magazine_portfolio, "books": books}
    )


# Оставляем этот эндпоинт ТОЛЬКО для первоначальной загрузки истории при входе на сайт
@app.get("/api/get_lines")
async def get_lines():
    conn = sqlite3.connect("drawings.db")
    cursor = conn.cursor()
    cursor.execute("SELECT prevX, prevY, currX, currY, color, size FROM lines")
    rows = cursor.fetchall()
    conn.close()

    lines = []
    for r in rows:
        # Индексы 0, 1, 2, 3, 4, 5 соответствуют порядку колонок в SELECT
        lines.append({
            "prevX": r[0],
            "prevY": r[1],
            "currX": r[2],
            "currY": r[3],
            "color": r[4],
            "size": r[5]
        })
    return JSONResponse(content={"lines": lines})



# ---------------------------------------------------------------------
# ЖИВОЙ ТУННЕЛЬ WEBSOCKET
# ---------------------------------------------------------------------
@app.websocket("/ws/draw")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Ждем мазок от JavaScript клиента
            data = await websocket.receive_text()
            line_data = json.loads(data)

            # Сохраняем полученную линию в базу SQLite, чтобы она не пропала
            conn = sqlite3.connect("drawings.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO lines (prevX, prevY, currX, currY, color, size, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (line_data['prevX'], line_data['prevY'], line_data['currX'], line_data['currY'], line_data['color'],
                 line_data['size'], time.time())
            )
            conn.commit()
            conn.close()

            # Мгновенно пересылаем эту линию всем остальным юзерам на сайте
            await manager.broadcast(data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Ошибка сокета: {e}")
        manager.disconnect(websocket)
