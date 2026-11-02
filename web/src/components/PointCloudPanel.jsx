import React, { useEffect, useRef, useState } from 'react';
import { createPointCloudViewerSession } from '../pointcloud/pointCloudViewerSession.js';

const getToken = () => localStorage.getItem('jwt_token');
const labels = {
    CONNECTING: 'Connecting', STREAMING: 'Live', STALE: 'No fresh data', RETRYING: 'Retrying connection',
    EXHAUSTED: 'Connection retries exhausted', ERROR: 'Point cloud unavailable', CLOSED: 'Disconnected',
};

export default function PointCloudPanel({ deviceId }) {
    const viewport = useRef(null), session = useRef(null), preferredView = useRef('sensor');
    const [attempt, setAttempt] = useState(0);
    const [accumulate, setAccumulate] = useState(false);
    const [historyWindowMs, setHistoryWindowMs] = useState(1000);
    const [status, setStatus] = useState({ state: 'CONNECTING', error: null, pointCount: 0, hasFrame: false });
    useEffect(() => {
        if (!deviceId) return;
        setStatus({ state: 'CONNECTING', error: null, pointCount: 0, hasFrame: false });
        const current = createPointCloudViewerSession({ container: viewport.current, deviceId, getToken, onUpdate: next => {
            if (next.view) preferredView.current = next.view.mode;
            setStatus(next);
        }, accumulate, historyWindowMs, viewMode: preferredView.current });
        session.current = current;
        return () => {
            session.current = null;
            const error = current.stop();
            if (error) console.error(error);
        };
    }, [deviceId, attempt, accumulate, historyWindowMs]);
    const live = status.hasFrame;
    const unavailable = status.state === 'ERROR' || status.state === 'EXHAUSTED';
    const label = !deviceId ? 'No device selected' : status.state === 'CONNECTING' && live ? 'Reconnecting' : labels[status.state];
    const sensorView = (status.view?.mode ?? preferredView.current) === 'sensor';
    const heading = status.view?.heading ?? 0;
    const direction = ['Front +X', 'Left +Y', 'Rear −X', 'Right −Y'][Math.round(heading / 90) % 4];
    return (
        <section className="panel point-cloud-panel" aria-label="LiDAR point cloud">
            <div className="point-cloud-heading">
                <h2 className="panel-title">LiDAR · 3D Point Cloud</h2>
                <span className={`point-cloud-state ${live ? 'text-success' : ''}`} role="status">{label}</span>
            </div>
            <div className="point-cloud-info">
                <span>Sensor range: 30 m</span>
                <span>{deviceId && live ? `${status.pointCount.toLocaleString()} ${accumulate ? 'displayed points' : 'points'}` : '— points'}</span>
                {accumulate && live && <span>Latest: {status.latestPointCount?.toLocaleString()} points · {status.frameCount} frames</span>}
                <span className="point-cloud-axis"><b>X</b> / <b>Y</b> / <b>Z ↑</b> · sensor axes</span>
            </div>
            <div className="point-cloud-viewport">
                <div className="point-cloud-surface" ref={viewport} />
                {deviceId && !unavailable && <div className="point-cloud-view-info">
                    <strong>{sensorView ? 'Sensor view · origin (0, 0, 0) m' : 'Overview · orbit around target'}</strong>
                    <span>{sensorView ? `Looking: ${direction} · Heading ${heading.toFixed(0)}° · Elevation ${(status.view?.elevation ?? 0).toFixed(0)}° · FOV ${(status.view?.fov ?? 75).toFixed(0)}°` :
                        `Camera to target: ${(status.view?.distance ?? 65).toPrecision(3)} m`}</span>
                </div>}
                {(!deviceId || !live || status.pointCount === 0) && (
                    <div className="point-cloud-message">
                        <span>{!deviceId ? 'Select a device to view its point cloud.' :
                            live ? 'No points in the latest frame.' : status.error || 'Waiting for fresh LiDAR data.'}</span>
                    </div>
                )}
            </div>
            <div className="point-cloud-controls">
                <div className="point-cloud-view-buttons" role="group" aria-label="3D view controls">
                    <button type="button" aria-pressed={sensorView} onClick={() => session.current?.setViewMode('sensor')} disabled={!deviceId || unavailable}>Sensor view</button>
                    <button type="button" aria-pressed={!sensorView} onClick={() => session.current?.setViewMode('overview')} disabled={!deviceId || unavailable}>Overview</button>
                    <button type="button" onClick={() => session.current?.orbit(-0.2, 0)} disabled={!deviceId || unavailable} aria-label={`${sensorView ? 'Look' : 'Orbit'} left`}>←</button>
                    <button type="button" onClick={() => session.current?.orbit(0.2, 0)} disabled={!deviceId || unavailable} aria-label={`${sensorView ? 'Look' : 'Orbit'} right`}>→</button>
                    <button type="button" onClick={() => session.current?.orbit(0, 0.15)} disabled={!deviceId || unavailable} aria-label={`${sensorView ? 'Look' : 'Orbit'} up`}>↑</button>
                    <button type="button" onClick={() => session.current?.orbit(0, -0.15)} disabled={!deviceId || unavailable} aria-label={`${sensorView ? 'Look' : 'Orbit'} down`}>↓</button>
                    <button type="button" onClick={() => session.current?.zoom(0.8)} disabled={!deviceId || unavailable} aria-label="Zoom in">+</button>
                    <button type="button" onClick={() => session.current?.zoom(1.25)} disabled={!deviceId || unavailable} aria-label="Zoom out">−</button>
                    <button type="button" onClick={() => session.current?.fit()} disabled={!live || status.pointCount === 0 || unavailable}>Fit scene</button>
                    <button type="button" onClick={() => session.current?.reset()} disabled={!deviceId || unavailable}>Reset view</button>
                </div>
                <label className="point-cloud-accumulation" title="Changing accumulation clears recent frames and resets the view.">
                    <input type="checkbox" checked={accumulate} disabled={!deviceId}
                        onChange={event => setAccumulate(event.target.checked)} />
                    Accumulate (stationary sensor only)
                </label>
                <label className="point-cloud-accumulation">
                    Trail window
                    <select aria-label="Accumulation window" value={historyWindowMs} disabled={!deviceId || !accumulate}
                        onChange={event => setHistoryWindowMs(Number(event.target.value))}>
                        <option value={500}>0.5 s</option><option value={1000}>1 s</option>
                    </select>
                </label>
                <button type="button" onClick={() => setAttempt(value => value + 1)} disabled={!deviceId}>Reconnect</button>
            </div>
            {accumulate && <p className="point-cloud-hint">Up to {historyWindowMs / 1000} s · {historyWindowMs / 100} distinct frames · {(historyWindowMs / 100 * 12000).toLocaleString()} points. Older points fade. Keep the sensor stationary; moving people leave short trails.</p>}
            <p className="point-cloud-hint">Sensor axes: +X front · −X rear · +Y left · −Y right · +Z up. Directions follow the sensor mounting, not compass north.</p>
            <p className="point-cloud-hint">{sensorView ? 'Drag to look around · Scroll changes FOV without moving the camera' : 'Drag to orbit · Scroll changes camera distance · Reference grid: 5 m'} · Color: fitted Z height (blue → cyan → yellow → red), clamped</p>
        </section>
    );
}
