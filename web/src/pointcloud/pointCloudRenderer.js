import { MAX_FRAME_POINTS, MAX_HISTORY_FRAMES, MAX_HISTORY_POINTS } from './pointCloudHistory.js';
export const DEFAULT_VIEW_DISTANCE = 65;
const vertexSource = `
attribute vec3 position;
uniform vec3 eye, right, up, center;
uniform vec2 heightRange;
uniform float distance, aspect, pointSize;
uniform bool points;
uniform vec3 tint;
varying vec3 color;
void main() {
    vec3 relative = position - center;
    float depth = distance - dot(relative, eye);
    float scale = 1.7320508 * min(1.0, aspect);
    gl_Position = vec4(dot(relative, right) * scale / aspect,
        dot(relative, up) * scale, 1.0010005 * depth - 0.20010005, depth);
    gl_PointSize = pointSize;
    float height = clamp((position.z - heightRange.x) / (heightRange.y - heightRange.x), 0.0, 1.0);
    vec3 low = vec3(0.12, 0.35, 1.0), middle = vec3(0.0, 0.95, 0.9);
    vec3 high = vec3(1.0, 0.92, 0.12), top = vec3(1.0, 0.22, 0.12);
    vec3 heightColor = height < 0.3333333 ? mix(low, middle, height * 3.0) :
        height < 0.6666667 ? mix(middle, high, height * 3.0 - 1.0) : mix(high, top, height * 3.0 - 2.0);
    color = points ? heightColor : tint;
}`;
const fragmentSource = `
precision mediump float;
uniform bool points;
varying vec3 color;
void main() {
    if (points && length(gl_PointCoord - vec2(0.5)) > 0.5) discard;
    gl_FragColor = vec4(color, 1.0);
}`;

export function cameraBasis(yaw, pitch) {
    const c = Math.cos(pitch), s = Math.sin(pitch), x = Math.cos(yaw), y = Math.sin(yaw);
    return { eye: [c * x, c * y, s], right: [-y, x, 0], up: [-s * x, -s * y, c] };
}

export function fitPointCloud(positions, count) {
    if (!Number.isInteger(count) || count < 1 || count > MAX_HISTORY_POINTS || positions.length < count * 3)
        throw new Error('Invalid point cloud for scene fitting');
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < count * 3; i++) {
        const value = positions[i], axis = i % 3;
        if (!Number.isFinite(value)) throw new Error('Invalid point-cloud coordinate');
        min[axis] = Math.min(min[axis], value); max[axis] = Math.max(max[axis], value);
    }
    const center = min.map((value, axis) => (value + max[axis]) / 2);
    let radius = 0;
    for (let i = 0; i < count; i++) radius = Math.max(radius,
        Math.hypot(positions[i * 3] - center[0], positions[i * 3 + 1] - center[1], positions[i * 3 + 2] - center[2]));
    const heightMiddle = (min[2] + max[2]) / 2, heightSpan = Math.max(0.5, max[2] - min[2]);
    return { center, distance: Math.max(2, Math.min(100, radius * 2.2)),
        heightRange: [heightMiddle - heightSpan / 2, heightMiddle + heightSpan / 2] };
}

export function createPointCloudRenderer(canvas, onError, { accumulate = false } = {}) {
    const gl = canvas.getContext('webgl', { alpha: false, antialias: false });
    if (!gl) throw new Error('WebGL is unavailable');
    let disposed = false, failed = false, raf = null, observer = null, pointer = null;
    let yaw = -Math.PI / 4, pitch = 0.35, distance = DEFAULT_VIEW_DISTANCE, count = 0;
    let center = [0, 0, 0], heightRange = [-0.25, 0.25], fitted = false;
    const capacity = accumulate ? MAX_HISTORY_POINTS : MAX_FRAME_POINTS;
    const vertices = new Float32Array(capacity * 3);
    const buffers = [], shaders = [], listeners = [];
    let program;
    const listen = (target, name, handler, options) => {
        target.addEventListener(name, handler, options);
        listeners.push(() => target.removeEventListener(name, handler, options));
    };
    const destroy = () => {
        if (disposed) return;
        disposed = true;
        if (raf != null) cancelAnimationFrame(raf);
        observer?.disconnect();
        for (const remove of listeners) remove();
        if (pointer && canvas.hasPointerCapture(pointer.id)) canvas.releasePointerCapture(pointer.id);
        pointer = null;
        for (const buffer of buffers) gl.deleteBuffer(buffer);
        if (program) gl.deleteProgram(program);
        for (const shader of shaders) gl.deleteShader(shader);
        gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
    const fail = (error) => {
        if (disposed || failed) return;
        failed = true;
        onError(error instanceof Error ? error : new Error('3D rendering failed'));
    };
    try {
        for (const [type, source] of [[gl.VERTEX_SHADER, vertexSource], [gl.FRAGMENT_SHADER, fragmentSource]]) {
            const shader = gl.createShader(type);
            if (!shader) throw new Error('Unable to allocate a 3D shader');
            shaders.push(shader); gl.shaderSource(shader, source); gl.compileShader(shader);
            if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error('Unable to compile a 3D shader');
        }
        program = gl.createProgram();
        if (!program) throw new Error('Unable to allocate the 3D program');
        for (const shader of shaders) gl.attachShader(program, shader);
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('Unable to link the 3D program');
        gl.useProgram(program);
        const position = gl.getAttribLocation(program, 'position');
        const uniforms = Object.fromEntries(['eye', 'right', 'up', 'center', 'heightRange', 'distance', 'aspect', 'pointSize', 'points', 'tint']
            .map(name => [name, gl.getUniformLocation(program, name)]));
        if (position < 0 || Object.values(uniforms).some(value => value == null)) throw new Error('Invalid 3D program attributes');
        const allocate = (data, usage) => {
            const buffer = gl.createBuffer();
            if (!buffer) throw new Error('Unable to allocate a 3D buffer');
            buffers.push(buffer); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, usage);
            return buffer;
        };
        const cloud = allocate(vertices.byteLength, gl.DYNAMIC_DRAW);
        const grid = [];
        for (let n = -30; n <= 30; n += 5) grid.push(-30, n, 0, 30, n, 0, n, -30, 0, n, 30, 0);
        grid.push(0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 3);
        const reference = allocate(new Float32Array(grid), gl.STATIC_DRAW);
        const maxPointSize = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1];
        gl.enable(gl.DEPTH_TEST); gl.clearColor(0.027, 0.035, 0.047, 1);
        const bind = buffer => {
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
            gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0); gl.enableVertexAttribArray(position);
        };
        const draw = () => {
            raf = null;
            if (disposed || failed) return;
            try {
                const rect = canvas.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return;
                const dpr = Math.min(2, window.devicePixelRatio || 1, 2048 / Math.max(rect.width, rect.height));
                const width = Math.max(1, Math.min(2048, Math.round(rect.width * dpr)));
                const height = Math.max(1, Math.min(2048, Math.round(rect.height * dpr)));
                if (canvas.width !== width) canvas.width = width;
                if (canvas.height !== height) canvas.height = height;
                gl.viewport(0, 0, canvas.width, canvas.height);
                gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
                const basis = cameraBasis(yaw, pitch);
                for (const name of ['eye', 'right', 'up']) gl.uniform3fv(uniforms[name], basis[name]);
                gl.uniform3fv(uniforms.center, center); gl.uniform2fv(uniforms.heightRange, heightRange);
                gl.uniform1f(uniforms.distance, distance); gl.uniform1f(uniforms.aspect, rect.width / rect.height);
                gl.uniform1f(uniforms.pointSize, Math.min(maxPointSize, Math.max(1, 2 * dpr)));
                bind(reference); gl.uniform1i(uniforms.points, 0); gl.uniform3fv(uniforms.tint, [0.11, 0.17, 0.21]);
                gl.drawArrays(gl.LINES, 0, grid.length / 3 - 6);
                for (const [i, color] of [[0, [0.95, 0.3, 0.3]], [1, [0.3, 0.9, 0.5]], [2, [0.35, 0.6, 1]]]) {
                    gl.uniform3fv(uniforms.tint, color); gl.drawArrays(gl.LINES, grid.length / 3 - 6 + i * 2, 2);
                }
                bind(cloud); gl.uniform1i(uniforms.points, 1); gl.drawArrays(gl.POINTS, 0, count);
                if (gl.getError() !== gl.NO_ERROR) throw new Error('3D rendering failed');
            } catch (error) { fail(error); }
        };
        const schedule = () => { if (!disposed && !failed && raf == null) raf = requestAnimationFrame(draw); };
        const fit = () => {
            if (disposed || failed || count === 0) return;
            ({ center, distance, heightRange } = fitPointCloud(vertices, count));
            fitted = true; schedule();
        };
        const orbit = (dx, dy) => {
            if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;
            yaw = (yaw + dx) % (Math.PI * 2); pitch = Math.max(-1.45, Math.min(1.45, pitch + dy)); schedule();
        };
        const zoom = factor => {
            if (!Number.isFinite(factor) || factor <= 0) return;
            distance = Math.max(2, Math.min(100, distance * factor)); schedule();
        };
        listen(canvas, 'pointerdown', event => {
            if (pointer || event.button !== 0) return;
            canvas.setPointerCapture(event.pointerId);
            pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
        });
        listen(canvas, 'pointermove', event => {
            if (!pointer || pointer.id !== event.pointerId) return;
            orbit((pointer.x - event.clientX) * 0.008, (event.clientY - pointer.y) * 0.008);
            pointer.x = event.clientX; pointer.y = event.clientY;
        });
        const release = event => {
            if (!pointer || pointer.id !== event.pointerId) return;
            if (canvas.hasPointerCapture(pointer.id)) canvas.releasePointerCapture(pointer.id);
            pointer = null;
        };
        listen(canvas, 'pointerup', release); listen(canvas, 'pointercancel', release); listen(canvas, 'lostpointercapture', release);
        listen(canvas, 'wheel', event => {
            event.preventDefault(); zoom(Math.exp(Math.max(-200, Math.min(200, event.deltaY)) * 0.003));
        }, { passive: false });
        listen(canvas, 'webglcontextlost', event => { event.preventDefault(); fail(new Error('3D graphics context lost. Reconnect to restore the view.')); });
        listen(window, 'resize', schedule);
        observer = new ResizeObserver(schedule); observer.observe(canvas); schedule();
        if (gl.getError() !== gl.NO_ERROR) throw new Error('Unable to initialize 3D graphics');
        const setFrames = frames => {
            if (disposed || failed) return;
            if (!Array.isArray(frames) || frames.length > (accumulate ? MAX_HISTORY_FRAMES : 1))
                throw new Error('Invalid 3D frame batch');
            let nextCount = 0;
            for (const frame of frames) {
                if (!(frame.data instanceof Uint8Array) || !Number.isInteger(frame.pointCount) || frame.pointCount < 0 ||
                    frame.pointCount > MAX_FRAME_POINTS || frame.data.byteLength !== 32 + frame.pointCount * 12)
                    throw new Error('Invalid 3D frame');
                nextCount += frame.pointCount;
            }
            if (nextCount > capacity) throw new Error('3D point capacity exceeded');
            let offset = 0;
            for (const frame of frames) {
                const view = new DataView(frame.data.buffer, frame.data.byteOffset, frame.data.byteLength);
                for (let i = 0; i < frame.pointCount * 3; i++) {
                    const value = view.getFloat32(32 + i * 4, true);
                    if (!Number.isFinite(value)) throw new Error('Invalid point-cloud coordinate');
                    vertices[offset++] = value;
                }
            }
            count = nextCount;
            if (frames.length > 0) {
                gl.bindBuffer(gl.ARRAY_BUFFER, cloud);
                gl.bufferSubData(gl.ARRAY_BUFFER, 0, vertices.subarray(0, count * 3));
                if (!fitted) fit();
            }
            schedule();
        };
        return {
            setFrame(frame) { setFrames(frame == null ? [] : [frame]); },
            setFrames,
            orbit, zoom, fit,
            reset() {
                if (disposed || failed) return;
                yaw = -Math.PI / 4; pitch = 0.35;
                if (count > 0) fit();
                else { center = [0, 0, 0]; distance = DEFAULT_VIEW_DISTANCE; heightRange = [-0.25, 0.25]; fitted = false; schedule(); }
            },
            destroy,
        };
    } catch (error) { destroy(); throw error; }
}
