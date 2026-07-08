import React, { useState, useEffect } from 'react';

const EMPTY_FORM = { name: '', serialNumber: '', deviceKey: '', description: '' };

export default function DeviceModal({ mode, device, onSubmit, onClose }) {
    const [form, setForm] = useState(EMPTY_FORM);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (mode === 'edit' && device) {
            setForm({
                name: device.name || '',
                serialNumber: device.serialNumber || '',
                deviceKey: device.deviceKey || '',
                description: device.description || '',
            });
        } else {
            setForm(EMPTY_FORM);
        }
        setError('');
    }, [mode, device]);

    const handleChange = (e) => setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

    const handleSubmit = (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        onSubmit(form)
            .catch((err) => setError(err.message || 'Request failed'))
            .finally(() => setLoading(false));
    };

    const isRegister = mode === 'register';
    const title = isRegister ? 'Register Device' : 'Edit Device';

    return (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
            <div className="modal-card">
                <div className="modal-header">
                    <h3 className="modal-title">{title}</h3>
                    <button className="modal-close-btn" onClick={onClose} aria-label="Close">✕</button>
                </div>
                <form className="modal-form" onSubmit={handleSubmit}>
                    {error && <div className="auth-error">{error}</div>}
                    <div className="auth-field">
                        <label className="auth-label">Device Name</label>
                        <input
                            className="auth-input"
                            type="text"
                            name="name"
                            value={form.name}
                            onChange={handleChange}
                            required
                        />
                    </div>
                    {isRegister && (
                        <>
                            <div className="auth-field">
                                <label className="auth-label">Serial Number</label>
                                <input
                                    className="auth-input"
                                    type="text"
                                    name="serialNumber"
                                    value={form.serialNumber}
                                    onChange={handleChange}
                                    required
                                />
                            </div>
                            <div className="auth-field">
                                <label className="auth-label">Device Key</label>
                                <input
                                    className="auth-input"
                                    type="text"
                                    name="deviceKey"
                                    value={form.deviceKey}
                                    onChange={handleChange}
                                    required
                                />
                            </div>
                        </>
                    )}
                    <div className="auth-field">
                        <label className="auth-label">Description (optional)</label>
                        <input
                            className="auth-input"
                            type="text"
                            name="description"
                            value={form.description}
                            onChange={handleChange}
                        />
                    </div>
                    <div className="modal-actions">
                        <button className="auth-btn auth-btn-primary" type="submit" disabled={loading}>
                            {loading ? 'Saving...' : isRegister ? 'Register' : 'Save'}
                        </button>
                        <button className="auth-btn auth-btn-secondary" type="button" onClick={onClose} disabled={loading}>
                            Cancel
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
