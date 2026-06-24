# Wildfire Spot — Web API Contract

Phase 2 · Spring Boot Mock Backend
Base URL: `http://localhost:8080`

---

## GET /api/status

Returns current robot operational state.

**Response 200**
```json
{
  "state": "PATROL",
  "mode": "AUTO",
  "robotConnected": true,
  "lastUpdate": "2026-06-24T21:00:00"
}
```

---

## GET /api/health

Returns hardware component health flags.

**Response 200**
```json
{
  "robotCore": true,
  "camera": false,
  "gps": true,
  "lidar": true,
  "sensors": true
}
```

---

## GET /api/gps

Returns current GPS fix and coordinates.

**Response 200**
```json
{
  "latitude": 37.5665,
  "longitude": 126.9780,
  "fix": true,
  "updatedAt": "2026-06-24T21:00:00"
}
```

---

## GET /api/sensors

Returns all sensor telemetry.

`flame` object booleans: `true` = flame detected, `false` = clear.

**Response 200**
```json
{
  "temperature": 31.5,
  "humidity": 42.0,
  "mq2Gas": 128,
  "flame": {
    "frontLeft": false,
    "frontRight": false,
    "left": true,
    "right": false
  },
  "lidarStatus": "SCANNING"
}
```

---

## GET /api/fire/status

Returns fire verification pipeline results.

**Response 200**
```json
{
  "hardwareConfirmed": true,
  "cameraDetected": false,
  "finalConfirmedFire": false
}
```

---

## GET /api/logs

Returns recent system log entries.

**Response 200**
```json
{
  "logs": [
    {
      "level": "INFO",
      "message": "AUTO MODE ENABLED",
      "timestamp": "2026-06-24T21:00:03"
    },
    {
      "level": "WARN",
      "message": "CAMERA STREAM WAITING (FEED_UNAVAILABLE)",
      "timestamp": "2026-06-24T21:00:13"
    }
  ]
}
```

`level` values: `INFO`, `WARN`, `ERROR`

---

## POST /api/control

Send a movement command.

**Request**
```json
{
  "command": "FORWARD"
}
```

`command` allowed values: `FORWARD`, `BACKWARD`, `LEFT`, `RIGHT`, `STOP`, `RESET`

**Response 200**
```json
{
  "accepted": true,
  "command": "FORWARD"
}
```

**Response 400 — invalid command**
```json
{
  "error": "INVALID_REQUEST",
  "message": "Invalid or unrecognized value in request body"
}
```

---

## POST /api/mode

Switch robot operating mode.

**Request**
```json
{
  "mode": "MANUAL"
}
```

`mode` allowed values: `AUTO`, `MANUAL`

**Response 200**
```json
{
  "accepted": true,
  "mode": "MANUAL"
}
```

**Response 400 — invalid mode**
```json
{
  "error": "INVALID_REQUEST",
  "message": "Invalid or unrecognized value in request body"
}
```

---

## Future APIs (Not Implemented)

The following endpoints are reserved for Phase 3+:

```
GET /api/video/raw        — Raw MJPEG camera stream
GET /api/video/detection  — AI-annotated overlay stream
WS  /ws/telemetry         — Real-time telemetry WebSocket
```

---

## Notes

- All timestamps use ISO-8601 local datetime format (`LocalDateTime`, no timezone suffix).
- CORS is open (`*`) for Phase 2 local development only. Restrict before deployment.
- Phase 3 migration: replace `DashboardService` mock bodies with `RobotGatewayClient` calls.
