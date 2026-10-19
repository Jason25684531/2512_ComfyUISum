const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'frontend/dashboard.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'frontend/dashboard.js'), 'utf8');
new vm.Script(js);
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]));
for (const [, destination] of html.matchAll(/href="#([^/"][^"]*)"/g)) {
    assert.ok(ids.has(destination), `Missing destination: ${destination}`);
}
for (const [, source] of html.matchAll(/<script[^>]+src="([^"]+)"/g)) {
    assert.ok(fs.existsSync(path.join(root, 'frontend', source)), `Missing script: ${source}`);
}
for (const forbidden of ['/login.html', '/profile.html', '登入', '註冊', '會員中心', '/api/me', 'onclick=']) {
    assert.ok(!(html + js).includes(forbidden), `Forbidden legacy UI: ${forbidden}`);
}
assert.ok(!fs.existsSync(path.join(root, 'frontend/profile.html')));
assert.ok(!js.includes('localStorage'));

// Exercise the same conversion functions used by Hero and workspace payloads.
const context = vm.createContext({document: {addEventListener() {}}});
vm.runInContext(js, context);
const config = JSON.parse(fs.readFileSync(path.join(root, 'ComfyUIworkflow/config.json'), 'utf8'));
context.fixtureConfig = config;
vm.runInContext(`
    for (const [id, entry] of Object.entries(fixtureConfig)) {
        if (!id.startsWith('_')) toolConfig[id] = {choices: entry.choices || {}, defaults: entry.defaults || {}};
    }
`, context);
const evaluate = code => JSON.parse(JSON.stringify(vm.runInContext(code, context)));
assert.deepEqual(evaluate('RESOLUTIONS'), config._runtime.resolution_tiers);
assert.equal(evaluate("toolSize('image_gpt25_sunburst', '16:9', '1080p').size"), '1536x864');
assert.equal(vm.runInContext("toolSize('image_gpt25_sunburst', '16:9', '720p')", context), undefined);
assert.deepEqual(evaluate("toolSize('video_minimax_h3', '16:9', '1080p')"), {width: 1536, height: 864});
assert.deepEqual(evaluate("toolSize('video_minimax_h3', '9:16', '720p')"), {width: 576, height: 1024});
vm.runInContext("toolConfig.video_minimax_h3.choices = {width:[1920],height:[1088]}", context);
assert.equal(vm.runInContext("toolSize('video_minimax_h3', '9:16', '1080p')", context), undefined);
assert.equal(evaluate("ensureDraft('text_to_image').ratio"), '16:9');
assert.equal(evaluate("ensureDraft('text_to_image').tier"), '720p');
console.log('Dashboard parse and navigation smoke checks passed.');
