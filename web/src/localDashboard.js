const boolean = value => typeof value === 'boolean' ? value : null;
const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const text = value => typeof value === 'string' ? value : null;

export function normalizeLocalDashboard(data) {
    const status = data?.status, gps = data?.gps, sensors = data?.sensors, fire = data?.fire;
    const flame = ['frontLeft', 'frontRight', 'left', 'right'].map(key => boolean(sensors?.flame?.[key]));
    const latitude = number(gps?.latitude), longitude = number(gps?.longitude);
    const fixed = gps?.fix === true && latitude !== null && longitude !== null &&
        Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
    const fireFlags = ['suspected', 'verified', 'cameraDetected', 'sensorDetected'].map(key => boolean(fire?.[key]));
    const confidence = data?.vision?.model_available === true ? number(data.vision.confidence) : null;
    return {
        status: { online: boolean(status?.robotConnected), mode: text(status?.mode),
            robotState: text(status?.state), batteryLevel: null, lastSeenAt: text(status?.lastUpdate) },
        gps: { latitude: fixed ? latitude : null, longitude: fixed ? longitude : null,
            fix: gps == null ? null : fixed },
        sensors: { temperature: number(sensors?.temperature), humidity: number(sensors?.humidity),
            flameDetected: flame.includes(true) ? true : flame.every(value => value === false) ? false : null },
        fire: { fireDetected: fireFlags.includes(true) ? true : fireFlags.every(value => value === false) ? false : null,
            confidence: confidence !== null && confidence >= 0 && confidence <= 1 ? confidence : null,
            severity: text(fire?.state), source: null },
        health: Object.fromEntries(['robot', 'camera', 'gps', 'lidar', 'sensor'].map(key => [key, boolean(data?.health?.[key])])),
        logs: Array.isArray(data?.logs?.logs) ? data.logs.logs.filter(entry => typeof entry.message === 'string').map(entry => ({
            time: text(entry.timestamp) ?? 'Unknown time', text: `${text(entry.level) ?? 'UNKNOWN'}: ${entry.message}`,
        })) : [],
        camera: { available: boolean(data?.camera?.available), pan: text(data?.camera?.pan) ?? 'UNKNOWN',
            tilt: number(data?.camera?.tilt) },
    };
}
