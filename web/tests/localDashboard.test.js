import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeLocalDashboard } from '../src/localDashboard.js';
import { connectPointCloud } from '../src/transport/pointCloudTransport.js';
import { readFileSync } from 'node:fs';

const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/point_cloud_v1.json', import.meta.url)))[0];
const binary = Uint8Array.from(Buffer.from(fixture.hex, 'hex'));

test('missing and malformed local data stay unknown instead of healthy or zero', () => {
    for (const input of [null, {}, { sensors: { temperature: '24', humidity: NaN }, health: { camera: 'yes' } }]) {
        const result = normalizeLocalDashboard(input);
        assert.equal(result.status.online, null);
        assert.equal(result.sensors.temperature, null); assert.equal(result.sensors.humidity, null);
        assert.equal(result.fire.fireDetected, null); assert.equal(result.health.camera, null);
        assert.equal(result.gps.latitude, null); assert.deepEqual(result.logs, []);
    }
});

test('local contract maps live state, incomplete flame data and no GPS fix honestly', () => {
    const result = normalizeLocalDashboard({
        status: { robotConnected: true, mode: 'MANUAL', state: 'IDLE', lastUpdate: '2026-01-01' },
        gps: { latitude: 37, longitude: 127, fix: false },
        sensors: { temperature: 0, humidity: 40, flame: { frontLeft: false } },
        fire: { state: 'NORMAL', suspected: false, verified: false, cameraDetected: false, sensorDetected: false },
        vision: { model_available: true, confidence: 0.8 },
        health: { robot: true, camera: false, lidar: false },
        logs: { logs: [{ message: 'Actual runtime entry', level: 'WARNING', timestamp: '2026-01-01' }] },
    });
    assert.equal(result.status.online, true); assert.equal(result.status.batteryLevel, null);
    assert.equal(result.sensors.temperature, 0); assert.equal(result.sensors.flameDetected, null);
    assert.equal(result.gps.fix, false); assert.equal(result.gps.latitude, null);
    assert.equal(result.fire.fireDetected, false); assert.equal(result.fire.confidence, 0.8);
    assert.equal(result.fire.severity, 'NORMAL'); assert.equal(result.logs[0].text, 'WARNING: Actual runtime entry');
});

test('local point cloud uses Python route and never reads or sends a stale NAS token', async () => {
    let request, received;
    const connection = connectPointCloud({ localMode: true,
        getToken: () => { throw new Error('NAS token must not be read'); },
        onFrame: frame => { if (frame) received = frame; }, onState: () => {}, retryDelays: [],
        fetchImpl: async (url, init) => {
            request = { url, init };
            return new Response(binary, { headers: { 'Content-Type': 'application/octet-stream' } });
        },
    });
    await connection.done;
    assert.equal(request.url, '/robot/point-cloud/stream');
    assert.deepEqual(request.init.headers, {}); assert.equal(received.cloudId, 42);
    connection.stop();
});

test('NAS stream still requires authentication and uses original device route', async () => {
    let called = false;
    const connection = connectPointCloud({ deviceId: 'device', getToken: () => null,
        onFrame: () => {}, onState: () => {}, fetchImpl: async () => { called = true; } });
    await connection.done;
    assert.equal(called, false); assert.equal(connection.getStatus().error, 'Authentication required');
});
