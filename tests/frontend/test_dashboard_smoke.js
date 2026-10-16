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
console.log('Dashboard parse and navigation smoke checks passed.');
