import json
import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import numpy as np

from utils.config import (
    GAIT_DIAGNOSTIC_LOG_BACKUPS,
    GAIT_DIAGNOSTIC_LOG_ENABLED,
    GAIT_DIAGNOSTIC_LOG_MAX_BYTES,
    GAIT_DIAGNOSTIC_LOG_PATH,
    GAIT_DIAGNOSTIC_LOG_RATE_HZ,
)


def _json_safe(value):
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    return value


class GaitDiagnosticLogger:
    def __init__(
        self,
        enabled=GAIT_DIAGNOSTIC_LOG_ENABLED,
        path=GAIT_DIAGNOSTIC_LOG_PATH,
        rate_hz=GAIT_DIAGNOSTIC_LOG_RATE_HZ,
        max_bytes=GAIT_DIAGNOSTIC_LOG_MAX_BYTES,
        backup_count=GAIT_DIAGNOSTIC_LOG_BACKUPS,
        monotonic=time.monotonic,
    ):
        self.enabled = bool(enabled)
        self.path = path
        self.interval = 1.0 / max(float(rate_hz), 0.1)
        self.monotonic = monotonic
        self._last_sample = None
        self._last_anomaly = {}
        self._anomaly_interval = 1.0
        self._logger = None
        if not self.enabled:
            return

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._logger = logging.getLogger(f"wildfire.gait_diagnostics.{path}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not any(getattr(handler, "_gait_diag_path", None) == path for handler in self._logger.handlers):
            handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count)
            handler.setFormatter(logging.Formatter("%(message)s"))
            handler._gait_diag_path = path
            self._logger.addHandler(handler)

    def should_sample(self, now=None):
        if not self.enabled:
            return False
        now = self.monotonic() if now is None else now
        if self._last_sample is None or now - self._last_sample >= self.interval:
            self._last_sample = now
            return True
        return False

    def snapshot(self, record, now=None):
        if self.should_sample(now):
            self._write("snapshot", record)

    def anomaly(self, record, now=None):
        if not self.enabled:
            return
        now = self.monotonic() if now is None else now
        key = (
            record.get("anomaly_type"),
            record.get("failed_leg"),
            record.get("failure_reason"),
        )
        if now - self._last_anomaly.get(key, -self._anomaly_interval) < self._anomaly_interval:
            return
        self._last_anomaly[key] = now
        self._write("anomaly", record)

    def _write(self, event_type, record):
        if self._logger is None:
            return
        try:
            payload = {
                "schema_version": 1,
                "event_type": event_type,
                "utc_timestamp": datetime.now(timezone.utc).isoformat(),
                **_json_safe(record),
            }
            self._logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        except (TypeError, ValueError, OSError, RuntimeError):
            return
