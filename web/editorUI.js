// Shared Node 1.0 canvas editor for bounding boxes.
//
// The layout mirrors the Nodes 2.0 "创建边界框" panel, stacked vertically:
//   toolbar (网格 / 全部清除)  ->  canvas  ->  obj|文本 段控件
//   ->  文本  ->  描述  ->  调色板
// Data is the node's own editor_state shape, unchanged:
//   {x, y, width, height, metadata: {type, text, desc, palette}}
// x/y/width/height are canvas pixels; the canvas is drawn on a 0-1000 grid.

export const GRID = 1000;

const HANDLE_SIZE = 8;
const HANDLE_HIT = 10;
const MIN_BOX = 5;
const CLICK_PAD = 3;
const DEFAULT_COLOR = "#9d9d9d";
const SELECTED_COLOR = "#ffffff";

const COLORS = [
    "#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff",
    "#ff8000", "#8000ff", "#0080ff", "#ff0080", "#80ff00", "#ff8080",
    "#80ff80", "#8080ff", "#ffff80", "#ff80ff", "#80ffff",
];

const TYPE_LABELS = { obj: "物体", text: "文本" };

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export function emptyBox(type = "obj") {
    return { x: 0, y: 0, width: 0, height: 0, metadata: { type, text: "", desc: "", palette: [] } };
}

export function normalizeBox(raw) {
    if (!raw || typeof raw !== "object") return null;
    const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
    const meta = raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {};
    const type = meta.type === "text" ? "text" : "obj";
    let x = num(raw.x), y = num(raw.y), w = num(raw.width), h = num(raw.height);
    if (w < 0) { x += w; w = -w; }
    if (h < 0) { y += h; h = -h; }
    const palette = Array.isArray(meta.palette)
        ? meta.palette.filter((c) => typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c.trim())).slice(0, 5)
        : [];
    return {
        x, y, width: w, height: h,
        metadata: {
            type,
            text: type === "text" ? String(meta.text ?? "") : "",
            desc: String(meta.desc ?? ""),
            palette: palette.map((c) => c.trim().toUpperCase()),
        },
    };
}

// Accepts an array, a JSON string, or the {__value__: [...]} wrapper the frontend
// uses when a widget value is an array.
export function parseBoxes(value) {
    let data = value;
    if (typeof data === "string") {
        try {
            data = JSON.parse(data.replace(/^\uFEFF/, "").trim() || "[]");
        } catch (e) {
            return [];
        }
    }
    if (data && !Array.isArray(data) && typeof data === "object") {
        data = Array.isArray(data.__value__) ? data.__value__ : Array.isArray(data.boxes) ? data.boxes : [data];
    }
    if (!Array.isArray(data)) return [];
    return data.map(normalizeBox).filter(Boolean);
}

function el(tag, css, text) {
    const node = document.createElement(tag);
    if (css) node.style.cssText = css;
    if (text != null) node.textContent = text;
    return node;
}

function stopGestures(node) {
    for (const type of ["mousedown", "pointerdown", "wheel", "dblclick", "contextmenu", "keydown", "keyup"]) {
        node.addEventListener(type, (e) => e.stopPropagation());
    }
}

function iconButton(css) {
    const b = el("button", "display:flex;align-items:center;justify-content:center;gap:5px;cursor:pointer;" +
        "background:#333;color:#e8e8e8;border:1px solid #4d4d4d;border-radius:4px;" +
        "font:12px ui-sans-serif,system-ui,sans-serif;padding:4px 9px;white-space:nowrap;" + (css || ""));
    b.addEventListener("mousedown", (e) => e.stopPropagation());
    return b;
}

function fieldLabel(text) {
    return el("div", "color:#9a9a9a;font:11px ui-sans-serif,system-ui,sans-serif;margin:0 0 3px 1px;", text);
}

function textArea(placeholder, height) {
    const a = el("textarea",
        "width:100%;box-sizing:border-box;resize:none;background:#242424;color:#e8e8e8;border:1px solid #454545;" +
        "border-radius:5px;padding:6px 8px;font:12px ui-sans-serif,system-ui,sans-serif;line-height:1.45;" +
        `height:${height}px;`);
    a.placeholder = placeholder;
    a.spellcheck = false;
    a.addEventListener("mousedown", (e) => e.stopPropagation());
    a.addEventListener("wheel", (e) => e.stopPropagation());
    return a;
}

// Greedy character wrap: works for CJK too, where words have no spaces.
function wrapText(ctx, text, maxWidth) {
    const lines = [];
    for (const para of String(text).split("\n")) {
        if (!para) {
            lines.push("");
            continue;
        }
        let line = "";
        for (const ch of para) {
            const next = line + ch;
            if (line && ctx.measureText(next).width > maxWidth) {
                lines.push(line);
                line = ch;
            } else {
                line = next;
            }
        }
        if (line) lines.push(line);
    }
    return lines;
}

/**
 * @param {object} opts
 * @param {() => any} opts.getBoxes   current boxes (array / JSON string / __value__)
 * @param {(boxes: object[]) => void} opts.setBoxes  persist boxes
 * @param {() => [number, number]} opts.getDims       canvas width/height in pixels
 * @param {() => void} [opts.onChange]               after every commit
 */
export function createBoxEditor(opts) {
    const { getBoxes, setBoxes, getDims, onChange } = opts;

    let boxes = [];
    let selected = -1;
    let drag = null;
    let dpr = window.devicePixelRatio || 1;
    let showGrid = true;
    let lastKey = null;
    let primed = false;

    // ---------- shell ----------
    const container = el("div",
        "display:flex;flex-direction:column;width:100%;height:100%;box-sizing:border-box;overflow:hidden;" +
        "background:#1c1c1c;color:#e0e0e0;border:1px solid #3c3c3c;border-radius:6px;" +
        "font:12px ui-sans-serif,system-ui,sans-serif;");
    stopGestures(container);

    const toolbar = el("div",
        "display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px;flex:none;" +
        "background:#232323;border-bottom:1px solid #3a3a3a;overflow:hidden;");
    container.appendChild(toolbar);

    const gridBtn = iconButton();
    gridBtn.innerHTML = '<span style="font-size:13px;line-height:1">▦</span><span>网格</span>';
    gridBtn.title = "显示 / 隐藏网格";
    gridBtn.addEventListener("click", () => {
        showGrid = !showGrid;
        gridBtn.style.background = showGrid ? "#333" : "#2a2a2a";
        gridBtn.style.color = showGrid ? "#e8e8e8" : "#8a8a8a";
        draw();
    });
    toolbar.appendChild(gridBtn);

    const right = el("div", "display:flex;align-items:center;gap:6px;flex:none;");
    toolbar.appendChild(right);

    const addBtn = iconButton("padding:4px 8px;");
    addBtn.textContent = "＋";
    addBtn.title = "在画布中心添加一个框";
    right.appendChild(addBtn);

    const delBtn = iconButton("padding:4px 8px;");
    delBtn.textContent = "－";
    delBtn.title = "删除选中的框（Del）";
    right.appendChild(delBtn);

    const clearBtn = iconButton();
    clearBtn.innerHTML = '<span style="font-size:13px;line-height:1">⟲</span><span>全部清除</span>';
    clearBtn.title = "删除所有框";
    right.appendChild(clearBtn);

    const canvasWrap = el("div", "position:relative;width:100%;flex:1 1 320px;min-height:220px;background:#161616;overflow:hidden;");
    container.appendChild(canvasWrap);

    const canvas = el("canvas", "display:block;width:100%;height:100%;cursor:crosshair;outline:none;");
    canvas.tabIndex = 0;
    canvasWrap.appendChild(canvas);

    // ---------- segmented obj / 文本 ----------
    const segment = el("div", "display:flex;gap:6px;padding:6px;flex:none;background:#1c1c1c;");
    container.appendChild(segment);

    const segButtons = {};
    for (const type of ["obj", "text"]) {
        const b = el("button",
            "flex:1 1 0;cursor:pointer;padding:7px 0;border-radius:5px;border:1px solid #454545;" +
            "background:#2b2b2b;color:#c8c8c8;font:12px ui-sans-serif,system-ui,sans-serif;");
        b.textContent = TYPE_LABELS[type];
        b.addEventListener("mousedown", (e) => e.stopPropagation());
        b.addEventListener("click", () => {
            pull();
            if (selected < 0) return;
            const meta = boxes[selected].metadata;
            meta.type = type;
            if (type === "obj") meta.text = "";
            commit();
        });
        segment.appendChild(b);
        segButtons[type] = b;
    }

    // ---------- 文本 / 描述 ----------
    const textField = el("div", "padding:0 6px 6px;flex:none;");
    textField.appendChild(fieldLabel("文本"));
    const textIn = textArea("输入要渲染的文字…", 48);
    textField.appendChild(textIn);
    container.appendChild(textField);

    const descField = el("div", "padding:0 6px 6px;flex:none;");
    descField.appendChild(fieldLabel("描述"));
    const descIn = textArea("输入该框的描述…", 72);
    descField.appendChild(descIn);
    container.appendChild(descField);

    // ---------- 调色板 ----------
    const paletteRow = el("div", "display:flex;align-items:center;gap:6px;padding:0 6px 6px;flex:none;flex-wrap:wrap;");
    paletteRow.appendChild(el("span", "color:#9a9a9a;font:11px ui-sans-serif,system-ui,sans-serif;", "调色板"));
    container.appendChild(paletteRow);

    const colorPick = el("input",
        "width:22px;height:22px;padding:0;border:1px solid #4d4d4d;background:#242424;border-radius:4px;cursor:pointer;");
    colorPick.type = "color";
    colorPick.value = "#ff0000";
    colorPick.title = "添加色板颜色（最多 5 个）";
    colorPick.addEventListener("mousedown", (e) => e.stopPropagation());
    colorPick.addEventListener("input", () => {
        pull();
        if (selected < 0) return;
        const list = boxes[selected].metadata.palette;
        if (list.length >= 5) return;
        boxes[selected].metadata.palette = list.concat(colorPick.value.toUpperCase());
        commit();
    });
    paletteRow.appendChild(colorPick);

    const swatches = [];
    for (let i = 0; i < 5; i++) {
        const sw = el("span",
            "width:22px;height:22px;border-radius:4px;background:#242424;border:1px dashed #4d4d4d;" +
            "cursor:pointer;display:inline-block;box-sizing:border-box;");
        sw.addEventListener("mousedown", (e) => e.stopPropagation());
        sw.addEventListener("click", () => {
            pull();
            if (selected < 0) return;
            const list = boxes[selected].metadata.palette;
            if (!list[i]) return;
            const next = list.slice();
            next.splice(i, 1);
            boxes[selected].metadata.palette = next;
            commit();
        });
        paletteRow.appendChild(sw);
        swatches.push(sw);
    }

    const status = el("div",
        "padding:4px 8px 5px;font:11px ui-monospace,monospace;color:#7a7a7a;flex:none;" +
        "border-top:1px solid #2e2e2e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;");
    container.appendChild(status);

    // ---------- geometry ----------
    const dims = () => {
        const d = getDims?.() || [1024, 1024];
        return [Math.max(16, Number(d[0]) || 1024), Math.max(16, Number(d[1]) || 1024)];
    };
    const displaySize = () => {
        const r = canvas.getBoundingClientRect();
        return { w: r.width > 0 ? r.width : canvas.width / dpr, h: r.height > 0 ? r.height : canvas.height / dpr };
    };
    // Small inset so a box covering the whole canvas still shows its border and handles.
    const INSET = 5;
    const innerSize = () => {
        const d = displaySize();
        return { w: Math.max(8, d.w - INSET * 2), h: Math.max(8, d.h - INSET * 2), ox: INSET, oy: INSET };
    };
    const pxX = (g) => { const s = innerSize(); return s.ox + (g / GRID) * s.w; };
    const pxY = (g) => { const s = innerSize(); return s.oy + (g / GRID) * s.h; };
    const gridX = (px) => { const s = innerSize(); return clamp(((px - s.ox) / s.w) * GRID, 0, GRID); };
    const gridY = (py) => { const s = innerSize(); return clamp(((py - s.oy) / s.h) * GRID, 0, GRID); };

    const boxGrid = (b) => {
        const [W, H] = dims();
        return [(b.x / W) * GRID, (b.y / H) * GRID, ((b.x + b.width) / W) * GRID, ((b.y + b.height) / H) * GRID];
    };

    const setGrid = (b, g) => {
        const [W, H] = dims();
        const x1 = clamp(Math.round(g[0]), 0, GRID), y1 = clamp(Math.round(g[1]), 0, GRID);
        const x2 = clamp(Math.round(g[2]), 0, GRID), y2 = clamp(Math.round(g[3]), 0, GRID);
        b.x = Math.round((x1 / GRID) * W);
        b.y = Math.round((y1 / GRID) * H);
        b.width = Math.max(MIN_BOX, Math.round(((x2 - x1) / GRID) * W));
        b.height = Math.max(MIN_BOX, Math.round(((y2 - y1) / GRID) * H));
    };

    // ---------- state plumbing ----------
    function pull() {
        const next = parseBoxes(getBoxes());
        const key = JSON.stringify(next);
        if (primed && key === lastKey) return false;
        boxes = next;
        lastKey = key;
        primed = true;
        if (selected >= boxes.length) selected = -1;
        return true;
    }

    function commit() {
        lastKey = JSON.stringify(boxes);
        setBoxes(boxes.map((b) => ({
            x: b.x, y: b.y, width: b.width, height: b.height,
            metadata: {
                type: b.metadata.type,
                text: b.metadata.text,
                desc: b.metadata.desc,
                palette: b.metadata.palette.slice(),
            },
        })));
        draw();
        onChange?.();
    }

    // ---------- painting ----------
    function resize() {
        const r = canvas.getBoundingClientRect();
        dpr = window.devicePixelRatio || 1;
        const w = Math.max(1, Math.floor(r.width * dpr));
        const h = Math.max(1, Math.floor(r.height * dpr));
        if (canvas.width !== w || canvas.height !== h) {
            canvas.width = w;
            canvas.height = h;
        }
    }

    const handlePoints = (g) => {
        const x1 = pxX(g[0]), y1 = pxY(g[1]), x2 = pxX(g[2]), y2 = pxY(g[3]);
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        return [
            { name: "nw", x: x1, y: y1 }, { name: "n", x: mx, y: y1 }, { name: "ne", x: x2, y: y1 },
            { name: "e", x: x2, y: my }, { name: "se", x: x2, y: y2 }, { name: "s", x: mx, y: y2 },
            { name: "sw", x: x1, y: y2 }, { name: "w", x: x1, y: my },
        ];
    };

    function draw() {
        const c = canvas.getContext("2d");
        if (!c) return;
        // Never overwrite the in-progress drag with the backing widget's older value.
        if (!drag) pull();
        resize();
        const w = canvas.width / dpr, h = canvas.height / dpr;
        c.setTransform(dpr, 0, 0, dpr, 0, 0);

        c.fillStyle = "#161616";
        c.fillRect(0, 0, w, h);

        if (showGrid) {
            c.fillStyle = "#2f2f2f";
            const step = 24;
            for (let x = step / 2; x < w; x += step) {
                for (let y = step / 2; y < h; y += step) {
                    c.fillRect(x, y, 1.2, 1.2);
                }
            }
        }

        for (let i = 0; i < boxes.length; i++) {
            const b = boxes[i];
            const g = boxGrid(b);
            const x1 = pxX(g[0]), y1 = pxY(g[1]), x2 = pxX(g[2]), y2 = pxY(g[3]);
            const bw = Math.max(1, x2 - x1), bh = Math.max(1, y2 - y1);
            const color = b.metadata.palette[0] || DEFAULT_COLOR;
            const isSel = i === selected;

            c.strokeStyle = isSel ? SELECTED_COLOR : color;
            c.lineWidth = isSel ? 2 : 1.2;
            c.strokeRect(x1 + 0.5, y1 + 0.5, bw, bh);

            // palette strip along the top edge
            const pal = b.metadata.palette.slice(0, 5);
            if (pal.length > 1 && bw > 6) {
                const seg = bw / pal.length;
                for (let p = 0; p < pal.length; p++) {
                    c.fillStyle = pal[p];
                    c.fillRect(x1 + p * seg, y1, Math.max(1, seg), 2.5);
                }
            }

            // content: text in quotes then desc, clipped to the box
            if (bw > 14 && bh > 18) {
                c.save();
                c.beginPath();
                c.rect(x1 + 1, y1 + 1, Math.max(1, bw - 2), Math.max(1, bh - 2));
                c.clip();
                c.font = "11px ui-sans-serif,system-ui,sans-serif";
                c.textBaseline = "top";
                const body = b.metadata.type === "text" && b.metadata.text
                    ? `"${b.metadata.text}"${b.metadata.desc ? " — " + b.metadata.desc : ""}`
                    : b.metadata.desc;
                if (body) {
                    const lines = wrapText(c, body, Math.max(8, bw - 10));
                    c.fillStyle = "#a8a8a8";
                    let ty = y1 + 4;
                    // leave room for the number badge on the first line
                    for (const line of lines) {
                        if (ty > y2 - 6) break;
                        c.fillText(line, x1 + 4, ty);
                        ty += 14;
                    }
                }
                c.restore();
            }

            // number badge at the top-left corner, like the Node 2.0 canvas
            if (bw > 24) {
                const tag = String(i + 1).padStart(2, "0");
                c.font = "10px ui-monospace,monospace";
                const tw = c.measureText(tag).width + 6;
                c.fillStyle = isSel ? "#e8e8e8" : "#6e6e6e";
                c.fillRect(x1, y1, tw, 13);
                c.fillStyle = "#161616";
                c.textBaseline = "top";
                c.fillText(tag, x1 + 3, y1 + 2);
            }

            if (isSel) {
                c.fillStyle = "#ffffff";
                c.strokeStyle = "#111111";
                c.lineWidth = 1;
                for (const hd of handlePoints(g)) {
                    c.fillRect(hd.x - HANDLE_SIZE / 2, hd.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
                    c.strokeRect(hd.x - HANDLE_SIZE / 2, hd.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
                }
            }
        }

        refreshControls();
    }

    function hitHandle(px, py) {
        if (selected < 0) return null;
        for (const hd of handlePoints(boxGrid(boxes[selected]))) {
            if (Math.abs(px - hd.x) <= HANDLE_HIT && Math.abs(py - hd.y) <= HANDLE_HIT) return hd.name;
        }
        return null;
    }

    function hitBox(px, py) {
        const cx = gridX(px), cy = gridY(py);
        for (let i = boxes.length - 1; i >= 0; i--) {
            const g = boxGrid(boxes[i]);
            if (cx >= g[0] - CLICK_PAD && cx <= g[2] + CLICK_PAD && cy >= g[1] - CLICK_PAD && cy <= g[3] + CLICK_PAD) return i;
        }
        return -1;
    }

    function cursorFor(px, py) {
        const hd = hitHandle(px, py);
        if (hd) {
            if (hd === "nw" || hd === "se") return "nwse-resize";
            if (hd === "ne" || hd === "sw") return "nesw-resize";
            if (hd === "n" || hd === "s") return "ns-resize";
            return "ew-resize";
        }
        return hitBox(px, py) >= 0 ? "move" : "crosshair";
    }

    // ---------- controls reflect the selection ----------
    function refreshControls() {
        const b = selected >= 0 ? boxes[selected] : null;
        const off = !b;
        const type = b ? b.metadata.type : "obj";

        for (const t of ["obj", "text"]) {
            const on = !off && type === t;
            const btn = segButtons[t];
            btn.disabled = off;
            btn.style.background = on ? "#4b4b5e" : "#2b2b2b";
            btn.style.color = off ? "#666" : on ? "#ffffff" : "#c8c8c8";
            btn.style.borderColor = on ? "#6f6f8c" : "#454545";
        }

        textIn.disabled = off || type !== "text";
        textIn.style.opacity = textIn.disabled ? "0.55" : "1";
        descIn.disabled = off;
        descIn.style.opacity = off ? "0.55" : "1";
        colorPick.disabled = off || (b ? b.metadata.palette.length >= 5 : true);
        colorPick.style.opacity = colorPick.disabled ? "0.4" : "1";

        if (document.activeElement !== textIn) textIn.value = b ? b.metadata.text : "";
        if (document.activeElement !== descIn) descIn.value = b ? b.metadata.desc : "";

        for (let i = 0; i < swatches.length; i++) {
            const color = b ? b.metadata.palette[i] : null;
            swatches[i].style.background = color || "#242424";
            swatches[i].style.border = color ? "1px solid #555" : "1px dashed #4d4d4d";
            swatches[i].title = color ? `删除色板 ${i + 1}（${color}）` : "空色板";
        }

        if (!b) {
            status.textContent = `${boxes.length} 个框 · 未选中`;
            return;
        }
        const g = boxGrid(b);
        status.textContent = `${boxes.length} 个框 · #${selected + 1} · ${b.width}×${b.height} @ (${b.x}, ${b.y})` +
            ` · 网格 [${g.map((v) => Math.round(v)).join(", ")}]`;
    }

    // ---------- mutations ----------
    addBtn.addEventListener("click", () => {
        pull();
        const [W, H] = dims();
        const w = Math.round(W * 0.25), h = Math.round(H * 0.2);
        const b = emptyBox("obj");
        b.x = Math.round((W - w) / 2);
        b.y = Math.round((H - h) / 2);
        b.width = w;
        b.height = h;
        boxes.push(b);
        selected = boxes.length - 1;
        commit();
    });

    delBtn.addEventListener("click", () => {
        pull();
        if (selected < 0) return;
        boxes.splice(selected, 1);
        selected = -1;
        commit();
    });

    clearBtn.addEventListener("click", () => {
        pull();
        if (!boxes.length) return;
        boxes = [];
        selected = -1;
        commit();
    });

    textIn.addEventListener("input", () => {
        pull();
        if (selected < 0) return;
        boxes[selected].metadata.text = textIn.value;
        commit();
    });
    descIn.addEventListener("input", () => {
        pull();
        if (selected < 0) return;
        boxes[selected].metadata.desc = descIn.value;
        commit();
    });

    // ---------- pointer ----------
    const coords = (e) => {
        const r = canvas.getBoundingClientRect();
        return { px: e.clientX - r.left, py: e.clientY - r.top };
    };

    function onMove(e) {
        if (!drag) return;
        e.preventDefault();
        e.stopPropagation();
        const { px, py } = coords(e);
        const b = boxes[drag.index];
        if (!b) return;
        const ds = drag.display;
        if (!ds.w || !ds.h) return;
        const dx = ((px - drag.start.px) / ds.w) * GRID;
        const dy = ((py - drag.start.py) / ds.h) * GRID;
        const o = drag.grid;
        if (drag.mode === "create") {
            setGrid(b, [Math.min(o[0], o[0] + dx), Math.min(o[1], o[1] + dy), Math.max(o[0], o[0] + dx), Math.max(o[1], o[1] + dy)]);
        } else if (drag.mode === "move") {
            const bw = o[2] - o[0], bh = o[3] - o[1];
            const nx = clamp(o[0] + dx, 0, GRID - bw), ny = clamp(o[1] + dy, 0, GRID - bh);
            setGrid(b, [nx, ny, nx + bw, ny + bh]);
        } else {
            let [x1, y1, x2, y2] = o;
            const which = drag.mode.slice(7);
            if (which.includes("w")) x1 = clamp(o[0] + dx, 0, x2 - MIN_BOX);
            if (which.includes("e")) x2 = clamp(o[2] + dx, x1 + MIN_BOX, GRID);
            if (which.includes("n")) y1 = clamp(o[1] + dy, 0, y2 - MIN_BOX);
            if (which.includes("s")) y2 = clamp(o[3] + dy, y1 + MIN_BOX, GRID);
            setGrid(b, [x1, y1, x2, y2]);
        }
        draw();
    }

    function endDrag(e) {
        if (!drag) return;
        const wasCreate = drag.mode === "create";
        const index = drag.index;
        drag = null;
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", endDrag, true);
        if (e) { try { e.preventDefault(); } catch (err) { /* ignore */ } }
        const b = boxes[index];
        if (wasCreate && b && b.width <= MIN_BOX && b.height <= MIN_BOX) {
            boxes.splice(index, 1);
            selected = -1;
        } else if (selected >= boxes.length) {
            selected = -1;
        }
        commit();
    }

    function cleanupDrag() {
        if (!drag) return;
        drag = null;
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", endDrag, true);
        canvas.style.cursor = "default";
    }

    canvas.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        canvas.focus();
        cleanupDrag();
        pull();
        resize();
        const { px, py } = coords(e);
        const ds = displaySize();
        const hd = hitHandle(px, py);
        if (hd) {
            drag = { mode: "resize:" + hd, index: selected, start: { px, py }, grid: boxGrid(boxes[selected]), display: ds };
            window.addEventListener("mousemove", onMove, true);
            window.addEventListener("mouseup", endDrag, true);
            return;
        }
        const hit = hitBox(px, py);
        if (hit >= 0) {
            selected = hit;
            drag = { mode: "move", index: hit, start: { px, py }, grid: boxGrid(boxes[hit]), display: ds };
            window.addEventListener("mousemove", onMove, true);
            window.addEventListener("mouseup", endDrag, true);
            draw();
            return;
        }
        const b = emptyBox("obj");
        setGrid(b, [gridX(px), gridY(py), gridX(px), gridY(py)]);
        boxes.push(b);
        selected = boxes.length - 1;
        drag = { mode: "create", index: selected, start: { px, py }, grid: [gridX(px), gridY(py), gridX(px), gridY(py)], display: ds };
        window.addEventListener("mousemove", onMove, true);
        window.addEventListener("mouseup", endDrag, true);
        draw();
    });

    canvas.addEventListener("mousemove", (e) => {
        if (drag) return;
        const { px, py } = coords(e);
        canvas.style.cursor = cursorFor(px, py);
    });
    canvas.addEventListener("mouseleave", () => { if (!drag) canvas.style.cursor = "default"; });

    canvas.addEventListener("keydown", (e) => {
        pull();
        if (selected < 0) return;
        const b = boxes[selected];
        const step = e.shiftKey ? 10 : 1;
        if (e.key === "Delete" || e.key === "Backspace") {
            e.preventDefault();
            boxes.splice(selected, 1);
            selected = -1;
            commit();
            return;
        }
        const nudge = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
        if (!nudge) return;
        e.preventDefault();
        b.x = Math.max(0, b.x + nudge[0]);
        b.y = Math.max(0, b.y + nudge[1]);
        commit();
    });

    const ro = new ResizeObserver(() => draw());
    ro.observe(canvasWrap);
    const onBlur = () => cleanupDrag();
    window.addEventListener("blur", onBlur);

    return {
        container,
        canvas,
        draw,
        /** Re-read the backing widget (e.g. after configure / execute). */
        refresh() {
            primed = false;
            pull();
            draw();
        },
        /** Same as refresh but also repaints the controls. */
        reload() {
            selected = -1;
            primed = false;
            pull();
            draw();
        },
        destroy() {
            ro.disconnect();
            window.removeEventListener("blur", onBlur);
            cleanupDrag();
        },
    };
}
