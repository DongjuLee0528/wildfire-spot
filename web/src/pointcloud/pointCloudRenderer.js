const MAX_POINTS = 12000;
export const DEFAULT_VIEW_DISTANCE = 65;
const vertexSource = `
attribute vec3 position;
uniform vec3 eye, right, up;
uniform float distance, aspect, pointSize;
uniform bool points;
uniform vec3 tint;
varying vec3 color;
void main() {
    float depth = distance - dot(position, eye);
    float scale = 1.7320508 * min(1.0, aspect);
    gl_Position = vec4(dot(position, right) * scale / aspect,
        dot(position, up) * scale, 1.0010005 * depth - 0.20010005, depth);
    gl_PointSize = pointSize;
    float height = clamp((position.z + 3.0) / 8.0, 0.0, 1.0);
    color = points ? mix(vec3(0.05, 0.72, 0.9), vec3(1.0, 0.78, 0.2), height) : tint;
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

export function createPointCloudRenderer(canvas, onError) {
    const gl = canvas.getContext('webgl', { alpha: false, antialias: false });
    if (!gl) throw new Error('WebGL is unavailable');
    let disposed = false, failed = false, raf = null, observer = null, pointer = null;
    let yaw = -Math.PI / 4, pitch = 0.55, distance = DEFAULT_VIEW_DISTANCE, count = 0;
    const vertices = new Float32Array(MAX_POINTS * 3);
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
        const uniforms = Object.fromEntries(['eye', 'right', 'up', 'distance', 'aspect', 'pointSize', 'points', 'tint']
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
                const dpr = Math.min(2, window.devicePixelRatio || 1);
                const width = Math.max(1, Math.min(2048, Math.round(rect.width * dpr)));
                const height = Math.max(1, Math.min(2048, Math.round(rect.height * dpr)));
                if (canvas.width !== width) canvas.width = width;
                if (canvas.height !== height) canvas.height = height;
                gl.viewport(0, 0, canvas.width, canvas.height);
                gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
                const basis = cameraBasis(yaw, pitch);
                for (const name of ['eye', 'right', 'up']) gl.uniform3fv(uniforms[name], basis[name]);
                gl.uniform1f(uniforms.distance, distance); gl.uniform1f(uniforms.aspect, rect.width / rect.height);
                gl.uniform1f(uniforms.pointSize, Math.min(maxPointSize, 3 * dpr));
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
        return {
            setFrame(frame) {
                if (disposed || failed) return;
                if (frame == null) count = 0;
                else {
                    if (!(frame.data instanceof Uint8Array) || !Number.isInteger(frame.pointCount) || frame.pointCount < 0 ||
                        frame.pointCount > MAX_POINTS || frame.data.byteLength !== 32 + frame.pointCount * 12)
                        throw new Error('Invalid 3D frame');
                    const view = new DataView(frame.data.buffer, frame.data.byteOffset, frame.data.byteLength);
                    for (let i = 0; i < frame.pointCount * 3; i++) vertices[i] = view.getFloat32(32 + i * 4, true);
                    count = frame.pointCount;
                    gl.bindBuffer(gl.ARRAY_BUFFER, cloud); gl.bufferSubData(gl.ARRAY_BUFFER, 0, vertices.subarray(0, count * 3));
                }
                schedule();
            },
            orbit, zoom,
            reset() { yaw = -Math.PI / 4; pitch = 0.55; distance = DEFAULT_VIEW_DISTANCE; schedule(); },
            destroy,
        };
    } catch (error) { destroy(); throw error; }
}
