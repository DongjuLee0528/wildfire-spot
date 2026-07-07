import React, { useState, useEffect, useRef } from 'react';

export default function App() {
    const [currentTime, setCurrentTime] = useState(new Date().toISOString());
    const [currentKeyCommand, setCurrentKeyCommand] = useState('STOP');
    const CAMERA_FALLBACK = { available: false, pan: 'UNKNOWN', tilt: null };
    const [cameraStatus, setCameraStatus] = useState({ available: null, pan: 'IDLE', tilt: null });
    const [streamError, setStreamError] = useState(false);
    const imgRef = useRef(null);
    const [cameraCommandError, setCameraCommandError] = useState('');
    const [controlError, setControlError] = useState('');
    const STATUS_FALLBACK = { state: '...', mode: '...', robotConnected: null, lastUpdate: null };
    const [robotStatus, setRobotStatus] = useState(STATUS_FALLBACK);
    const GPS_FALLBACK = { latitude: null, longitude: null, fix: null };
    const [gpsData, setGpsData] = useState(GPS_FALLBACK);
    const SENSOR_FALLBACK = {
        temperature: null, humidity: null, mq2Gas: null,
        flame: { frontLeft: null, frontRight: null, left: null, right: null },
        lidarStatus: null,
    };
    const [sensorData, setSensorData] = useState(SENSOR_FALLBACK);
    const fireStatus = [
        { label: 'Hardware Confirmed', status: 'DETECTED', level: 'detected' },
        { label: 'Camera Detected', status: 'CLEAR', level: 'clear' },
        { label: 'Final Confirmed Fire', status: 'CLEAR', level: 'clear' },
    ];

    const fetchWithTimeout = (url, options = {}, timeoutMs = 5000) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        return fetch(url, { ...options, signal: controller.signal })
            .finally(() => clearTimeout(timer));
    };

    const readJsonResponse = (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json().catch(() => {
            throw new Error('Malformed JSON');
        });
    };

    const normalizeCameraStatus = (data) => {
        if (!data || typeof data !== 'object' || typeof data.available !== 'boolean') {
            return CAMERA_FALLBACK;
        }
        return {
            available: data.available,
            pan: typeof data.pan === 'string' ? data.pan : 'UNKNOWN',
            tilt: data.tilt ?? null,
        };
    };

    const fetchRobotStatus = () => (
        fetchWithTimeout('/api/status')
            .then(readJsonResponse)
            .then((data) => {
                if (!data || typeof data !== 'object') return;
                setRobotStatus({
                    state: typeof data.state === 'string' ? data.state : '...',
                    mode: typeof data.mode === 'string' ? data.mode : '...',
                    robotConnected: typeof data.robotConnected === 'boolean' ? data.robotConnected : null,
                    lastUpdate: data.lastUpdate ?? null,
                });
            })
            .catch((err) => console.error('Robot status fetch failed:', err))
    );

    const fetchGps = () => (
        fetchWithTimeout('/api/gps')
            .then(readJsonResponse)
            .then((data) => {
                if (!data || typeof data !== 'object') return;
                setGpsData({
                    latitude: typeof data.latitude === 'number' ? data.latitude : null,
                    longitude: typeof data.longitude === 'number' ? data.longitude : null,
                    fix: typeof data.fix === 'boolean' ? data.fix : null,
                });
            })
            .catch((err) => console.error('GPS fetch failed:', err))
    );

    const fetchCameraStatus = () => (
        fetchWithTimeout('/api/camera/status')
            .then(readJsonResponse)
            .then((data) => setCameraStatus(normalizeCameraStatus(data)))
            .catch((err) => {
                console.error('Camera status fetch failed:', err);
                setCameraStatus(CAMERA_FALLBACK);
            })
    );

    useEffect(() => {
        fetchRobotStatus();
        const statusTimer = setInterval(fetchRobotStatus, 5000);
        return () => clearInterval(statusTimer);
    }, []);

    useEffect(() => {
        fetchGps();
        const gpsTimer = setInterval(fetchGps, 3000);
        return () => clearInterval(gpsTimer);
    }, []);

    useEffect(() => {
        const fetchSensors = () => (
            fetchWithTimeout('/api/sensors')
                .then(readJsonResponse)
                .then((data) => {
                    if (!data || typeof data !== 'object') return;
                    setSensorData({
                        temperature: typeof data.temperature === 'number' ? data.temperature : null,
                        humidity: typeof data.humidity === 'number' ? data.humidity : null,
                        mq2Gas: typeof data.mq2Gas === 'number' ? data.mq2Gas : null,
                        flame: data.flame && typeof data.flame === 'object' ? data.flame : SENSOR_FALLBACK.flame,
                        lidarStatus: typeof data.lidarStatus === 'string' ? data.lidarStatus : null,
                    });
                })
                .catch((err) => console.error('Sensor fetch failed:', err))
        );
        fetchSensors();
        const sensorTimer = setInterval(fetchSensors, 4000);
        return () => clearInterval(sensorTimer);
    }, []);

    useEffect(() => {
        fetchCameraStatus();
    }, []);

    const sendControlCommand = (command) => {
        setControlError('');
        fetchWithTimeout('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command }),
        })
            .then(readJsonResponse)
            .then((data) => {
                if (!data || typeof data !== 'object' || typeof data.accepted !== 'boolean') {
                    setControlError('INVALID_RESPONSE');
                    return;
                }
                if (data.accepted === false) {
                    console.warn('Control command rejected:', data.command);
                    setControlError('REJECTED');
                }
            })
            .catch((err) => {
                console.error('Control command failed:', err);
                setControlError('REQUEST_FAILED');
            });
    };

    const sendCameraCommand = (command) => {
        setCameraCommandError('');
        fetchWithTimeout('/api/camera/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command }),
        })
            .then(readJsonResponse)
            .then((data) => {
                if (!data || typeof data !== 'object' || typeof data.accepted !== 'boolean') {
                    setCameraCommandError('INVALID_RESPONSE');
                    return;
                }
                if (data.accepted === false) {
                    console.warn('Camera command rejected:', data.reason ?? 'no reason');
                    setCameraCommandError(data.reason ?? 'REJECTED');
                    return;
                }
                setCameraCommandError('');
                fetchCameraStatus();
            })
            .catch((err) => {
                console.error('Camera command failed:', err);
                setCameraCommandError('REQUEST_FAILED');
            });
    };

    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC');
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        const KEY_COMMAND_MAP = { W: 'FORWARD', A: 'LEFT', S: 'BACKWARD', D: 'RIGHT' };

        const handleKeyDown = (e) => {
            if (e.repeat) return;
            const key = e.key.toUpperCase();
            const command = e.key === 'Escape' ? 'STOP' : KEY_COMMAND_MAP[key];
            if (!command) return;
            setCurrentKeyCommand(command);
            sendControlCommand(command);
        };

        const handleKeyUp = (e) => {
            const key = e.key.toUpperCase();
            if (KEY_COMMAND_MAP[key]) {
                setCurrentKeyCommand('STOP');
                sendControlCommand('STOP');
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        window.addEventListener('keyup', handleKeyUp);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            window.removeEventListener('keyup', handleKeyUp);
        };
    }, []);

    const logs = [
        { time: '12:45:02', text: 'SYSTEM INITIALIZED SUCCESSFULLY' },
        { time: '12:45:05', text: 'AUTO MODE ENABLED' },
        { time: '12:45:06', text: 'GPS FIX ACQUIRED - 3D FIX' },
        { time: '12:45:08', text: 'SENSOR DATA UPDATED (NOMINAL)' },
        { time: '12:45:12', text: 'HARDWARE FIRE CHECK ACTIVE' },
        { time: '12:45:15', text: 'CAMERA STREAM WAITING (FEED_UNAVAILABLE)' },
    ];

    return (
        <div className="dashboard-container">
            <header className="dashboard-header">
                <div className="header-brand">
                    <span className="brand-icon">🔥</span>
                    <h1>Wildfire Spot</h1>
                    <span className="sub-title">AIoT Quadruped Robot Center</span>
                </div>
                <div className="header-status-group">
                    <div className="status-item">
                        <span className="status-label">CONN STATUS:</span>
                        <span className="status-value text-success">ONLINE</span>
                    </div>
                    <div className="status-item">
                        <span className="status-label">MODE:</span>
                        <span className="status-value text-active">AUTO</span>
                    </div>
                    <div className="status-item timestamp">
                        {currentTime}
                    </div>
                </div>
            </header>

            <main className="dashboard-grid">

                <section className="grid-column col-left">
                    <div className="panel animate-border">
                        <h2 className="panel-title">Robot Status</h2>
                        <div className="panel-content status-grid">
                            <div className="data-row">
                                <span className="label">Mode</span>
                                <span className="value">{robotStatus.mode}</span>
                            </div>
                            <div className="data-row">
                                <span className="label">StateMachine</span>
                                <span className="value text-highlight">{robotStatus.state}</span>
                            </div>
                            <div className="data-row">
                                <span className="label">Robot Connection</span>
                                <span className={`value ${robotStatus.robotConnected === true ? 'text-success' : robotStatus.robotConnected === false ? 'text-error' : ''}`}>
                                    {robotStatus.robotConnected === null ? '...' : robotStatus.robotConnected ? 'ONLINE' : 'OFFLINE'}
                                </span>
                            </div>
                            <div className="data-row">
                                <span className="label">Last Update</span>
                                <span className="value subtext">
                                    {robotStatus.lastUpdate ? new Date(robotStatus.lastUpdate).toLocaleTimeString() : '...'}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="panel">
                        <h2 className="panel-title">Current Mode Selection</h2>
                        <div className="panel-content mode-container">
                            <div className="mode-btn active">
                                <div className="radio-indicator checked"></div>
                                <div className="mode-info">
                                    <span className="mode-name">AUTO</span>
                                    <span className="mode-desc">Autonomous Navigation</span>
                                </div>
                            </div>
                            <div className="mode-btn disabled">
                                <div className="radio-indicator"></div>
                                <div className="mode-info">
                                    <span className="mode-name">MANUAL</span>
                                    <span className="mode-desc">Keyboard Override</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="panel">
                        <h2 className="panel-title">System Health Check</h2>
                        <div className="panel-content health-list">
                            <div className="health-item">
                                <span className="indicator status-ok"></span>
                                <span className="health-label">Robot Core</span>
                            </div>
                            <div className="health-item">
                                <span className="indicator status-ok"></span>
                                <span className="health-label">Camera Module</span>
                            </div>
                            <div className="health-item">
                                <span className="indicator status-ok"></span>
                                <span className="health-label">GPS Receiver</span>
                            </div>
                            <div className="health-item">
                                <span className="indicator status-ok"></span>
                                <span className="health-label">LiDAR Scanner</span>
                            </div>
                            <div className="health-item">
                                <span className="indicator status-ok"></span>
                                <span className="health-label">Environmental Sensors</span>
                            </div>
                        </div>
                    </div>
                </section>

                <section className="grid-column col-center">
                    <div className="panel main-camera-panel">
                        <div className="panel-header-actions">
                            <h2 className="panel-title">Primary Live Camera Stream</h2>
                            <span className="badge-overlay-reserved">AI Overlay Space Reserved</span>
                        </div>
                        <div className="panel-content camera-viewport">
                            <div className="ai-overlay-placeholder">
                                <div className="corner tl"></div>
                                <div className="corner tr"></div>
                                <div className="corner bl"></div>
                                <div className="corner br"></div>
                                {streamError ? (
                                    <div className="error-message-container">
                                        <span className="warning-icon">⚠</span>
                                        <p className="main-msg">CAMERA FEED UNAVAILABLE</p>
                                        <p className="sub-msg">Hardware pipeline active. Awaiting visual stream data sync...</p>
                                    </div>
                                ) : (
                                    <img
                                        ref={imgRef}
                                        src="/api/camera/stream"
                                        alt="Camera Stream"
                                        className="camera-stream-img"
                                        onError={() => setStreamError(true)}
                                        onLoad={() => setStreamError(false)}
                                    />
                                )}
                            </div>
                        </div>
                        <div className="camera-control-inline">
                            <span className="camera-stream-label">
                                Available: {cameraStatus.available === null ? '...' : cameraStatus.available ? 'YES' : 'NO'}
                                {' | '}Pan: {cameraStatus.pan ?? 'UNKNOWN'}
                                {' | '}Tilt: {cameraStatus.tilt != null ? `${cameraStatus.tilt}°` : 'N/A'}
                                {cameraCommandError ? ` | Command: ${cameraCommandError}` : ''}
                            </span>
                            <div className="camera-d-pad">
                                <div className="camera-d-pad-row">
                                    <button className="camera-btn" onClick={() => sendCameraCommand('CAMERA_UP')}>Up (I)</button>
                                </div>
                                <div className="camera-d-pad-row">
                                    <button className="camera-btn" onClick={() => sendCameraCommand('CAMERA_LEFT')}>Left (J)</button>
                                    <button className="camera-btn" onClick={() => sendCameraCommand('CAMERA_CENTER')}>Center (O)</button>
                                    <button className="camera-btn" onClick={() => sendCameraCommand('CAMERA_RIGHT')}>Right (L)</button>
                                </div>
                                <div className="camera-d-pad-row">
                                    <button className="camera-btn" onClick={() => sendCameraCommand('CAMERA_DOWN')}>Down (K)</button>
                                </div>
                            </div>
                            <span className="camera-shortcut-hint">Shortcuts: I / J / K / L / O</span>
                        </div>
                    </div>

                    <div className="center-bottom-split">
                        <div className="panel command-panel">
                            <h2 className="panel-title">Manual Override Commands</h2>
                            <div className="panel-content command-layout">
                                <div className="keyboard-map">
                                    <div className="key-row">
                                        <button className={`key-cap ${currentKeyCommand === 'FORWARD' ? 'pressed' : ''}`} onClick={() => sendControlCommand('FORWARD')}>W</button>
                                    </div>
                                    <div className="key-row">
                                        <button className={`key-cap ${currentKeyCommand === 'LEFT' ? 'pressed' : ''}`} onClick={() => sendControlCommand('LEFT')}>A</button>
                                        <button className={`key-cap ${currentKeyCommand === 'BACKWARD' ? 'pressed' : ''}`} onClick={() => sendControlCommand('BACKWARD')}>S</button>
                                        <button className={`key-cap ${currentKeyCommand === 'RIGHT' ? 'pressed' : ''}`} onClick={() => sendControlCommand('RIGHT')}>D</button>
                                    </div>
                                    <div className="key-row esc-row">
                                        <button className={`key-cap esc ${currentKeyCommand === 'STOP' ? 'pressed' : ''}`} onClick={() => sendControlCommand('STOP')}>ESC (STOP)</button>
                                    </div>
                                </div>
                                <div className="command-status-display">
                                    <span className="status-title">CURRENT COMMAND</span>
                                    <div className={`current-cmd-value ${currentKeyCommand !== 'STOP' ? 'cmd-active' : ''}`}>
                                        {currentKeyCommand}
                                    </div>
                                    {controlError && (
                                        <span className="camera-stream-label">ERR: {controlError}</span>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="panel fire-status-panel">
                            <h2 className="panel-title">Analysis & Verification Status</h2>
                            <div className="panel-content fire-grid">
                                {fireStatus.map((item) => (
                                    <div key={item.label} className={`fire-card status-${item.level}`}>
                                        <span className="fire-card-label">{item.label}</span>
                                        <span className="fire-card-value">{item.status}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </section>

                <section className="grid-column col-right">
                    <div className="panel">
                        <h2 className="panel-title">Sensor Telemetry Monitoring</h2>
                        <div className="panel-content sensor-list">
                            <div className="sensor-item">
                                <div className="sensor-meta">
                                    <span className="sensor-name">Temperature</span>
                                    <span className="sensor-val">
                                        {sensorData.temperature !== null ? `${sensorData.temperature.toFixed(1)} °C` : 'N/A'}
                                    </span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill" style={{width: sensorData.temperature !== null ? `${Math.min(sensorData.temperature / 60 * 100, 100).toFixed(1)}%` : '0%'}}></div></div>
                            </div>
                            <div className="sensor-item">
                                <div className="sensor-meta">
                                    <span className="sensor-name">Humidity</span>
                                    <span className="sensor-val">
                                        {sensorData.humidity !== null ? `${sensorData.humidity.toFixed(1)} %` : 'N/A'}
                                    </span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill" style={{width: sensorData.humidity !== null ? `${Math.min(sensorData.humidity, 100).toFixed(1)}%` : '0%'}}></div></div>
                            </div>
                            <div className="sensor-item">
                                <div className="sensor-meta">
                                    <span className="sensor-name">MQ-2 Gas Sensor</span>
                                    <span className={`sensor-val ${sensorData.mq2Gas !== null && sensorData.mq2Gas < 300 ? 'text-success' : sensorData.mq2Gas !== null ? 'text-error' : ''}`}>
                                        {sensorData.mq2Gas !== null ? `${sensorData.mq2Gas} ppm${sensorData.mq2Gas < 300 ? ' (Safe)' : ' (Alert)'}` : 'N/A'}
                                    </span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill safe" style={{width: sensorData.mq2Gas !== null ? `${Math.min(sensorData.mq2Gas / 1000 * 100, 100).toFixed(1)}%` : '0%'}}></div></div>
                            </div>
                            <div className="sensor-grid-2x2">
                                {[
                                    { label: 'Flame Front Left', val: sensorData.flame.frontLeft },
                                    { label: 'Flame Front Right', val: sensorData.flame.frontRight },
                                    { label: 'Flame Left', val: sensorData.flame.left },
                                    { label: 'Flame Right', val: sensorData.flame.right },
                                ].map((sensor) => {
                                    const status = sensor.val === null ? 'unknown' : sensor.val ? 'detected' : 'clear';
                                    return (
                                        <div key={sensor.label} className={`sensor-mini-card flame-${status}`}>
                                            <span className="mini-lbl">{sensor.label}</span>
                                            <span className="mini-val">{sensor.val === null ? '...' : sensor.val ? 'DETECTED' : 'CLEAR'}</span>
                                        </div>
                                    );
                                })}
                            </div>
                            <div className="sensor-item font-industrial">
                                <div className="sensor-meta">
                                    <span className="sensor-name">LiDAR Node Status</span>
                                    <span className="status-text-badge">{sensorData.lidarStatus ?? '...'}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="panel">
                        <h2 className="panel-title">Geospatial Telemetry (GPS)</h2>
                        <div className="panel-content map-wrapper">
                            <div className="mock-map-canvas">
                                <div className="map-grid-lines"></div>
                                <div className="map-robot-marker">
                                    <span className="ping"></span>
                                    <span className="marker-core"></span>
                                </div>
                                <span className="map-scale-indicator">50m</span>
                            </div>
                            <div className="map-coordinates">
                                <div className="coord">
                                    <span className="c-lbl">LAT:</span>
                                    <span className="c-val">
                                        {gpsData.latitude !== null ? `${gpsData.latitude.toFixed(4)} °N` : 'N/A'}
                                    </span>
                                </div>
                                <div className="coord">
                                    <span className="c-lbl">LON:</span>
                                    <span className="c-val">
                                        {gpsData.longitude !== null ? `${gpsData.longitude.toFixed(4)} °E` : 'N/A'}
                                    </span>
                                </div>
                                <div className="coord">
                                    <span className="c-lbl">FIX:</span>
                                    <span className={`c-val ${gpsData.fix === true ? 'text-success' : gpsData.fix === false ? 'text-error' : ''}`}>
                                        {gpsData.fix === null ? '...' : gpsData.fix ? 'ACQUIRED' : 'NO FIX'}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="panel log-panel">
                        <h2 className="panel-title">Terminal System Logs</h2>
                        <div className="panel-content log-terminal">
                            {logs.map((log, index) => (
                                <div key={index} className="log-line">
                                    <span className="log-time">[{log.time}]</span>
                                    <span className="log-text">{log.text}</span>
                                </div>
                            ))}
                            <div className="log-cursor"></div>
                        </div>
                    </div>
                </section>

            </main>
        </div>
    );
}
