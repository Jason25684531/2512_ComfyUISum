// [TEMP] Node self-check for RegionalCanvasEditor's pure logic (no DOM required).
// Run: node frontend/test_regional_canvas.js
const assert = require("assert");
const { clamp01, computeResize, canonicalizeElement, validateElements, sanitizeColor } = require("../../frontend/regional-canvas.js");

assert.strictEqual(clamp01(-0.5), 0);
assert.strictEqual(clamp01(1.5), 1);
assert.strictEqual(clamp01(0.3), 0.3);
console.log("[OK] clamp01");

assert.strictEqual(sanitizeColor("#ff00aa"), "#ff00aa");
assert.strictEqual(sanitizeColor("red"), "#888888");
assert.strictEqual(sanitizeColor(undefined), "#888888");
console.log("[OK] sanitizeColor rejects non-hex input");

const canon = canonicalizeElement({ x: 2, y: -1, w: 0.3, h: 0.4, type: "bad", palette: ["#fff000", "not-hex"] });
assert.deepStrictEqual(canon, { x: 1, y: 0, w: 0.3, h: 0.4, type: "obj", text: "", desc: "", palette: ["#fff000"] });
console.log("[OK] canonicalizeElement clamps coords, defaults bad type to obj, drops invalid hex");

const approxEqual = (actual, expected) => {
    for (const key of Object.keys(expected)) {
        assert.ok(Math.abs(actual[key] - expected[key]) < 1e-9, `${key}: ${actual[key]} != ${expected[key]}`);
    }
};

// resize from bottom-right corner: only w/h grow, x/y unchanged
let r = computeResize({ x: 0.2, y: 0.2, w: 0.3, h: 0.3 }, "br", 0.1, 0.1);
approxEqual(r, { x: 0.2, y: 0.2, w: 0.4, h: 0.4 });
console.log("[OK] computeResize br grows w/h only");

// resize from top-left corner: x/y move, w/h shrink accordingly
r = computeResize({ x: 0.2, y: 0.2, w: 0.3, h: 0.3 }, "tl", 0.1, 0.1);
approxEqual(r, { x: 0.3, y: 0.3, w: 0.2, h: 0.2 });
console.log("[OK] computeResize tl moves origin and shrinks size");

// resize cannot shrink below MIN_SIZE
r = computeResize({ x: 0.2, y: 0.2, w: 0.05, h: 0.05 }, "br", -1, -1);
assert.ok(r.w >= 0.02 && r.h >= 0.02);
console.log("[OK] computeResize enforces minimum size");

// resize cannot push box out of [0,1] bounds
r = computeResize({ x: 0.9, y: 0.9, w: 0.05, h: 0.05 }, "br", 0.5, 0.5);
assert.ok(r.x + r.w <= 1.0001 && r.y + r.h <= 1.0001);
console.log("[OK] computeResize clamps box within [0,1]");

let v = validateElements([{ type: "obj", desc: "a box", text: "" }]);
assert.strictEqual(v.valid, true);
v = validateElements([{ type: "obj", desc: "", text: "" }]);
assert.strictEqual(v.valid, false);
assert.strictEqual(v.index, 0);
v = validateElements([{ type: "text", desc: "x", text: "" }]);
assert.strictEqual(v.valid, false);
console.log("[OK] validateElements requires desc for obj and text for text");

console.log("All regional-canvas pure-logic tests passed.");
