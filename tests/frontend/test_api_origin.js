const assert = require("assert");
const fs = require("fs");
const vm = require("node:vm");
const test = require("node:test");

// Only the origin-selection prelude; the rest of config.js fetches runtime config.
const prelude = fs.readFileSync("frontend/config.js", "utf8").split("window.API_URL =")[0];
const apiOrigin = (location) => new Function("window", `${prelude}return _defaultApiOrigin;`)({ location });

const page = (protocol, hostname, port = "") => ({
    protocol, hostname, port,
    origin: protocol === "file:" ? "null" : `${protocol}//${hostname}${port ? `:${port}` : ""}`,
});

assert.strictEqual(apiOrigin(page("https:", "demo.trycloudflare.com")), "https://demo.trycloudflare.com");
assert.strictEqual(apiOrigin(page("http:", "localhost", "5000")), "http://localhost:5000");
assert.strictEqual(apiOrigin(page("http:", "192.168.1.20", "5000")), "http://192.168.1.20:5000");
assert.strictEqual(apiOrigin(page("http:", "localhost", "5500")), "http://localhost:5000");
assert.strictEqual(apiOrigin(page("file:", "")), "http://localhost:5000");
console.log("api origin ok");

test("runtime config preserves the served page origin", async () => {
    for (const location of [page("http:", "127.0.0.1", "5000"), page("http:", "192.168.1.20", "5000"), page("https:", "demo.trycloudflare.com"), page("http:", "localhost", "5500")]) {
        const window = {location};
        vm.runInNewContext(fs.readFileSync("frontend/config.js", "utf8"), {
            window, console,
            fetch: async () => ({ok: true, json: async () => ({api_origin: "http://localhost:5000", workflow_catalog: []})})
        });
        await window.STUDIO_RUNTIME_READY;
        const expected = location.port === "5500" ? "http://localhost:5000" : location.origin;
        assert.strictEqual(window.API_URL, expected);
        assert.strictEqual(window.API_BASE_URL, `${expected}/api`);
        assert.strictEqual(window.STUDIO_RUNTIME_CONFIG.api_origin, expected);
    }
});
