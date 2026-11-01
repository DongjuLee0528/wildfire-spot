import { createPointCloudRenderer } from './pointCloudRenderer.js';
import { connectPointCloud } from '../transport/pointCloudTransport.js';

export function createPointCloudViewerSession({ container, deviceId, getToken, onUpdate,
    createRenderer = createPointCloudRenderer, connect = connectPointCloud }) {
    let disposed = false, failed = false, renderer = null, transport = null, cleanupError = null;
    let status = { state: 'CONNECTING', error: null, pointCount: 0, hasFrame: false };
    const canvas = container.ownerDocument.createElement('canvas');
    canvas.className = 'point-cloud-canvas';
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Live 3D LiDAR point cloud. Drag to orbit and scroll to zoom.');
    container.append(canvas);
    const cleanup = () => {
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
        status = { state: 'ERROR', error: error instanceof Error ? error.message : '3D viewer unavailable', pointCount: 0, hasFrame: false };
        onUpdate({ ...status });
    };
    const publish = patch => {
        if (disposed || failed) return;
        status = { ...status, ...patch }; onUpdate({ ...status });
    };
    try {
        renderer = createRenderer(canvas, fail);
        if (failed) { renderer.destroy(); renderer = null; }
        else {
            transport = connect({ deviceId, getToken,
                onFrame(frame) {
                    if (disposed || failed) return;
                    try {
                        renderer.setFrame(frame);
                        publish({ pointCount: frame?.pointCount ?? 0, hasFrame: frame != null });
                    } catch (error) { fail(error); }
                },
                onState(next) { publish(next); },
            });
            if (failed || disposed) transport.stop();
        }
    } catch (error) { fail(error); }
    return {
        orbit(dx, dy) { if (!disposed && !failed) renderer?.orbit(dx, dy); },
        zoom(factor) { if (!disposed && !failed) renderer?.zoom(factor); },
        reset() { if (!disposed && !failed) renderer?.reset(); },
        stop() {
            if (!disposed) { disposed = true; cleanup(); }
            return cleanupError;
        },
        getStatus: () => ({ ...status, cleanupError }),
    };
}
