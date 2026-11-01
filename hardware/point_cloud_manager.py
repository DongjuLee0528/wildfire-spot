import ipaddress
import logging
import math
import os
from pathlib import Path
import selectors
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from utils.point_cloud_metrics import PointCloudMetrics

logger = logging.getLogger(__name__)
_HEADER = struct.Struct('<4sIIIdII')
_MAX_POINTS = 12000
_MAX_CHUNK = 65536


@dataclass(frozen=True)
class PointCloudFrame:
    timestamp: float
    cloud_id: int
    ring_count: int
    point_count: int
    data: bytes


class FrameDecoder:
    def __init__(self):
        self._buffer = bytearray()

    def feed(self, chunk):
        if len(chunk) > _MAX_CHUNK:
            raise ValueError('Frame input chunk exceeds 65536 bytes')
        self._buffer.extend(chunk)
        while len(self._buffer) >= _HEADER.size:
            magic, version, size, count, stamp, cloud_id, rings = _HEADER.unpack_from(self._buffer)
            if magic != b'L2PC' or version != 1:
                raise ValueError('Invalid point-cloud magic or version')
            if count > _MAX_POINTS or size != count * 12:
                raise ValueError('Invalid point-cloud payload size or count')
            if not math.isfinite(stamp) or stamp < 0:
                raise ValueError('Invalid point-cloud timestamp')
            total = _HEADER.size + size
            if len(self._buffer) < total:
                break
            data = bytes(self._buffer[:total])
            del self._buffer[:total]
            for x, y, z in struct.iter_unpack('<fff', data[_HEADER.size:]):
                distance2 = x*x + y*y + z*z
                if not math.isfinite(distance2) or not 0 < distance2 <= 900:
                    raise ValueError('Invalid or out-of-range point-cloud coordinate')
            yield PointCloudFrame(stamp, cloud_id, rings, count, data)

    def finish(self):
        if self._buffer:
            raise ValueError('Receiver ended with a partial point-cloud frame')


class PointCloudManager:
    def __init__(self, receiver_path, local_ip='192.168.1.2', lidar_ip='192.168.1.62',
                 *, stale_after=2.0, frame_timeout=6.0, shutdown_timeout=3.0,
                 restart_delays=(1.0, 2.0, 4.0, 8.0, 16.0)):
        self._command = (str(Path(receiver_path).expanduser().resolve()),
                         str(ipaddress.IPv4Address(local_ip)), str(ipaddress.IPv4Address(lidar_ip)))
        if not all(math.isfinite(value) and value > 0
                   for value in (stale_after, frame_timeout, shutdown_timeout)):
            raise ValueError('Point-cloud timeouts must be finite and positive')
        if frame_timeout <= stale_after:
            raise ValueError('Frame timeout must exceed stale threshold')
        if len(restart_delays) > 5 or not all(math.isfinite(value) and value >= 0 for value in restart_delays):
            raise ValueError('At most five finite nonnegative restart delays are allowed')
        self._stale_after = stale_after
        self._frame_timeout = frame_timeout
        self._shutdown_timeout = shutdown_timeout
        self._restart_delays = tuple(restart_delays)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._thread = None
        self._state = 'STOPPED'
        self._error = None
        self._latest = None
        self._received_at = None
        self._restart_count = 0
        self._pid = None
        self._metrics = PointCloudMetrics('receiver_decoded')

    def _set_state(self, state, error=None):
        with self._lock:
            self._state, self._error = state, error
            if state != 'STREAMING':
                self._latest = self._received_at = None

    def start(self):
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            with self._lock:
                if self._pid is not None:
                    raise RuntimeError('Previous receiver has not been reaped; refusing another start')
                self._restart_count = 0
            self._stop.clear()
            self._metrics.reset()
            self._set_state('STARTING')
            if not Path(self._command[0]).is_file() or not os.access(self._command[0], os.X_OK):
                error = 'L2 receiver executable is missing or not executable: ' + self._command[0]
                self._set_state('ERROR', error)
                logger.error('%s', error)
                return
            try:
                self._thread = threading.Thread(target=self._run, name='l2-point-cloud', daemon=True)
                self._thread.start()
            except RuntimeError as error:
                self._thread = None
                self._set_state('ERROR', str(error))
                logger.error('Cannot start point-cloud worker: %s', error)

    def get_status(self):
        with self._lock:
            age = None if self._received_at is None else time.monotonic() - self._received_at
            state = self._state
            if state == 'STREAMING' and age is not None and age > self._stale_after:
                state = 'STALE'
            return {'state': state, 'error': self._error, 'age_seconds': age,
                    'restart_count': self._restart_count, 'pid': self._pid}

    def get_latest_frame(self):
        with self._lock:
            if (self._state != 'STREAMING' or self._received_at is None or
                    time.monotonic() - self._received_at > self._stale_after):
                return None
            return self._latest

    def _consume(self, process, stderr_tail):
        decoder = FrameDecoder()
        last_frame = time.monotonic()
        with selectors.DefaultSelector() as selector:
            for stream, label in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
            while not self._stop.is_set():
                if time.monotonic() - last_frame > self._frame_timeout:
                    raise RuntimeError('No complete point-cloud frame within timeout')
                for key, _ in selector.select(timeout=0.1):
                    try:
                        chunk = os.read(key.fd, _MAX_CHUNK)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        if key.data == 'stdout':
                            decoder.finish()
                            try:
                                process.wait(timeout=0.1)
                            except subprocess.TimeoutExpired:
                                logger.debug('Receiver closed stdout before exiting')
                            raise RuntimeError('L2 receiver stdout closed')
                        continue
                    if key.data == 'stderr':
                        stderr_tail.extend(chunk)
                        del stderr_tail[:-4096]
                    else:
                        for frame in decoder.feed(chunk):
                            last_frame = time.monotonic()
                            with self._lock:
                                self._latest, self._received_at = frame, last_frame
                                self._state, self._error = 'STREAMING', None
                            self._metrics.record(frame.data)

    def _drain_stderr(self, process, stderr_tail):
        os.set_blocking(process.stderr.fileno(), False)
        for _ in range(16):
            try:
                chunk = os.read(process.stderr.fileno(), _MAX_CHUNK)
            except BlockingIOError:
                break
            if not chunk:
                break
            stderr_tail.extend(chunk)
            del stderr_tail[:-4096]

    def _cleanup(self, process, stderr_tail):
        try:
            if process.poll() is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    logger.debug('Receiver already exited before terminate')
                try:
                    process.wait(timeout=self._shutdown_timeout)
                except subprocess.TimeoutExpired:
                    logger.warning('L2 receiver did not terminate; killing process %s', process.pid)
                    try:
                        process.kill()
                    except ProcessLookupError:
                        logger.debug('Receiver already exited before kill')
                    process.wait(timeout=1.0)
            else:
                process.wait()
            with self._lock:
                self._pid = None
        finally:
            try:
                self._drain_stderr(process, stderr_tail)
            finally:
                try:
                    process.stdout.close()
                finally:
                    process.stderr.close()

    def _run(self):
        try:
            self._run_receiver()
        finally:
            self._metrics.finish()

    def _run_receiver(self):
        for attempt in range(len(self._restart_delays) + 1):
            if self._stop.is_set():
                break
            self._set_state('STARTING')
            with self._lock:
                self._restart_count = attempt
            try:
                process = subprocess.Popen(self._command, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           bufsize=0, start_new_session=True)
            except OSError as error:
                self._set_state('ERROR', str(error))
                logger.error('Cannot start L2 receiver: %s', error)
                return
            with self._lock:
                self._pid = process.pid
            stderr_tail = bytearray()
            error_message = None
            try:
                self._consume(process, stderr_tail)
            except Exception as error:
                error_message = str(error)
                self._set_state('ERROR', error_message)
            finally:
                try:
                    self._cleanup(process, stderr_tail)
                except Exception as error:
                    message = '{}; L2 receiver cleanup failed: {}'.format(
                        error_message or 'Receiver shutdown', error)
                    self._set_state('ERROR', message)
                    logger.exception('%s', message)
                    return
            if self._stop.is_set():
                break
            message = '{} (exit {}); stderr: {}'.format(
                error_message or 'L2 receiver stopped unexpectedly', process.returncode,
                stderr_tail.decode('utf-8', errors='replace'))
            logger.warning('%s', message)
            if process.returncode == 2 or attempt == len(self._restart_delays):
                self._set_state('ERROR', message)
                return
            self._set_state('RESTARTING', message)
            if self._stop.wait(self._restart_delays[attempt]):
                break
        self._set_state('STOPPED')

    def close(self):
        with self._lifecycle_lock:
            self._stop.set()
            self._set_state('STOPPING')
            if self._thread is not None:
                self._thread.join(timeout=self._shutdown_timeout + 3.0)
                if self._thread.is_alive():
                    self._set_state('ERROR', 'Point-cloud worker did not stop within shutdown deadline')
                    raise RuntimeError('Point-cloud worker did not stop within shutdown deadline')
            with self._lock:
                if self._pid is not None:
                    self._state = 'ERROR'
                    self._error = 'L2 receiver cleanup failed; child process may still exist'
                    raise RuntimeError(self._error)
            self._set_state('STOPPED')
