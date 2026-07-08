import React, { useState } from 'react';

export default function LoginPage({ onLoginSuccess, onGoSignup }) {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        })
            .then((res) => {
                if (!res.ok) {
                    return res.json().catch(() => null).then((body) => {
                        throw new Error(body?.message || `HTTP ${res.status}`);
                    });
                }
                return res.json();
            })
            .then((data) => {
                const token = data?.accessToken ?? data?.token;
                if (!token) throw new Error('No token received');
                localStorage.setItem('jwt_token', token);
                onLoginSuccess();
            })
            .catch((err) => setError(err.message || 'Login failed'))
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
                    <h2 className="auth-title">Sign In</h2>
                    {error && <div className="auth-error">{error}</div>}
                    <div className="auth-field">
                        <label className="auth-label">Email</label>
                        <input
                            className="auth-input"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            autoComplete="email"
                            required
                        />
                    </div>
                    <div className="auth-field">
                        <label className="auth-label">Password</label>
                        <input
                            className="auth-input"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            autoComplete="current-password"
                            required
                        />
                    </div>
                    <button className="auth-btn auth-btn-primary" type="submit" disabled={loading}>
                        {loading ? 'Signing in...' : 'Sign In'}
                    </button>
                    <button className="auth-btn auth-btn-secondary" type="button" onClick={onGoSignup}>
                        Create Account
                    </button>
                </form>
            </div>
        </div>
    );
}
