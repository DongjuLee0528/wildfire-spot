import test from 'node:test';
import assert from 'node:assert/strict';
import { PointCloudHistory, HISTORY_WINDOW_MS, MAX_HISTORY_FRAMES, MAX_HISTORY_POINTS } from '../src/pointcloud/pointCloudHistory.js';

function frame(id, count = 2) {
    return { cloudId: id, timestamp: id + 100, pointCount: count, data: new Uint8Array(32 + count * 12) };
}

test('history retains at most five original frames and60000 points under a long burst', () => {
    let time = 0;
    const history = new PointCloudHistory(() => time);
    for (let i = 0; i < 2000; i++) {
        const original = frame(i, 12000); history.push(original);
        const current = history.snapshot();
        assert.ok(current.frames.length <= MAX_HISTORY_FRAMES);
        assert.ok(current.pointCount <= MAX_HISTORY_POINTS);
        assert.equal(current.frames.at(-1), original);
        assert.ok(current.frames.reduce((sum, item) => sum + item.data.byteLength, 0) <= 720160);
        time++;
    }
    assert.equal(history.snapshot().pointCount, 60000);
    assert.deepEqual(history.snapshot().frames.map(item => item.cloudId), [1995, 1996, 1997, 1998, 1999]);
});

test('receipt window expires at500ms without new input or sensor clock dependence', () => {
    let time = 0;
    const history = new PointCloudHistory(() => time);
    history.push({ ...frame(1), timestamp: 1e12 });
    time = HISTORY_WINDOW_MS - 1; assert.equal(history.snapshot().pointCount, 2);
    assert.equal(history.snapshot().expiresAt, 500);
    time = HISTORY_WINDOW_MS; assert.equal(history.snapshot().pointCount, 0);
    assert.equal(history.snapshot().expiresAt, null);
});

test('duplicate metadata cannot inflate density or extend the last frame lifetime', () => {
    let time = 0;
    const history = new PointCloudHistory(() => time), first = frame(1);
    history.push(first); time = 100; history.push(frame(2));
    time = 250; history.push({ ...first, data: first.data.slice() });
    assert.equal(history.snapshot().frames.length, 2);
    time = 499; history.push(frame(2));
    assert.equal(history.snapshot().expiresAt, 500);
    time = 500; assert.equal(history.snapshot().frames.length, 1);
    time = 600; history.push(frame(2)); assert.equal(history.snapshot().frames.length, 0);
    history.clear(); history.push(frame(2)); assert.equal(history.snapshot().frames.length, 0);
    history.push(frame(3)); assert.equal(history.snapshot().frames.length, 1);
    const next = new PointCloudHistory(() => time); next.push(frame(2)); assert.equal(next.snapshot().frames.length, 1);
});

test('empty frames immediately remove previous points and remain valid zero-point observations', () => {
    const history = new PointCloudHistory(() => 0);
    history.push(frame(1, 100)); history.push(frame(2, 0));
    assert.equal(history.snapshot().pointCount, 0);
    assert.equal(history.snapshot().frames.length, 1);
    assert.equal(history.snapshot().latestPointCount, 0);
    history.clear(); assert.equal(history.snapshot().frames.length, 0);
});

test('invalid history frame bounds and metadata fail instead of retaining unbounded data', () => {
    const history = new PointCloudHistory(() => 0), valid = frame(1);
    for (const bad of [{ ...valid, pointCount: 12001 }, { ...valid, pointCount: -1 },
        { ...valid, data: new Uint8Array(1) }, { ...valid, cloudId: -1 },
        { ...valid, timestamp: NaN }, { ...valid, timestamp: -1 }]) assert.throws(() => history.push(bad));
    assert.equal(history.snapshot().pointCount, 0);
});
