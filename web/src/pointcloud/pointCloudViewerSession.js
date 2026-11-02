import { createPointCloudRenderer } from './pointCloudRenderer.js';
import { PointCloudHistory } from './pointCloudHistory.js';
import { connectPointCloud } from '../transport/pointCloudTransport.js';

export function createPointCloudViewerSession({ container, deviceId, getToken, onUpdate,
    createRenderer = createPointCloudRenderer, connect = connectPointCloud, accumulate = false,
    historyWindowMs = 500, viewMode = 'sensor',
    now = () => performance.now(), setTimer = setTimeout, clearTimer = clearTimeout }) {
    let disposed = false, failed = false, renderer = null, transport = null, cleanupError = null;
    let status = { state: 'CONNECTING', error: null, pointCount: 0, latestPointCount: 0, frameCount: 0, hasFrame: false };
    const history = accumulate ? new PointCloudHistory(now, historyWindowMs) : null;
    let historyTimer = null;
    const canvas = container.ownerDocument.createElement('canvas');
    canvas.className = 'point-cloud-canvas';
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Live 3D LiDAR point cloud. Sensor view: drag to look around and scroll to change field of view. Overview: drag to orbit and scroll to change camera distance. Sensor frame: +X front, -X rear, +Y left, -Y right, +Z up.');
    container.append(canvas);
    const cancelHistoryTimer = () => {
        if (historyTimer != null) clearTimer(historyTimer);
        historyTimer = null;
    };
    const cleanup = () => {
        cancelHistoryTimer(); history?.clear();
        const previousTransport = transport, previousRenderer = renderer;
        transport = renderer = null;
        try { previousTransport?.stop(); }
        catch { cleanupError = 'Point-cloud connection cleanup failed'; }
        try { previousRenderer?.destroy(); }
        catch { cleanupError = 'Point-cloud graphics cleanup failed'; }
        canvas.remove();
    };
    const fail = error => {
        if (disposed || failed) return;
        failed = true;
        cleanup();
        status = { state: 'ERROR', error: error instanceof Error ? error.message : '3D viewer unavailable', pointCount: 0, latestPointCount: 0, frameCount: 0, hasFrame: false };
        try { onUpdate({ ...status }); }
        catch { cleanupError = [cleanupError, 'Point-cloud status callback failed'].filter(Boolean).join('; '); console.error(cleanupError); }
    };
    const publish = patch => {
        if (disposed || failed) return;
        status = { ...status, ...patch }; onUpdate({ ...status });
    };
    const renderHistory = () => {
        cancelHistoryTimer();
        const current = history.snapshot();
        renderer.setFrames(current.frames, current.receivedAt);
        publish({ pointCount: current.pointCount, latestPointCount: current.latestPointCount,
            frameCount: current.frames.length, hasFrame: current.frames.length > 0 });
        if (!disposed && !failed && current.expiresAt != null) {
            historyTimer = setTimer(() => {
                historyTimer = null;
                if (disposed || failed) return;
                try {
                    renderHistory();
                    if (!status.hasFrame && ['STREAMING', 'CONNECTING'].includes(status.state))
                        publish({ state: 'STALE', error: null });
                } catch (error) { fail(error); }
            }, Math.max(1, current.expiresAt - now()));
        }
    };
    try {
        renderer = createRenderer(canvas, fail, { accumulate, historyWindowMs, viewMode, now, onView: view => publish({ view }) });
        if (failed) { renderer.destroy(); renderer = null; }
        else {
            transport = connect({ deviceId, getToken,
                onFrame(frame) {
                    if (disposed || failed) return;
                    try {
                        if (history) {
                            if (frame == null) history.clear();
                            else history.push(frame);
                            renderHistory();
                        } else {
                            renderer.setFrame(frame);
                            publish({ pointCount: frame?.pointCount ?? 0, latestPointCount: frame?.pointCount ?? 0,
                                frameCount: frame == null ? 0 : 1, hasFrame: frame != null });
                        }
                    } catch (error) { fail(error); }
                },
                onState(next) {
                    if (disposed || failed) return;
                    try {
                        if (history && ['STALE', 'RETRYING', 'ERROR', 'EXHAUSTED', 'CLOSED'].includes(next.state)) {
                            history.clear(); renderHistory();
                        }
                        if (history && next.state === 'STREAMING' && !status.hasFrame)
                            publish({ ...next, state: 'STALE' });
                        else publish(next);
                    } catch (error) { fail(error); }
                },
            });
            if (failed || disposed) transport.stop();
        }
    } catch (error) { fail(error); }
    return {
        orbit(dx, dy) { if (!disposed && !failed) renderer?.orbit(dx, dy); },
        zoom(factor) { if (!disposed && !failed) renderer?.zoom(factor); },
        setViewMode(mode) { if (!disposed && !failed) renderer?.setViewMode(mode); },
        fit() { if (!disposed && !failed) renderer?.fit(); },
        reset() { if (!disposed && !failed) renderer?.reset(); },
        stop() {
            if (!disposed) { disposed = true; cleanup(); }
            return cleanupError;
        },
        getStatus: () => ({ ...status, cleanupError }),
    };
}
