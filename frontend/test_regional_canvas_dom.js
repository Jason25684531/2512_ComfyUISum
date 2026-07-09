// [TEMP] Minimal fake-DOM smoke test for RegionalCanvasEditor's public API.
// No jsdom/playwright dependency (none installed) - hand-rolled stub covers
// just enough of the DOM surface the class touches (createElement/appendChild/
// classList/style/addEventListener/getBoundingClientRect).
// Run: node frontend/test_regional_canvas_dom.js
const assert = require("assert");

function makeFakeElement(tag) {
    const el = {
        tagName: tag.toUpperCase(),
        style: {},
        children: [],
        _listeners: {},
        classList: {
            _set: new Set(),
            add(...cls) { cls.forEach((c) => this._set.add(c)); },
            remove(...cls) { cls.forEach((c) => this._set.delete(c)); },
            toggle(cls, force) {
                if (force === undefined) { this._set.has(cls) ? this._set.delete(cls) : this._set.add(cls); }
                else if (force) this._set.add(cls);
                else this._set.delete(cls);
            },
            contains(cls) { return this._set.has(cls); },
        },
        appendChild(child) { this.children.push(child); return child; },
        addEventListener(evt, fn) { (this._listeners[evt] = this._listeners[evt] || []).push(fn); },
        removeEventListener() {},
        getBoundingClientRect() { return { left: 0, top: 0, width: 200, height: 300 }; },
        set innerHTML(v) { this.children = []; },
        get innerHTML() { return ""; },
        set textContent(v) { this._text = v; },
        get textContent() { return this._text || ""; },
        focusCount: 0,
        focus() { this.focusCount += 1; global.document.activeElement = this; },
    };
    return el;
}

global.document = {
    createElement: (tag) => makeFakeElement(tag),
    addEventListener() {},
    activeElement: { tagName: "BODY" },
};
global.window = {
    addEventListener() {},
    RegionalCanvasEditor: undefined,
};

const { RegionalCanvasEditor } = (() => {
    // regional-canvas.js assigns to window/module.exports but also declares
    // the class at module scope - re-require after stubbing document/window.
    delete require.cache[require.resolve("./regional-canvas.js")];
    const mod = require("./regional-canvas.js");
    return { RegionalCanvasEditor: global.window.RegionalCanvasEditor, mod };
})();

const mount = makeFakeElement("div");
const editor = new RegionalCanvasEditor(mount);
assert.strictEqual(editor.elements.length, 0);
console.log("[OK] constructor mounts without throwing, starts with 0 elements");

editor.setElementsData(JSON.stringify([
    { x: 0.1, y: 0.1, w: 0.2, h: 0.2, type: "obj", text: "", desc: "box A", palette: ["#ff0000"] },
]));
assert.strictEqual(editor.elements.length, 1);
console.log("[OK] setElementsData loads elements");

const json = editor.getElementsData();
const parsed = JSON.parse(json);
assert.strictEqual(parsed.length, 1);
assert.strictEqual(parsed[0].desc, "box A");
console.log("[OK] getElementsData round-trips");

editor.setAspect(1080, 1920);
assert.strictEqual(editor.stage.style.aspectRatio, "1080 / 1920");
console.log("[OK] setAspect updates stage CSS");

let result = editor.validate();
assert.strictEqual(result.valid, true);
console.log("[OK] validate() passes for a populated desc");

editor.elements.push({ x: 0, y: 0, w: 0.1, h: 0.1, type: "text", text: "", desc: "", palette: [] });
result = editor.validate();
assert.strictEqual(result.valid, false);
assert.strictEqual(result.index, 1);
console.log("[OK] validate() flags a text element with empty text");

editor.selectIndex(0);
assert.strictEqual(editor.selectedIndex, 0);
console.log("[OK] selectIndex updates selection");

editor.setBackgroundImage("/outputs/abc123.png");
assert.ok(editor.stage.style.backgroundImage.includes('url("/outputs/abc123.png")'));
console.log("[OK] setBackgroundImage sets stage CSS background");

editor.setBackgroundImage('/outputs/"evil.png');
assert.ok(!editor.stage.style.backgroundImage.includes('"evil'));
console.log("[OK] setBackgroundImage strips quote characters from the URL");

editor.setBackgroundImage(null);
assert.strictEqual(editor.stage.style.backgroundImage, "");
console.log("[OK] setBackgroundImage(null) clears the background");

// Regression test for the props-panel interaction bug: window-level pointerup
// (fired on every click anywhere on the page, e.g. clicking into a textarea)
// must NOT rebuild the props panel unless a drag was actually in progress.
editor.selectIndex(0);
const descNodeBefore = editor.propsEl.children[1];
descNodeBefore.focus();
assert.strictEqual(global.document.activeElement, descNodeBefore);
assert.strictEqual(editor._drag, null);
editor._onPointerUp();
assert.strictEqual(editor.propsEl.children[1], descNodeBefore, "props panel must not be rebuilt on a plain click (no active drag)");
assert.strictEqual(global.document.activeElement, descNodeBefore, "focus must survive a plain click's pointerup");
console.log("[OK] _onPointerUp() without an active drag does not rebuild the props panel or steal focus");

// A real drag (create-box) must still render on pointerup as before.
const elementsBefore = editor.elements.length;
editor._onStagePointerDown({ target: editor.stage, clientX: 10, clientY: 10 });
editor._onPointerMove({ clientX: 100, clientY: 150 });
editor._onPointerUp();
assert.strictEqual(editor.elements.length, elementsBefore + 1, "a completed create-drag must still add a new element");
assert.strictEqual(editor.selectedIndex, editor.elements.length - 1);
console.log("[OK] _onPointerUp() after a create-drag still commits the new bbox and re-renders");

console.log("All RegionalCanvasEditor fake-DOM smoke tests passed.");
