"""Оптимизация картинок сайта (запускается вручную, нужен Pillow: pip install pillow).

Что делает:
  1. Берёт из static/images все JPG/PNG, на которые есть ссылки в шаблоне и в site_data.py.
  2. Для каждой делает два WebP: <имя>.webp (до 2400 px, для просмотра на весь экран)
     и <имя>-m.webp (до 1600 px, для самой страницы).
  3. Записывает размеры в static/images/manifest.json (по ним в шаблоне ставятся width/height).
  4. Исходники (и картинки, которые нигде не используются) переносит в папки
     _originals/ и unused_images/ рядом с main.py: на сервер они не попадают.

Запуск из корня проекта:  python tools/optimize_images.py
Повторный запуск безопасен: уже перенесённые исходники берутся из _originals/.
"""
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "static" / "images"
ORIGINALS = ROOT / "_originals"
UNUSED = ROOT / "unused_images"
FULL_SIDE, MID_SIDE = 2400, 1600
SRC_EXT = {".jpg", ".jpeg", ".png"}
KEEP_AS_IS = {"og.jpg"}      # картинка для превью ссылок: остаётся JPEG (его понимают все мессенджеры)


def used_names() -> set:
    text = ((ROOT / "templates" / "index.html").read_text(encoding="utf-8")
            + (ROOT / "site_data.py").read_text(encoding="utf-8")
            + (ROOT / "main.py").read_text(encoding="utf-8")).lower()
    names = set()
    for p in list(IMAGES.iterdir()) + list(ORIGINALS.glob("*")):
        if p.suffix.lower() in SRC_EXT and p.name.lower() not in KEEP_AS_IS:
            if p.name.lower() in text or p.stem.lower() + ".webp" in text:
                names.add(p.name.lower())
    return names


def save_webp(img: Image.Image, path: Path, side: int, quality: int) -> tuple:
    im = img.copy()
    im.thumbnail((side, side), Image.LANCZOS)          # уменьшает, но не увеличивает
    if im.mode in ("P", "LA"):
        im = im.convert("RGBA")
    elif im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    im.save(path, "WEBP", quality=quality, method=6)
    return im.size


def main() -> None:
    ORIGINALS.mkdir(exist_ok=True)
    UNUSED.mkdir(exist_ok=True)
    # исходники, лежащие в static, переносим в _originals (или в unused_images, если не нужны)
    used = used_names()
    for p in sorted(IMAGES.iterdir()):
        if p.is_file() and p.suffix.lower() in SRC_EXT and p.name.lower() not in KEEP_AS_IS:
            target = ORIGINALS if p.name.lower() in used else UNUSED
            shutil.move(str(p), str(target / p.name))
    manifest = {}
    for src in sorted(ORIGINALS.iterdir()):
        if src.suffix.lower() not in SRC_EXT or src.name.lower() not in used:
            continue
        with Image.open(src) as im:
            im.load()
            full = save_webp(im, IMAGES / (src.stem + ".webp"), FULL_SIDE, 82)
            mid = save_webp(im, IMAGES / (src.stem + "-m.webp"), MID_SIDE, 80)
        manifest[(src.stem + ".webp").lower()] = list(full)
        manifest[(src.stem + "-m.webp").lower()] = list(mid)
        print(f"{src.name:34s} {full[0]}x{full[1]} / {mid[0]}x{mid[1]}")
    (IMAGES / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print("готово:", len(manifest) // 2, "картинок")


if __name__ == "__main__":
    main()
