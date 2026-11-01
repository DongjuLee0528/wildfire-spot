import test from 'node:test';
import assert from 'node:assert/strict';
import { createPointCloudViewerSession } from '../src/pointcloud/pointCloudViewerSession.js';

function setup({ startupError = false, frameError = false, synchronousFailure = false, destroyError = false } = {}) {
    let callbacks, fail, stopped = 0, destroyed = 0, token = 'first-token', connections = 0;
    const canvases = [], updates = [], frames = [];
    const container = { ownerDocument: { createElement() {
        const canvas = { setAttribute() {}, remove() { this.removed = true; } }; canvases.push(canvas); return canvas;
    } }, append() {} };
    const create = () => createPointCloudViewerSession({ container, deviceId: 'test-device', getToken: () => token,
        onUpdate: value => updates.push(value),
        createRenderer: (_canvas, onError) => {
            fail = onError;
            if (startupError) throw new Error('No WebGL');
            if (synchronousFailure) onError(new Error('Initialization callback failed'));
            return { setFrame: frame => { if (frameError) throw new Error('Upload failed'); frames.push(frame); },
                destroy: () => { destroyed++; if (destroyError) throw new Error('Cleanup failed'); }, orbit() {}, zoom() {}, reset() {} };
        },
        connect: options => { callbacks = options; connections++; options.getToken(); return { stop: () => { stopped++; } }; },
    });
    return { create, canvases, updates, frames, setToken: value => { token = value; },
        get callbacks() { return callbacks; }, get fail() { return fail; },
        counts: () => ({ stopped, destroyed, connections }) };
}

test('new session/canvas per generation; cleanup and late callbacks are guarded', () => {
    const env = setup(), first = env.create(), old = env.callbacks;
    old.onFrame({ pointCount: 2 }); old.onState({ state: 'STREAMING', error: null });
    assert.equal(first.getStatus().pointCount, 2);
    first.stop(); first.stop();
    const before = env.updates.length;
    old.onFrame({ pointCount: 9 }); old.onState({ state: 'ERROR' });
    assert.equal(env.updates.length, before); assert.ok(env.canvases[0].removed);
    const second = env.create(); assert.notEqual(env.canvases[0], env.canvases[1]);
    assert.equal(second.getStatus().pointCount, 0); second.stop();
    assert.deepEqual(env.counts(), { stopped: 2, destroyed: 2, connections: 2 });
});

test('rotation CONNECTING preserves points; empty and null clear their count correctly', () => {
    const env = setup(), session = env.create();
    env.callbacks.onFrame({ pointCount: 12000 }); env.callbacks.onState({ state: 'CONNECTING', error: null });
    assert.equal(session.getStatus().pointCount, 12000); assert.ok(session.getStatus().hasFrame);
    env.callbacks.onFrame({ pointCount: 0 }); env.callbacks.onState({ state: 'STREAMING', error: null });
    assert.equal(session.getStatus().pointCount, 0); assert.ok(session.getStatus().hasFrame);
    env.callbacks.onFrame(null); env.callbacks.onState({ state: 'STALE', error: null });
    assert.equal(session.getStatus().pointCount, 0); assert.equal(session.getStatus().hasFrame, false);
    session.stop();
});

test('renderer failure stops feed, clears count and retry creates a fresh generation', () => {
    const env = setup(), first = env.create();
    env.callbacks.onFrame({ pointCount: 5 }); env.fail(new Error('Context lost'));
    assert.equal(first.getStatus().state, 'ERROR'); assert.equal(first.getStatus().pointCount, 0);
    assert.equal(env.counts().stopped, 1);
    const before = env.updates.length; env.callbacks.onFrame({ pointCount: 9 }); assert.equal(env.updates.length, before);
    first.stop(); env.setToken('new-token'); const second = env.create();
    assert.equal(env.callbacks.getToken(), 'new-token'); assert.notEqual(env.canvases[0], env.canvases[1]); second.stop();
});

test('failed renderer initialization cannot start transport', () => {
    const env = setup({ startupError: true }), session = env.create();
    assert.equal(env.counts().connections, 0); assert.equal(session.getStatus().state, 'ERROR');
    assert.ok(env.canvases[0].removed); session.stop();
});


test('synchronous renderer failure and upload exception cannot leave an active feed', () => {
    const startup = setup({ synchronousFailure: true }), first = startup.create();
    assert.equal(startup.counts().connections, 0); assert.equal(startup.counts().destroyed, 1);
    first.stop(); assert.equal(startup.counts().destroyed, 1);
    const upload = setup({ frameError: true }), second = upload.create();
    upload.callbacks.onFrame({ pointCount: 5 });
    assert.equal(upload.counts().stopped, 1); assert.equal(second.getStatus().state, 'ERROR');
    assert.equal(second.getStatus().pointCount, 0); second.stop();
});

test('cleanup failure is retained and canvas still removed', () => {
    const env = setup({ destroyError: true }), session = env.create();
    assert.equal(session.stop(), 'Point-cloud graphics cleanup failed');
    assert.ok(env.canvases[0].removed); assert.equal(env.counts().stopped, 1);
    assert.equal(session.getStatus().cleanupError, 'Point-cloud graphics cleanup failed');
});
