import test from 'node:test';
import assert from 'node:assert/strict';
import { cameraBasis, createPointCloudRenderer, DEFAULT_VIEW_DISTANCE, fitPointCloud } from '../src/pointcloud/pointCloudRenderer.js';

function environment(fault = '') {
    const calls = [], callbacks = new Map(), events = new Map(), removed = [];
    let id = 0;
    const gl = new Proxy({ NO_ERROR: 0, ALIASED_POINT_SIZE_RANGE: 1, COMPILE_STATUS: 2, LINK_STATUS: 3,
        VERTEX_SHADER: 4, FRAGMENT_SHADER: 5, ARRAY_BUFFER: 6, DYNAMIC_DRAW: 7, STATIC_DRAW: 8,
        DEPTH_TEST: 9, COLOR_BUFFER_BIT: 16, DEPTH_BUFFER_BIT: 32, LINES: 10, POINTS: 11, FLOAT: 12,
        createShader: () => ({}), getShaderParameter: () => fault !== 'compile',
        createProgram: () => ({}), getProgramParameter: () => fault !== 'link',
        createBuffer: () => fault === 'allocation' ? null : {},
        getAttribLocation: () => 0, getUniformLocation: (_program, name) => name, getParameter: () => [1, 4],
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
    assert.equal(env.calls.filter(call => call[0] === 'uniform1f' && call[1] === 'distance').at(-1)[2], 2);
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
    assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 60000);
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
        assert.equal(received.length, before + 1); assert.equal(received.at(-1)[3].length, 0);
        renderer.setFrame(null); env.flush();
        assert.equal(env.calls.filter(call => call[0] === 'bufferSubData').length, received.length);
        assert.equal(env.calls.filter(c => c[0] === 'drawArrays' && c[1] === env.gl.POINTS).at(-1)[3], 0);
        renderer.destroy();
    }
});
