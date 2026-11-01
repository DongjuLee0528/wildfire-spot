import json
import logging
import math
import random
import threading
import time
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)
_UNSET = object()


class UploadProtocolError(Exception):
    pass


class UploadUnavailable(Exception):
    pass


class PointCloudUploader:
    def __init__(self, manager, serial_number, device_key, base_url, *,
                 session_factory=requests.Session, retry_delays=(1, 2, 4, 8, 16),
                 degraded_delay=30, jitter=lambda: random.uniform(0, 3)):
        url = urlsplit(base_url)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username or
                url.password or url.query or url.fragment):
            raise ValueError('Invalid point-cloud backend URL')
        if manager is None or not serial_number or not device_key:
            raise ValueError('Point-cloud source and device credentials are required')
        if len(retry_delays) > 5 or any(not math.isfinite(delay) or delay < 0 for delay in retry_delays) or not math.isfinite(degraded_delay) or degraded_delay < 0:
            raise ValueError('Invalid point-cloud retry settings')
        self._manager = manager
        self._serial = serial_number
        self._key = device_key
        self._base = base_url.rstrip('/')
        self._session_factory = session_factory
        self._retry_delays = tuple(retry_delays)
        self._degraded_delay = degraded_delay
        self._jitter = jitter
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._lifecycle = threading.Lock()
        self._thread = None
        self._state = 'STOPPED'
        self._error = None
        self._failures = 0
        self._token = None
        self._last_sent = None
        self._cleanup_error = None

    def _set_state(self, state, error=_UNSET):
        with self._lock:
            self._state = state
            if error is not _UNSET:
                self._error = error

    def get_status(self):
        with self._lock:
            return {'state': self._state, 'error': self._error, 'failures': self._failures}

    def start(self):
        with self._lifecycle:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._token = self._last_sent = None
            self._cleanup_error = None
            with self._lock:
                self._failures = 0
            self._set_state('WAITING', None)
            try:
                self._thread = threading.Thread(target=self._run, name='point-cloud-upload', daemon=True)
                self._thread.start()
            except RuntimeError:
                self._thread = None
                self._set_state('ERROR', 'Cannot start point-cloud upload worker')
                logger.error('Cannot start point-cloud upload worker')

    def _login(self, session):
        with session.post(self._base + '/api/device-auth/login',
                          json={'serialNumber': self._serial, 'deviceKey': self._key},
                          timeout=(1, 2), stream=True, allow_redirects=False) as response:
            if response.status_code == 401:
                raise UploadProtocolError('Device credentials rejected')
            if response.status_code in (403, 429) or response.status_code >= 500:
                raise UploadUnavailable('Device login temporarily unavailable')
            if response.status_code != 200:
                raise UploadProtocolError('Unexpected device login status')
            data = bytearray()
            deadline = time.monotonic() + 2
            for chunk in response.iter_content(chunk_size=1024):
                if self._stop.is_set():
                    return
                if time.monotonic() > deadline:
                    raise UploadUnavailable('Device login body timed out')
                data.extend(chunk)
                if len(data) > 8192:
                    raise UploadProtocolError('Device login response too large')
            try:
                content = json.loads(data)
                token = content.get('accessToken') or content.get('deviceToken') or content.get('token')
            except (ValueError, AttributeError):
                raise UploadProtocolError('Malformed device login response') from None
            if not isinstance(token, str) or not token or len(token) > 8192:
                raise UploadProtocolError('Missing device token')
            self._token = token

    def _post_frame(self, session, frame):
        if not 32 <= len(frame.data) <= 144032:
            raise UploadProtocolError('Invalid outgoing point-cloud size')
        with session.post(self._base + '/api/device/point-cloud', data=frame.data,
                          headers={'Content-Type': 'application/octet-stream',
                                   'Authorization': 'Bearer ' + self._token},
                          timeout=(1, 2), stream=True, allow_redirects=False) as response:
            if response.status_code == 204 and response.content:
                raise UploadProtocolError('Unexpected point-cloud response body')
            return response.status_code

    def _deliver(self, session, frame):
        if not self._token:
            self._login(session)
        if self._stop.is_set():
            return None
        frame = self._manager.get_latest_frame()
        if frame is None:
            return None
        status = self._post_frame(session, frame)
        if status in (401, 403):
            self._token = None
            self._login(session)
            if self._stop.is_set():
                return None
            frame = self._manager.get_latest_frame()
            if frame is None:
                return None
            status = self._post_frame(session, frame)
            if status in (401, 403):
                raise UploadProtocolError('Point-cloud device authorization rejected after login')
        if status == 204:
            return frame
        if status == 429 or status >= 500:
            raise UploadUnavailable('Point-cloud backend temporarily unavailable')
        raise UploadProtocolError('Unexpected point-cloud upload status')

    def _run(self):
        session = None
        try:
            session = self._session_factory()
            while not self._stop.is_set():
                frame = self._manager.get_latest_frame()
                if frame is None or frame is self._last_sent:
                    if frame is None:
                        self._set_state('WAITING')
                    self._stop.wait(0.1)
                    continue
                try:
                    self._set_state('CONNECTING')
                    sent = self._deliver(session, frame)
                    if self._stop.is_set():
                        break
                    if sent is not None:
                        self._last_sent = sent
                        with self._lock:
                            self._failures = 0
                        self._set_state('STREAMING', None)
                    self._stop.wait(0.1)
                except UploadProtocolError as error:
                    self._set_state('ERROR', str(error))
                    logger.error('Point-cloud upload stopped: %s', error)
                    return
                except (requests.RequestException, UploadUnavailable) as error:
                    with self._lock:
                        self._failures += 1
                        failures = self._failures
                    state = 'RETRYING' if failures <= len(self._retry_delays) else 'DEGRADED'
                    self._set_state(state, 'Point-cloud upload unavailable: ' + type(error).__name__)
                    if failures <= len(self._retry_delays):
                        delay = self._retry_delays[failures - 1]
                    else:
                        delay = self._degraded_delay + self._jitter()
                    logger.warning('Point-cloud upload %s; retry delayed', state.lower())
                    self._stop.wait(delay)
        except Exception as error:
            self._set_state('ERROR', 'Point-cloud upload worker failed: ' + type(error).__name__)
            logger.error('Point-cloud upload worker failed (%s)', type(error).__name__)
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as error:
                    self._cleanup_error = 'Point-cloud session cleanup failed: ' + type(error).__name__
                    previous = self.get_status()['error']
                    self._set_state('ERROR', (previous + '; ' if previous else '') + self._cleanup_error)
                    logger.error('Point-cloud session cleanup failed (%s)', type(error).__name__)
            if self._stop.is_set() and self._cleanup_error is None:
                self._set_state('STOPPED')

    def request_stop(self):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive() and self._cleanup_error is None:
            self._set_state('STOPPING')

    def close(self):
        with self._lifecycle:
            self.request_stop()
            if self._thread is not None:
                self._thread.join(timeout=7)
                if self._thread.is_alive():
                    self._set_state('ERROR', 'Point-cloud upload worker did not stop')
                    raise RuntimeError('Point-cloud upload worker did not stop')
            if self._cleanup_error is not None:
                raise RuntimeError(self._cleanup_error)
            self._set_state('STOPPED')


def start_point_cloud_uploader(manager, enabled, serial_number, device_key, base_url):
    if not enabled or manager is None:
        logger.info('Point-cloud uploader disabled: no enabled source')
        return None
    try:
        uploader = PointCloudUploader(manager, serial_number, device_key, base_url)
        uploader.start()
        return uploader
    except Exception as error:
        logger.error('Point-cloud uploader could not initialize (%s)', type(error).__name__)
        return None
