import test from 'node:test';
import assert from 'node:assert/strict';
import { cameraBasis, createPointCloudRenderer, DEFAULT_VIEW_DISTANCE } from '../src/pointcloud/pointCloudRenderer.js';

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
    assert.deepEqual(env.calls.filter(call => call[0] === 'uniform3fv' && call[1] === 'eye').at(-1)[2], cameraBasis(-Math.PI / 4 - 40 * 0.008, 0.55 + 10 * 0.008).eye);
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


test('default/reset view fits every30m direction in landscape and portrait', () => {
    const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
    const basis = cameraBasis(-Math.PI / 4, 0.55);
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
