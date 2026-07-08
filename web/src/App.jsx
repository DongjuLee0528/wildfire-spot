import React, { useState, useEffect, useRef } from 'react';

const JWT_KEY = 'jwt_token';
const getToken = () => localStorage.getItem(JWT_KEY);

export default function App({ onLogout, onNavigate, activeDevice, onNavigateDevice }) {
    const [currentTime, setCurrentTime] = useState(new Date().toISOString());
    const [currentKeyCommand, setCurrentKeyCommand] = useState('STOP');
    const CAMERA_FALLBACK = { available: false, pan: 'UNKNOWN', tilt: null };
    const [cameraStatus, setCameraStatus] = useState({ available: null, pan: 'IDLE', tilt: null });
    const [streamError, setStreamError] = useState(false);
    const imgRef = useRef(null);
    const [cameraCommandError, setCameraCommandError] = useState('');
    const [controlError, setControlError] = useState('');
    const STATUS_FALLBACK = { online: null, mode: null, robotState: null, batteryLevel: null, lastSeenAt: null };
    const [robotStatus, setRobotStatus] = useState(STATUS_FALLBACK);
    const GPS_FALLBACK = { latitude: null, longitude: null, fix: null };
    const [gpsData, setGpsData] = useState(GPS_FALLBACK);
    const SENSOR_FALLBACK = {
        temperature: null, humidity: null, smokeLevel: null, gasLevel: null, flameDetected: null,
    };
    const [sensorData, setSensorData] = useState(SENSOR_FALLBACK);
    const FIRE_FALLBACK = { fireDetected: null, confidence: null, severity: null, source: null };
    const [fireData, setFireData] = useState(FIRE_FALLBACK);

    const [activeMission, setActiveMission] = useState(null);
    const [missionHistory, setMissionHistory] = useState([]);
    const [missionLoading, setMissionLoading] = useState(false);
    const [missionError, setMissionError] = useState('');
    const [missionNameInput, setMissionNameInput] = useState('');
    const [missionTypeInput, setMissionTypeInput] = useState('PATROL');

    const fetchMissionData = () => {
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        Promise.all([
            fetch('/api/missions/active', { headers }).then((r) => {
                if (r.status === 401 || r.status === 403) { onLogout && onLogout(); throw new Error('Unauthorized'); }
                if (r.status === 404) return null;
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json().catch(() => null);
            }),
            fetch('/api/missions', { headers }).then((r) => {
                if (r.status === 401 || r.status === 403) { onLogout && onLogout(); throw new Error('Unauthorized'); }
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json().catch(() => []);
            }),
        ])
            .then(([active, history]) => {
                setActiveMission(active ?? null);
                setMissionHistory(Array.isArray(history) ? history : []);
                setMissionError('');
            })
            .catch((err) => {
                if (err.message !== 'Unauthorized') setMissionError(err.message || 'Failed to load missions');
            });
    };

    const startMission = () => {
        if (!activeDevice) return;
        const token = getToken();
        const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
        const body = JSON.stringify({
            deviceId: activeDevice.id,
            missionName: missionNameInput.trim() || 'Patrol Mission',
            missionType: missionTypeInput.trim() || 'PATROL',
        });
        setMissionLoading(true);
        setMissionError('');
        fetch('/api/missions/start', { method: 'POST', headers, body })
            .then((r) => {
                if (r.status === 401 || r.status === 403) { onLogout && onLogout(); throw new Error('Unauthorized'); }
                if (!r.ok) return r.json().then((b) => { throw new Error(b?.message || `HTTP ${r.status}`); }).catch((e) => { throw e instanceof SyntaxError ? new Error(`HTTP ${r.status}`) : e; });
                return r.json();
            })
            .then(() => { setMissionNameInput(''); fetchMissionData(); })
            .catch((err) => { if (err.message !== 'Unauthorized') setMissionError(err.message || 'Failed to start mission'); })
            .finally(() => setMissionLoading(false));
    };

    const finishMission = () => {
        if (!activeMission) return;
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        setMissionLoading(true);
        setMissionError('');
        fetch(`/api/missions/${activeMission.id}/finish`, { method: 'POST', headers })
            .then((r) => {
                if (r.status === 401 || r.status === 403) { onLogout && onLogout(); throw new Error('Unauthorized'); }
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(() => fetchMissionData())
            .catch((err) => { if (err.message !== 'Unauthorized') setMissionError(err.message || 'Failed to finish mission'); })
            .finally(() => setMissionLoading(false));
    };

    const cancelMission = () => {
        if (!activeMission) return;
        if (!window.confirm(`Cancel mission "${activeMission.missionName}"?`)) return;
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        setMissionLoading(true);
        setMissionError('');
        fetch(`/api/missions/${activeMission.id}/cancel`, { method: 'POST', headers })
            .then((r) => {
                if (r.status === 401 || r.status === 403) { onLogout && onLogout(); throw new Error('Unauthorized'); }
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(() => fetchMissionData())
            .catch((err) => { if (err.message !== 'Unauthorized') setMissionError(err.message || 'Failed to cancel mission'); })
            .finally(() => setMissionLoading(false));
    };

    const fetchWithTimeout = (url, options = {}, timeoutMs = 5000) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        const token = getToken();
        const headers = {
            ...(options.headers || {}),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        };
        return fetch(url, { ...options, headers, signal: controller.signal })
            .finally(() => clearTimeout(timer));
    };

    const handleUnauthorized = (res) => {
        if (res.status === 401 || res.status === 403) {
            onLogout && onLogout();
            throw new Error('Unauthorized');
        }
        return res;
    };

    const readJsonResponse = (res) => {
        handleUnauthorized(res);
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

    const fetchRobotStatus = () => {
        if (!activeDevice) return;
        fetchWithTimeout(`/api/devices/${activeDevice.id}`)
            .then((res) => {
                handleUnauthorized(res);
                if (res.status === 404) { setRobotStatus(STATUS_FALLBACK); return null; }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json().catch(() => null);
            })
            .then((data) => {
                if (!data || typeof data !== 'object') return;
                setRobotStatus({
                    online: typeof data.online === 'boolean' ? data.online : null,
                    mode: typeof data.mode === 'string' ? data.mode : null,
                    robotState: typeof data.robotState === 'string' ? data.robotState : null,
                    batteryLevel: typeof data.batteryLevel === 'number' ? data.batteryLevel : null,
                    lastSeenAt: data.lastSeenAt ?? null,
                });
            })
            .catch((err) => console.error('Robot status fetch failed:', err));
    };

    const fetchGps = () => {
        if (!activeDevice) return;
        fetchWithTimeout(`/api/devices/${activeDevice.id}/gps/latest`)
            .then((res) => {
                handleUnauthorized(res);
                if (res.status === 404) { setGpsData(GPS_FALLBACK); return null; }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json().catch(() => null);
            })
            .then((data) => {
                if (!data || typeof data !== 'object') return;
                setGpsData({
                    latitude: typeof data.latitude === 'number' ? data.latitude : null,
                    longitude: typeof data.longitude === 'number' ? data.longitude : null,
                    fix: data.latitude != null && data.longitude != null,
                });
            })
            .catch((err) => console.error('GPS fetch failed:', err));
    };

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
        fetchMissionData();
    }, []);

    useEffect(() => {
        setRobotStatus(STATUS_FALLBACK);
        fetchRobotStatus();
        const statusTimer = setInterval(fetchRobotStatus, 5000);
        return () => clearInterval(statusTimer);
    }, [activeDevice?.id]);

    useEffect(() => {
        setGpsData(GPS_FALLBACK);
        fetchGps();
        const gpsTimer = setInterval(fetchGps, 5000);
        return () => clearInterval(gpsTimer);
    }, [activeDevice?.id]);

    useEffect(() => {
        setSensorData(SENSOR_FALLBACK);
        if (!activeDevice) return;
        const fetchSensors = () =>
            fetchWithTimeout(`/api/devices/${activeDevice.id}/sensors/latest`)
                .then((res) => {
                    handleUnauthorized(res);
                    if (res.status === 404) { setSensorData(SENSOR_FALLBACK); return null; }
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json().catch(() => null);
                })
                .then((data) => {
                    if (!data || typeof data !== 'object') return;
                    setSensorData({
                        temperature: typeof data.temperature === 'number' ? data.temperature : null,
                        humidity: typeof data.humidity === 'number' ? data.humidity : null,
                        smokeLevel: typeof data.smokeLevel === 'number' ? data.smokeLevel : null,
                        gasLevel: typeof data.gasLevel === 'number' ? data.gasLevel : null,
                        flameDetected: typeof data.flameDetected === 'boolean' ? data.flameDetected : null,
                    });
                })
                .catch((err) => console.error('Sensor fetch failed:', err));
        fetchSensors();
        const sensorTimer = setInterval(fetchSensors, 5000);
        return () => clearInterval(sensorTimer);
    }, [activeDevice?.id]);

    useEffect(() => {
        setFireData(FIRE_FALLBACK);
        if (!activeDevice) return;
        const fetchFireStatus = () =>
            fetchWithTimeout(`/api/devices/${activeDevice.id}/fire-events/latest`)
                .then((res) => {
                    handleUnauthorized(res);
                    if (res.status === 404) { setFireData(FIRE_FALLBACK); return null; }
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json().catch(() => null);
                })
                .then((data) => {
                    if (!data || typeof data !== 'object') return;
                    setFireData({
                        fireDetected: typeof data.fireDetected === 'boolean' ? data.fireDetected : null,
                        confidence: typeof data.confidence === 'number' ? data.confidence : null,
                        severity: typeof data.severity === 'string' ? data.severity : null,
                        source: typeof data.source === 'string' ? data.source : null,
                    });
                })
                .catch((err) => console.error('Fire status fetch failed:', err));
        fetchFireStatus();
        const fireTimer = setInterval(fetchFireStatus, 5000);
        return () => clearInterval(fireTimer);
    }, [activeDevice?.id]);

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
                    <div className="active-device-indicator">
                        <span className="status-label">DEVICE:</span>
                        {activeDevice ? (
                            <span className="status-value text-highlight active-device-name">{activeDevice.name}</span>
                        ) : (
                            <button className="active-device-none" onClick={onNavigateDevice}>No device selected</button>
                        )}
                    </div>
                    <button className="nav-btn" onClick={() => onNavigate && onNavigate('/device')}>Devices</button>
                    <button className="logout-btn" onClick={onLogout}>LOGOUT</button>
                </div>
            </header>

            <main className="dashboard-grid">

                <section className="grid-column col-left">
                    <div className="panel">
                        <h2 className="panel-title">Mission Control</h2>
                        <div className="panel-content mission-panel-content">
                            <div className="mission-device-row">
                                <span className="label">Device</span>
                                {activeDevice ? (
                                    <span className="value text-highlight">{activeDevice.name}</span>
                                ) : (
                                    <button className="active-device-none" onClick={onNavigateDevice}>No device selected</button>
                                )}
                            </div>

                            {missionError && <div className="mission-error">{missionError}</div>}

                            {activeMission ? (
                                <div className="mission-active-card">
                                    <div className="mission-active-header">
                                        <span className="mission-active-label">ACTIVE</span>
                                        <span className={`mission-status-badge mission-status-${activeMission.status.toLowerCase()}`}>{activeMission.status}</span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">Name</span>
                                        <span className="value">{activeMission.missionName}</span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">Type</span>
                                        <span className="value text-highlight">{activeMission.missionType}</span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">Started</span>
                                        <span className="value subtext">{new Date(activeMission.startedAt).toLocaleTimeString()}</span>
                                    </div>
                                    {activeMission.durationSeconds != null && (
                                        <div className="data-row">
                                            <span className="label">Duration</span>
                                            <span className="value subtext">{activeMission.durationSeconds}s</span>
                                        </div>
                                    )}
                                    <div className="mission-action-row">
                                        <button
                                            className="mission-btn mission-btn-finish"
                                            onClick={finishMission}
                                            disabled={missionLoading}
                                        >
                                            {missionLoading ? '...' : 'Finish'}
                                        </button>
                                        <button
                                            className="mission-btn mission-btn-cancel"
                                            onClick={cancelMission}
                                            disabled={missionLoading}
                                        >
                                            {missionLoading ? '...' : 'Cancel'}
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <div className="mission-start-form">
                                    <div className="auth-field">
                                        <label className="auth-label">Mission Name</label>
                                        <input
                                            className="auth-input mission-input"
                                            type="text"
                                            placeholder="Patrol Mission"
                                            value={missionNameInput}
                                            onChange={(e) => setMissionNameInput(e.target.value)}
                                            disabled={!activeDevice || missionLoading}
                                        />
                                    </div>
                                    <div className="auth-field">
                                        <label className="auth-label">Mission Type</label>
                                        <select
                                            className="auth-input mission-input"
                                            value={missionTypeInput}
                                            onChange={(e) => setMissionTypeInput(e.target.value)}
                                            disabled={!activeDevice || missionLoading}
                                        >
                                            <option value="PATROL">PATROL</option>
                                            <option value="SURVEY">SURVEY</option>
                                            <option value="INSPECTION">INSPECTION</option>
                                            <option value="EMERGENCY">EMERGENCY</option>
                                        </select>
                                    </div>
                                    <button
                                        className="mission-btn mission-btn-start"
                                        onClick={startMission}
                                        disabled={!activeDevice || missionLoading}
                                    >
                                        {missionLoading ? 'Starting...' : 'Start Mission'}
                                    </button>
                                </div>
                            )}

                            <div className="mission-history-section">
                                <span className="mission-history-title">Recent Missions</span>
                                {missionHistory.length === 0 ? (
                                    <div className="mission-empty">No missions recorded.</div>
                                ) : (
                                    <div className="mission-history-list">
                                        {missionHistory.slice(0, 5).map((m) => (
                                            <div key={m.id} className="mission-history-item">
                                                <div className="mission-history-top">
                                                    <span className="mission-history-name">{m.missionName}</span>
                                                    <span className={`mission-status-badge mission-status-${m.status.toLowerCase()}`}>{m.status}</span>
                                                </div>
                                                <div className="mission-history-meta">
                                                    <span className="subtext">{m.missionType}</span>
                                                    {m.durationSeconds != null && (
                                                        <span className="subtext">{m.durationSeconds}s</span>
                                                    )}
                                                    <span className="subtext">{new Date(m.startedAt).toLocaleString()}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="panel animate-border">
                        <h2 className="panel-title">Robot Status</h2>
                        <div className="panel-content status-grid">
                            {!activeDevice ? (
                                <div className="data-row"><span className="label subtext">No device selected</span></div>
                            ) : (
                                <>
                                    <div className="data-row">
                                        <span className="label">Connection</span>
                                        <span className={`value ${robotStatus.online === true ? 'text-success' : robotStatus.online === false ? 'text-error' : ''}`}>
                                            {robotStatus.online === null ? '...' : robotStatus.online ? 'ONLINE' : 'OFFLINE'}
                                        </span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">Mode</span>
                                        <span className="value">{robotStatus.mode ?? '...'}</span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">State</span>
                                        <span className="value text-highlight">{robotStatus.robotState ?? '...'}</span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">Battery</span>
                                        <span className="value">{robotStatus.batteryLevel !== null ? `${robotStatus.batteryLevel.toFixed(1)} %` : '...'}</span>
                                    </div>
                                    <div className="data-row">
                                        <span className="label">Last Seen</span>
                                        <span className="value subtext">
                                            {robotStatus.lastSeenAt ? new Date(robotStatus.lastSeenAt).toLocaleTimeString() : '...'}
                                        </span>
                                    </div>
                                </>
                            )}
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
                                {!activeDevice ? (
                                    <div className="fire-card status-unknown">
                                        <span className="fire-card-label">No device selected</span>
                                        <span className="fire-card-value">—</span>
                                    </div>
                                ) : (
                                    <>
                                        <div className={`fire-card status-${fireData.fireDetected === null ? 'unknown' : fireData.fireDetected ? 'detected' : 'clear'}`}>
                                            <span className="fire-card-label">Fire Detected</span>
                                            <span className="fire-card-value">{fireData.fireDetected === null ? '...' : fireData.fireDetected ? 'DETECTED' : 'CLEAR'}</span>
                                        </div>
                                        <div className="fire-card status-unknown">
                                            <span className="fire-card-label">Confidence</span>
                                            <span className="fire-card-value">{fireData.confidence !== null ? `${(fireData.confidence * 100).toFixed(0)}%` : '...'}</span>
                                        </div>
                                        <div className="fire-card status-unknown">
                                            <span className="fire-card-label">Severity</span>
                                            <span className="fire-card-value">{fireData.severity ?? '...'}</span>
                                        </div>
                                    </>
                                )}
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
                                    <span className="sensor-name">Smoke / Gas (MQ-2)</span>
                                    <span className={`sensor-val ${sensorData.smokeLevel !== null && sensorData.smokeLevel < 300 ? 'text-success' : sensorData.smokeLevel !== null ? 'text-error' : ''}`}>
                                        {sensorData.smokeLevel !== null ? `${sensorData.smokeLevel.toFixed(0)} ppm${sensorData.smokeLevel < 300 ? ' (Safe)' : ' (Alert)'}` : 'N/A'}
                                    </span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill safe" style={{width: sensorData.smokeLevel !== null ? `${Math.min(sensorData.smokeLevel / 1000 * 100, 100).toFixed(1)}%` : '0%'}}></div></div>
                            </div>
                            <div className="sensor-grid-2x2">
                                <div className={`sensor-mini-card flame-${sensorData.flameDetected === null ? 'unknown' : sensorData.flameDetected ? 'detected' : 'clear'}`}>
                                    <span className="mini-lbl">Flame Sensor</span>
                                    <span className="mini-val">{sensorData.flameDetected === null ? '...' : sensorData.flameDetected ? 'DETECTED' : 'CLEAR'}</span>
                                </div>
                                <div className="sensor-mini-card flame-unknown">
                                    <span className="mini-lbl">Gas Level</span>
                                    <span className="mini-val">{sensorData.gasLevel !== null ? sensorData.gasLevel.toFixed(0) : '...'}</span>
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
