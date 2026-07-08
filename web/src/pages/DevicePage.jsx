import React, { useState, useEffect, useCallback } from 'react';
import DeviceCard from '../components/DeviceCard.jsx';
import DeviceModal from '../components/DeviceModal.jsx';

const JWT_KEY = 'jwt_token';
const getToken = () => localStorage.getItem(JWT_KEY);

function authFetch(url, options = {}) {
    const token = getToken();
    return fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
    });
}

export default function DevicePage({ onLogout, onNavigate, activeDevice, onSetActiveDevice }) {
    const [devices, setDevices] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedId, setSelectedId] = useState(() => activeDevice?.id ?? null);
    const [modal, setModal] = useState(null);

    const handleSelect = (device) => {
        if (selectedId === device.id) {
            setSelectedId(null);
            onSetActiveDevice && onSetActiveDevice(null);
        } else {
            setSelectedId(device.id);
            onSetActiveDevice && onSetActiveDevice(device);
        }
    };

    const handleAuthError = useCallback((res) => {
        if (res.status === 401 || res.status === 403) {
            onLogout && onLogout();
            throw new Error('Unauthorized');
        }
        return res;
    }, [onLogout]);

    const loadDevices = useCallback(() => {
        setLoading(true);
        setError('');
        authFetch('/api/devices')
            .then((res) => {
                handleAuthError(res);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data) => setDevices(Array.isArray(data) ? data : []))
            .catch((err) => {
                if (err.message !== 'Unauthorized') setError(err.message || 'Failed to load devices');
            })
            .finally(() => setLoading(false));
    }, [handleAuthError]);

    useEffect(() => { loadDevices(); }, [loadDevices]);

    const handleRegister = (formData) => {
        return authFetch('/api/devices', {
            method: 'POST',
            body: JSON.stringify(formData),
        })
            .then((res) => {
                handleAuthError(res);
                if (!res.ok) return res.json().then((b) => { throw new Error(b?.message || `HTTP ${res.status}`); });
                return res.json();
            })
            .then(() => { loadDevices(); setModal(null); });
    };

    const handleEdit = (formData) => {
        return authFetch(`/api/devices/${modal.device.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ name: formData.name, description: formData.description }),
        })
            .then((res) => {
                handleAuthError(res);
                if (!res.ok) return res.json().then((b) => { throw new Error(b?.message || `HTTP ${res.status}`); });
                return res.json();
            })
            .then(() => { loadDevices(); setModal(null); });
    };

    const handleDelete = (device) => {
        if (!window.confirm(`Remove device "${device.name}"?`)) return;
        authFetch(`/api/devices/${device.id}`, { method: 'DELETE' })
            .then((res) => {
                handleAuthError(res);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
            })
            .then(() => {
                if (selectedId === device.id) {
                    setSelectedId(null);
                    onSetActiveDevice && onSetActiveDevice(null);
                }
                loadDevices();
            })
            .catch((err) => {
                if (err.message !== 'Unauthorized') setError(err.message || 'Failed to remove device');
            });
    };

    return (
        <div className="dashboard-container">
            <header className="dashboard-header">
                <div className="header-brand">
                    <span className="brand-icon">🔥</span>
                    <h1>Wildfire Spot</h1>
                    <span className="sub-title">AIoT Quadruped Robot Center</span>
                </div>
                <div className="header-status-group">
                    <button className="nav-btn" onClick={() => onNavigate('/')}>Dashboard</button>
                    <button className="nav-btn nav-btn-active">Devices</button>
                    <button className="logout-btn" onClick={onLogout}>LOGOUT</button>
                </div>
            </header>

            <main className="device-page-main">
                <div className="device-page-toolbar">
                    <h2 className="device-page-title">Devices</h2>
                    <button className="device-register-btn" onClick={() => setModal({ mode: 'register' })}>
                        + Register Device
                    </button>
                </div>

                {error && <div className="device-page-error">{error}</div>}

                {loading ? (
                    <div className="device-state-msg">Loading devices...</div>
                ) : devices.length === 0 ? (
                    <div className="device-state-msg">No devices registered. Click <strong>+ Register Device</strong> to add one.</div>
                ) : (
                    <div className="device-grid">
                        {devices.map((device) => (
                            <DeviceCard
                                key={device.id}
                                device={device}
                                selected={selectedId === device.id}
                                onSelect={() => handleSelect(device)}
                                onEdit={() => setModal({ mode: 'edit', device })}
                                onDelete={() => handleDelete(device)}
                            />
                        ))}
                    </div>
                )}
            </main>

            {modal && (
                <DeviceModal
                    mode={modal.mode}
                    device={modal.device}
                    onSubmit={modal.mode === 'register' ? handleRegister : handleEdit}
                    onClose={() => setModal(null)}
                />
            )}
        </div>
    );
}
