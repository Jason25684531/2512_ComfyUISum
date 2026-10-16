const assert = require("assert");
const fs = require("fs");

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
