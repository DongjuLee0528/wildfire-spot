import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import readline from 'node:readline';

const input = readline.createInterface({ input: process.stdin, terminal: false });
const pending = [];
let waiting, stopping = false, startupDone = false, cleanupPromise, watchdog;
let vite, browserServer, browser, page, fixtureUrl, renderer;
let writes = 0, navigations = 0;
const errors = [];
const reply = (event, data = {}) => process.stdout.write(JSON.stringify({ event, ...data }) + '\n');
const next = () => stopping ? Promise.resolve(null) : pending.length ? Promise.resolve(pending.shift()) :
    new Promise(resolve => { waiting = resolve; });
function requestStop() {
    if (stopping) return;
    stopping = true;
    if (waiting) { waiting(null); waiting = null; }
    watchdog = setTimeout(() => {
        browserServer?.process().kill('SIGKILL');
        process.exit(2);
    }, 18000);
    watchdog.unref();
    if (startupDone) void cleanup().catch(() => { process.exitCode = 1; });
}
input.on('line', line => {
    try {
        assert.ok(line.length <= 8192, 'Command limit');
        const value = JSON.parse(line);
        if (waiting) { const resolve = waiting; waiting = null; resolve(value); }
        else { assert.ok(pending.length < 8, 'Command queue limit'); pending.push(value); }
    } catch { errors.push('Invalid command'); requestStop(); }
});
input.on('close', requestStop);
process.on('SIGTERM', requestStop);
process.on('SIGINT', requestStop);

async function cleanup() {
    if (cleanupPromise) return cleanupPromise;
    stopping = true;
    cleanupPromise = (async () => {
        const failed = [];
        try { await browser?.close(); } catch { failed.push('Browser close'); }
        try { await browserServer?.close(); }
        catch { await browserServer?.kill(); failed.push('Browser server close'); }
        try { await vite?.close(); } catch { failed.push('Vite close'); }
        input.close();
        clearTimeout(watchdog);
        assert.equal(writes, 0, 'No control or other API writes');
        assert.deepEqual(errors, [], 'No JavaScript errors or unexpected navigation');
        assert.deepEqual(failed, [], 'Cleanup completed without errors');
    })();
    return cleanupPromise;
}

async function main() {
    const config = await next();
    if (!config) return;
    const backend = new URL(config.baseUrl);
    assert.equal(backend.protocol, 'http:'); assert.equal(backend.hostname, '127.0.0.1');
    assert.ok(backend.port); assert.equal(backend.pathname, '/'); assert.ok(!backend.username && !backend.password && !backend.search && !backend.hash);
    const root = await fs.realpath(fileURLToPath(new URL('../..', import.meta.url)));
    const web = path.join(root, 'web');
    const { createServer } = await import(pathToFileURL(path.join(web, 'node_modules/vite/dist/node/index.js')));
    const { default: react } = await import(pathToFileURL(path.join(web, 'node_modules/@vitejs/plugin-react/dist/index.js')));
    const { chromium } = await import(pathToFileURL(process.env.POINT_CLOUD_PLAYWRIGHT_MODULE));
    if (stopping) return;
    const fixturePlugin = { name: 'point-cloud-test-page', configureServer(server) {
        server.middlewares.use(async (req, res, done) => {
        if (req.url !== '/__pointcloud-test') return done();
        try {
            const html = await server.transformIndexHtml(req.url, `<!doctype html><html><head></head><body>
<div id="fixture" style="width:600px;max-width:95vw;margin:20px"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';
import PointCloudPanel from '/src/components/PointCloudPanel.jsx';import '/src/App.css';
const root=createRoot(document.getElementById('fixture'));
window.mountPanel=id=>root.render(React.createElement(React.StrictMode,null,React.createElement(PointCloudPanel,{key:id,deviceId:id})));
window.unmountPanel=()=>root.unmount();
</script></body></html>`);
            res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html);
        } catch { res.writeHead(500); res.end('Fixture page unavailable'); }
    });
    } };
    vite = await createServer({ configFile: false, root: web, logLevel: 'silent', plugins: [react(), fixturePlugin],
        cacheDir: path.join(config.directory, 'vite-cache'), optimizeDeps: { include: ['react', 'react-dom/client'] },
        server: { host: '127.0.0.1', port: 0, hmr: false, proxy: { '/api': config.baseUrl } } });
    if (stopping) return;
    await vite.listen();
    if (stopping) return;
    fixtureUrl = `http://127.0.0.1:${vite.httpServer.address().port}/__pointcloud-test`;
    browserServer = await chromium.launchServer({ executablePath: process.env.POINT_CLOUD_CHROME,
        host: '127.0.0.1', port: 0, headless: true, timeout: 15000,
        args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    if (stopping) return;
    browser = await chromium.connect(browserServer.wsEndpoint(), { timeout: 5000 });
    if (stopping) return;
    const context = await browser.newContext({ locale: 'en-US' });
    await context.route('**/*', route => {
        const request = route.request(), url = new URL(request.url());
        if (url.hostname !== '127.0.0.1') { errors.push('External browser request blocked'); return route.abort(); }
        if (url.pathname.startsWith('/api/') && (request.method() !== 'GET' || !/^\/api\/devices\/[a-zA-Z0-9-]+\/point-cloud\/stream$/.test(url.pathname))) {
            writes++; return route.abort();
        }
        return route.continue();
    });
    await context.addInitScript(({ token, origin }) => {
        if (location.origin !== origin) return;
        localStorage.setItem('jwt_token', token);
        window.gpuSamples = new WeakMap();
        const proto = WebGLRenderingContext.prototype, upload = proto.bufferSubData, draw = proto.drawArrays;
        const sample = gl => {
            if (!window.gpuSamples.has(gl.canvas)) window.gpuSamples.set(gl.canvas, { uploads: 0, count: 0, drawn: 0, first: [], last: [] });
            return window.gpuSamples.get(gl.canvas);
        };
        proto.bufferSubData = function(...args) {
            const data = args[2], current = sample(this);
            current.uploads++; current.count = data.length / 3;
            current.first = Array.from(data.subarray(0, 12)); current.last = Array.from(data.subarray(-3));
            return upload.apply(this, args);
        };
        proto.drawArrays = function(mode, first, count) {
            if (mode === this.POINTS) sample(this).drawn = count;
            return draw.call(this, mode, first, count);
        };
    }, { token: config.token, origin: new URL(fixtureUrl).origin });
    page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('framenavigated', frame => { if (frame === page.mainFrame() && ++navigations > 1 && !stopping) errors.push('Unexpected page navigation'); });
    await page.goto(fixtureUrl, { timeout: 15000 });
    await page.waitForFunction(() => typeof window.mountPanel === 'function');
    await page.evaluate(id => window.mountPanel(id), config.deviceId);
    await expectFrame('normal');
    renderer = await page.locator('canvas').evaluate(canvas => {
        const gl = canvas.getContext('webgl'), extension = gl.getExtension('WEBGL_debug_renderer_info');
        return gl.getParameter(extension ? extension.UNMASKED_RENDERER_WEBGL : gl.RENDERER);
    });
    assert.match(renderer, /SwiftShader/i, 'Software renderer evidence');
    startupDone = true;
    if (stopping) return;
    reply('ready', { renderer, browserPid: browserServer.process().pid });
    for (;;) {
        const command = await next();
        if (!command || stopping) break;
        if (command.command === 'stop') break;
        if (['normal', 'empty', 'max', 'recovered'].includes(command.command)) await expectFrame(command.command);
        else if (command.command === 'clear') await expectClear();
        else if (command.command === 'isolation') {
            const statuses = await page.evaluate(async ({ otherToken, deviceToken, deviceId }) => {
                const url = `/api/devices/${deviceId}/point-cloud/stream`;
                const result = [];
                for (const token of [otherToken, deviceToken]) {
                    const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, redirect: 'error' });
                    result.push(response.status); await response.body?.cancel();
                }
                return result;
            }, config);
            assert.deepEqual(statuses, [404, 403]);
        } else if (command.command === 'foreign') {
            const old = await page.locator('canvas').elementHandle();
            await page.evaluate(id => window.mountPanel(id), config.otherDeviceId);
            await page.getByText('Point-cloud HTTP 404', { exact: true }).waitFor({ timeout: 5000 });
            assert.equal(await old.evaluate(canvas => canvas.isConnected), false); await old.dispose();
            await expectClear();
        } else if (command.command === 'back') {
            const old = await page.locator('canvas').elementHandle();
            await page.evaluate(id => window.mountPanel(id), config.deviceId);
            await page.waitForFunction(canvas => !canvas.isConnected, old, { timeout: 5000 });
            await expectFrame('recovered');
            assert.equal(await old.evaluate(canvas => canvas.isConnected), false); await old.dispose();
        } else throw new Error('Unknown browser command');
        assert.deepEqual(errors, []); reply(command.command);
    }
    await cleanup();
    reply('stopped');
}

async function expectFrame(kind) {
    const count = kind === 'empty' ? 0 : kind === 'max' ? 12000 : 4;
    const baseline = await page.evaluate(() => window.gpuSamples.get(document.querySelector('canvas'))?.uploads ?? 0);
    await page.waitForFunction(({ count, baseline }) => {
        const canvas = document.querySelector('canvas'), current = canvas && window.gpuSamples.get(canvas);
        return current && current.uploads > baseline && current.count === count && current.drawn === count &&
            document.querySelector('.point-cloud-state')?.textContent === 'Live';
    }, { count, baseline }, { timeout: 7000 });
    const current = await page.locator('canvas').evaluate(canvas => window.gpuSamples.get(canvas));
    if (kind === 'max') { assert.deepEqual(current.first.slice(0, 3), [0.25, 0, 0]); assert.deepEqual(current.last, [29.25, 0, 0]); }
    else if (kind !== 'empty') assert.deepEqual(current.first, [kind === 'recovered' ? 2 : 1, kind === 'recovered' ? 3 : 2,
        kind === 'recovered' ? 4 : 3, 30, 0, 0, -30, 0, 0, 0, 0, -5]);
    else await page.getByText('No points in the latest frame.', { exact: true }).waitFor();
    await page.getByText(`${count.toLocaleString('en-US')} points`, { exact: true }).waitFor();
}
async function expectClear() {
    await page.waitForFunction(() => {
        const canvas = document.querySelector('canvas'), current = canvas && window.gpuSamples.get(canvas);
        return current?.drawn === 0 && document.querySelector('.point-cloud-info')?.textContent.includes('— points');
    }, null, { timeout: 4000 });
}
try { await main(); }
catch (error) { if (!stopping) { reply('error', { kind: error.name, message: error.message }); process.exitCode = 1; } }
finally {
    startupDone = true;
    try { await cleanup(); }
    catch (error) { reply('error', { kind: error.name, message: error.message }); process.exitCode = 1; }
}
