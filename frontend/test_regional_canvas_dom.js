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

console.log("All RegionalCanvasEditor fake-DOM smoke tests passed.");
