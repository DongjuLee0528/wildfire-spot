import test from 'node:test';
import assert from 'node:assert/strict';
import { cameraBasis, createPointCloudRenderer, DEFAULT_VIEW_DISTANCE, fitPointCloud } from '../src/pointcloud/pointCloudRenderer.js';

function environment(fault = '') {
    const calls = [], callbacks = new Map(), events = new Map(), removed = [];
    let id = 0;
    const gl = new Proxy({ NO_ERROR: 0, ALIASED_POINT_SIZE_RANGE: 1, COMPILE_STATUS: 2, LINK_STATUS: 3,
        VERTEX_SHADER: 4, FRAGMENT_SHADER: 5, ARRAY_BUFFER: 6, DYNAMIC_DRAW: 7, STATIC_DRAW: 8,
        DEPTH_TEST: 9, COLOR_BUFFER_BIT: 16, DEPTH_BUFFER_BIT: 32, LINES: 10, POINTS: 11, FLOAT: 12,
        isContextLost: () => false,
        createShader: () => ({}), getShaderParameter: () => fault !== 'compile',
        createProgram: () => ({}), getProgramParameter: () => fault !== 'link',
        createBuffer: () => fault === 'allocation' ? null : {},
        getAttribLocation: (_program, name) => name === 'receivedAt' ? 1 : 0, getUniformLocation: (_program, name) => name, getParameter: () => [1, 4],
        getError: () => fault === 'gl-error' ? 1285 : 0,
        getExtension: () => ({ loseContext: () => calls.push(['loseContext']) }),
    }, { get(target, name) { return target[name] ?? ((...args) => calls.push([name, ...args])); } });
    const canvas = {
        getContext: () => fault === 'unavailable' ? null : gl,
        addEventListener: (name, fn) => events.set(name, fn), removeEventListener: name => { removed.push(name); events.delete(name); },
        getBoundingClientRect: () => ({ width: 600, height: 300 }),
        setPointerCapture() {}, hasPointerCapture: () => false, releasePointerCapture() {},
    };
    globalThis.window = { devicePixelRatio: 3, addEventListener() {}, removeEventListener() {} };
    globalThis.ResizeObserver = class { observe() {} disconnect() { calls.push(['disconnect']); } };
    globalThis.requestAnimationFrame = fn => { callbacks.set(++id, fn); return id; };
    globalThis.cancelAnimationFrame = key => callbacks.delete(key);
    const flush = () => { const all = [...callbacks.values()]; callbacks.clear(); all.forEach(fn => fn()); };
    return { gl, calls, canvas, flush, callbacks, events, removed };
}
function frame(count) {
    const data = new Uint8Array(32 + count * 12), view = new DataView(data.buffer);
    for (let i = 0; i < count; i++) {
        view.setFloat32(32 + i * 12, 1, true); view.setFloat32(36 + i * 12, -2, true); view.setFloat32(40 + i * 12, 3, true);
    }
    return { data, pointCount: count };
}

test('camera basis preserves Z-up orthonormal right-handed sensor view', () => {
    for (const [yaw, pitch] of [[0, 0], [-0.8, 0.55], [20, 1.45], [20, -1.45]]) {
        const { eye, right, up } = cameraBasis(yaw, pitch);
        const dot = (a, b) => a.reduce((sum, v, i) => sum + v * b[i], 0);
        for (const vector of [eye, right, up]) assert.ok(Math.abs(dot(vector, vector) - 1) < 1e-10);
        assert.ok(Math.abs(dot(eye, right)) < 1e-10); assert.ok(Math.abs(dot(eye, up)) < 1e-10);
        assert.ok(Math.abs(dot(up, right)) < 1e-10); assert.ok(up[2] > 0);
    }
});

test('bounded GPU allocation, little endian XYZ, latest count, empty and stale clearing', () => {
    const env = environment(), errors = [];
    const renderer = createPointCloudRenderer(env.canvas, error => errors.push(error));
    renderer.setFrame(frame(12000)); renderer.setFrame(frame(2));
    assert.equal(env.callbacks.size, 1);
    const uploads = env.calls.filter(call => call[0] === 'bufferSubData');
    assert.deepEqual(Array.from(uploads.at(-1)[3]), [1, -2, 3, 1, -2, 3]);
    assert.equal(env.calls.filter(call => call[0] === 'bufferData' && call[2] === 144000).length, 1);
    env.flush(); assert.ok(env.calls.some(call => call[0] === 'drawArrays' && call[1] === env.gl.POINTS && call[3] === 2));
    assert.equal(env.canvas.width, 1200); assert.equal(env.canvas.height, 600);
    renderer.setFrame(frame(0)); env.flush(); renderer.setFrame(null); env.flush();
    assert.equal(env.calls.filter(call => call[0] === 'drawArrays' && call[1] === env.gl.POINTS).at(-1)[3], 0);
    assert.throws(() => renderer.setFrame(frame(12001)), /Invalid 3D frame/);
    assert.throws(() => renderer.setFrame({ data: new Uint8Array(32), pointCount: 1 }), /Invalid 3D frame/);
    assert.equal(errors.length, 0); renderer.destroy();
});

test('on-demand orbit/zoom/reset, size cap, zero-size and input cleanup', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail);
    env.flush(); assert.equal(env.callbacks.size, 0);
    renderer.orbit(100, 100); renderer.zoom(0.0001); env.flush();
    assert.equal(env.calls.filter(call => call[0] === 'uniform1f' && call[1] === 'distance').at(-1)[2], DEFAULT_VIEW_DISTANCE * 0.0001);
    assert.deepEqual(env.calls.filter(call => call[0] === 'uniform3fv' && call[1] === 'eye').at(-1)[2], cameraBasis((-Math.PI / 4 + 100) % (Math.PI * 2), 1.45).eye);
    renderer.reset(); renderer.zoom(10000);
    env.canvas.getBoundingClientRect = () => ({ width: 10000, height: 10000 }); env.flush();
    assert.equal(env.calls.filter(call => call[0] === 'uniform1f' && call[1] === 'distance').at(-1)[2], 100);
    renderer.reset(); renderer.orbit(0, -100); env.flush();
    assert.deepEqual(env.calls.filter(call => call[0] === 'uniform3fv' && call[1] === 'eye').at(-1)[2], cameraBasis(-Math.PI / 4, -1.45).eye);
    assert.equal(env.canvas.width, 2048); assert.equal(env.canvas.height, 2048);
    env.canvas.getBoundingClientRect = () => ({ width: 0, height: 0 }); renderer.reset(); env.flush();
    assert.equal(env.callbacks.size, 0);
    env.canvas.getBoundingClientRect = () => ({ width: 600, height: 300 }); renderer.reset(); env.flush();
    env.events.get('pointerdown')({ button: 0, pointerId: 1, clientX: 0, clientY: 0 });
    env.events.get('pointermove')({ pointerId: 1, clientX: 40, clientY: 10 });
    env.flush();
    assert.deepEqual(env.calls.filter(call => call[0] === 'uniform3fv' && call[1] === 'eye').at(-1)[2], cameraBasis(-Math.PI / 4 - 40 * 0.008, 0.35 + 10 * 0.008).eye);
    env.events.get('pointercancel')({ pointerId: 1 });
    const afterCancel = env.calls.length;
    env.events.get('pointermove')({ pointerId: 1, clientX: 100, clientY: 100 }); env.flush();
    assert.equal(env.calls.length, afterCancel);
    let prevented = false;
    env.events.get('wheel')({ deltaY: 10, preventDefault: () => { prevented = true; } });
    env.flush();
    assert.equal(env.calls.filter(call => call[0] === 'uniform1f' && call[1] === 'distance').at(-1)[2], DEFAULT_VIEW_DISTANCE * Math.exp(0.03));
    renderer.reset(); env.flush();
    assert.equal(env.calls.filter(call => call[0] === 'uniform1f' && call[1] === 'distance').at(-1)[2], DEFAULT_VIEW_DISTANCE);
    assert.ok(prevented); renderer.destroy(); renderer.destroy();
    assert.equal(env.callbacks.size, 0); assert.equal(env.events.size, 0);
    assert.equal(env.calls.filter(call => call[0] === 'deleteBuffer').length, 2);
    assert.equal(env.calls.filter(call => call[0] === 'deleteShader').length, 2);
    assert.equal(env.calls.filter(call => call[0] === 'deleteProgram').length, 1);
    assert.equal(env.calls.filter(call => call[0] === 'loseContext').length, 1);
});

test('context loss reports once and no rendering occurs afterwards', () => {
    const env = environment(), errors = [];
    const renderer = createPointCloudRenderer(env.canvas, error => errors.push(error));
    let prevented = false;
    env.events.get('webglcontextlost')({ preventDefault: () => { prevented = true; } });
    renderer.setFrame(frame(1)); env.flush();
    assert.ok(prevented); assert.equal(errors.length, 1);
    assert.equal(env.calls.filter(call => call[0] === 'drawArrays').length, 0);
    renderer.destroy();
});

test('startup failures free allocated resources and never leave scheduled work', () => {
    for (const fault of ['unavailable', 'compile', 'link', 'allocation', 'gl-error']) {
        const env = environment(fault);
        assert.throws(() => createPointCloudRenderer(env.canvas, assert.fail));
        assert.equal(env.callbacks.size, 0);
        assert.equal(env.events.size, 0);
        if (fault !== 'unavailable') assert.equal(env.calls.filter(call => call[0] === 'loseContext').length, 1);
    }
});


test('fallback view fits every30m direction in landscape and portrait', () => {
    const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
    const basis = cameraBasis(-Math.PI / 4, 0.35);
    for (const aspect of [0.3, 0.8, 1, 2, 4]) {
        const scale = Math.sqrt(3) * Math.min(1, aspect);
        for (let latitude = -90; latitude <= 90; latitude += 5) for (let longitude = 0; longitude < 360; longitude += 5) {
            const a = latitude * Math.PI / 180, b = longitude * Math.PI / 180;
            const p = [30 * Math.cos(a) * Math.cos(b), 30 * Math.cos(a) * Math.sin(b), 30 * Math.sin(a)];
            const depth = DEFAULT_VIEW_DISTANCE - dot(p, basis.eye);
            assert.ok(Math.abs(dot(p, basis.right) * scale / aspect / depth) < 1);
            assert.ok(Math.abs(dot(p, basis.up) * scale / depth) < 1);
            assert.ok(depth > 0.1 && depth < 200);
        }
    }
});

function cloudFrame(points) {
    const data = new Uint8Array(32 + points.length * 12), view = new DataView(data.buffer);
    points.flat().forEach((value, i) => view.setFloat32(32 + i * 4, value, true));
    return { data, pointCount: points.length };
}
const lastUniform = (env, type, name) => env.calls.filter(call => call[0] === type && call[1] === name).at(-1)?.[2];

test('fit centers an off-axis room and preserves projection proportions at any view aspect', () => {
    const points = [];
    for (const x of [1, 7]) for (const y of [-4, 4]) for (const z of [-1, 2]) points.push([x, y, z]);
    const fit = fitPointCloud(points.flat(), points.length);
    assert.deepEqual(fit.center, [4, 0, 0.5]);
    assert.deepEqual(fit.heightRange, [-1, 2]);
    assert.ok(fit.distance < 15);
    for (const aspect of [0.3, 0.8, 1, 2, 5]) for (const [yaw, pitch] of [[0, 0], [-Math.PI / 4, 0.35], [2, -1.45]]) {
        const basis = cameraBasis(yaw, pitch), scale = Math.sqrt(3) * Math.min(1, aspect);
        const dot = (a, b) => a.reduce((sum, v, i) => sum + v * b[i], 0);
        for (const point of points) {
            const relative = point.map((v, i) => v - fit.center[i]);
            const depth = fit.distance - dot(relative, basis.eye);
            assert.ok(depth > 0.1 && depth < 200);
            assert.ok(Math.abs(dot(relative, basis.right) * scale / aspect / depth) < 1);
            assert.ok(Math.abs(dot(relative, basis.up) * scale / depth) < 1);
        }
    }
});

test('first nonempty frame fits once; replacement, stale and empty do not move the view or accumulate points', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail);
    renderer.setFrame(frame(0)); env.flush();
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), DEFAULT_VIEW_DISTANCE);
    const first = cloudFrame([[1, -2, -1], [7, 4, 2]]);
    renderer.setFrame(first); env.flush();
    const fitted = lastUniform(env, 'uniform1f', 'distance');
    assert.ok(fitted < 20); assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [4, 1, 0.5]);
    assert.deepEqual(lastUniform(env, 'uniform2fv', 'heightRange'), [-1, 2]);
    renderer.zoom(0.8); env.flush();
    const manual = lastUniform(env, 'uniform1f', 'distance');
    renderer.setFrame(cloudFrame([[-10, -9, 5], [-8, -7, 6], [-9, -8, 5.5]])); env.flush();
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), manual);
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [4, 1, 0.5]);
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 3);
    renderer.fit(); env.flush();
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [-9, -8, 5.5]);
    assert.deepEqual(lastUniform(env, 'uniform2fv', 'heightRange'), [5, 6]);
    renderer.orbit(0.4, 0.2); renderer.reset(); env.flush();
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'eye'), cameraBasis(-Math.PI / 4, 0.35).eye);
    renderer.setFrame(null); renderer.fit(); env.flush();
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 0);
    renderer.setFrame(frame(0)); renderer.fit(); env.flush();
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 0);
    renderer.destroy(); const calls = env.calls.length; renderer.fit(); renderer.reset(); env.flush();
    assert.equal(env.calls.length, calls);
});

test('flat and single-point frames have finite fitted view and nonzero height span; malformed coordinates fail', () => {
    for (const points of [[[0, 0, 0]], [[2, 2, 4], [3, 4, 4]], [[30, 0, 0], [-30, 0, 0], [0, 30, 0]]]) {
        const fit = fitPointCloud(points.flat(), points.length);
        assert.ok(fit.center.every(Number.isFinite));
        assert.ok(fit.distance >= 2 && fit.distance <= 100);
        assert.ok(fit.heightRange[1] - fit.heightRange[0] >= 0.5);
    }
    for (const [positions, count] of [[[], 0], [[1, 2], 1], [[0, Infinity, 0], 1], [[0, NaN, 0], 1]])
        assert.throws(() => fitPointCloud(positions, count));
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail);
    assert.throws(() => renderer.setFrame(cloudFrame([[1, NaN, 3]])), /Invalid point-cloud coordinate/);
    renderer.destroy();
});

test('30m sphere stays in view after scene fit and XYZ payload is unchanged', () => {
    const points = [];
    for (let lat = -90; lat <= 90; lat += 15) for (let lon = 0; lon < 360; lon += 15) {
        const a = lat * Math.PI / 180, b = lon * Math.PI / 180;
        points.push([30 * Math.cos(a) * Math.cos(b), 30 * Math.cos(a) * Math.sin(b), 30 * Math.sin(a)]);
    }
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail), source = cloudFrame(points);
    renderer.setFrame(source); env.flush();
    const center = lastUniform(env, 'uniform3fv', 'center'), distance = lastUniform(env, 'uniform1f', 'distance');
    assert.ok(distance >= 60 && distance < 70);
    const uploaded = env.calls.filter(c => c[0] === 'bufferSubData').at(-1)[3];
    assert.deepEqual(Array.from(uploaded), Array.from(new Float32Array(source.data.buffer, 32)));
    for (const aspect of [0.3, 1, 5]) for (const [yaw, pitch] of [[0, 0], [-Math.PI / 4, 0.35], [2, 1.45]]) {
        const basis = cameraBasis(yaw, pitch), scale = Math.sqrt(3) * Math.min(1, aspect);
        const dot = (a, b) => a.reduce((sum, v, i) => sum + v * b[i], 0);
        for (const point of points) {
            const relative = point.map((v, i) => v - center[i]), depth = distance - dot(relative, basis.eye);
            assert.ok(depth > 0.1 && depth < 200);
            assert.ok(Math.abs(dot(relative, basis.right) * scale / aspect / depth) < 1);
            assert.ok(Math.abs(dot(relative, basis.up) * scale / depth) < 1);
        }
    }
    renderer.destroy();
});

test('wide high-DPR canvas keeps buffer aspect and point sprites bounded', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail);
    env.canvas.getBoundingClientRect = () => ({ width: 1900, height: 380 }); env.flush();
    assert.equal(env.canvas.width, 2048); assert.equal(env.canvas.height, 410);
    assert.ok(Math.abs(env.canvas.width / env.canvas.height - 5) < 0.01);
    const size = lastUniform(env, 'uniform1f', 'pointSize');
    assert.ok(size >= 1 && size <= 4);
    assert.ok(Math.abs(size / (env.canvas.width / 1900) - 2) < 0.01);
    renderer.destroy();
});


test('accumulation uses a fixed60000-point buffer, preserves frame XYZ, and rejects per-frame or batch overflow', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail, { accumulate: true });
    assert.equal(env.calls.filter(call => call[0] === 'bufferData' && call[2] === 720000).length, 1);
    renderer.setFrames([frame(12000), frame(12000), frame(12000), frame(12000), frame(12000)]); env.flush();
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).slice(-5).reduce((sum, c) => sum + c[3], 0), 60000);
    renderer.setFrames([cloudFrame([[1, 2, 3]]), cloudFrame([[-1, -2, -3]])]); env.flush();
    assert.deepEqual(Array.from(env.calls.filter(c => c[0] === 'bufferSubData').at(-1)[3]), [1, 2, 3, -1, -2, -3]);
    assert.throws(() => renderer.setFrames(Array.from({ length: 6 }, () => frame(1))), /Invalid 3D frame batch/);
    assert.throws(() => renderer.setFrames([frame(12001)]), /Invalid 3D frame/);
    renderer.setFrames([]); env.flush();
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 0);
    renderer.destroy();
    const single = environment(), plain = createPointCloudRenderer(single.canvas, assert.fail);
    assert.throws(() => plain.setFrames([frame(1), frame(1)]), /Invalid 3D frame batch/);
    plain.destroy();
});

test('empty reset allows a later frame to refit; stale recovery alone preserves the chosen view', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail);
    renderer.setFrame(cloudFrame([[1, 2, 3], [4, 5, 6]])); renderer.zoom(0.8); env.flush();
    const distance = lastUniform(env, 'uniform1f', 'distance');
    renderer.setFrame(null); renderer.setFrame(cloudFrame([[-10, -10, -10], [10, 10, 10]])); env.flush();
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), distance);
    renderer.setFrame(null); renderer.reset(); renderer.setFrame(cloudFrame([[-10, -10, -10], [10, 10, 10]])); env.flush();
    assert.ok(lastUniform(env, 'uniform1f', 'distance') > distance);
    renderer.destroy();
});


test('valid empty frame performs a zero-length GPU upload; stale/null clear does not pretend to receive a frame', () => {
    for (const accumulate of [false, true]) {
        const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail, { accumulate });
        renderer.setFrame(frame(2)); env.flush();
        const before = env.calls.filter(call => call[0] === 'bufferSubData').length;
        renderer.setFrame(frame(0)); env.flush();
        const received = env.calls.filter(call => call[0] === 'bufferSubData');
        assert.equal(received.length, before + (accumulate ? 2 : 1)); assert.equal(received.at(-1)[3].length, 0);
        renderer.setFrame(null); env.flush();
        assert.equal(env.calls.filter(call => call[0] === 'bufferSubData').length, received.length);
        assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 0);
        renderer.destroy();
    }
});


test('sensor origin looks +X with -Y on the right and Z up, independent of cloud bounds', () => {
    const env = environment(), views = [];
    const renderer = createPointCloudRenderer(env.canvas, assert.fail, { viewMode: 'sensor', onView: value => views.push(value) });
    renderer.setFrame(cloudFrame([[4, -2, -1], [8, 3, 2]])); env.flush();
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [0, 0, 0]);
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), 0);
    const eye = lastUniform(env, 'uniform3fv', 'eye'), right = lastUniform(env, 'uniform3fv', 'right');
    assert.ok(Math.abs(eye[0] + 1) < 1e-10); assert.ok(Math.abs(right[1] + 1) < 1e-10);
    assert.equal(views.at(-1).heading, 0); assert.ok(Math.abs(views.at(-1).elevation) < 1e-10);
    renderer.zoom(0.001); renderer.orbit(0, 0.15); env.flush();
    assert.equal(views.at(-1).fov, 30); assert.ok(views.at(-1).elevation > 0);
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), 0);
    renderer.reset(); renderer.orbit(-Math.PI, 0); env.flush();
    assert.equal(Math.round(views.at(-1).heading), 180);
    assert.ok(lastUniform(env, 'uniform3fv', 'eye')[0] > 0.99);
    renderer.zoom(1e8); env.flush(); assert.equal(views.at(-1).fov, 110);
    renderer.setViewMode('overview'); env.flush();
    assert.ok(lastUniform(env, 'uniform1f', 'distance') >= 2);
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [6, 0.5, 0.5]);
    renderer.setViewMode('sensor'); env.flush(); assert.equal(views.at(-1).heading, 0);
    assert.throws(() => renderer.setViewMode('bad'), /Invalid view mode/);
    renderer.destroy();
});

test('one-second accumulation has bounded ten-frame buffers, receipt ages, fade clock and cancellation', () => {
    let time = 100;
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail,
        { accumulate: true, historyWindowMs: 1000, now: () => time, viewMode: 'sensor' });
    const frames = Array.from({ length: 10 }, () => frame(12000));
    time = 1000; renderer.setFrames(frames, Array.from({ length: 10 }, (_, i) => 100 + i * 100)); env.flush();
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).slice(-10).reduce((sum, c) => sum + c[3], 0), 120000);
    assert.ok(env.calls.some(c => c[0] === 'bufferData' && c[2] === 1440000));
    assert.ok(env.calls.some(c => c[0] === 'bufferData' && c[2] === 480000));
    assert.equal(lastUniform(env, 'uniform1f', 'fadeWindow'), 1);
    assert.equal(lastUniform(env, 'uniform1f', 'clock'), 0.9);
    const uploads = env.calls.filter(c => c[0] === 'bufferSubData');
    assert.equal(uploads.at(-2)[3].length, 120000); assert.equal(uploads.at(-2)[3][0], 0);
    assert.ok(Math.abs(uploads.at(-2)[3].at(-1) - 0.9) < 1e-6);
    assert.equal(env.callbacks.size, 1);
    time = 1500; env.flush(); assert.equal(lastUniform(env, 'uniform1f', 'clock'), 1.4);
    assert.equal(env.calls.filter(c => c[0] === 'bufferSubData').length, uploads.length);
    assert.throws(() => renderer.setFrames([...frames, frame(1)]), /Invalid 3D frame batch/);
    assert.throws(() => renderer.setFrames([frame(1)], [99]), /Invalid frame receipt times/);
    assert.throws(() => renderer.setFrames([frame(1)], [Infinity]), /Invalid frame receipt times/);
    renderer.setFrames([] , []); env.flush(); assert.equal(env.callbacks.size, 0);
    renderer.destroy(); assert.equal(env.calls.filter(c => c[0] === 'deleteBuffer').length, 3);
    assert.throws(() => createPointCloudRenderer(environment().canvas, assert.fail, { historyWindowMs: 2000 }));
});


test('overview selected while empty fits resumed data after sensor-mode color fitting', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail, { viewMode: 'sensor' });
    renderer.setFrame(cloudFrame([[20, 10, 1], [22, 12, 2]])); env.flush();
    renderer.setFrame(null); renderer.setViewMode('overview'); env.flush();
    renderer.setFrame(cloudFrame([[20, 10, 1], [22, 12, 2]])); env.flush();
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [21, 11, 1.5]);
    assert.ok(lastUniform(env, 'uniform1f', 'distance') < 10);
    renderer.setViewMode('sensor'); renderer.setFrame(null); renderer.fit();
    renderer.setFrame(cloudFrame([[8, 4, 1], [10, 6, 2]])); env.flush();
    assert.deepEqual(lastUniform(env, 'uniform3fv', 'center'), [9, 5, 1.5]);
    renderer.destroy();
});

test('history is drawn oldest to newest with isolated depth so faded foreground cannot hide fresh points', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail, { accumulate: true });
    renderer.setFrames([cloudFrame([[2, 0, 0]]), cloudFrame([[5, 0, 0], [6, 0, 1]])]);
    const before = env.calls.length; env.flush();
    const calls = env.calls.slice(before), draws = calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS);
    assert.deepEqual(draws.map(c => c.slice(2)), [[0, 1], [1, 2]]);
    for (const draw of draws) assert.deepEqual(calls[calls.indexOf(draw) - 1], ['clear', env.gl.DEPTH_BUFFER_BIT]);
    renderer.destroy();
});


test('context loss detected during a fade draw reports the same recoverable message before DOM event delivery', () => {
    const env = environment(), errors = [];
    const renderer = createPointCloudRenderer(env.canvas, error => errors.push(error), { accumulate: true, now: () => 0 });
    renderer.setFrames([frame(1)], [0]);
    env.gl.getError = () => 1285; env.gl.isContextLost = () => true;
    env.flush();
    assert.equal(errors.length, 1);
    assert.equal(errors[0].message, '3D graphics context lost. Reconnect to restore the view.');
    env.events.get('webglcontextlost')({ preventDefault() {} }); assert.equal(errors.length, 1);
    renderer.destroy(); assert.equal(env.callbacks.size, 0);
});


test('sensor pointer drag turns right/down without moving origin and cancellation stops further look input', () => {
    const env = environment(), views = [];
    const renderer = createPointCloudRenderer(env.canvas, assert.fail, { viewMode: 'sensor', onView: view => views.push(view) });
    env.flush();
    env.events.get('pointerdown')({ button: 0, pointerId: 1, clientX: 0, clientY: 0 });
    env.events.get('pointermove')({ pointerId: 1, clientX: 40, clientY: 10 }); env.flush();
    assert.ok(views.at(-1).heading > 330 && views.at(-1).heading < 350);
    assert.ok(views.at(-1).elevation < 0); assert.equal(lastUniform(env, 'uniform1f', 'distance'), 0);
    env.events.get('pointercancel')({ pointerId: 1 });
    const before = views.length;
    env.events.get('pointermove')({ pointerId: 1, clientX: 80, clientY: 50 }); env.flush();
    assert.equal(views.length, before); renderer.destroy();
});


test('Overview zoom crosses two meters and continues to numeric precision limits with ordinary zoom-out recovery', () => {
    const env = environment(), renderer = createPointCloudRenderer(env.canvas, assert.fail);
    renderer.setFrame(cloudFrame([[0, 0, 0], [1, 1, 1]]));
    for (let i = 0; i < 100; i++) renderer.zoom(0.8);
    env.flush();
    let distance = lastUniform(env, 'uniform1f', 'distance');
    assert.ok(distance > 0 && distance < 1e-8);
    renderer.zoom(Number.MIN_VALUE); env.flush();
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), distance);
    for (let i = 0; i < 4000; i++) renderer.zoom(0.8);
    env.flush(); distance = lastUniform(env, 'uniform1f', 'distance');
    assert.ok(distance >= 2 ** -1022 && distance < 1e-300);
    renderer.zoom(1.25); env.flush();
    assert.ok(lastUniform(env, 'uniform1f', 'distance') > distance);
    renderer.zoom(1e308); env.flush();
    renderer.zoom(100); env.flush();
    assert.equal(lastUniform(env, 'uniform1f', 'distance'), 100);
    for (const invalid of [0, -1, NaN, Infinity]) renderer.zoom(invalid);
    env.flush(); assert.equal(lastUniform(env, 'uniform1f', 'distance'), 100);
    renderer.reset(); env.flush();
    assert.ok(lastUniform(env, 'uniform1f', 'distance') >= 2);
    renderer.destroy();
});
