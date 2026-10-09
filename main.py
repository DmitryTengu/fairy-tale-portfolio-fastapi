import sqlite3
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Модель данных для приема рисунка от JavaScript
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
    # Создаем таблицу для линий, если её нет. Храним координаты, цвет, толщину и время создания
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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Автоматическая очистка: удаляем рисунки старше 30 минут (1800 секунд)
    conn = sqlite3.connect("drawings.db")
    cursor = conn.cursor()
    now = time.time()
    cursor.execute("DELETE FROM lines WHERE ? - timestamp > 800", (now,))
    conn.commit()
    conn.close()

    # Данные нашего портфолио
    magazine_portfolio = [
        {"image": "portfolio1.JPG", "title": "Журналы «Матуліна сонейка» и «Зайкина библиотека»"},
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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"portfolio": magazine_portfolio, "books": books}
    )


# Эндпоинт 1: Получение всех активных линий для отрисовки у других юзеров
@app.get("/api/get_lines")
async def get_lines():
    conn = sqlite3.connect("drawings.db")
    cursor = conn.cursor()
    cursor.execute("SELECT prevX, prevY, currX, currY, color, size FROM lines")
    rows = cursor.fetchall()
    conn.close()

    lines = []
    for r in rows:
        lines.append({"prevX": r[0], "prevY": r[1], "currX": r[2], "currY": r[3], "color": r[4], "size": r[5]})
    return JSONResponse(content={"lines": lines})


# Эндпоинт 2: Сохранение новой линии в базу данных
@app.post("/api/save_line")
async def save_line(line: DrawingLine):
    conn = sqlite3.connect("drawings.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO lines (prevX, prevY, currX, currY, color, size, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (line.prevX, line.prevY, line.currX, line.currY, line.color, line.size, time.time())
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
