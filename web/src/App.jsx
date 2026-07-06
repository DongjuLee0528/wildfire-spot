import React, { useState, useEffect } from 'react';

export default function App() {
    const [currentTime, setCurrentTime] = useState(new Date().toISOString());
    const [currentKeyCommand, setCurrentKeyCommand] = useState('STOP');
    const robotMode = 'AUTO';
    const stateMachine = 'PATROL';
    const flameSensors = [
        { label: 'Flame Front Left', status: 'CLEAR' },
        { label: 'Flame Front Right', status: 'CLEAR' },
        { label: 'Flame Left', status: 'DETECTED' },
        { label: 'Flame Right', status: 'CLEAR' },
    ];
    const fireStatus = [
        { label: 'Hardware Confirmed', status: 'DETECTED', level: 'detected' },
        { label: 'Camera Detected', status: 'CLEAR', level: 'clear' },
        { label: 'Final Confirmed Fire', status: 'CLEAR', level: 'clear' },
    ];

    // 실시간 시간 업데이트 (학술/데모용 UTC 표현 스타일)
    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC');
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    // 키보드 제어 상태 시각화 핸들러 (실제 로봇 제어 없음, UI 피드백용)
    useEffect(() => {
        const handleKeyDown = (e) => {
            const key = e.key.toUpperCase();
            if (key === 'W') setCurrentKeyCommand('FORWARD');
            if (key === 'A') setCurrentKeyCommand('LEFT');
            if (key === 'S') setCurrentKeyCommand('BACKWARD');
            if (key === 'D') setCurrentKeyCommand('RIGHT');
            if (e.key === 'Escape') setCurrentKeyCommand('STOP');
        };

        const handleKeyUp = () => {
            // 키를 떼면 데모 편의상 STOP으로 복귀 처리
            setCurrentKeyCommand('STOP');
        };

        window.addEventListener('keydown', handleKeyDown);
        window.addEventListener('keyup', handleKeyUp);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            window.removeEventListener('keyup', handleKeyUp);
        };
    }, []);

    // 모의 로그 데이터
    const logs = [
        { time: '12:45:02', text: 'SYSTEM INITIALIZED SUCCESSFULLY' },
        { time: '12:45:05', text: 'AUTO MODE ENABLED' },
        { time: '12:45:06', text: 'GPS FIX ACQUIRED - 3D FIX' },
        { time: '12:45:08', text: 'SENSOR DATA UPDATED (NOMINAL)' },
        { time: '12:45:12', text: 'HARDWARE FIRE CHECK ACTIVE' },
        { time: '12:45:15', text: 'CAMERA STREAM WAITING (FEED_UNAVAILABLE)' },
    ];

    const handleCameraControl = (command) => {
        console.log(`Camera command: ${command}`);
        // API call will be implemented here
    };

    return (
        <div className="dashboard-container">
            {/* 1. Header */}
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

            {/* Main Grid Layout */}
            <main className="dashboard-grid">

                {/* Left Column */}
                <section className="grid-column col-left">
                    {/* 3. Robot Status Panel */}
                    <div className="panel animate-border">
                        <h2 className="panel-title">Robot Status</h2>
                        <div className="panel-content status-grid">
                            <div className="data-row">
                                <span className="label">Mode</span>
                                <span className="value">{robotMode}</span>
                            </div>
                            <div className="data-row">
                                <span className="label">StateMachine</span>
                                <span className="value text-highlight">{stateMachine}</span>
                            </div>
                            <div className="data-row">
                                <span className="label">Robot Connection</span>
                                <span className="value text-success">ONLINE</span>
                            </div>
                            <div className="data-row">
                                <span className="label">Last Update</span>
                                <span className="value subtext">Just Now</span>
                            </div>
                        </div>
                    </div>

                    {/* 4. Current Mode Panel */}
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

                    {/* 8. Health Check Panel */}
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

                {/* Center Column */}
                <section className="grid-column col-center">
                    {/* 2. Camera Panel */}
                    <div className="panel main-camera-panel">
                        <div className="panel-header-actions">
                            <h2 className="panel-title">Primary Live Camera Stream</h2>
                            <span className="badge-overlay-reserved">AI Overlay Space Reserved</span>
                        </div>
                        <div className="panel-content camera-viewport">
                            {/* Future AI Overlay Bounding Box Grid Mock */}
                            <div className="ai-overlay-placeholder">
                                <div className="corner tl"></div>
                                <div className="corner tr"></div>
                                <div className="corner bl"></div>
                                <div className="corner br"></div>
                                <div className="error-message-container">
                                    <span className="warning-icon">⚠</span>
                                    <p className="main-msg">CAMERA FEED UNAVAILABLE</p>
                                    <p className="sub-msg">Hardware pipeline active. Awaiting visual stream data sync...</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* New Camera Control Panel */}
                    <div className="panel camera-control-panel">
                        <h2 className="panel-title">Camera Pan/Tilt Control</h2>
                        <div className="panel-content camera-controls">
                            <div className="camera-status">
                                <span className="status-label">Status:</span>
                                <span className="status-value">IDLE</span>
                            </div>
                            <div className="d-pad">
                                <button className="d-pad-btn up" onClick={() => handleCameraControl('CAMERA_UP')}>Up</button>
                                <button className="d-pad-btn left" onClick={() => handleCameraControl('CAMERA_LEFT')}>Left</button>
                                <button className="d-pad-btn center" onClick={() => handleCameraControl('CAMERA_CENTER')}>Center</button>
                                <button className="d-pad-btn right" onClick={() => handleCameraControl('CAMERA_RIGHT')}>Right</button>
                                <button className="d-pad-btn down" onClick={() => handleCameraControl('CAMERA_DOWN')}>Down</button>
                            </div>
                        </div>
                    </div>

                    <div className="center-bottom-split">
                        {/* 9. Current Command Panel */}
                        <div className="panel command-panel">
                            <h2 className="panel-title">Manual Override Commands</h2>
                            <div className="panel-content command-layout">
                                <div className="keyboard-map">
                                    <div className="key-row">
                                        <div className={`key-cap ${currentKeyCommand === 'FORWARD' ? 'pressed' : ''}`}>W</div>
                                    </div>
                                    <div className="key-row">
                                        <div className={`key-cap ${currentKeyCommand === 'LEFT' ? 'pressed' : ''}`}>A</div>
                                        <div className={`key-cap ${currentKeyCommand === 'BACKWARD' ? 'pressed' : ''}`}>S</div>
                                        <div className={`key-cap ${currentKeyCommand === 'RIGHT' ? 'pressed' : ''}`}>D</div>
                                    </div>
                                    <div className="key-row esc-row">
                                        <div className={`key-cap esc ${currentKeyCommand === 'STOP' ? 'pressed' : ''}`}>ESC (STOP)</div>
                                    </div>
                                </div>
                                <div className="command-status-display">
                                    <span className="status-title">CURRENT COMMAND</span>
                                    <div className={`current-cmd-value ${currentKeyCommand !== 'STOP' ? 'cmd-active' : ''}`}>
                                        {currentKeyCommand}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* 7. Fire Status Panel */}
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

                {/* Right Column */}
                <section className="grid-column col-right">
                    {/* 6. Sensor Data Panel */}
                    <div className="panel">
                        <h2 className="panel-title">Sensor Telemetry Monitoring</h2>
                        <div className="panel-content sensor-list">
                            <div className="sensor-item">
                                <div className="sensor-meta">
                                    <span className="sensor-name">Temperature</span>
                                    <span className="sensor-val">24.8 °C</span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill" style={{width: '45%'}}></div></div>
                            </div>
                            <div className="sensor-item">
                                <div className="sensor-meta">
                                    <span className="sensor-name">Humidity</span>
                                    <span className="sensor-val">42.1 %</span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill" style={{width: '60%'}}></div></div>
                            </div>
                            <div className="sensor-item">
                                <div className="sensor-meta">
                                    <span className="sensor-name">MQ-2 Gas Sensor</span>
                                    <span className="sensor-val text-success">112 ppm (Safe)</span>
                                </div>
                                <div className="sensor-bar-bg"><div className="sensor-bar-fill safe" style={{width: '22%'}}></div></div>
                            </div>
                            <div className="sensor-grid-2x2">
                                {flameSensors.map((sensor) => (
                                    <div key={sensor.label} className={`sensor-mini-card flame-${sensor.status.toLowerCase()}`}>
                                        <span className="mini-lbl">{sensor.label}</span>
                                        <span className="mini-val">{sensor.status}</span>
                                    </div>
                                ))}
                            </div>
                            <div className="sensor-item font-industrial">
                                <div className="sensor-meta">
                                    <span className="sensor-name">LiDAR Node Status</span>
                                    <span className="status-text-badge">SCANNING</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* 5. GPS Map Panel */}
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
                                    <span className="c-val">37.5665 °N</span>
                                </div>
                                <div className="coord">
                                    <span className="c-lbl">LON:</span>
                                    <span className="c-val">126.9780 °E</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* 10. System Log Panel */}
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
