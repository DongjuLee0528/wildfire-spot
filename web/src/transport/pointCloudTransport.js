import { PointCloudMetrics } from '../pointcloud/pointCloudMetrics.js';

const MAX_FRAME = 144032;

export class TruncatedFrameError extends Error {}
export class PointCloudProtocolError extends Error {}

export class PointCloudDecoder {
    constructor(metrics = null) {
        this.metrics = metrics;
        this.buffer = new Uint8Array(MAX_FRAME);
        this.offset = 0;
        this.total = 32;
    }

    feed(chunk) {
        let latest = null;
        let position = 0;
        while (position < chunk.length) {
            const count = Math.min(this.total - this.offset, chunk.length - position);
            this.buffer.set(chunk.subarray(position, position + count), this.offset);
            this.offset += count;
            position += count;
            const view = new DataView(this.buffer.buffer);
            if (this.offset === 32 && this.total === 32) {
                if (this.buffer[0] !== 76 || this.buffer[1] !== 50 || this.buffer[2] !== 80 || this.buffer[3] !== 67 ||
                    view.getUint32(4, true) !== 1) throw new PointCloudProtocolError('Invalid point-cloud magic/version');
                const size = view.getUint32(8, true), points = view.getUint32(12, true);
                const timestamp = view.getFloat64(16, true);
                if (points > 12000 || size !== points * 12 || !Number.isFinite(timestamp) || timestamp < 0)
                    throw new PointCloudProtocolError('Invalid point-cloud header');
                this.total = 32 + size;
            }
            if (this.offset === this.total && this.offset >= 32) {
                for (let offset = 32; offset < this.total; offset += 12) {
                    const x = view.getFloat32(offset, true), y = view.getFloat32(offset + 4, true), z = view.getFloat32(offset + 8, true);
                    const distance = x * x + y * y + z * z;
                    if (!Number.isFinite(distance) || distance <= 0 || distance > 900)
                        throw new PointCloudProtocolError('Invalid point-cloud coordinates');
                }
                latest = {
                    data: this.buffer.slice(0, this.total),
                    pointCount: view.getUint32(12, true), timestamp: view.getFloat64(16, true),
                    cloudId: view.getUint32(24, true), ringCount: view.getUint32(28, true),
                };
                this.metrics?.record(latest);
                this.offset = 0;
                this.total = 32;
            }
        }
        return latest;
    }

    finish() {
        if (this.offset) throw new TruncatedFrameError('Truncated point-cloud frame');
    }
}

export function connectPointCloud({ deviceId, getToken, onFrame, onState, localMode = false,
    fetchImpl = globalThis.fetch, retryDelays = [1000, 2000, 4000, 8000, 16000],
    staleMs = 2000, timeoutMs = 6000, stableMs = 10000, rotationMs = 55000 }) {
    if ((!localMode && !deviceId) || typeof getToken !== 'function' || typeof onFrame !== 'function' || typeof onState !== 'function' ||
        retryDelays.length > 5 || retryDelays.some(value => !Number.isFinite(value) || value < 0) ||
        ![staleMs, timeoutMs, stableMs, rotationMs].every(value => Number.isFinite(value) && value > 0) || timeoutMs <= staleMs)
        throw new TypeError('Invalid point-cloud transport settings');
    const decodedMetrics = new PointCloudMetrics('browser_decoded');
    const deliveredMetrics = new PointCloudMetrics('viewer_delivered');
    let stopped = false, controller = null, reader = null, staleTimer = null, waitTimer = null, finishWait = null;
    let currentState = 'CONNECTING', failure = null, lastPublishedAt = null, consumerFailed = false;
    const timers = new Set();
    const emitState = (state) => {
        if (stopped) return;
        currentState = state;
        if (!stopped) onState({ state, error: failure });
    };
    const cancelTimer = (id) => { if (id != null) { clearTimeout(id); timers.delete(id); } };
    const clearStale = () => { cancelTimer(staleTimer); staleTimer = null; };
    const wait = (ms) => new Promise(resolve => {
        if (stopped) { resolve(); return; }
        finishWait = resolve;
        waitTimer = setTimeout(() => { timers.delete(waitTimer); waitTimer = null; finishWait = null; resolve(); }, ms);
        timers.add(waitTimer);
    });
    const timed = async (promise, ms) => {
        let timer, onAbort;
        const attempt = controller;
        try {
            return await Promise.race([promise, new Promise((_, reject) => {
                onAbort = () => reject(new Error('Point-cloud request aborted'));
                if (attempt.signal.aborted) { onAbort(); return; }
                attempt.signal.addEventListener('abort', onAbort, { once: true });
                timer = setTimeout(() => { timers.delete(timer); attempt.abort(); reject(new Error('Point-cloud read timed out')); }, ms);
                timers.add(timer);
            })]);
        } finally {
            cancelTimer(timer);
            if (onAbort) attempt.signal.removeEventListener('abort', onAbort);
        }
    };
    const armStale = () => {
        clearStale();
        if (lastPublishedAt == null || stopped) return;
        staleTimer = setTimeout(() => {
            timers.delete(staleTimer); staleTimer = null;
            if (!stopped) {
                try { lastPublishedAt = null; clearDisplay(); emitState('STALE'); }
                catch {
                    consumerFailed = true; controller?.abort();
                    if (finishWait) {
                        cancelTimer(waitTimer); waitTimer = null;
                        const resolve = finishWait; finishWait = null; resolve();
                    }
                }
            }
        }, Math.max(0, staleMs - (performance.now() - lastPublishedAt)));
        timers.add(staleTimer);
    };
    const clearDisplay = () => { if (!stopped) onFrame(null); };
    const stop = () => {
        if (stopped) return;
        stopped = true; currentState = 'CLOSED';
        for (const timer of timers) clearTimeout(timer);
        timers.clear();
        if (finishWait) finishWait();
        finishWait = null;
        controller?.abort();
        if (reader) {
            try { Promise.resolve(reader.cancel()).catch(() => { failure ??= 'Point-cloud reader cancellation failed'; }); }
            catch { failure ??= 'Point-cloud reader cancellation failed'; }
        }
    };

    const done = (async () => {
        await Promise.resolve();
        let failures = 0;
        while (!stopped) {
            if (consumerFailed) { failure = 'Point-cloud consumer callback failed'; emitState('ERROR'); return; }
            let permanent = false, cleanRotation = false;
            const started = performance.now();
            let firstFrame = null, lastFrame = started;
            controller = new AbortController();
            const decoder = new PointCloudDecoder(decodedMetrics);
            try {
                failure = null;
                emitState('CONNECTING');
                if (stopped) break;
                let token;
                try { token = localMode ? null : getToken(); }
                catch { permanent = true; failure = 'Authentication callback failed'; throw new Error(failure); }
                if (stopped) break;
                if (!localMode && (typeof token !== 'string' || !token)) { permanent = true; failure = 'Authentication required'; throw new Error(failure); }
                const attempt = controller;
                const response = await timed(Promise.resolve(fetchImpl(localMode ? '/robot/point-cloud/stream' : `/api/devices/${encodeURIComponent(deviceId)}/point-cloud/stream`, {
                    headers: localMode ? {} : { Authorization: `Bearer ${token}` }, signal: controller.signal, cache: 'no-store', redirect: 'error',
                })).then(async response => {
                    if (attempt.signal.aborted) {
                        if (response.body) await response.body.cancel();
                        throw new Error('Point-cloud request aborted');
                    }
                    return response;
                }), timeoutMs);
                if (stopped) { if (response.body) await response.body.cancel(); break; }
                if (response.status !== 200) {
                    permanent = ![429, 503].includes(response.status) && response.status < 500;
                    failure = [401, 403].includes(response.status) ? 'Authentication required' : `Point-cloud HTTP ${response.status}`;
                    if (response.body) await response.body.cancel();
                    throw new Error(failure);
                }
                if (!response.body || response.headers.get('content-type')?.split(';')[0] !== 'application/octet-stream') {
                    permanent = true;
                    if (response.body) await response.body.cancel();
                    throw new PointCloudProtocolError('Invalid point-cloud response');
                }
                reader = response.body.getReader();
                while (!stopped) {
                    const remaining = timeoutMs - (performance.now() - lastFrame);
                    if (remaining <= 0) throw new Error('Point-cloud read timed out');
                    const result = await timed(reader.read(), remaining);
                    if (stopped) break;
                    if (result.done) {
                        decoder.finish();
                        cleanRotation = firstFrame != null && performance.now() - started >= rotationMs;
                        break;
                    }
                    const frame = decoder.feed(result.value);
                    if (frame) {
                        lastFrame = performance.now();
                        if (firstFrame == null) firstFrame = lastFrame;
                        lastPublishedAt = lastFrame;
                        try { onFrame(frame); deliveredMetrics.record(frame); emitState('STREAMING'); }
                        catch { consumerFailed = true; throw new Error('Point-cloud consumer callback failed'); }
                        armStale();
                        if (lastFrame - firstFrame >= stableMs) failures = 0;
                    }
                }
            } catch (error) {
                if (stopped) break;
                failure ??= error instanceof PointCloudProtocolError ? error.message :
                    consumerFailed ? 'Point-cloud consumer callback failed' :
                    error instanceof TruncatedFrameError ? 'Point-cloud connection truncated' : 'Point-cloud connection unavailable';
                permanent = permanent || error instanceof PointCloudProtocolError || consumerFailed;
            } finally {
                if (!cleanRotation) clearStale();
                controller.abort();
                if (reader) {
                    try { await reader.cancel(); } catch { failure ??= 'Point-cloud connection closed'; }
                    try { reader.releaseLock(); } catch { failure ??= 'Point-cloud reader closed'; }
                    reader = null;
                }
            }
            if (stopped) break;
            if (cleanRotation) { failures = 0; await wait(100); continue; }
            try { lastPublishedAt = null; clearDisplay(); }
            catch { permanent = true; failure = 'Point-cloud consumer callback failed'; }
            if (permanent) { emitState('ERROR'); return; }
            if (failures >= retryDelays.length) { emitState('EXHAUSTED'); return; }
            emitState('RETRYING');
            await wait(retryDelays[failures++]);
        }
    })().catch(() => {
        failure = 'Point-cloud consumer callback failed';
        currentState = 'ERROR';
        stop();
        currentState = 'ERROR';
    }).finally(() => { decodedMetrics.finish(); deliveredMetrics.finish(); });
    return { stop, done, getStatus: () => ({ state: currentState, error: failure }) };
}
