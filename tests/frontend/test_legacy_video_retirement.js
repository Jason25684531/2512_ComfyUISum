const assert = require("assert");
const fs = require("fs");

const dashboard = fs.readFileSync("frontend/dashboard.html", "utf8");
const script = fs.readFileSync("frontend/dashboard.js", "utf8");
const catalog = fs.readFileSync("frontend/config.js", "utf8");
for (const id of ["veo3_long_video", "t2v_veo3", "flf_veo3", "veo3MultiMode"]) {
    assert.ok(!(dashboard + script).includes(id), `${id} must not remain in Video Studio`);
}
for (const id of ["veo3_long_video", "t2v_veo3", "flf_veo3"]) {
    assert.ok(!catalog.includes(id), `${id} must not remain in the fallback catalog`);
}
assert.ok(script.includes("? 'ltx_i2v'"));
assert.ok(script.includes("payload.workflow = currentVideoTool"));
console.log("Legacy video workflow retirement checks passed.");
