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
// View state lives in the hash router; localStorage only remembers dismissed workflow guides.
assert.deepEqual([...js.matchAll(/localStorage\.(\w+)\(`([^$]+)/g)].map(match => match[1] + ' ' + match[2]),
    ['getItem studio-guide-seen:', 'setItem studio-guide-seen:']);
assert.equal(js.split('localStorage').length - 1, 2);

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
assert.deepEqual(evaluate("toolSize('image_gpt25_sunburst', '16:9', '720p')"), {width: 1280, height: 720});
assert.deepEqual(evaluate("toolSize('image_gpt25_sunburst', '9:16', '1080p')"), {width: 1088, height: 1920});
for (const tier of Object.values(config._runtime.resolution_tiers)) for (const {width, height} of Object.values(tier)) {
    assert.ok(config.image_gpt25_sunburst.choices.custom_width.includes(width) && config.image_gpt25_sunburst.choices.custom_height.includes(height));
    assert.ok(width % 16 === 0 && height % 16 === 0 && width * height >= 655360, `Sunburst rejects ${width}x${height}`);
}
const presets = config.video_minimax_h3.choices.resolution_presets;
assert.equal(presets.length, 20);
for (const size of [...presets, {width: 1024, height: 576}, {width: 1920, height: 1088}]) {
    const error = vm.runInContext(`minimaxDimensionError(${JSON.stringify(size)})`, context);
    assert.equal(error, '', JSON.stringify(size));
}
assert.deepEqual({width: presets.at(-1).width, height: presets.at(-1).height}, {width: 1920, height: 1088});
for (const value of ['', 0, -32, 31, 608.5, 1080, 'bad', null, true]) {
    for (const name of ['width', 'height']) {
        assert.match(vm.runInContext(`minimaxDimensionError(${JSON.stringify({width: 608, height: 352, [name]: value})})`, context), /32/);
    }
}
assert.equal(evaluate("ensureDraft('video_minimax_h3').values.width"), 1344);
assert.equal(evaluate("ensureDraft('video_minimax_h3').values.height"), 768);
assert.equal(evaluate("ensureDraft('text_to_image').ratio"), '16:9');
assert.equal(evaluate("ensureDraft('text_to_image').tier"), '720p');
console.log('Dashboard parse and navigation smoke checks passed.');
