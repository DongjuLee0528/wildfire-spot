import test from 'node:test';
import assert from 'node:assert/strict';
import { createPointCloudViewerSession } from '../src/pointcloud/pointCloudViewerSession.js';

function setup({ startupError = false, frameError = false, synchronousFailure = false, destroyError = false, accumulate = false, historyWindowMs = 500, clock, onUpdateExtra } = {}) {
    let callbacks, fail, stopped = 0, destroyed = 0, token = 'first-token', connections = 0, fits = 0;
    const canvases = [], updates = [], frames = [], batches = [];
    const container = { ownerDocument: { createElement() {
        const canvas = { setAttribute() {}, remove() { this.removed = true; } }; canvases.push(canvas); return canvas;
    } }, append() {} };
    const create = () => createPointCloudViewerSession({ container, deviceId: 'test-device', getToken: () => token,
        onUpdate: value => { updates.push(value); onUpdateExtra?.(value); }, accumulate, historyWindowMs,
        now: clock?.now, setTimer: clock?.setTimer, clearTimer: clock?.clearTimer,
        createRenderer: (_canvas, onError) => {
            fail = onError;
            if (startupError) throw new Error('No WebGL');
            if (synchronousFailure) onError(new Error('Initialization callback failed'));
            return { setFrames: values => { if (frameError) throw new Error('Upload failed'); batches.push(values); }, setFrame: frame => { if (frameError) throw new Error('Upload failed'); frames.push(frame); },
                destroy: () => { destroyed++; if (destroyError) throw new Error('Cleanup failed'); }, orbit() {}, zoom() {}, reset() {}, fit() { fits++; } };
        },
        connect: options => { callbacks = options; connections++; options.getToken(); return { stop: () => { stopped++; } }; },
    });
    return { create, canvases, updates, frames, batches, setToken: value => { token = value; },
        get callbacks() { return callbacks; }, get fail() { return fail; },
        counts: () => ({ stopped, destroyed, connections }), get fits() { return fits; } };
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


test('fit action reaches only the active renderer and cannot act after failure or disposal', () => {
    const env = setup(), session = env.create();
    session.fit(); assert.equal(env.fits, 1);
    env.fail(new Error('Context lost')); session.fit(); assert.equal(env.fits, 1);
    session.stop(); session.fit(); assert.equal(env.fits, 1);
    const second = env.create(); second.fit(); assert.equal(env.fits, 2); second.stop();
});


function clockFixture() {
    let time = 0, serial = 0;
    const pending = new Map();
    return {
        now: () => time,
        setTimer: (callback, delay) => { const id = ++serial; pending.set(id, { at: time + delay, callback }); return id; },
        clearTimer: id => pending.delete(id),
        size: () => pending.size,
        advance(delta) {
            const end = time + delta;
            let budget = 100;
            while (true) {
                const due = [...pending].filter(([, item]) => item.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
                if (!due) break;
                assert.ok(--budget > 0, 'Timer loop'); pending.delete(due[0]); time = due[1].at; due[1].callback();
            }
            time = end;
        },
    };
}
function historyFrame(id, count = 2) {
    return { cloudId: id, timestamp: id, pointCount: count, data: new Uint8Array(32 + count * 12) };
}

test('accumulation timer expires points without input and duplicates do not prolong them', () => {
    const clock = clockFixture(), env = setup({ accumulate: true, clock }), session = env.create();
    env.callbacks.onFrame(historyFrame(1)); env.callbacks.onState({ state: 'STREAMING', error: null });
    clock.advance(100); env.callbacks.onFrame(historyFrame(2, 3));
    assert.equal(session.getStatus().pointCount, 5); assert.equal(session.getStatus().latestPointCount, 3);
    assert.equal(session.getStatus().frameCount, 2); assert.equal(clock.size(), 1);
    clock.advance(399); env.callbacks.onFrame(historyFrame(2, 3));
    clock.advance(1); assert.equal(session.getStatus().pointCount, 3);
    clock.advance(100); assert.equal(session.getStatus().pointCount, 0);
    assert.equal(session.getStatus().state, 'STALE'); assert.equal(session.getStatus().hasFrame, false);
    assert.equal(clock.size(), 0); assert.deepEqual(env.batches.at(-1), []);
    env.callbacks.onFrame(historyFrame(2, 3)); env.callbacks.onState({ state: 'STREAMING' });
    assert.equal(session.getStatus().state, 'STALE'); assert.equal(session.getStatus().hasFrame, false);
    env.callbacks.onFrame(historyFrame(3)); env.callbacks.onState({ state: 'STREAMING', error: null });
    assert.equal(session.getStatus().pointCount, 2); assert.equal(session.getStatus().state, 'STREAMING');
    session.stop(); assert.equal(clock.size(), 0);
});

test('empty/null/error/retry clear accumulation; healthy rotation cannot hold points past the window', () => {
    const clock = clockFixture(), env = setup({ accumulate: true, clock }), session = env.create();
    env.callbacks.onFrame(historyFrame(1, 12000)); env.callbacks.onFrame(historyFrame(2, 0));
    assert.equal(session.getStatus().pointCount, 0); assert.equal(session.getStatus().hasFrame, true);
    env.callbacks.onFrame(historyFrame(3)); env.callbacks.onFrame(null);
    assert.equal(session.getStatus().hasFrame, false); assert.equal(clock.size(), 0);
    let sequence = 4;
    for (const state of ['RETRYING', 'ERROR', 'EXHAUSTED', 'STALE', 'CLOSED']) {
        env.callbacks.onFrame(historyFrame(sequence++)); assert.equal(session.getStatus().pointCount, 2); env.callbacks.onState({ state, error: 'fixture' });
        assert.equal(session.getStatus().pointCount, 0); assert.equal(clock.size(), 0);
    }
    env.callbacks.onFrame(historyFrame(20)); env.callbacks.onState({ state: 'CONNECTING', error: null });
    clock.advance(499); assert.equal(session.getStatus().pointCount, 2);
    clock.advance(1); assert.equal(session.getStatus().pointCount, 0); assert.equal(session.getStatus().state, 'STALE');
    session.stop();
});

test('accumulation stop/error/reentrant cleanup removes timers and cannot affect the next generation', () => {
    const clock = clockFixture(), env = setup({ accumulate: true, clock }), first = env.create(), old = env.callbacks;
    old.onFrame(historyFrame(1)); first.stop(); assert.equal(clock.size(), 0);
    const second = env.create(); env.callbacks.onFrame(historyFrame(2, 3));
    old.onFrame(historyFrame(3, 100)); old.onState({ state: 'ERROR' });
    assert.equal(second.getStatus().pointCount, 3); assert.equal(clock.size(), 1);
    env.fail(new Error('Context lost')); assert.equal(clock.size(), 0); assert.equal(second.getStatus().pointCount, 0);
    second.stop(); clock.advance(1000); assert.equal(clock.size(), 0);
    const failure = setup({ accumulate: true, clock, frameError: true }), broken = failure.create();
    failure.callbacks.onFrame(historyFrame(1)); assert.equal(broken.getStatus().state, 'ERROR');
    assert.equal(clock.size(), 0); broken.stop();
    let current;
    const reentrant = setup({ accumulate: true, clock, onUpdateExtra: () => current.stop() });
    current = reentrant.create(); reentrant.callbacks.onFrame(historyFrame(1)); assert.equal(clock.size(), 0);
});

test('expiry observer failure is recorded, closes the feed and never escapes the asynchronous timer', () => {
    const clock = clockFixture(), messages = [], original = console.error;
    const env = setup({ accumulate: true, clock, onUpdateExtra: () => { if (clock.now() >= 500) throw new Error('observer failed'); } });
    const session = env.create(); env.callbacks.onFrame(historyFrame(1));
    try {
        console.error = message => messages.push(message);
        assert.doesNotThrow(() => clock.advance(500));
    } finally { console.error = original; }
    assert.equal(session.getStatus().state, 'ERROR'); assert.equal(session.getStatus().pointCount, 0);
    assert.equal(clock.size(), 0); assert.equal(env.counts().stopped, 1);
    assert.equal(session.stop(), 'Point-cloud status callback failed');
    assert.deepEqual(messages, ['Point-cloud status callback failed']);
});


test('expiry preserves graphics cleanup failure alongside observer notification failure', () => {
    const clock = clockFixture(), original = console.error, messages = [];
    const env = setup({ accumulate: true, clock, destroyError: true,
        onUpdateExtra: () => { if (clock.now() >= 500) throw new Error('observer failed'); } });
    const session = env.create(); env.callbacks.onFrame(historyFrame(1));
    try { console.error = value => messages.push(value); assert.doesNotThrow(() => clock.advance(500)); }
    finally { console.error = original; }
    assert.equal(session.stop(), 'Point-cloud graphics cleanup failed; Point-cloud status callback failed');
    assert.equal(messages.length, 1); assert.equal(clock.size(), 0);
});


test('automatic retries cannot revive the expired last cloud; a new viewer can receive it independently', () => {
    const clock = clockFixture(), env = setup({ accumulate: true, clock }), session = env.create();
    env.callbacks.onFrame(historyFrame(1)); env.callbacks.onState({ state: 'STREAMING', error: null });
    clock.advance(500); assert.equal(session.getStatus().pointCount, 0);
    env.callbacks.onFrame(null); env.callbacks.onState({ state: 'RETRYING', error: 'network' });
    env.callbacks.onFrame(historyFrame(1)); env.callbacks.onState({ state: 'STREAMING', error: null });
    assert.equal(session.getStatus().pointCount, 0); assert.equal(session.getStatus().state, 'STALE');
    assert.equal(clock.size(), 0);
    env.callbacks.onFrame(historyFrame(2, 3)); env.callbacks.onState({ state: 'STREAMING', error: null });
    assert.equal(session.getStatus().pointCount, 3); assert.equal(session.getStatus().state, 'STREAMING');
    session.stop(); const next = env.create(); env.callbacks.onFrame(historyFrame(1));
    assert.equal(next.getStatus().pointCount, 2); next.stop(); assert.equal(clock.size(), 0);
});


test('one-second session expires receipt history at the selected window and clears its timer on stop', () => {
    const clock = clockFixture(), env = setup({ accumulate: true, historyWindowMs: 1000, clock }), session = env.create();
    env.callbacks.onFrame(historyFrame(1)); env.callbacks.onState({ state: 'STREAMING', error: null });
    clock.advance(500); assert.equal(session.getStatus().pointCount, 2);
    clock.advance(499); assert.equal(session.getStatus().pointCount, 2);
    clock.advance(1); assert.equal(session.getStatus().pointCount, 0);
    assert.equal(session.getStatus().state, 'STALE'); assert.equal(clock.size(), 0);
    env.callbacks.onFrame(historyFrame(2)); assert.equal(clock.size(), 1);
    session.stop(); assert.equal(clock.size(), 0);
});
