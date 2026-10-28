    (function () {
        'use strict';

        function storeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
        function storeSet(key, val) { try { localStorage.setItem(key, val); } catch (e) { /* без хранилища тоже работает */ } }
        function randomId(len) {
            const bytes = new Uint8Array(len);
            (window.crypto || window.msCrypto).getRandomValues(bytes);
            return Array.from(bytes, (b) => (b % 36).toString(36)).join('');
        }
        // Личный id посетителя: по нему сервер понимает, какие рисунки можно стирать
        let CID = storeGet('fairyCid');
        if (!CID || !/^[a-z0-9]{8,40}$/.test(CID)) { CID = randomId(16); storeSet('fairyCid', CID); }

        // =====================================================================
        // 1. ОБЩИЙ ХОЛСТ
        // =====================================================================
        const canvas = document.getElementById('drawingCanvas');
        const ctx = canvas.getContext('2d');
        const COLORS = ['#0d9488', '#2dd4bf', '#f59e0b', '#ec4899', '#8b5cf6', '#3b82f6', '#ef4444', '#84cc16'];
        const SIZES = [4, 8, 14];
        const MAX_LINES = 20000;

        const state = {
            lines: [],          // все мазки (координаты: x экрана, y страницы)
            showOthers: true,
            color: COLORS[0],
            size: SIZES[1],
            canDraw: window.matchMedia('(pointer: fine)').matches, // на телефоне по умолчанию выключено, чтобы не мешать скроллу
            drawing: false,
            tool: 'brush',      // 'brush' или 'eraser'
            brush: 'w',         // 'w' акварель, 'o' масло
            lx: 0, ly: 0,
            raf: 0
        };

        function resizeCanvas() {
            const r = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.round(window.innerWidth * r);
            canvas.height = Math.round(window.innerHeight * r);
            ctx.setTransform(r, 0, 0, r, 0, 0);
            redraw();
        }

        // ---------- Кисти: акварель и масло ----------
        // Мазок рисуется целиком из отрезков, соединённых концами. Так нет «бусин» на стыках,
        // а фактура одинакова у всех посетителей (случайность берётся не из Math.random,
        // а из координат начала мазка).
        const rnd = (a, b) => { const h = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return h - Math.floor(h); };

        function parseColor(c) {
            let m = /^#([0-9a-f]{6})$/i.exec(c);
            if (m) { const n = parseInt(m[1], 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
            m = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(c);
            if (m) return [parseInt(m[1] + m[1], 16), parseInt(m[2] + m[2], 16), parseInt(m[3] + m[3], 16)];
            m = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/.exec(c);
            if (m) return [Math.min(255, +m[1]), Math.min(255, +m[2]), Math.min(255, +m[3])];
            return [13, 148, 136];
        }
        // k > 0 светлее, k < 0 темнее
        function shade(rgb, k) {
            const f = (v) => Math.round(k >= 0 ? v + (255 - v) * k : v * (1 + k));
            return 'rgb(' + f(rgb[0]) + ',' + f(rgb[1]) + ',' + f(rgb[2]) + ')';
        }

        let built = { src: null, len: -1, chains: [] };
        function buildChains() {
            const open = new Map(), chains = [];
            for (let i = 0; i < state.lines.length; i++) {
                const l = state.lines[i];
                const style = '|' + l.color + '|' + l.size + '|' + (l.brush === 'o' ? 'o' : 'w') + '|' + (l.mine ? 1 : 0);
                const from = l.prevX + '|' + l.prevY + style;
                let c = open.get(from);
                if (c) {
                    open.delete(from);
                } else {
                    c = {
                        pts: [l.prevX, l.prevY], color: l.color, size: l.size, brush: l.brush === 'o' ? 'o' : 'w', mine: !!l.mine,
                        minY: l.prevY, maxY: l.prevY
                    };
                    chains.push(c);
                }
                c.pts.push(l.currX, l.currY);
                if (l.currY < c.minY) c.minY = l.currY;
                if (l.currY > c.maxY) c.maxY = l.currY;
                open.set(l.currX + '|' + l.currY + style, c);
            }
            built = { src: state.lines, len: state.lines.length, chains: chains };
        }

        // Путь мазка со сдвигом off вбок (для щетинок), сглаженный квадратичными кривыми
        function tracePath(c, off, i0, i1) {
            const p = c.pts, nx = c.nx, ny = c.ny;
            const X = (i) => p[2 * i] + (nx ? nx[i] * off : 0);
            const Y = (i) => p[2 * i + 1] + (ny ? ny[i] * off : 0);
            ctx.beginPath();
            ctx.moveTo(X(i0), Y(i0));
            for (let i = i0 + 1; i <= i1; i++) {
                ctx.quadraticCurveTo(X(i - 1), Y(i - 1), (X(i - 1) + X(i)) / 2, (Y(i - 1) + Y(i)) / 2);
            }
            ctx.lineTo(X(i1), Y(i1));
        }
        function strokeChain(c, off, i0, i1, width, color, alpha) {
            if (i1 <= i0) return;
            tracePath(c, off, i0, i1);
            ctx.lineWidth = width;
            ctx.strokeStyle = color;
            ctx.globalAlpha = alpha;
            ctx.stroke();
        }

        // Акварель: прозрачный слой, у краёв светлее, в центре насыщеннее
        function drawWater(c) {
            if (!c.rgb) c.rgb = parseColor(c.color);
            const col = 'rgb(' + c.rgb[0] + ',' + c.rgb[1] + ',' + c.rgb[2] + ')';
            const n = c.pts.length / 2 - 1;
            strokeChain(c, 0, 0, n, c.size * 2.5, col, 0.06);
            strokeChain(c, 0, 0, n, c.size * 1.95, col, 0.09);
            strokeChain(c, 0, 0, n, c.size * 1.4, col, 0.13);
            strokeChain(c, 0, 0, n, c.size * 0.9, col, 0.2);
        }

        // Масло: плотная краска, видны борозды от щетины, светлый и тёмный край
        function prepOil(c) {
            const n = c.pts.length / 2;
            c.nx = new Float32Array(n); c.ny = new Float32Array(n);
            for (let i = 0; i < n; i++) {
                const a = Math.max(0, i - 3), b = Math.min(n - 1, i + 3);
                const tx = c.pts[2 * b] - c.pts[2 * a], ty = c.pts[2 * b + 1] - c.pts[2 * a + 1];
                const len = Math.hypot(tx, ty) || 1;
                c.nx[i] = -ty / len; c.ny[i] = tx / len;
            }
            const rgb = parseColor(c.color), seed = c.pts[0] * 0.37 + c.pts[1] * 0.11 + c.size;
            const N = Math.max(5, Math.min(14, Math.round(c.size) + 2));
            c.bristles = [];
            for (let j = 0; j < N; j++) {
                const t0 = n > 10 ? Math.floor(rnd(seed, j + 80) * 5) : 0, t1 = n > 10 ? Math.floor(rnd(seed, j + 120) * 5) : 0;
                c.bristles.push({
                    off: (j / (N - 1) - 0.5) * c.size * 1.3 + (rnd(seed, j + 160) - 0.5) * c.size * 0.12,
                    w: Math.max(1, c.size * 1.3 / N * (0.8 + 0.8 * rnd(seed, j + 40))),
                    color: shade(rgb, (rnd(seed, j) - 0.5) * 0.8),
                    alpha: 0.7 + 0.28 * rnd(seed, j + 200),
                    i0: t0, i1: n - 1 - t1
                });
            }
            c.base = shade(rgb, -0.1); c.hi = shade(rgb, 0.45); c.lo = shade(rgb, -0.4);
        }
        function drawOil(c) {
            if (!c.bristles) prepOil(c);
            const n = c.pts.length / 2 - 1;
            strokeChain(c, 0, 0, n, c.size * 1.0, c.base, 0.85);
            for (let j = 0; j < c.bristles.length; j++) {
                const b = c.bristles[j];
                strokeChain(c, b.off, b.i0, b.i1, b.w, b.color, b.alpha);
            }
            strokeChain(c, -c.size * 0.44, 0, n, Math.max(1, c.size * 0.14), c.hi, 0.6);
            strokeChain(c, c.size * 0.47, 0, n, Math.max(1, c.size * 0.14), c.lo, 0.5);
        }

        // Перерисовка из памяти: быстрая, без запросов к серверу. Рисуем только то, что видно на экране.
        function redraw() {
            state.raf = 0;
            if (built.src !== state.lines || built.len !== state.lines.length) buildChains();
            ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
            const sy = window.pageYOffset, h = window.innerHeight;
            ctx.save();
            ctx.translate(0, -sy);
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            for (let i = 0; i < built.chains.length; i++) {
                const c = built.chains[i];
                if (!state.showOthers && !c.mine) continue;
                const pad = c.size * 2.5;
                if (c.maxY + pad < sy || c.minY - pad > sy + h) continue;
                if (c.brush === 'o') drawOil(c); else drawWater(c);
            }
            ctx.restore();
            ctx.globalAlpha = 1;
        }
        function scheduleRedraw() { if (!state.raf) state.raf = requestAnimationFrame(redraw); }

        function addLine(line) {
            state.lines.push(line);
            if (state.lines.length > MAX_LINES) state.lines.splice(0, state.lines.length - MAX_LINES);
        }

        window.addEventListener('resize', resizeCanvas);
        window.addEventListener('scroll', scheduleRedraw, { passive: true });

        // ---- ввод: мышь и палец ----
        const NO_DRAW = '.nav-btn, .scroll-btn, .featured-art-frame, .magazine-card, .about-photo, .service-card, .steps li, .book-container, .social-link, .lightbox, .tools, .collection-btn, .hidden-char, .coll-overlay, .contact-form, .coll-hint, .site-nav, .sticker-view, .site-footer';

        function isTextZone(x) {
            const center = window.innerWidth / 2;
            const limit = window.innerWidth > 968 ? 320 : 120;
            return x > center - limit && x < center + limit;
        }
        function canStart(target, x) {
            if (!state.canDraw || isTextZone(x)) return false;
            const tag = target.tagName;
            if (tag === 'IMG' || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON') return false;
            return !target.closest(NO_DRAW);
        }
        function startAt(x, y) {
            state.drawing = true; state.lx = x; state.ly = y;
            if (state.tool === 'eraser') eraseSweep(x, y, x, y);
        }

        // ---- ластик: подтирает только свои линии, как в Paint ----
        // Линия состоит из коротких отрезков. Ластик вырезает из отрезков круг:
        // уцелевшие концы остаются, середина исчезает (у всех посетителей тоже).
        function eraserRadius() { return state.size * 1.5 + 6; }
        const round1 = (n) => Math.round(n * 10) / 10;

        // Часть отрезка A-B внутри круга (C, r): [t1, t2] от 0 до 1 или null
        function circleCut(ax, ay, bx, by, cx, cy, r) {
            const dx = bx - ax, dy = by - ay, fx = ax - cx, fy = ay - cy;
            const a = dx * dx + dy * dy;
            if (a === 0) return Math.hypot(fx, fy) <= r ? [0, 1] : null;
            const b = 2 * (fx * dx + fy * dy);
            const c = fx * fx + fy * fy - r * r;
            const disc = b * b - 4 * a * c;
            if (disc < 0) return null;
            const sq = Math.sqrt(disc);
            const t1 = (-b - sq) / (2 * a), t2 = (-b + sq) / (2 * a);
            if (t2 < 0 || t1 > 1) return null;
            return [Math.max(0, t1), Math.min(1, t2)];
        }
        function piece(l, t0, t1) {
            const dx = l.currX - l.prevX, dy = l.currY - l.prevY;
            return {
                prevX: round1(l.prevX + dx * t0), prevY: round1(l.prevY + dy * t0),
                currX: round1(l.prevX + dx * t1), currY: round1(l.prevY + dy * t1),
                color: l.color, size: l.size, brush: l.brush || 'w', lid: randomId(10), mine: true
            };
        }
        // Один круг ластика. removed: id старых отрезков (они есть на сервере),
        // added: новые кусочки, которые ещё не отправлены.
        function cutCircle(cx, cy, r, removed, added) {
            const gone = new Set(), fresh = [];
            for (let i = 0; i < state.lines.length; i++) {
                const l = state.lines[i];
                if (!l.mine || !l.lid) continue;
                const rr = r + l.size * (l.brush === 'o' ? 0.75 : 1.25); // с учётом видимой ширины мазка
                if (Math.max(l.prevY, l.currY) + rr < cy || Math.min(l.prevY, l.currY) - rr > cy) continue;
                if (Math.max(l.prevX, l.currX) + rr < cx || Math.min(l.prevX, l.currX) - rr > cx) continue;
                const t = circleCut(l.prevX, l.prevY, l.currX, l.currY, cx, cy, rr);
                if (!t) continue;
                gone.add(l.lid);
                const len = Math.hypot(l.currX - l.prevX, l.currY - l.prevY);
                if (t[0] * len > 1) fresh.push(piece(l, 0, t[0]));
                if ((1 - t[1]) * len > 1) fresh.push(piece(l, t[1], 1));
            }
            if (!gone.size) return;
            state.lines = state.lines.filter((l) => !gone.has(l.lid));
            gone.forEach((lid) => { if (added.has(lid)) added.delete(lid); else removed.add(lid); });
            fresh.forEach((l) => { state.lines.push(l); added.set(l.lid, l); });
        }
        function sendCut(removeIds, addLines) {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            const clean = (l) => ({ prevX: l.prevX, prevY: l.prevY, currX: l.currX, currY: l.currY, color: l.color, size: l.size, brush: l.brush || 'w', lid: l.lid });
            const CHUNK = 25;
            let adds = addLines.map(clean);
            for (let i = 0; i < Math.max(removeIds.length, 1); i += CHUNK) {
                const rem = removeIds.slice(i, i + CHUNK);
                const last = i + CHUNK >= removeIds.length;
                const add = last ? adds : adds.splice(0, rem.length * 6);
                ws.send(JSON.stringify({ cut: { remove: rem, add: add } }));
            }
        }
        // Проводим ластиком от (x1, y1) до (x2, y2) координат экрана, не оставляя пропусков
        function eraseSweep(x1, y1, x2, y2) {
            const r = eraserRadius(), sy = window.pageYOffset;
            const steps = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / (r * 0.5)));
            const removed = new Set(), added = new Map();
            for (let i = 1; i <= steps; i++) {
                cutCircle(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps + sy, r, removed, added);
            }
            if (!removed.size && !added.size) return;
            scheduleRedraw();
            sendCut(Array.from(removed), Array.from(added.values()));
        }
        function eraseAllMine() {
            const before = state.lines.length;
            state.lines = state.lines.filter((l) => !l.mine);
            if (state.lines.length === before) { toast('У вас пока нет рисунков'); return; }
            redraw();
            if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ clear: true }));
            toast('Ваши рисунки стёрты');
        }
        function updateEraserCursor() {
            const r = Math.round(eraserRadius()), d = r * 2 + 4;
            const svg = "<svg xmlns='http://www.w3.org/2000/svg' width='" + d + "' height='" + d + "'><circle cx='" + d / 2 + "' cy='" + d / 2 +
                "' r='" + r + "' fill='rgba(236,72,153,0.12)' stroke='#ec4899' stroke-width='2'/></svg>";
            document.body.style.setProperty('--eraser-cursor', 'url("data:image/svg+xml;utf8,' + encodeURIComponent(svg) + '") ' + d / 2 + ' ' + d / 2 + ', cell');
        }

        function moveTo(x, y) {
            if (state.tool === 'eraser') {
                if (Math.hypot(x - state.lx, y - state.ly) < 2) return;
                eraseSweep(state.lx, state.ly, x, y); state.lx = x; state.ly = y; return;
            }
            if (Math.hypot(x - state.lx, y - state.ly) < 4) return; // не шлём лишние микро-мазки
            const sy = window.pageYOffset;
            const line = {
                prevX: Math.round(state.lx * 10) / 10, prevY: Math.round((state.ly + sy) * 10) / 10,
                currX: Math.round(x * 10) / 10, currY: Math.round((y + sy) * 10) / 10,
                color: state.color, size: state.size, brush: state.brush, lid: randomId(10), mine: true
            };
            addLine(line);
            scheduleRedraw();
            sendLine(line);
            state.lx = x; state.ly = y;
        }

        document.addEventListener('mousedown', (e) => { if (canStart(e.target, e.clientX)) startAt(e.clientX, e.clientY); });
        document.addEventListener('mousemove', (e) => { if (state.drawing) moveTo(e.clientX, e.clientY); });
        document.addEventListener('touchstart', (e) => {
            const t = e.touches && e.touches[0];
            if (t && canStart(e.target, t.clientX)) startAt(t.clientX, t.clientY);
        }, { passive: true });
        document.addEventListener('touchmove', (e) => {
            const t = e.touches && e.touches[0];
            if (!state.drawing || !t) return;
            e.preventDefault(); // пока включён режим рисования, страница не скроллится
            moveTo(t.clientX, t.clientY);
        }, { passive: false });
        const stop = () => { state.drawing = false; };
        document.addEventListener('mouseup', stop);
        document.addEventListener('touchend', stop);
        document.addEventListener('touchcancel', stop);

        // ---- WebSocket ----
        let ws = null, retries = 0;
        const liveDot = document.getElementById('liveDot');

        function connectWebSocket() {
            const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            ws = new WebSocket(proto + window.location.host + '/ws/draw?cid=' + CID);
            ws.onopen = () => { retries = 0; liveDot.classList.add('on'); loadHistory(); };
            ws.onmessage = (event) => {
                let l;
                try { l = JSON.parse(event.data); } catch (e) { return; }
                if (l && l.cut) {
                    const gone = new Set(l.cut.remove || []);
                    state.lines = state.lines.filter((x) => !gone.has(x.lid));
                    (l.cut.add || []).forEach((x) => { if (typeof x.prevX === 'number') addLine(x); });
                    scheduleRedraw();
                    return;
                }
                if (!l || typeof l.prevX !== 'number') return;
                addLine(l);
                if (state.showOthers) scheduleRedraw();
            };
            ws.onclose = () => {
                liveDot.classList.remove('on');
                retries += 1;
                setTimeout(connectWebSocket, Math.min(15000, 1500 * retries));
            };
        }
        function sendLine(line) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    prevX: line.prevX, prevY: line.prevY, currX: line.currX, currY: line.currY,
                    color: line.color, size: line.size, brush: line.brush || 'w', lid: line.lid
                }));
            }
        }
        // История один раз при подключении (раньше шёл запрос на каждый скролл)
        function loadHistory() {
            fetch('/api/get_lines?cid=' + CID)
                .then((res) => res.json())
                .then((data) => { state.lines = Array.isArray(data.lines) ? data.lines : []; redraw(); })
                .catch((err) => console.log('Ошибка загрузки истории:', err));
        }

        // ---- панель кисти ----
        const tools = document.getElementById('tools');
        const swatchBox = document.getElementById('swatches');
        const sizeBox = document.getElementById('sizes');
        const btnDraw = document.getElementById('btnDraw');
        const btnOthers = document.getElementById('btnOthers');

        COLORS.forEach((c, i) => {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'swatch' + (i === 0 ? ' active' : '');
            b.style.background = c; b.setAttribute('aria-label', 'Цвет ' + (i + 1));
            b.addEventListener('click', () => {
                state.color = c;
                swatchBox.querySelectorAll('.swatch').forEach((x) => x.classList.toggle('active', x === b));
            });
            swatchBox.appendChild(b);
        });
        SIZES.forEach((s, i) => {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'size-btn' + (i === 1 ? ' active' : '');
            b.setAttribute('aria-label', 'Толщина ' + (i + 1));
            b.innerHTML = '<i style="width:' + (s + 2) + 'px;height:' + (s + 2) + 'px"></i>';
            b.addEventListener('click', () => {
                state.size = s;
                updateEraserCursor();
                sizeBox.querySelectorAll('.size-btn').forEach((x) => x.classList.toggle('active', x === b));
            });
            sizeBox.appendChild(b);
        });
        const btnWater = document.getElementById('btnWater');
        const btnOil = document.getElementById('btnOil');
        const btnEraser = document.getElementById('btnEraser');
        function setTool(tool) {
            state.tool = tool;
            if (tool === 'eraser') state.canDraw = true;
            btnWater.classList.toggle('on', tool === 'brush' && state.brush === 'w');
            btnOil.classList.toggle('on', tool === 'brush' && state.brush === 'o');
            btnEraser.classList.toggle('on', tool === 'eraser');
            updateEraserCursor();
            document.body.classList.toggle('erasing', tool === 'eraser' && state.canDraw);
            syncToolButtons();
        }
        function setBrush(kind) { state.brush = kind; state.canDraw = true; setTool('brush'); }
        btnWater.addEventListener('click', () => setBrush('w'));
        btnOil.addEventListener('click', () => setBrush('o'));
        btnEraser.addEventListener('click', () => setTool('eraser'));
        document.getElementById('btnClearMine').addEventListener('click', eraseAllMine);

        function syncToolButtons() {
            btnDraw.classList.toggle('on', state.canDraw);
            btnDraw.textContent = state.canDraw ? '✏️ Рисую' : '✏️ Рисовать';
            btnOthers.classList.toggle('on', state.showOthers);
            btnOthers.textContent = state.showOthers ? '👁️ Чужие' : '🙈 Скрыты';
            document.body.classList.toggle('erasing', state.tool === 'eraser' && state.canDraw);
        }
        btnDraw.addEventListener('click', () => { state.canDraw = !state.canDraw; syncToolButtons(); });
        btnOthers.addEventListener('click', () => { state.showOthers = !state.showOthers; syncToolButtons(); redraw(); });
        const toolsBtn = document.getElementById('toolsToggle');
        function setToolsOpen(open) {
            tools.classList.toggle('collapsed', !open);
            toolsBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
            storeSet('fairyToolsOpen', open ? '1' : '0');
        }
        toolsBtn.addEventListener('click', () => setToolsOpen(tools.classList.contains('collapsed')));
        // Панель кисти по умолчанию свёрнута (раньше на ноутбуке закрывала приветствие); выбор посетителя запоминается
        {
            const open = storeGet('fairyToolsOpen') === '1' && window.innerWidth > 968;
            tools.classList.toggle('collapsed', !open);
            toolsBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
        syncToolButtons();

        function startCanvas() { resizeCanvas(); connectWebSocket(); }
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startCanvas);
        else startCanvas();

        // =====================================================================
        // 2. МИНИ-ИГРА: НАЙДИ ГЕРОЕВ
        // =====================================================================
        const STORE_KEY = 'fairyFoundV2';
        const PLACE_KEY = 'fairyPlaceV2';
        const GAME = window.GAME_DATA || { per_wave: 3, total: 0, roster: [], spots: [], hints: {} };
        const PER = GAME.per_wave;
        const total = GAME.total;
        const collBtn = document.getElementById('collectionBtn');
        const counter = document.getElementById('collCounter');
        const overlay2 = document.getElementById('collOverlay');
        const toastEl = document.getElementById('toast');
        const hintEl = document.getElementById('collHint');

        const order = GAME.roster.map((c) => c.id);
        const info = {};
        GAME.roster.forEach((c) => {
            info[c.id] = { id: c.id, name: c.name, book: c.book, emoji: c.emoji, img: c.url || '', about: c.about || '' };
        });
        let found = [];
        try { found = JSON.parse(storeGet(STORE_KEY) || '[]'); } catch (e) { found = []; }
        if (!Array.isArray(found)) found = [];
        found = found.filter((id, i) => info[id] && found.indexOf(id) === i);   // чужие и повторы не считаются
        let places = {};
        try { places = JSON.parse(storeGet(PLACE_KEY) || '{}') || {}; } catch (e) { places = {}; }
        const layers = {};
        document.querySelectorAll('.char-layer').forEach((l) => { layers[l.dataset.section] = l; });
        const heroEls = {};

        // =====================================================================
        // СТИКЕРЫ: герои лежат на сайте пятёрками. Нашёл всех пятерых, следующие пять появятся
        // на следующий день (после полуночи). Так до конца коллекции.
        // Прогресс хранится в браузере посетителя, у каждого свой.
        // =====================================================================
        const UNLOCK_KEY = 'fairyStickerDoneV1';   // когда посетитель закончил каждую пятёрку
        const SEEN_KEY = 'fairyStickerSeenV1';     // сколько пятёрок он уже видел в книге
        const BATCH = Math.max(1, GAME.per_wave || 5);
        const DAY_GATE = GAME.day_gate !== false;  // false: следующая пятёрка сразу (STICKER_DAY_GATE=0 в .env)
        const batches = [];
        for (let i = 0; i < order.length; i += BATCH) batches.push(order.slice(i, i + BATCH));
        // Время берём с сервера: смена часов на устройстве не помогает открыть стикеры раньше
        const clockOffset = GAME.server_now ? GAME.server_now - Date.now() : 0;
        const nowMs = () => Date.now() + clockOffset;
        const dayKey = (ts) => {
            const d = new Date(ts);
            return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        };
        let doneAt = {};
        try { doneAt = JSON.parse(storeGet(UNLOCK_KEY) || '{}') || {}; } catch (e) { doneAt = {}; }
        const notFound = (id) => found.indexOf(id) === -1;

        // Запоминаем момент, когда найдена вся пятёрка
        function recordDone() {
            let changed = false;
            batches.forEach((batch, k) => {
                if (!doneAt['b' + k] && !batch.some(notFound)) { doneAt['b' + k] = nowMs(); changed = true; }
            });
            if (changed) storeSet(UNLOCK_KEY, JSON.stringify(doneAt));
        }
        // Пятёрка k открыта: первая сразу; начатую не закрываем; остальные на следующий день после предыдущей
        function batchOpen(k) {
            if (k === 0 || batches[k].some((id) => !notFound(id))) return true;
            const prev = doneAt['b' + (k - 1)];
            if (!prev) return false;
            return DAY_GATE ? dayKey(nowMs()) > dayKey(prev) : true;
        }
        // Когда откроется пятёрка k: полночь после окончания предыдущей (null, если предыдущая ещё не найдена)
        function opensAt(k) {
            const prev = k > 0 ? doneAt['b' + (k - 1)] : null;
            if (!prev) return null;
            const d = new Date(prev);
            return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1).getTime();
        }
        // Первая пятёрка с ненайденными стикерами, если она ещё закрыта: { k, at }
        function waitInfo() {
            for (let k = 0; k < batches.length; k++) {
                if (batches[k].some(notFound)) return batchOpen(k) ? null : { k: k, at: opensAt(k) };
            }
            return null;
        }
        function openCount() { let n = 0; batches.forEach((b, k) => { if (batchOpen(k)) n++; }); return n; }
        function leftText(ms) {
            const min = Math.max(1, Math.ceil(ms / 60000));
            if (min < 60) return 'через ' + min + ' мин';
            return ('через ' + Math.floor(min / 60) + ' ч ' + (min % 60 ? (min % 60) + ' мин' : '')).trim();
        }

        function updateCounter() { counter.textContent = found.length + '/' + total; }
        function toast(text) {
            toastEl.textContent = text;
            toastEl.classList.add('show');
            clearTimeout(toast.t);
            toast.t = setTimeout(() => toastEl.classList.remove('show'), 2800);
        }

        // Текущая пятёрка: стикеры первой пятёрки, где остались ненайденные (если её день уже наступил)
        function currentWaveIds() {
            for (let k = 0; k < batches.length; k++) {
                const left = batches[k].filter(notFound);
                if (left.length) return batchOpen(k) ? left : [];
            }
            return [];
        }

        // Случайные места: разные разделы для героев одной волны
        function pickPlaces(ids) {
            const used = {};
            ids.forEach((id) => { if (places[id]) used[places[id].s] = true; });
            const taken = Object.keys(places).map((k) => places[k].s + '|' + places[k].l + '|' + places[k].t);
            ids.forEach((id) => {
                if (places[id]) return;
                let pool = GAME.spots.filter((p) => !used[p.section]);
                if (!pool.length) pool = GAME.spots.slice();
                const fresh = pool.filter((p) => taken.indexOf(p.section + '|' + p.left + '|' + p.top) === -1);
                if (fresh.length) pool = fresh;
                const p = pool[Math.floor(Math.random() * pool.length)];
                const jitter = (v, d, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v + (Math.random() * 2 - 1) * d)));
                places[id] = {
                    s: p.section, l: jitter(p.left, 1.5, 1, 94), t: jitter(p.top, 3, 2, 92),
                    r: Math.round(Math.random() * 20 - 10), z: 88 + Math.round(Math.random() * 24)
                };
                used[p.section] = true;
                taken.push(p.section + '|' + p.left + '|' + p.top);
            });
            storeSet(PLACE_KEY, JSON.stringify(places));
        }

        function spawn(id, animate) {
            const c = GAME.roster.find((x) => x.id === id);
            const pl = places[id];
            const layer = layers[pl.s];
            if (!c || !layer || heroEls[id]) return;
            const el = document.createElement('button');
            el.type = 'button';
            el.className = 'hidden-char' + (animate ? ' appear' : '');
            el.dataset.id = id; el.dataset.name = c.name; el.dataset.book = c.book; el.dataset.emoji = c.emoji || '';
            el.setAttribute('aria-label', 'Найти героя сказки');
            el.style.cssText = '--left:' + pl.l + '%;top:' + pl.t + '%;--size:' + pl.z + 'px;--rot:' + pl.r + 'deg;';
            const im = document.createElement('img');
            im.src = c.url; im.alt = ''; im.dataset.emoji = c.emoji || '';
            im.addEventListener('error', () => charFallback(im));
            el.appendChild(im);
            el.addEventListener('click', (e) => { e.stopPropagation(); collect(el); });
            layer.appendChild(el);
            heroEls[id] = el;
        }

        function showWave(animate) {
            const ids = currentWaveIds();
            pickPlaces(ids);
            ids.forEach((id) => spawn(id, animate));
            return ids.length;
        }

        function visual(c) {
            const wrap = document.createElement('div');
            wrap.className = 'coll-art';
            const img = document.createElement('img');
            img.src = c.img; img.alt = c.name; img.dataset.emoji = c.emoji;
            img.addEventListener('error', () => charFallback(img));
            wrap.appendChild(img);
            return wrap;
        }

        // Просмотр героя или стикера крупно
        const stickerView = document.getElementById('stickerView');
        function openSticker(id) {
            const c = info[id];
            if (!c || notFound(id)) return;
            const big = document.getElementById('stickerBig');
            big.innerHTML = '';
            big.appendChild(visual(c));
            document.getElementById('stickerName').textContent = c.name;
            document.getElementById('stickerBook').textContent = c.book ? 'Из книги «' + c.book + '»' : 'Герой сказок Анны-Анастасии';
            const about = document.getElementById('stickerAbout');
            about.textContent = c.about || '';
            about.hidden = !c.about;
            stickerView.hidden = false;
            requestAnimationFrame(() => stickerView.classList.add('active'));
            document.getElementById('stickerViewClose').focus();
        }
        function closeSticker() {
            if (stickerView.hidden) return;
            stickerView.classList.remove('active');
            stickerView.hidden = true;
        }
        document.getElementById('stickerViewClose').addEventListener('click', closeSticker);
        stickerView.addEventListener('click', (e) => { if (e.target === stickerView) closeSticker(); });

        function makeViewable(node, id) {
            node.classList.add('viewable');
            node.tabIndex = 0;
            node.setAttribute('role', 'button');
            node.addEventListener('click', () => openSticker(id));
            node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openSticker(id); } });
        }

        const TILT = [-4, 3, -2, 5, -5, 2, -3, 4];
        // Стикер в книге: found (найден), hiding (лежит на сайте), future (откроется завтра)
        function stickerEl(id, state, n) {
            const c = info[id];
            const item = document.createElement('div');
            item.className = 'sticker' + (state === 'found' ? '' : ' locked') + (state === 'future' ? ' future' : '');
            item.style.setProperty('--r', TILT[n % TILT.length] + 'deg');
            const face = document.createElement('div');
            face.className = 'sticker-face';
            face.appendChild(visual(c));
            const name = document.createElement('span');
            name.className = 'sticker-name';
            if (state === 'found') {
                name.textContent = c.name;
                makeViewable(item, id);
                item.setAttribute('aria-label', 'Открыть стикер: ' + c.name);
            } else if (state === 'hiding') {
                name.textContent = '???';
                item.title = places[id] ? GAME.hints[places[id].s] : 'Где-то прячется';
            } else {
                name.textContent = 'Завтра';
            }
            item.appendChild(face); item.appendChild(name);
            return item;
        }

        function renderCollection() {
            const grid = document.getElementById('collGrid');
            grid.innerHTML = '';
            const hiding = currentWaveIds();
            const wait = waitInfo();
            let n = 0;
            order.filter((id) => !notFound(id)).forEach((id) => grid.appendChild(stickerEl(id, 'found', n++)));
            hiding.forEach((id) => grid.appendChild(stickerEl(id, 'hiding', n++)));
            if (wait) batches[wait.k].forEach((id) => grid.appendChild(stickerEl(id, 'future', n++)));
            const done = found.length >= total && total > 0;
            document.getElementById('collBar').style.width = (total ? (found.length / total) * 100 : 0) + '%';
            document.getElementById('collSub').textContent = done ? 'Коллекция собрана!' : 'Собрано ' + found.length + ' из ' + total;
            let next = '';
            if (!done) {
                if (hiding.length) {
                    next = 'Сегодня на сайте лежат стикеры: ' + hiding.length + '. Найди ' + (hiding.length === 1 ? 'его' : 'их') +
                        (DAY_GATE ? ', и завтра появятся новые.' : ', и появятся новые.');
                } else if (wait && wait.at) {
                    next = 'Все стикеры на сегодня найдены. Новые откроются завтра, ' + leftText(wait.at - nowMs()) + '.';
                }
            }
            document.getElementById('collNext').textContent = next;
            document.getElementById('collDone').hidden = !done;
            document.getElementById('collDoneLink').href = 'https://t.me/angry_miu?text=' +
                encodeURIComponent('Здравствуйте! Нашёл всех героев на вашем сайте ✨');
        }
        function updateBadge() {
            const seen = parseInt(storeGet(SEEN_KEY) || '0', 10) || 0;
            collBtn.classList.toggle('has-new', openCount() > seen);
        }
        let collTicker = null;
        function openCollection() {
            renderCollection(); overlay2.classList.add('active'); hideHint();
            storeSet(SEEN_KEY, String(openCount())); updateBadge();
            clearInterval(collTicker);
            collTicker = setInterval(() => { if (overlay2.classList.contains('active')) renderCollection(); }, 30000);
        }
        function closeCollection() { overlay2.classList.remove('active'); clearInterval(collTicker); closeSticker(); }
        collBtn.addEventListener('click', openCollection);
        document.getElementById('collClose').addEventListener('click', closeCollection);
        overlay2.addEventListener('click', (e) => { if (e.target === overlay2) closeCollection(); });
        document.getElementById('collReset').addEventListener('click', () => {
            if (!window.confirm('Начать игру заново? Найденные герои снова спрячутся.')) return;
            found = []; places = {}; doneAt = {};
            storeSet(STORE_KEY, '[]'); storeSet(PLACE_KEY, '{}'); storeSet(UNLOCK_KEY, '{}'); storeSet(SEEN_KEY, '1');
            updateBadge();
            Object.keys(heroEls).forEach((id) => { heroEls[id].remove(); delete heroEls[id]; });
            showWave(true);
            updateCounter(); renderCollection();
        });

        function fly(el) {
            const from = el.getBoundingClientRect();
            const to = collBtn.getBoundingClientRect();
            const clone = el.cloneNode(true);
            clone.className = 'flying-char';
            clone.removeAttribute('style');
            clone.style.cssText = 'left:' + from.left + 'px;top:' + from.top + 'px;width:' + from.width + 'px;height:' + from.height + 'px;--size:' + from.width + 'px;';
            document.body.appendChild(clone);
            const dx = to.left + to.width / 2 - (from.left + from.width / 2);
            const dy = to.top + to.height / 2 - (from.top + from.height / 2);
            const anim = clone.animate([
                { transform: 'translate(0,0) scale(1) rotate(0)', opacity: 1 },
                { transform: 'translate(' + dx * 0.4 + 'px,' + (dy * 0.4 - 70) + 'px) scale(1.35) rotate(12deg)', opacity: 1, offset: 0.4 },
                { transform: 'translate(' + dx + 'px,' + dy + 'px) scale(0.2) rotate(-10deg)', opacity: 0.3 }
            ], { duration: 850, easing: 'cubic-bezier(.5,0,.3,1)' });
            anim.onfinish = () => {
                clone.remove();
                collBtn.classList.remove('pulse'); void collBtn.offsetWidth; collBtn.classList.add('pulse');
            };
        }

        function sparkleBurst(el) {
            const r = el.getBoundingClientRect();
            for (let i = 0; i < 10; i++) {
                const s = document.createElement('div');
                s.className = 'magic-sparkle';
                const size = Math.random() * 8 + 4;
                s.style.cssText = 'width:' + size + 'px;height:' + size + 'px;left:' + (r.left + r.width / 2 + (Math.random() - 0.5) * r.width) + 'px;top:' +
                    (r.top + r.height / 2 + (Math.random() - 0.5) * r.height) + 'px;background:' + COLORS[i % COLORS.length];
                document.body.appendChild(s);
                setTimeout(() => s.remove(), 1000);
            }
        }

        function collect(el) {
            const id = el.dataset.id;
            if (found.indexOf(id) !== -1) return;
            found.push(id);
            storeSet(STORE_KEY, JSON.stringify(found));
            delete places[id];
            storeSet(PLACE_KEY, JSON.stringify(places));
            sparkleBurst(el);
            fly(el);
            delete heroEls[id];
            el.classList.add('gone');
            setTimeout(() => el.remove(), 900);
            updateCounter();
            hideHint();
            recordDone();
            if (found.length >= total) {
                toast('Вы нашли все стикеры! 🎉');
                setTimeout(openCollection, 1300);
            } else if (!Object.keys(heroEls).length) {
                if (currentWaveIds().length) {
                    toast('Вся пятёрка найдена! На сайте появились новые стикеры ✨');
                    setTimeout(() => { showWave(true); }, 1000);
                } else {
                    toast('Все стикеры на сегодня найдены! Новые появятся завтра ✨');
                    setTimeout(openCollection, 1500);
                    scheduleUnlock();
                }
            } else {
                toast('Нашёлся стикер: ' + el.dataset.name + '! Осталось найти ещё ' + Object.keys(heroEls).length);
            }
        }
        // Если посетитель играл раньше, уже найденные пятёрки засчитываются, а отсчёт «до завтра» идёт с его первого захода
        recordDone();
        if (storeGet(SEEN_KEY) === null) storeSet(SEEN_KEY, String(openCount()));   // красная точка только для новых пятёрок
        updateCounter();
        showWave(false);
        updateBadge();

        // Наступил новый день, пока страница открыта (или посетитель вернулся во вкладку): открываем стикеры
        let unlockTimer = null;
        function scheduleUnlock() {
            clearTimeout(unlockTimer);
            const wait = waitInfo();
            if (wait && wait.at) {
                const ms = Math.min(Math.max(wait.at - nowMs(), 0) + 1500, 2147000000);
                unlockTimer = setTimeout(() => checkUnlock(true), ms);
            }
        }
        function checkUnlock(announce) {
            recordDone();
            if (!Object.keys(heroEls).length && currentWaveIds().length) {
                showWave(true);
                if (announce) toast('Появились новые стикеры! ✨');
            }
            updateBadge();
            scheduleUnlock();
        }
        document.addEventListener('visibilitychange', () => { if (!document.hidden) checkUnlock(true); });
        scheduleUnlock();

        function hideHint() { hintEl.classList.remove('show'); storeSet('fairyHintSeen', '1'); }
        hintEl.addEventListener('click', hideHint);
        if (found.length === 0 && !storeGet('fairyHintSeen')) {
            setTimeout(() => hintEl.classList.add('show'), 2500);
            setTimeout(hideHint, 12000);
        }

        // =====================================================================
        // 3. СЛАЙДЕРЫ КНИГ, ПРОСМОТР КАРТИНОК, ФОРМА, ЭФФЕКТЫ
        // =====================================================================
        function initBook(box) {
            const stage = box.querySelector('.flip-stage');
            const book = box.querySelector('.flip-book');
            const leavesBox = box.querySelector('.fb-leaves');
            const elL = book.querySelector('.pg-left'), elR = book.querySelector('.pg-right');
            const castL = book.querySelector('.cast-l'), castR = book.querySelector('.cast-r');
            const urls = Array.from(box.querySelectorAll('.fb-src i')).map((i) => i.dataset.u);
            const zurls = Array.from(box.querySelectorAll('.fb-src i')).map((i) => i.dataset.z || i.dataset.u);   // крупная версия для «Увеличить»
            const N = urls.length;
            const dots = Array.from(box.querySelectorAll('.flip-dot'));
            const countEl = box.querySelector('.flip-count');
            const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const NS = 24;            // полос в листе: чем больше, тем плавнее изгиб
            const BEND = 1.9;         // изгиб листа, градусов на полосу
            const LIFT = 2;           // лист чуть приподнят над страницами, чтобы они не мерцали
            const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
            const rad = (d) => d * Math.PI / 180;
            let t = 0;                // 0 = закрыта, 1..N = разворот, N+1 = закрыта сзади
            let busy = false;
            let pw = 440;
            const live = { i: -1, p: 0 };   // какой лист сейчас в движении

            const url = (k) => 'url(' + JSON.stringify(urls[k - 1]) + ')';
            function setPg(el, k) {
                el.style.backgroundImage = k ? url(k) : '';
                el.classList.toggle('empty', !k);
            }

            // ----- листы -----
            function el(cls, parent) { const d = document.createElement('div'); d.className = cls; if (parent) parent.appendChild(d); return d; }
            function mkFaces(st, j, hinge) {
                const f = el('f', st), b = el('b', st);
                el('sh', f); el('sh', b);
                if (hinge) { el('hg', f); el('hg', b); }
                st.style.setProperty('--j', j);
                return { f, b };
            }
            const leaves = [];
            for (let i = 0; i <= N; i++) {
                const hard = i === 0 || i === N;
                const n = hard ? 1 : NS;
                const lf = el('lf st' + (hard ? ' hard' : ''), leavesBox);
                lf.style.setProperty('--n', n);
                if (i >= 1) lf.style.setProperty('--fi', url(i));
                if (i < N) lf.style.setProperty('--bi', url(i + 1));
                const strips = [lf];
                for (let j = 1; j < n; j++) strips.push(el('st', strips[j - 1]));
                strips[n - 1].classList.add('last');
                const faces = strips.map((s, j) => mkFaces(s, j, !hard && j === 0));
                if (i === 0) { faces[0].f.classList.add('cv'); faces[0].f.appendChild(box.querySelector('.tpl-cover').content.cloneNode(true)); }
                if (i === N) { faces[0].b.classList.add('cv'); faces[0].b.appendChild(box.querySelector('.tpl-back').content.cloneNode(true)); }
                leaves.push({ el: lf, strips, faces, hard, n });
            }

            // раскладка листа при прогрессе p: 0 = лежит справа, 1 = лежит слева
            function applyLeaf(i, p) {
                const lf = leaves[i];
                const th = -180 * p;
                const bend = lf.hard ? 0 : -BEND * Math.sin(Math.PI * p);
                let prev = 0, x = 0;
                for (let j = 0; j < lf.n; j++) {
                    const target = j === 0 ? th : th + j * bend;
                    const cum = Math.max(-180, Math.min(0, target));
                    const rel = cum - prev; prev = cum;
                    lf.strips[j].style.transform = (j === 0 ? 'translateZ(' + LIFT + 'px) ' : '') + 'rotateY(' + rel.toFixed(3) + 'deg)';
                    const sh = (0.32 * Math.abs(Math.sin(rad(cum)))).toFixed(3);
                    lf.faces[j].f.firstChild.style.opacity = sh;
                    lf.faces[j].b.firstChild.style.opacity = sh;
                    x += Math.cos(rad(cum)) / lf.n;
                }
                // тень от листа на страницах под ним
                const k = Math.min(1, Math.abs(Math.sin(rad(th))) * 2.4);
                castR.style.opacity = x > 0 ? (0.9 * k).toFixed(3) : 0;
                castR.style.transform = 'scaleX(' + Math.min(1, Math.max(0.001, x + 0.05)).toFixed(3) + ')';
                castL.style.opacity = x < 0 ? (0.9 * k).toFixed(3) : 0;
                castL.style.transform = 'scaleX(' + Math.min(1, Math.max(0.001, -x + 0.05)).toFixed(3) + ')';
                live.i = i; live.p = p;
                book.classList.add('turning');
                shift();
            }
            function shift() {
                let p0 = t >= 1 ? 1 : 0, pN = t >= N + 1 ? 1 : 0;
                if (live.i === 0) p0 = live.p;
                if (live.i === N) pN = live.p;
                const s = -25 * (1 - p0) + 25 * pN;
                book.style.transform = 'translateX(' + s.toFixed(3) + '%)';
            }
            function hideLeaves() { leaves.forEach((l) => { l.el.style.display = 'none'; }); castL.style.opacity = 0; castR.style.opacity = 0; }

            function label(tt) {
                if (tt === 0) return 'Обложка';
                if (tt >= N + 1) return 'Конец';
                return 'Разворот ' + tt + ' из ' + N;
            }
            function renderStable() {
                live.i = -1;
                book.classList.remove('turning');
                hideLeaves();
                const open = t >= 1 && t <= N;
                setPg(elL, open ? t : 0); setPg(elR, open ? t : 0);
                if (t === 0) { leaves[0].el.style.display = 'block'; applyLeaf(0, 0); }
                if (t === N + 1) { leaves[N].el.style.display = 'block'; applyLeaf(N, 1); }
                live.i = -1;
                book.classList.toggle('is-closed', t === 0);
                book.classList.toggle('is-open', open);
                book.classList.toggle('is-closed-back', t >= N + 1);
                book.classList.toggle('has-gutter', open);
                book.dataset.t = t;
                countEl.textContent = label(t);
                dots.forEach((d, k) => d.classList.toggle('on', t === k + 1));
                shift();
            }
            function prepare(i) {
                setPg(elL, i >= 1 ? i : 0);
                setPg(elR, i + 1 <= N ? i + 1 : 0);
                hideLeaves();
                leaves[i].el.style.display = 'block';
                book.classList.add('has-gutter');
            }
            function run(i, from, to, dur) {
                return new Promise((resolve) => {
                    const t0 = performance.now();
                    function frame(now) {
                        const k = dur > 0 && !reduce ? Math.min(1, (now - t0) / dur) : 1;
                        applyLeaf(i, from + (to - from) * ease(k));
                        if (k < 1) requestAnimationFrame(frame); else resolve();
                    }
                    requestAnimationFrame(frame);
                });
            }
            function sparkles() {
                if (reduce) return;
                const r = book.getBoundingClientRect();
                const cols = ['#fde68a', '#fbcfe8', '#a7f3d0', '#c4b5fd', '#ffffff'];
                for (let i = 0; i < 18; i++) {
                    const s = document.createElement('div');
                    s.className = 'magic-sparkle';
                    const size = Math.random() * 9 + 5;
                    s.style.cssText = 'width:' + size + 'px;height:' + size + 'px;left:' + (r.left + r.width * (0.5 + Math.random() * 0.5)) + 'px;top:' +
                        (r.top + r.height * (0.15 + Math.random() * 0.7)) + 'px;background:' + cols[i % cols.length];
                    document.body.appendChild(s);
                    setTimeout(() => s.remove(), 1000);
                }
            }
            async function step(dir, fast) {
                if (busy) return;
                if (dir > 0 && t >= N + 1) { dir = 0; }
                busy = true;
                try {
                    if (dir === 0) {                       // с задней обложки в начало: перелистываем всё назад быстро
                        while (t > 0) { await stepOnce(-1, true); }
                    } else {
                        await stepOnce(dir, fast);
                    }
                } finally { busy = false; }
            }
            async function stepOnce(dir, fast) {
                if ((dir > 0 && t > N) || (dir < 0 && t < 1)) return;
                const i = dir > 0 ? t : t - 1;
                const hard = leaves[i].hard;
                const dur = fast ? 320 : (hard ? 1100 : 900);
                if (t === 0 && dir > 0) sparkles();
                prepare(i);
                await run(i, dir > 0 ? 0 : 1, dir > 0 ? 1 : 0, dur);
                t += dir;
                renderStable();
            }
            async function goTo(target) {
                target = Math.max(0, Math.min(N + 1, target));
                if (busy || target === t) return;
                busy = true;
                try {
                    const dir = target > t ? 1 : -1;
                    const fast = Math.abs(target - t) > 1;
                    while (t !== target) await stepOnce(dir, fast);
                } finally { busy = false; }
            }
            function zoom() { window.openLightbox(zurls[Math.min(Math.max(t, 1), N) - 1]); }

            // ----- ввод: клик по половине, перетаскивание страницы, клавиши -----
            let drag = null;
            stage.addEventListener('pointerdown', (e) => {
                if (busy) return;
                drag = { x: e.clientX, y: e.clientY, mode: null, moved: false };
            });
            stage.addEventListener('pointermove', (e) => {
                if (!drag) return;
                const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
                if (!drag.mode) {
                    if (Math.abs(dx) < 8 || Math.abs(dx) < Math.abs(dy)) return;
                    const dir = dx < 0 ? 1 : -1;
                    if ((dir > 0 && t > N) || (dir < 0 && t < 1)) { drag = null; return; }
                    drag.moved = true;
                    drag.mode = { dir, i: dir > 0 ? t : t - 1 };
                    busy = true; prepare(drag.mode.i);
                    try { stage.setPointerCapture(e.pointerId); } catch (err) { /* не критично */ }
                }
                const m = drag.mode;
                const amount = Math.min(1, Math.max(0, (m.dir > 0 ? -dx : dx) / (pw * 1.5)));
                drag.p = m.dir > 0 ? amount : 1 - amount;
                applyLeaf(m.i, drag.p);
            });
            async function endDrag(cancel) {
                const d = drag; drag = null;
                if (!d) return;
                if (d.mode) {
                    const m = d.mode, p = d.p == null ? (m.dir > 0 ? 0 : 1) : d.p;
                    const complete = m.dir > 0 ? p > 0.4 : p < 0.6;
                    const to = m.dir > 0 ? (complete ? 1 : 0) : (complete ? 0 : 1);
                    await run(m.i, p, to, 380 * Math.max(0.4, Math.abs(to - p)));
                    if (complete) t += m.dir;
                    renderStable();
                    busy = false;
                    return;
                }
                if (cancel) return;
            }
            stage.addEventListener('pointerup', (e) => {
                const d = drag;
                if (d && !d.mode) {
                    drag = null;
                    const dx = e.clientX - d.x, dy = e.clientY - d.y;
                    if (Math.abs(dx) > 10 || Math.abs(dy) > 10) return;
                    const r = book.getBoundingClientRect();
                    const left = e.clientX < r.left + r.width / 2;
                    if (t === 0 || t >= N + 1) step(1); else step(left ? -1 : 1);
                    return;
                }
                endDrag(false);
            });
            stage.addEventListener('pointercancel', () => endDrag(true));
            stage.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowRight') { step(1); e.preventDefault(); }
                else if (e.key === 'ArrowLeft') { step(-1); e.preventDefault(); }
                else if (e.key === 'Enter' || e.key === ' ') { step(1); e.preventDefault(); }
            });
            box.addEventListener('click', (e) => {
                const act = e.target.closest('[data-act]');
                if (act) {
                    const a = act.dataset.act;
                    if (a === 'next') step(1); else if (a === 'prev') step(-1); else if (a === 'zoom') zoom();
                    return;
                }
                const dot = e.target.closest('.flip-dot');
                if (dot) goTo(parseInt(dot.dataset.spread, 10) + 1);
            });

            function measure() {
                pw = book.clientWidth / 2;
                book.style.setProperty('--pw', pw + 'px');
            }
            measure();
            if (window.ResizeObserver) new ResizeObserver(measure).observe(book); else window.addEventListener('resize', measure);
            renderStable();
        }
        document.querySelectorAll('.flipbook-wrap').forEach(initBook);

        const lightbox = document.getElementById('lightboxOverlay');
        const lightboxImg = document.getElementById('lightboxImage');
        window.openLightbox = function (src) {
            if (!src) return;
            lightboxImg.src = src;
            lightbox.classList.add('active');
            document.body.style.overflow = 'hidden';
        };
        window.closeLightbox = function () {
            lightbox.classList.remove('active');
            document.body.style.overflow = '';
            setTimeout(() => { lightboxImg.src = ''; }, 400);
        };
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') { if (!stickerView.hidden) { closeSticker(); return; } window.closeLightbox(); closeCollection(); }
        });

        // Форма связи: письмо уходит на почту художницы через сервер. Если почта на сервере
        // не настроена или сервер недоступен, открывается почтовая программа (или Telegram,
        // когда адрес почты не задан). window.fairyGo можно подменить, например в тестах.
        window.fairyGo = window.fairyGo || function (url, newTab) {
            if (newTab) window.open(url, '_blank', 'noopener'); else window.location.href = url;
        };
        window.sendContact = async function (event) {
            event.preventDefault();
            const form = event.target;
            const status = document.getElementById('formStatus');
            const btn = document.getElementById('formBtn');
            const email = form.dataset.email || '';
            const data = {
                name: form.elements.name.value.trim(),
                contact: form.elements.contact.value.trim(),
                message: form.elements.message.value.trim(),
                website: form.elements.website.value
            };
            const say = (text, cls) => { status.textContent = text; status.className = 'form-status' + (cls ? ' ' + cls : ''); };
            const fallback = () => {
                const body = 'Здравствуйте! Меня зовут ' + data.name + '.\n\n' + data.message + '\n\nКак со мной связаться: ' + data.contact;
                if (email) {
                    say('Открываем почтовую программу, останется нажать «Отправить».');
                    window.fairyGo('mailto:' + email + '?subject=' + encodeURIComponent('Сообщение с сайта') + '&body=' + encodeURIComponent(body), false);
                } else {
                    say('Открываем Telegram, останется нажать «Отправить».');
                    window.fairyGo('https://t.me/angry_miu?text=' + encodeURIComponent(body), true);
                }
            };
            btn.disabled = true;
            say('Отправляем…');
            try {
                const res = await fetch('/api/contact', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
                });
                if (res.ok) { say('Спасибо! Письмо отправлено, Анна-Анастасия скоро ответит ✨', 'ok'); form.reset(); }
                else if (res.status === 429) say('Вы отправили много сообщений подряд. Попробуйте чуть позже.', 'err');
                else if (res.status === 400) say('Проверьте, пожалуйста, что все поля заполнены.', 'err');
                else fallback();
            } catch (e) {
                fallback();
            } finally {
                btn.disabled = false;
            }
        };

        // Волшебная пыльца за курсором: звёзды, блёстки и светлячки.
        // Линия за мышкой не рисуется, чтобы не мешать рисовать.
        const trailCanvas = document.getElementById('trailCanvas');
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (window.matchMedia('(pointer: fine)').matches && !reduceMotion) {
            const tctx = trailCanvas.getContext('2d');
            const DUST_COLORS = ['#f59e0b', '#2dd4bf', '#ec4899', '#8b5cf6', '#fbbf24', '#60a5fa'];
            const parts = [];
            let tRaf = 0, lastX = null, lastY = 0, acc = 0, lastSpawn = 0;

            const resizeTrail = () => {
                const r = Math.min(window.devicePixelRatio || 1, 2);
                trailCanvas.width = Math.round(window.innerWidth * r);
                trailCanvas.height = Math.round(window.innerHeight * r);
                tctx.setTransform(r, 0, 0, r, 0, 0);
            };
            resizeTrail();
            window.addEventListener('resize', resizeTrail);

            // Звезда: n лучей, радиусы r и r*inner по очереди
            function starPath(x, y, r, inner, rays, rot) {
                tctx.beginPath();
                for (let i = 0; i < rays * 2; i++) {
                    const a = rot + i * Math.PI / rays;
                    const rad = i % 2 === 0 ? r : r * inner;
                    tctx.lineTo(x + Math.cos(a) * rad, y + Math.sin(a) * rad);
                }
                tctx.closePath();
            }
            function spawn(x, y, now) {
                const roll = Math.random();
                parts.push({
                    kind: roll < 0.45 ? 'sparkle' : roll < 0.75 ? 'star' : 'glow',
                    x: x + (Math.random() - 0.5) * 18, y: y + (Math.random() - 0.5) * 18,
                    vx: (Math.random() - 0.5) * 1.1, vy: -0.2 - Math.random() * 0.7,
                    rot: Math.random() * 3, spin: (Math.random() - 0.5) * 0.08,
                    size: 7 + Math.random() * 11, born: now, ttl: 1000 + Math.random() * 900,
                    tw: Math.random() * 6, color: DUST_COLORS[Math.floor(Math.random() * DUST_COLORS.length)]
                });
                if (parts.length > 90) parts.shift();
            }
            function frame(now) {
                tRaf = 0;
                tctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
                for (let i = parts.length - 1; i >= 0; i--) {
                    const p = parts[i];
                    const k = (now - p.born) / p.ttl;
                    if (k >= 1) { parts.splice(i, 1); continue; }
                    p.x += p.vx; p.y += p.vy; p.vy += 0.006; p.vx *= 0.995; p.rot += p.spin;
                    // появляется быстро, гаснет плавно, мерцает
                    const fade = k < 0.12 ? k / 0.12 : 1 - (k - 0.12) / 0.88;
                    const a = Math.max(0, fade) * (0.7 + 0.3 * Math.sin(now * 0.014 + p.tw));
                    const s = p.size * (0.55 + 0.45 * fade);
                    tctx.globalAlpha = a;
                    tctx.fillStyle = p.color;
                    tctx.shadowColor = p.color;
                    tctx.shadowBlur = 12;
                    if (p.kind === 'sparkle') { starPath(p.x, p.y, s, 0.16, 4, p.rot); tctx.fill(); }
                    else if (p.kind === 'star') { starPath(p.x, p.y, s * 0.8, 0.45, 5, p.rot); tctx.fill(); }
                    else { tctx.beginPath(); tctx.arc(p.x, p.y, s * 0.28, 0, Math.PI * 2); tctx.fill(); }
                }
                tctx.globalAlpha = 1; tctx.shadowBlur = 0;
                if (parts.length) tRaf = requestAnimationFrame(frame);
            }
            document.addEventListener('mousemove', (e) => {
                const now = performance.now();
                if (lastX !== null && !state.drawing) {
                    acc += Math.hypot(e.clientX - lastX, e.clientY - lastY);
                    let burst = 0;
                    while (acc > 26 && burst < 4) { acc -= 26; burst++; spawn(e.clientX, e.clientY, now); lastSpawn = now; }
                    if (acc > 26) acc = 0;
                    if (!burst && now - lastSpawn > 90 && acc > 3) { spawn(e.clientX, e.clientY, now); lastSpawn = now; acc = 0; }
                }
                lastX = e.clientX; lastY = e.clientY;
                if (parts.length && !tRaf) tRaf = requestAnimationFrame(frame);
            });
        }

        // Параллакс персонажа в первом экране
        if (window.matchMedia('(pointer: fine)').matches) {
            document.addEventListener('mousemove', (e) => {
                const rabbit = document.getElementById('rabbit-parallax');
                if (rabbit) {
                    const dx = (window.innerWidth / 2 - e.clientX) * 0.02;
                    const dy = (window.innerHeight / 2 - e.clientY) * 0.02;
                    rabbit.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
                }
            });
        }
    })();
    
