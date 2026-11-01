import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { connectPointCloud, PointCloudDecoder, PointCloudProtocolError, TruncatedFrameError } from '../src/transport/pointCloudTransport.js';

const fixtures = JSON.parse(readFileSync(new URL('../../tests/fixtures/point_cloud_v1.json', import.meta.url)));
const valid = Uint8Array.from(Buffer.from(fixtures[0].hex, 'hex'));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate) {
    for (let i = 0; i < 200; i++) { if (predicate()) return; await sleep(5); }
    assert.fail('condition not reached');
}
function response(chunks, status = 200, keepOpen = false) {
    return new Response(new ReadableStream({ start(controller) {
        for (const chunk of chunks) controller.enqueue(chunk);
        if (!keepOpen) controller.close();
    } }), { status, headers: { 'Content-Type': 'application/octet-stream' } });
}
function options(fetchImpl, extra = {}) {
    return { deviceId: 'device/one', getToken: () => 'test-token', onFrame: () => {}, onState: () => {}, fetchImpl,
        retryDelays: [1], staleMs: 20, timeoutMs: 60, stableMs: 30, rotationMs: 80, ...extra };
}

test('shared binary fixtures and arbitrary split/coalesced frames', () => {
    for (const fixture of fixtures) {
        const decoder = new PointCloudDecoder();
        const data = Uint8Array.from(Buffer.from(fixture.hex, 'hex'));
        if (fixture.valid) {
            let frame;
            for (let i = 0; i < data.length; i += 3) frame = decoder.feed(data.subarray(i, i + 3)) || frame;
            assert.ok(frame, fixture.name); decoder.finish();
        } else assert.throws(() => { decoder.feed(data); decoder.finish(); }, Error, fixture.name);
    }
    const decoder = new PointCloudDecoder();
    const batch = new Uint8Array(valid.length * 2000);
    for (let i = 0; i < 2000; i++) batch.set(valid, i * valid.length);
    assert.equal(decoder.feed(batch).cloudId, 42);
    assert.equal(decoder.offset, 0);
});

test('auth header, latest batch only, and resource stop suppresses callbacks', async () => {
    let request, streamController;
    const frames = [], states = [];
    const batch = new Uint8Array(valid.length * 2); batch.set(valid); batch.set(valid, valid.length);
    const transport = connectPointCloud(options(async (url, init) => {
        request = { url, init };
        return new Response(new ReadableStream({ start(controller) { streamController = controller; controller.enqueue(batch); } }),
            { headers: { 'Content-Type': 'application/octet-stream' } });
    }, { onFrame: frame => frames.push(frame), onState: state => states.push(state.state) }));
    await until(() => frames.some(Boolean));
    assert.equal(request.url, '/api/devices/device%2Fone/point-cloud/stream');
    assert.equal(request.init.headers.Authorization, 'Bearer test-token');
    assert.ok(!request.url.includes('test-token'));
    assert.equal(frames.filter(Boolean).length, 1);
    transport.stop(); const count = states.length;
    await transport.done; await sleep(30);
    assert.equal(states.length, count); assert.equal(transport.getStatus().state, 'CLOSED');
    assert.throws(() => streamController.enqueue(valid));
});

test('401/403/404 are terminal, not retried', async () => {
    for (const status of [401, 403, 404]) {
        let calls = 0;
        const transport = connectPointCloud(options(async () => { calls++; return response([], status); }));
        await transport.done;
        assert.equal(calls, 1); assert.equal(transport.getStatus().state, 'ERROR');
    }
});

test('partial EOF is retryable and retry budget exhausts with no stale bytes', async () => {
    let calls = 0; const states = [];
    const transport = connectPointCloud(options(async () => {
        calls++; return response([valid.subarray(0, 35)]);
    }, { onState: state => states.push(state.state) }));
    await transport.done;
    assert.equal(calls, 2); assert.ok(states.includes('RETRYING'));
    assert.equal(transport.getStatus().state, 'EXHAUSTED');
    let fresh = null;
    const restarted = connectPointCloud(options(async () => response([valid], 200, true), { onFrame: frame => { fresh = frame; } }));
    await until(() => fresh != null);
    restarted.stop(); await restarted.done;
});

test('invalid protocol is terminal and consumer exceptions stop transport', async () => {
    for (const extra of [{}, { onFrame: () => { throw new Error('injected'); } }]) {
        let calls = 0;
        const data = Object.keys(extra).length ? valid : new Uint8Array(32);
        const transport = connectPointCloud(options(async () => { calls++; return response([data], 200, true); }, extra));
        await transport.done;
        assert.equal(calls, 1); assert.equal(transport.getStatus().state, 'ERROR');
    }
});

test('stale display cleared and stalled partial reads time out', async () => {
    const frames = [], states = [];
    const transport = connectPointCloud(options(async () => response([valid], 200, true), {
        retryDelays: [], onFrame: frame => frames.push(frame), onState: state => states.push(state.state),
    }));
    await transport.done;
    assert.ok(frames.some(Boolean)); assert.ok(frames.includes(null)); assert.ok(states.includes('STALE'));
    assert.equal(transport.getStatus().state, 'EXHAUSTED');
});

test('stop interrupts long retry wait', async () => {
    const states = [];
    const transport = connectPointCloud(options(async () => response([], 503), {
        retryDelays: [30000], onState: state => states.push(state.state),
    }));
    await until(() => states.includes('RETRYING'));
    transport.stop(); await transport.done;
    assert.equal(transport.getStatus().state, 'CLOSED');
});

test('clean long stream rotation reconnects without spending failure budget', async () => {
    let calls = 0; const frames = [];
    const transport = connectPointCloud(options(async () => {
        calls++;
        let timer;
        return new Response(new ReadableStream({ start(controller) {
            controller.enqueue(valid);
            timer = setTimeout(() => controller.close(), 30);
        }, cancel() { clearTimeout(timer); } }), { headers: { 'Content-Type': 'application/octet-stream' } });
    }, { retryDelays: [], staleMs: 250, timeoutMs: 500, stableMs: 10, rotationMs: 20,
        onFrame: frame => frames.push(frame) }));
    await until(() => calls >= 2);
    transport.stop(); await transport.done;
    assert.notEqual(transport.getStatus().state, 'EXHAUSTED');
    assert.ok(frames.length >= 2); assert.ok(frames.every(Boolean));
});


test('stop resolves pending fetch and late body is canceled without callbacks', async () => {
    let resolveFetch, canceled = false; const frames = [];
    const transport = connectPointCloud(options(() => new Promise(resolve => { resolveFetch = resolve; }), {
        onFrame: value => frames.push(value),
    }));
    transport.stop(); await transport.done;
    resolveFetch(new Response(new ReadableStream({ cancel() { canceled = true; } }),
        { headers: { 'Content-Type': 'application/octet-stream' } }));
    await until(() => canceled);
    assert.equal(frames.length, 0);
});

test('authentication callback and state callback failures terminate cleanly', async () => {
    for (const extra of [{ getToken: () => { throw new Error('injected'); } },
                         { onState: () => { throw new Error('injected'); } }]) {
        let calls = 0;
        const transport = connectPointCloud(options(async () => { calls++; return response([valid]); }, extra));
        await transport.done;
        assert.equal(transport.getStatus().state, 'ERROR'); assert.equal(calls, 0);
    }
});


test('rotation preserves the original stale deadline when next connection has no frame', async () => {
    let calls = 0; const frames = [], states = [];
    const transport = connectPointCloud(options(async () => {
        calls++;
        if (calls > 1) return response([], 200, true);
        let timer;
        return new Response(new ReadableStream({ start(controller) {
            controller.enqueue(valid); timer = setTimeout(() => controller.close(), 30);
        }, cancel() { clearTimeout(timer); } }), { headers: { 'Content-Type': 'application/octet-stream' } });
    }, { retryDelays: [], staleMs: 160, timeoutMs: 500, rotationMs: 20,
        onFrame: frame => frames.push(frame), onState: state => states.push(state.state) }));
    await until(() => states.includes('STALE'));
    assert.equal(calls, 2); assert.ok(frames.includes(null));
    transport.stop(); await transport.done;
});


test('stale callback failure during rotation wait stops before another request', async () => {
    let calls = 0;
    const transport = connectPointCloud(options(async () => {
        calls++;
        let timer;
        return new Response(new ReadableStream({ start(controller) {
            controller.enqueue(valid); timer = setTimeout(() => controller.close(), 30);
        }, cancel() { clearTimeout(timer); } }), { headers: { 'Content-Type': 'application/octet-stream' } });
    }, { staleMs: 60, timeoutMs: 200, rotationMs: 20,
        onFrame: frame => { if (frame == null) throw new Error('injected'); } }));
    await transport.done;
    assert.equal(calls, 1); assert.equal(transport.getStatus().state, 'ERROR');
});
