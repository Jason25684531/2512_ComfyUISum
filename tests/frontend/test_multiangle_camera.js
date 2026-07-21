const assert = require("assert");
const fs = require("fs");
const { promptFor } = require("../../frontend/multiangle-camera.js");

assert.strictEqual(promptFor(0, 45, 5), "<sks> front view high-angle shot medium shot");
assert.ok(promptFor(22.5, 0, 5).includes("front-right quarter view"));
assert.ok(promptFor(0, -15, 5).includes("eye-level shot"));
assert.ok(promptFor(0, 0, 6).includes("close-up"));
const source = fs.readFileSync("frontend/multiangle-camera.js", "utf8");
assert.ok(source.includes("this.sliders = {}"));
assert.ok(source.includes("this.sliders[name].value = String(value)"));
console.log("Multi-angle prompt preview checks passed.");
