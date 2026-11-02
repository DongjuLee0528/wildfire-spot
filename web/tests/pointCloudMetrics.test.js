import test from 'node:test';
import assert from 'node:assert/strict';
import { PointCloudMetrics } from '../src/pointcloud/pointCloudMetrics.js';
import { PointCloudDecoder, connectPointCloud } from '../src/transport/pointCloudTransport.js';

function frame(id, count = 2, stamp = 1) {
    const bytes = new Uint8Array(32 + count * 12), view = new DataView(bytes.buffer);
    bytes.set([76, 50, 80, 67]);
    view.setUint32(4, 1, true); view.setUint32(8, count * 12, true);
    view.setUint32(12, count, true); view.setFloat64(16, stamp, true);
    view.setUint32(24, id, true); view.setUint32(28, 18, true);
    for (let i = 32; i < bytes.length; i += 12) view.setFloat32(i, 1, true);
    return bytes;
}

test('metrics use local intervals, count points/bytes, wrap IDs, finalize once', () => {
    let now = 0;
    const reports = [], metrics = new PointCloudMetrics('test', { now: () => now, emit: v => reports.push(v) });
    const decoder = new PointCloudDecoder(metrics);
    decoder.feed(frame(0xffffffff, 2, 0));
    now = 100; decoder.feed(frame(0, 0, 1793545893));
    now = 5000; decoder.feed(frame(2, 3));
    assert.equal(reports.length, 1);
    assert.equal(reports[0].frames, 3); assert.equal(reports[0].points, 5);
    assert.equal(reports[0].bytes, 156); assert.equal(reports[0].interval_mean_ms, 2500);
    assert.equal(reports[0].zero_timestamps, 1); assert.equal(reports[0].id_discontinuities, 1);
    assert.equal(reports[0].points_min, 0); assert.equal(reports[0].points_max, 3);
    metrics.finish(); metrics.finish(); assert.equal(reports.length, 2);
    assert.equal(reports[1].final, true);
});

test('invalid and partial frames are not counted; coalesced frames all counted', () => {
    const reports = [], metrics = new PointCloudMetrics('test', { emit: v => reports.push(v) });
    const decoder = new PointCloudDecoder(metrics);
    const a = frame(1), b = frame(2), batch = new Uint8Array(a.length + b.length);
    batch.set(a); batch.set(b, a.length);
    assert.equal(decoder.feed(batch).cloudId, 2);
    decoder.feed(a.subarray(0, 10));
    metrics.finish(); assert.equal(reports[0].frames, 2);
    const bad = frame(3); bad[0] = 0;
    const next = new PointCloudDecoder(metrics);
    assert.throws(() => next.feed(bad));
    assert.equal(metrics.frames, 2);
});

test('transport counts coalesced frames without crypto or secure context and preserves latest-only delivery', async () => {
    const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
    const previous = console.info, reports = [];
    console.info = (prefix, value) => reports.push(value);
    let transport;
    try {
        const a = frame(1), b = frame(2), batch = new Uint8Array(a.length + b.length);
        batch.set(a); batch.set(b, a.length);
        const delivered = [];
        transport = connectPointCloud({ deviceId: 'test', getToken: () => 'test-only-token',
            onFrame: f => { if (f) delivered.push(f.cloudId); }, onState: () => {}, retryDelays: [],
            fetchImpl: async () => new Response(new ReadableStream({ start(c) { c.enqueue(batch); c.close(); } }),
                { headers: { 'Content-Type': 'application/octet-stream' } }) });
        await transport.done;
        assert.deepEqual(delivered, [2]);
        assert.equal(reports.find(v => v.stage === 'browser_decoded').frames, 2);
        assert.equal(reports.find(v => v.stage === 'viewer_delivered').frames, 1);
        assert.ok(!JSON.stringify(reports).includes('test-only-token'));
        transport.stop();
        assert.equal(reports.length, 2);
    } finally {
        transport?.stop(); console.info = previous;
        if (cryptoDescriptor) Object.defineProperty(globalThis, 'crypto', cryptoDescriptor);
        else delete globalThis.crypto;
    }
});


test('diagnostic session labels remain distinct with the same wall clock', t => {
    t.mock.method(Date, 'now', () => 1234);
    const first = new PointCloudMetrics('test'), second = new PointCloudMetrics('test');
    assert.notEqual(first.session, second.session);
});
