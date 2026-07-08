import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import LoginPage from './pages/LoginPage.jsx'
import SignupPage from './pages/SignupPage.jsx'
import DevicePage from './pages/DevicePage.jsx'
import './App.css'

const JWT_KEY = 'jwt_token';
const ACTIVE_DEVICE_KEY = 'wildfire_active_device';

function getActiveDevice() {
    try { return JSON.parse(localStorage.getItem(ACTIVE_DEVICE_KEY)); } catch { return null; }
}

function setActiveDevice(device) {
    if (device) {
        localStorage.setItem(ACTIVE_DEVICE_KEY, JSON.stringify({ id: device.id, name: device.name, serialNumber: device.serialNumber }));
    } else {
        localStorage.removeItem(ACTIVE_DEVICE_KEY);
    }
}

function navigate(path) {
    window.history.pushState(null, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
}

function logout() {
    localStorage.removeItem(JWT_KEY);
    localStorage.removeItem(ACTIVE_DEVICE_KEY);
    navigate('/login');
}

function Root() {
    const [pathname, setPathname] = useState(window.location.pathname);
    const [authState, setAuthState] = useState('idle');
    const [activeDevice, setActiveDeviceState] = useState(() => getActiveDevice());

    const handleSetActiveDevice = (device) => {
        setActiveDevice(device);
        setActiveDeviceState(device ? { id: device.id, name: device.name, serialNumber: device.serialNumber } : null);
    };

    useEffect(() => {
        const onPop = () => setPathname(window.location.pathname);
        window.addEventListener('popstate', onPop);
        return () => window.removeEventListener('popstate', onPop);
    }, []);

    useEffect(() => {
        const token = localStorage.getItem(JWT_KEY);
        if (pathname === '/login' || pathname === '/signup') {
            setAuthState('idle');
            return;
        }
        if (!token) {
            navigate('/login');
            return;
        }
        setAuthState('checking');
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 5000);
        fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
        })
            .finally(() => clearTimeout(timer))
            .then((res) => {
                if (res.status === 401 || res.status === 403) {
                    localStorage.removeItem(JWT_KEY);
                    navigate('/login');
                } else if (!res.ok) {
                    localStorage.removeItem(JWT_KEY);
                    navigate('/login');
                } else {
                    setAuthState('ok');
                }
            })
            .catch((err) => {
                if (err && err.name === 'AbortError') return;
                localStorage.removeItem(JWT_KEY);
                navigate('/login');
            });
        return () => controller.abort();
    }, [pathname]);

    if (pathname === '/signup') {
        return (
            <SignupPage
                onSignupSuccess={() => navigate('/login')}
                onGoLogin={() => navigate('/login')}
            />
        );
    }

    if (pathname === '/login') {
        return (
            <LoginPage
                onLoginSuccess={() => navigate('/')}
                onGoSignup={() => navigate('/signup')}
            />
        );
    }

    if (authState === 'checking') {
        return <div className="auth-checking">Verifying session...</div>;
    }

    if (authState !== 'ok') {
        return null;
    }

    if (pathname === '/device') {
        return <DevicePage onLogout={logout} onNavigate={navigate} activeDevice={activeDevice} onSetActiveDevice={handleSetActiveDevice} />;
    }

    return <App onLogout={logout} onNavigate={navigate} activeDevice={activeDevice} onNavigateDevice={() => navigate('/device')} />;
}

ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
        <Root />
    </React.StrictMode>,
)
