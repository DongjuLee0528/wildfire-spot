import React, { useEffect, useRef, useState } from 'react';
import { createPointCloudViewerSession } from '../pointcloud/pointCloudViewerSession.js';

const getToken = () => localStorage.getItem('jwt_token');
const labels = {
    CONNECTING: 'Connecting', STREAMING: 'Live', STALE: 'No fresh data', RETRYING: 'Retrying connection',
    EXHAUSTED: 'Connection retries exhausted', ERROR: 'Point cloud unavailable', CLOSED: 'Disconnected',
};

export default function PointCloudPanel({ deviceId }) {
    const viewport = useRef(null), session = useRef(null);
    const [attempt, setAttempt] = useState(0);
    const [status, setStatus] = useState({ state: 'CONNECTING', error: null, pointCount: 0, hasFrame: false });
    useEffect(() => {
        if (!deviceId) return;
        setStatus({ state: 'CONNECTING', error: null, pointCount: 0, hasFrame: false });
        const current = createPointCloudViewerSession({ container: viewport.current, deviceId, getToken, onUpdate: setStatus });
        session.current = current;
        return () => {
            session.current = null;
            const error = current.stop();
            if (error) console.error(error);
        };
    }, [deviceId, attempt]);
    const live = status.hasFrame;
    const unavailable = status.state === 'ERROR' || status.state === 'EXHAUSTED';
    const label = !deviceId ? 'No device selected' : status.state === 'CONNECTING' && live ? 'Reconnecting' : labels[status.state];
    return (
        <section className="panel point-cloud-panel" aria-label="LiDAR point cloud">
            <div className="point-cloud-heading">
                <h2 className="panel-title">LiDAR · 3D Point Cloud</h2>
                <span className={`point-cloud-state ${live ? 'text-success' : ''}`} role="status">{label}</span>
            </div>
            <div className="point-cloud-info">
                <span>Sensor range: 30 m</span>
                <span>{deviceId && live ? `${status.pointCount.toLocaleString()} points` : '— points'}</span>
                <span className="point-cloud-axis"><b>X</b> / <b>Y</b> / <b>Z ↑</b> · sensor axes</span>
            </div>
            <div className="point-cloud-viewport">
                <div className="point-cloud-surface" ref={viewport} />
                {(!deviceId || !live || status.pointCount === 0) && (
                    <div className="point-cloud-message">
                        <span>{!deviceId ? 'Select a device to view its point cloud.' :
                            live ? 'No points in the latest frame.' : status.error || 'Waiting for fresh LiDAR data.'}</span>
                    </div>
                )}
            </div>
            <div className="point-cloud-controls">
                <div className="point-cloud-view-buttons" role="group" aria-label="3D view controls">
                    <button type="button" onClick={() => session.current?.orbit(-0.2, 0)} disabled={!deviceId || unavailable} aria-label="Orbit left">←</button>
                    <button type="button" onClick={() => session.current?.orbit(0.2, 0)} disabled={!deviceId || unavailable} aria-label="Orbit right">→</button>
                    <button type="button" onClick={() => session.current?.orbit(0, 0.15)} disabled={!deviceId || unavailable} aria-label="Orbit up">↑</button>
                    <button type="button" onClick={() => session.current?.orbit(0, -0.15)} disabled={!deviceId || unavailable} aria-label="Orbit down">↓</button>
                    <button type="button" onClick={() => session.current?.zoom(0.8)} disabled={!deviceId || unavailable} aria-label="Zoom in">+</button>
                    <button type="button" onClick={() => session.current?.zoom(1.25)} disabled={!deviceId || unavailable} aria-label="Zoom out">−</button>
                    <button type="button" onClick={() => session.current?.reset()} disabled={!deviceId || unavailable}>Reset view</button>
                </div>
                <button type="button" onClick={() => setAttempt(value => value + 1)} disabled={!deviceId}>Reconnect</button>
            </div>
            <p className="point-cloud-hint">Drag to orbit · Scroll to zoom · Grid: 5 m · Color: Z −3 m (blue) to +5 m (amber), clamped</p>
        </section>
    );
}
