/**
 * RegionalCanvasEditor: BBox canvas editor for Ideogram4 regional-prompt workflow.
 * Pure Vanilla JS (Pointer Events), no dependencies. All user text renders via
 * textContent only; palette colors are hex-validated before being written to inline style.
 */

const HEX_COLOR_RE = /^#[0-9a-fA-F]{6}$/;
const MIN_SIZE = 0.02;
const DEFAULT_PALETTE = ["#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#f87171"];

function clamp01(v) {
    return Math.max(0, Math.min(1, v));
}

function sanitizeColor(color) {
    return typeof color === "string" && HEX_COLOR_RE.test(color) ? color : "#888888";
}

function canonicalizeElement(el) {
    return {
        x: clamp01(Number(el.x) || 0),
        y: clamp01(Number(el.y) || 0),
        w: clamp01(Number(el.w) || 0),
        h: clamp01(Number(el.h) || 0),
        type: el.type === "text" ? "text" : "obj",
        text: typeof el.text === "string" ? el.text : "",
        desc: typeof el.desc === "string" ? el.desc : "",
        palette: Array.isArray(el.palette) ? el.palette.filter((c) => HEX_COLOR_RE.test(c)) : [],
    };
}

// Resize math for a single corner drag. corner is one of tl/tr/bl/br.
function computeResize(box, corner, dx, dy) {
    let { x, y, w, h } = box;
    if (corner.includes("l")) {
        const newX = clamp01(x + dx);
        w = x + w - newX;
        x = newX;
    } else if (corner.includes("r")) {
        w = clamp01(x + w + dx) - x;
    }
    if (corner.includes("t")) {
        const newY = clamp01(y + dy);
        h = y + h - newY;
        y = newY;
    } else if (corner.includes("b")) {
        h = clamp01(y + h + dy) - y;
    }
    w = Math.max(MIN_SIZE, w);
    h = Math.max(MIN_SIZE, h);
    if (x + w > 1) x = 1 - w;
    if (y + h > 1) y = 1 - h;
    return { x, y, w, h };
}

function validateElements(elements) {
    for (let i = 0; i < elements.length; i++) {
        const el = elements[i];
        if (el.type === "obj" && !el.desc.trim()) {
            return { valid: false, index: i, message: `第 ${i + 1} 個區塊（obj）的 desc 不可為空` };
        }
        if (el.type === "text" && !el.text.trim()) {
            return { valid: false, index: i, message: `第 ${i + 1} 個區塊（text）的 text 不可為空` };
        }
    }
    return { valid: true, index: null, message: "" };
}

class RegionalCanvasEditor {
    constructor(mountEl) {
        this.mountEl = mountEl;
        this.elements = [];
        this.selectedIndex = null;
        this.aspect = { w: 1080, h: 1920 };
        this._drag = null;
        this._onKeyDown = this._onKeyDown.bind(this);
        this._buildDom();
        document.addEventListener("keydown", this._onKeyDown);
    }

    _buildDom() {
        this.mountEl.innerHTML = "";
        this.root = document.createElement("div");
        this.root.style.cssText = "display:flex;gap:12px;width:100%;height:100%;align-items:flex-start;justify-content:center;";

        this.stageWrap = document.createElement("div");
        this.stageWrap.style.cssText = "position:relative;max-width:480px;width:100%;flex-shrink:0;";
        this.stage = document.createElement("div");
        this.stage.style.cssText = "position:relative;width:100%;background:#111827;border:1px solid #333;overflow:hidden;touch-action:none;";
        this.stageWrap.appendChild(this.stage);

        this.sidebar = document.createElement("div");
        this.sidebar.style.cssText = "width:220px;max-height:60vh;overflow-y:auto;display:flex;flex-direction:column;gap:8px;";
        this.listEl = document.createElement("div");
        this.propsEl = document.createElement("div");
        this.sidebar.appendChild(this.listEl);
        this.sidebar.appendChild(this.propsEl);

        this.root.appendChild(this.stageWrap);
        this.root.appendChild(this.sidebar);
        this.mountEl.appendChild(this.root);

        this._applyAspect();
        this.stage.addEventListener("pointerdown", (e) => this._onStagePointerDown(e));
        window.addEventListener("pointermove", (e) => this._onPointerMove(e));
        window.addEventListener("pointerup", () => this._onPointerUp());

        this._render();
    }

    _applyAspect() {
        this.stage.style.aspectRatio = `${this.aspect.w} / ${this.aspect.h}`;
    }

    setAspect(w, h) {
        this.aspect = { w, h };
        this._applyAspect();
    }

    // 將上一次生成結果以半透明方式疊在畫布底層，方便比對 bbox 落點；不影響 bbox 互動層
    setBackgroundImage(url) {
        if (!url) {
            this.stage.style.backgroundImage = "";
            return;
        }
        const safeUrl = String(url).replace(/["'\\]/g, "");
        this.stage.style.backgroundImage = `linear-gradient(rgba(17,24,39,0.55), rgba(17,24,39,0.55)), url("${safeUrl}")`;
        this.stage.style.backgroundSize = "cover";
        this.stage.style.backgroundPosition = "center";
    }

    getElementsData() {
        return JSON.stringify(this.elements.map(canonicalizeElement));
    }

    setElementsData(raw) {
        let parsed = [];
        try {
            parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        } catch {
            parsed = [];
        }
        this.elements = Array.isArray(parsed) ? parsed.map(canonicalizeElement) : [];
        this.selectedIndex = null;
        this._render();
    }

    validate() {
        return validateElements(this.elements);
    }

    selectIndex(index) {
        this.selectedIndex = index;
        this._render();
    }

    _pointerToNorm(e) {
        const rect = this.stage.getBoundingClientRect();
        return {
            x: clamp01((e.clientX - rect.left) / rect.width),
            y: clamp01((e.clientY - rect.top) / rect.height),
        };
    }

    _onStagePointerDown(e) {
        if (e.target !== this.stage) return; // clicks on bboxes/handles are handled by their own listeners
        const start = this._pointerToNorm(e);
        this.selectedIndex = null;
        this._drag = { mode: "create", start };
        this._render();
    }

    _onBoxPointerDown(e, index) {
        e.stopPropagation();
        this.selectedIndex = index;
        const start = this._pointerToNorm(e);
        const box = this.elements[index];
        this._drag = { mode: "move", index, start, origin: { x: box.x, y: box.y } };
        this._render();
    }

    _onHandlePointerDown(e, index, corner) {
        e.stopPropagation();
        this.selectedIndex = index;
        const start = this._pointerToNorm(e);
        const box = this.elements[index];
        this._drag = { mode: "resize", index, corner, start, origin: { ...box } };
    }

    _onPointerMove(e) {
        if (!this._drag) return;
        const cur = this._pointerToNorm(e);
        const dx = cur.x - this._drag.start.x;
        const dy = cur.y - this._drag.start.y;

        if (this._drag.mode === "create") {
            const x = Math.min(this._drag.start.x, cur.x);
            const y = Math.min(this._drag.start.y, cur.y);
            const w = Math.abs(cur.x - this._drag.start.x);
            const h = Math.abs(cur.y - this._drag.start.y);
            this._drag.preview = { x, y, w, h };
            this._render();
        } else if (this._drag.mode === "move") {
            const box = this.elements[this._drag.index];
            box.x = clamp01(Math.min(1 - box.w, Math.max(0, this._drag.origin.x + dx)));
            box.y = clamp01(Math.min(1 - box.h, Math.max(0, this._drag.origin.y + dy)));
            this._render();
        } else if (this._drag.mode === "resize") {
            const updated = computeResize(this._drag.origin, this._drag.corner, dx, dy);
            Object.assign(this.elements[this._drag.index], updated);
            this._render();
        }
    }

    _onPointerUp() {
        if (this._drag && this._drag.mode === "create" && this._drag.preview) {
            const { x, y, w, h } = this._drag.preview;
            if (w > MIN_SIZE && h > MIN_SIZE) {
                const palette = [DEFAULT_PALETTE[this.elements.length % DEFAULT_PALETTE.length]];
                this.elements.push(canonicalizeElement({ x, y, w, h, type: "obj", text: "", desc: "", palette }));
                this.selectedIndex = this.elements.length - 1;
            }
        }
        this._drag = null;
        this._render();
    }

    _onKeyDown(e) {
        if ((e.key === "Delete" || e.key === "Backspace") && this.selectedIndex !== null) {
            if (document.activeElement && ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
            this.elements.splice(this.selectedIndex, 1);
            this.selectedIndex = null;
            this._render();
        }
    }

    _deleteIndex(index) {
        this.elements.splice(index, 1);
        if (this.selectedIndex === index) this.selectedIndex = null;
        else if (this.selectedIndex > index) this.selectedIndex -= 1;
        this._render();
    }

    _render() {
        this._renderStage();
        this._renderList();
        this._renderProps();
    }

    _renderStage() {
        this.stage.innerHTML = "";
        this.elements.forEach((el, index) => {
            const color = sanitizeColor(el.palette[0]);
            const selected = index === this.selectedIndex;
            const box = document.createElement("div");
            box.style.cssText = `position:absolute;left:${el.x * 100}%;top:${el.y * 100}%;width:${el.w * 100}%;height:${el.h * 100}%;box-sizing:border-box;border:2px solid ${selected ? "#f97316" : color};background:${color}22;cursor:move;`;
            box.addEventListener("pointerdown", (e) => this._onBoxPointerDown(e, index));

            const label = document.createElement("div");
            label.style.cssText = `position:absolute;top:0;left:0;background:${color};color:#111;font-size:11px;padding:1px 4px;max-width:100%;overflow:hidden;white-space:nowrap;`;
            label.textContent = `${index + 1}. ${el.type === "text" ? el.text : el.desc}`;
            box.appendChild(label);

            if (selected) {
                ["tl", "tr", "bl", "br"].forEach((corner) => {
                    const handle = document.createElement("div");
                    const top = corner.includes("t") ? "-4px" : "auto";
                    const bottom = corner.includes("b") ? "-4px" : "auto";
                    const left = corner.includes("l") ? "-4px" : "auto";
                    const right = corner.includes("r") ? "-4px" : "auto";
                    handle.style.cssText = `position:absolute;top:${top};bottom:${bottom};left:${left};right:${right};width:8px;height:8px;background:#f97316;cursor:${corner === "tl" || corner === "br" ? "nwse-resize" : "nesw-resize"};`;
                    handle.addEventListener("pointerdown", (e) => this._onHandlePointerDown(e, index, corner));
                    box.appendChild(handle);
                });
            }
            this.stage.appendChild(box);
        });

        if (this._drag && this._drag.mode === "create" && this._drag.preview) {
            const { x, y, w, h } = this._drag.preview;
            const preview = document.createElement("div");
            preview.style.cssText = `position:absolute;left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%;border:2px dashed #22d3ee;pointer-events:none;`;
            this.stage.appendChild(preview);
        }
    }

    _renderList() {
        this.listEl.innerHTML = "";
        this.elements.forEach((el, index) => {
            const row = document.createElement("div");
            row.style.cssText = `display:flex;align-items:center;gap:6px;padding:4px;border-radius:6px;cursor:pointer;background:${index === this.selectedIndex ? "#374151" : "transparent"};`;
            row.addEventListener("click", () => this.selectIndex(index));

            const swatch = document.createElement("span");
            swatch.style.cssText = `width:10px;height:10px;border-radius:2px;flex-shrink:0;background:${sanitizeColor(el.palette[0])};`;
            row.appendChild(swatch);

            const text = document.createElement("span");
            text.style.cssText = "flex:1;font-size:12px;color:#e5e7eb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
            text.textContent = `${index + 1}. ${el.type === "text" ? el.text : el.desc || "(未命名)"}`;
            row.appendChild(text);

            const del = document.createElement("button");
            del.textContent = "×";
            del.style.cssText = "color:#f87171;background:none;border:none;cursor:pointer;font-size:14px;";
            del.addEventListener("click", (e) => {
                e.stopPropagation();
                this._deleteIndex(index);
            });
            row.appendChild(del);

            this.listEl.appendChild(row);
        });
    }

    _renderProps() {
        this.propsEl.innerHTML = "";
        if (this.selectedIndex === null || !this.elements[this.selectedIndex]) return;
        const el = this.elements[this.selectedIndex];

        const typeRow = document.createElement("div");
        typeRow.style.cssText = "display:flex;gap:4px;";
        ["obj", "text"].forEach((t) => {
            const btn = document.createElement("button");
            btn.textContent = t;
            btn.style.cssText = `flex:1;padding:4px;font-size:12px;border-radius:6px;border:1px solid #374151;background:${el.type === t ? "#0891b2" : "transparent"};color:#e5e7eb;cursor:pointer;`;
            btn.addEventListener("click", () => {
                el.type = t;
                this._render();
            });
            typeRow.appendChild(btn);
        });
        this.propsEl.appendChild(typeRow);

        const descInput = document.createElement("textarea");
        descInput.placeholder = "desc（obj 描述）";
        descInput.value = el.desc;
        descInput.style.cssText = "width:100%;margin-top:6px;font-size:12px;padding:4px;background:#111827;border:1px solid #374151;border-radius:6px;color:#e5e7eb;";
        descInput.addEventListener("input", () => {
            el.desc = descInput.value;
            this._renderStage();
            this._renderList();
        });
        this.propsEl.appendChild(descInput);

        if (el.type === "text") {
            const textInput = document.createElement("textarea");
            textInput.placeholder = "text（顯示文字）";
            textInput.value = el.text;
            textInput.style.cssText = descInput.style.cssText;
            textInput.addEventListener("input", () => {
                el.text = textInput.value;
                this._renderStage();
                this._renderList();
            });
            this.propsEl.appendChild(textInput);
        }

        const paletteRow = document.createElement("div");
        paletteRow.style.cssText = "display:flex;gap:4px;flex-wrap:wrap;margin-top:6px;align-items:center;";
        el.palette.forEach((color, ci) => {
            const chip = document.createElement("span");
            chip.style.cssText = `display:inline-flex;align-items:center;gap:2px;background:#1f2937;border-radius:4px;padding:2px 4px;`;
            const sw = document.createElement("span");
            sw.style.cssText = `width:12px;height:12px;border-radius:2px;background:${sanitizeColor(color)};`;
            const rm = document.createElement("button");
            rm.textContent = "×";
            rm.style.cssText = "color:#f87171;background:none;border:none;cursor:pointer;font-size:11px;";
            rm.addEventListener("click", () => {
                el.palette.splice(ci, 1);
                this._render();
            });
            chip.appendChild(sw);
            chip.appendChild(rm);
            paletteRow.appendChild(chip);
        });
        const colorPicker = document.createElement("input");
        colorPicker.type = "color";
        colorPicker.style.cssText = "width:20px;height:20px;padding:0;border:none;";
        colorPicker.addEventListener("change", () => {
            if (HEX_COLOR_RE.test(colorPicker.value)) {
                el.palette.push(colorPicker.value);
                this._render();
            }
        });
        paletteRow.appendChild(colorPicker);
        this.propsEl.appendChild(paletteRow);
    }
}

if (typeof window !== "undefined") {
    window.RegionalCanvasEditor = RegionalCanvasEditor;
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { clamp01, computeResize, canonicalizeElement, validateElements, sanitizeColor };
}
