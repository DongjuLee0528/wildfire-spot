import logging
import math
import threading
import time
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameSnapshot:
    sequence: int
    received_at: float
    frame: object = field(repr=False)


class SharedFrameCapture:
    def __init__(self, capture, *, fps=30, max_age=0.5, clock=time.monotonic):
        if not math.isfinite(fps) or fps <= 0 or not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('Invalid camera capture timing')
        self._capture = capture
        self._period = 1 / fps
        self._max_age = max_age
        self._clock = clock
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._lifecycle = threading.RLock()
        self._thread = None
        self._latest = None
        self._sequence = 0
        self._state = 'STOPPED'
        self._error = None
        self._released = False
        self._read_error = None

    def start(self):
        with self._lifecycle:
            if self._thread is not None or self._stop.is_set() or self._released:
                raise RuntimeError('Camera capture can only be started once')
            self._state = 'STARTING'
            try:
                self._thread = threading.Thread(target=self._run, name='camera-capture', daemon=True)
                self._thread.start()
            except Exception:
                self._thread = None
                self._fail('Cannot start camera capture worker')
                self._release_capture()
                raise
            except BaseException:
                try:
                    self.close()
                except Exception as error:
                    logger.error('Camera startup cancellation cleanup failed (%s)', type(error).__name__)
                raise

    def _fail(self, message):
        with self._lock:
            self._state, self._error, self._latest = 'ERROR', message, None
        logger.error('%s', message)

    def _release_capture(self):
        with self._lock:
            if self._released:
                return
            self._released = True
        try:
            self._capture.release()
        except Exception as error:
            self._fail('Camera release failed: ' + type(error).__name__)

    def _run(self):
        failed_read = False
        try:
            while not self._stop.is_set():
                started = self._clock()
                try:
                    ok, frame = self._capture.read()
                    read_error = None if ok and frame is not None else 'Camera returned no frame'
                except Exception as error:
                    ok, frame = False, None
                    read_error = 'Camera read failed: ' + type(error).__name__
                received_at = self._clock()
                if self._stop.is_set():
                    break
                if not ok or frame is None:
                    with self._lock:
                        if self._stop.is_set():
                            break
                        self._latest, self._state = None, 'WAITING'
                        self._read_error = read_error
                    if not failed_read:
                        logger.warning('%s', read_error)
                    failed_read = True
                else:
                    shape = frame.shape
                    if len(shape) != 3 or shape[0] <= 0 or shape[1] <= 0 or shape[2] != 3:
                        raise ValueError('Invalid camera frame shape')
                    owned = frame.copy()
                    with self._lock:
                        if self._stop.is_set():
                            break
                        self._sequence += 1
                        self._latest = FrameSnapshot(self._sequence, received_at, owned)
                        self._state = 'STREAMING'
                        self._read_error = None
                    failed_read = False
                self._stop.wait(max(0, self._period - (self._clock() - started)))
        except Exception as error:
            self._fail('Camera capture failed: ' + type(error).__name__)
        finally:
            self._release_capture()
            with self._lock:
                self._latest = None
                if self._error is None:
                    self._state = 'STOPPED'

    def get_latest(self, after_sequence=None):
        with self._lock:
            current = self._latest
            if (self._stop.is_set() or current is None or current.sequence == after_sequence or
                    self._clock() - current.received_at >= self._max_age):
                return None
        return FrameSnapshot(current.sequence, current.received_at, current.frame.copy())

    def get_status(self):
        with self._lock:
            state = self._state
            if state == 'STREAMING' and self._latest is not None and self._clock() - self._latest.received_at >= self._max_age:
                state = 'STALE'
            return {'state': state, 'error': self._error, 'read_error': self._read_error, 'sequence': self._sequence}

    def close(self, timeout=2):
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError('Invalid camera close timeout')
        with self._lifecycle:
            self._stop.set()
            with self._lock:
                self._latest = None
            if self._thread is not None and self._thread.ident is not None:
                self._thread.join(timeout)
                if self._thread.is_alive():
                    self._fail('Camera capture worker did not stop')
                    raise RuntimeError('Camera capture worker did not stop')
            else:
                self._release_capture()
            if self._error is not None:
                raise RuntimeError(self._error)
            with self._lock:
                self._state = 'STOPPED'
