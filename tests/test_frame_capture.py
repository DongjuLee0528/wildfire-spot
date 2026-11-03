import threading
import time
import unittest
from unittest import mock

import numpy as np
from vision.frame_capture import SharedFrameCapture


class FakeCapture:
    def __init__(self, block_after_first=False, fail=False, release_error=False):
        self.image = np.zeros((32, 48, 3), dtype=np.uint8)
        self.calls = []
        self.releases = []
        self.gate = threading.Event()
        self.blocked = threading.Event()
        self.block_after_first, self.fail, self.release_error = block_after_first, fail, release_error
        self.empty = False
    def isOpened(self): return True
    def set(self, *_): return True
    def read(self):
        self.calls.append(threading.get_ident())
        if self.fail: raise OSError('fake read failure')
        if self.block_after_first and len(self.calls) > 1:
            self.blocked.set()
            if not self.gate.wait(3): raise RuntimeError('fake capture gate timed out')
        if self.empty: return False, None
        self.image.fill(len(self.calls) % 255)
        return True, self.image
    def release(self):
        self.releases.append(threading.get_ident())
        if self.release_error: raise OSError('fake release failure')


def until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.002)
    raise AssertionError('Condition not reached')


class CaptureTests(unittest.TestCase):
    def test_one_reader_shared_copies_and_no_capture_on_consumption(self):
        cap = FakeCapture(block_after_first=True)
        source = SharedFrameCapture(cap, fps=100)
        source.start()
        try:
            self.assertTrue(cap.blocked.wait(1))
            first = source.get_latest()
            self.assertEqual(first.sequence, 1)
            first.frame.fill(200)
            for _ in range(30):
                current = source.get_latest()
                self.assertTrue(np.all(current.frame == 1))
                self.assertEqual(current.sequence, 1)
            self.assertIsNone(source.get_latest(1))
            self.assertEqual(len(cap.calls), 2)
            self.assertEqual(len(set(cap.calls)), 1)
            self.assertNotEqual(cap.calls[0], threading.get_ident())
        finally:
            cap.gate.set(); source.close()
        self.assertEqual(len(cap.releases), 1)
        self.assertEqual(cap.releases[0], cap.calls[0])
        self.assertIsNone(source.get_latest())
        self.assertEqual(source.get_status()['state'], 'STOPPED')

    def test_freshness_expires_while_capture_is_blocked(self):
        clock = [0.0]
        cap = FakeCapture(block_after_first=True)
        source = SharedFrameCapture(cap, fps=100, clock=lambda: clock[0])
        source.start()
        try:
            self.assertTrue(cap.blocked.wait(1)); self.assertIsNotNone(source.get_latest())
            clock[0] = 0.5
            self.assertIsNone(source.get_latest()); self.assertEqual(source.get_status()['state'], 'STALE')
        finally:
            cap.gate.set(); source.close()

    def test_failed_reads_clear_then_recover_without_reopening(self):
        cap = FakeCapture(); source = SharedFrameCapture(cap, fps=100)
        source.start()
        try:
            until(lambda: source.get_latest() is not None)
            cap.empty = True
            until(lambda: source.get_status()['state'] == 'WAITING')
            self.assertIsNone(source.get_latest())
            cap.empty = False
            until(lambda: source.get_latest() is not None)
        finally: source.close()
        self.assertEqual(len(cap.releases), 1)

    def test_invalid_frames_and_release_failures_are_visible(self):
        for kwargs in ({'invalid': True}, {'release_error': True}):
            with self.subTest(kwargs=kwargs):
                cap = FakeCapture(release_error=kwargs.get('release_error', False))
                if kwargs.get('invalid'): cap.read = lambda: (True, np.zeros((2, 2), dtype=np.uint8))
                source = SharedFrameCapture(cap, fps=100)
                source.start()
                if kwargs.get('invalid'): until(lambda: source.get_status()['state'] == 'ERROR')
                else: until(lambda: source.get_latest() is not None)
                with self.assertRaises(RuntimeError): source.close()
                self.assertEqual(source.get_status()['state'], 'ERROR')
                self.assertIsNone(source.get_latest()); self.assertEqual(len(cap.releases), 1)

    def test_blocked_read_timeout_never_releases_capture_concurrently(self):
        cap = FakeCapture(block_after_first=True); source = SharedFrameCapture(cap, fps=100)
        source.start()
        try:
            self.assertTrue(cap.blocked.wait(1))
            with self.assertRaisesRegex(RuntimeError, 'did not stop'): source.close(timeout=0.01)
            self.assertEqual(cap.releases, [])
            self.assertIsNone(source.get_latest())
        finally:
            cap.gate.set(); source._thread.join(2)
        self.assertEqual(len(cap.releases), 1)
        self.assertEqual(source.get_status()['state'], 'ERROR')
        with self.assertRaises(RuntimeError): source.close()

    def test_start_failure_and_close_before_start_release_exactly_once(self):
        cap = FakeCapture(); source = SharedFrameCapture(cap)
        with mock.patch('vision.frame_capture.threading.Thread', side_effect=RuntimeError('no thread')):
            with self.assertRaises(RuntimeError): source.start()
        with self.assertRaises(RuntimeError): source.close()
        self.assertEqual(len(cap.releases), 1)
        other = FakeCapture(); unused = SharedFrameCapture(other)
        unused.close(); unused.close(); self.assertEqual(len(other.releases), 1)
        with self.assertRaises(RuntimeError): unused.start()
        self.assertEqual(other.calls, [])

    def test_capture_validation_and_start_once(self):
        for timing in ({'fps': 0}, {'fps': float('inf')}, {'max_age': 0}):
            with self.assertRaises(ValueError): SharedFrameCapture(FakeCapture(), **timing)
        source = SharedFrameCapture(FakeCapture()); source.start()
        try:
            with self.assertRaises(RuntimeError): source.start()
        finally: source.close()


    def test_stop_during_frame_copy_cannot_overwrite_shutdown_error(self):
        entered, gate = threading.Event(), threading.Event()
        class SlowFrame:
            shape = (32, 48, 3)
            def copy(self):
                entered.set(); gate.wait(3)
                return np.zeros(self.shape, dtype=np.uint8)
        cap = FakeCapture(); cap.read = lambda: (True, SlowFrame())
        source = SharedFrameCapture(cap); source.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(RuntimeError): source.close(timeout=0.01)
        finally: gate.set(); source._thread.join(2)
        self.assertEqual(source.get_status()['state'], 'ERROR')
        self.assertEqual(source.get_status()['sequence'], 0)
        self.assertIsNone(source.get_latest()); self.assertEqual(len(cap.releases), 1)
        with self.assertRaises(RuntimeError): source.close()


    def test_copy_time_counts_toward_frame_freshness(self):
        clock, count = [0.0], [0]
        blocked, gate = threading.Event(), threading.Event()
        class SlowFrame:
            shape = (32, 48, 3)
            def copy(self):
                clock[0] += 0.6
                return np.zeros(self.shape, dtype=np.uint8)
        cap = FakeCapture()
        def read():
            count[0] += 1
            if count[0] == 1: return True, SlowFrame()
            blocked.set(); gate.wait(3)
            return False, None
        cap.read = read
        source = SharedFrameCapture(cap, clock=lambda: clock[0]); source.start()
        try:
            self.assertTrue(blocked.wait(1))
            self.assertEqual(source.get_status()['state'], 'STALE')
            self.assertIsNone(source.get_latest())
        finally: gate.set(); source.close()


    def test_transient_read_exception_retries_same_handle_and_clears_error_on_recovery(self):
        cap = FakeCapture(fail=True); source = SharedFrameCapture(cap, fps=100); source.start()
        try:
            until(lambda: source.get_status()['state'] == 'WAITING')
            self.assertIn('OSError', source.get_status()['read_error'])
            self.assertIsNone(source.get_latest()); self.assertEqual(cap.releases, [])
            cap.fail = False; until(lambda: source.get_latest() is not None)
            self.assertIsNone(source.get_status()['read_error']); self.assertIsNone(source.get_status()['error'])
        finally: source.close()
        self.assertEqual(len(cap.releases), 1); self.assertEqual(source.get_status()['state'], 'STOPPED')

    def test_interrupted_start_releases_an_unstarted_handle(self):
        cap = FakeCapture(); source = SharedFrameCapture(cap)
        with mock.patch('vision.frame_capture.threading.Thread.start', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): source.start()
        source.close(); self.assertEqual(len(cap.releases), 1)
        self.assertEqual(source.get_status()['state'], 'STOPPED')


    def test_interruption_after_thread_spawn_joins_before_capture_release(self):
        cap = FakeCapture(); source = SharedFrameCapture(cap)
        start = threading.Thread.start
        def interrupted(thread):
            start(thread)
            raise KeyboardInterrupt
        with mock.patch('vision.frame_capture.threading.Thread.start', new=interrupted):
            with self.assertRaises(KeyboardInterrupt): source.start()
        self.assertFalse(source._thread.is_alive()); self.assertEqual(len(cap.releases), 1)
        self.assertEqual(source.get_status()['state'], 'STOPPED'); source.close()
