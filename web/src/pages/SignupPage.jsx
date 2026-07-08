import React, { useState } from 'react';

export default function SignupPage({ onSignupSuccess, onGoLogin }) {
    const [form, setForm] = useState({ name: '', email: '', username: '', password: '' });
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

    const handleSubmit = (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        })
            .then((res) => {
                if (!res.ok) {
                    return res.json().catch(() => null).then((body) => {
                        throw new Error(body?.message || `HTTP ${res.status}`);
                    });
                }
                return res.json();
            })
            .then(() => onSignupSuccess())
            .catch((err) => setError(err.message || 'Signup failed'))
            .finally(() => setLoading(false));
    };

    return (
        <div className="auth-page">
            <div className="auth-card">
                <div className="auth-brand">
                    <span className="brand-icon">🔥</span>
                    <h1>Wildfire Spot</h1>
                    <span className="auth-subtitle">AIoT Quadruped Robot Center</span>
                </div>
                <form className="auth-form" onSubmit={handleSubmit}>
                    <h2 className="auth-title">Create Account</h2>
                    {error && <div className="auth-error">{error}</div>}
                    <div className="auth-field">
                        <label className="auth-label">Name</label>
                        <input
                            className="auth-input"
                            type="text"
                            name="name"
                            value={form.name}
                            onChange={handleChange}
                            autoComplete="name"
                            required
                        />
                    </div>
                    <div className="auth-field">
                        <label className="auth-label">Email</label>
                        <input
                            className="auth-input"
                            type="email"
                            name="email"
                            value={form.email}
                            onChange={handleChange}
                            autoComplete="email"
                            required
                        />
                    </div>
                    <div className="auth-field">
                        <label className="auth-label">Username</label>
                        <input
                            className="auth-input"
                            type="text"
                            name="username"
                            value={form.username}
                            onChange={handleChange}
                            autoComplete="username"
                            required
                        />
                    </div>
                    <div className="auth-field">
                        <label className="auth-label">Password</label>
                        <input
                            className="auth-input"
                            type="password"
                            name="password"
                            value={form.password}
                            onChange={handleChange}
                            autoComplete="new-password"
                            minLength={8}
                            required
                        />
                    </div>
                    <button className="auth-btn auth-btn-primary" type="submit" disabled={loading}>
                        {loading ? 'Creating...' : 'Create Account'}
                    </button>
                    <button className="auth-btn auth-btn-secondary" type="button" onClick={onGoLogin}>
                        Back to Sign In
                    </button>
                </form>
            </div>
        </div>
    );
}
