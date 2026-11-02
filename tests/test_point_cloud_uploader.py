import json
import struct
from pathlib import Path
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

import requests
from hardware.point_cloud_manager import FrameDecoder
from robot.point_cloud_uploader import PointCloudUploader, UploadProtocolError, UploadUnavailable, start_point_cloud_uploader

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/point_cloud_v1.json').read_text())
DATA = bytes.fromhex(FIXTURES[0]['hex'])


class Response:
    def __init__(self, status, body=b''):
        self.status_code = status
        self.body = body
        self.closed = False
        self.consumed = False
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), chunk_size): yield self.body[offset:offset+chunk_size]
    @property
    def content(self): self.consumed = True; return self.body


class Session:
    def __init__(self, outcomes): self.outcomes = list(outcomes); self.calls = []; self.closed = False
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.outcomes.pop(0)
        if isinstance(result, Exception): raise result
        return result
    def close(self): self.closed = True


def login(): return Response(200, b'{"accessToken":"test-token"}')


class UploaderTests(unittest.TestCase):
    def source(self): return SimpleNamespace(get_latest_frame=lambda: SimpleNamespace(data=DATA))
    def uploader(self, session, **kwargs):
        uploader = PointCloudUploader(self.source(), 'test-device', 'test-only-key', 'http://example.invalid',
                                     session_factory=lambda: session, retry_delays=(0.001,), degraded_delay=0.01,
                                     jitter=lambda: 0, **kwargs)
        self.addCleanup(uploader.close)
        return uploader
    def until(self, predicate):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            if predicate(): return
            time.sleep(0.005)
        self.fail('condition not reached')

    def test_common_wire_fixtures(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture['name']):
                decoder = FrameDecoder()
                if fixture['valid']:
                    self.assertEqual(len(list(decoder.feed(bytes.fromhex(fixture['hex'])))), 1)
                    decoder.finish()
                else:
                    with self.assertRaises(ValueError):
                        list(decoder.feed(bytes.fromhex(fixture['hex'])))
                        decoder.finish()

    def test_no_source_or_disabled_does_not_start(self):
        with mock.patch('robot.point_cloud_uploader.PointCloudUploader') as cls:
            self.assertIsNone(start_point_cloud_uploader(None, True, 'sn', 'key', 'http://example.invalid'))
            self.assertIsNone(start_point_cloud_uploader(self.source(), False, 'sn', 'key', 'http://example.invalid'))
            cls.assert_not_called()
            obj = start_point_cloud_uploader(self.source(), True, 'sn', 'key', 'http://example.invalid')
            obj.start.assert_called_once()
        self.assertIsNone(start_point_cloud_uploader(self.source(), True, '', '', 'http://example.invalid'))

    def test_success_is_204_and_redirect_is_terminal(self):
        for status in (200, 201, 301, 400, 404, 405, 406, 413, 415):
            with self.subTest(status=status):
                session = Session([login(), Response(status)])
                uploader = self.uploader(session)
                with self.assertRaises(UploadProtocolError): uploader._deliver(session, SimpleNamespace(data=DATA))
                self.assertEqual(uploader._metrics.frames, 0)
        response = Response(204)
        session = Session([login(), response])
        uploader = self.uploader(session)
        self.assertEqual(uploader._deliver(session, SimpleNamespace(data=DATA)).data, DATA)
        self.assertEqual(uploader._metrics.frames, 1)
        self.assertEqual(uploader._metrics.bytes, len(DATA))
        self.assertTrue(response.consumed)
        self.assertFalse(session.calls[-1][1]['allow_redirects'])
        self.assertEqual(session.calls[-1][1]['data'], DATA)
        self.assertIn('Authorization', session.calls[-1][1]['headers'])

    def test_auth_refresh_uses_fresh_source_and_only_once(self):
        session = Session([login(), Response(401), login(), Response(204)])
        uploader = self.uploader(session)
        fresh_data = bytearray(DATA)
        fresh_data.extend(struct.pack('<fff', 1, 2, 3))
        struct.pack_into('<I', fresh_data, 8, len(fresh_data) - 32)
        struct.pack_into('<I', fresh_data, 12, (len(fresh_data) - 32) // 12)
        struct.pack_into('<I', fresh_data, 24, 99)
        original, fresh = SimpleNamespace(data=DATA), SimpleNamespace(data=bytes(fresh_data))
        uploader._manager = SimpleNamespace(get_latest_frame=mock.Mock(side_effect=[original, fresh]))
        self.assertIs(uploader._deliver(session, original), fresh)
        self.assertEqual(len(session.calls), 4)
        self.assertEqual(session.calls[1][1]['data'], DATA)
        self.assertEqual(session.calls[3][1]['data'], fresh.data)
        self.assertEqual(uploader._metrics.frames, 1)
        self.assertEqual(uploader._metrics.bytes, len(fresh.data))
        self.assertEqual(uploader._metrics.points, (len(fresh.data) - 32) // 12)
        self.assertEqual(uploader._metrics.last_id, 99)
        session = Session([login(), Response(403), login(), Response(403)])
        uploader = self.uploader(session)
        with self.assertRaisesRegex(UploadProtocolError, 'after login'):
            uploader._deliver(session, SimpleNamespace(data=DATA))
        self.assertEqual(len(session.calls), 4)
        self.assertEqual(uploader._metrics.frames, 0)

    def test_metrics_ignore_failed_uploads_and_204_with_body(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                session = Session([login(), Response(status)])
                uploader = self.uploader(session)
                with self.assertRaises(UploadUnavailable):
                    uploader._deliver(session, SimpleNamespace(data=DATA))
                self.assertEqual((uploader._metrics.frames, uploader._metrics.points, uploader._metrics.bytes), (0, 0, 0))
        session = Session([login(), Response(204, b'unexpected')])
        uploader = self.uploader(session)
        with self.assertRaises(UploadProtocolError):
            uploader._deliver(session, SimpleNamespace(data=DATA))
        self.assertEqual((uploader._metrics.frames, uploader._metrics.points, uploader._metrics.bytes), (0, 0, 0))

    def test_malformed_or_oversized_login_is_terminal(self):
        for body in [b'not json', b'[]', b'{}', b'{"accessToken":4}', b'x'*8193]:
            session = Session([Response(200, body)])
            uploader = self.uploader(session)
            with self.assertRaises(UploadProtocolError): uploader._deliver(session, SimpleNamespace(data=DATA))

    def test_freshness_rechecked_after_login(self):
        session = Session([login()])
        uploader = self.uploader(session)
        uploader._manager = SimpleNamespace(get_latest_frame=lambda: None)
        self.assertIsNone(uploader._deliver(session, SimpleNamespace(data=DATA)))
        self.assertEqual(len(session.calls), 1)

    def test_degraded_retry_recovers_without_restarting_receiver(self):
        session = Session([Response(403), Response(503), login(), Response(204)])
        uploader = self.uploader(session)
        frame = SimpleNamespace(data=DATA)
        uploader._manager = SimpleNamespace(get_latest_frame=lambda: frame)
        uploader.start()
        self.until(lambda: uploader.get_status()['state'] == 'STREAMING')
        self.assertEqual(uploader.get_status()['failures'], 0)
        self.assertEqual(uploader._metrics.frames, 1)
        self.assertEqual(uploader._metrics.bytes, len(DATA))
        uploader.close()
        self.assertTrue(uploader._metrics.finished)
        self.assertTrue(session.closed)

    def test_credentials_401_is_terminal_and_close_interrupts_wait(self):
        session = Session([Response(401)])
        uploader = self.uploader(session)
        uploader.start(); self.until(lambda: uploader.get_status()['state'] == 'ERROR')
        self.assertEqual(len(session.calls), 1)
        session2 = Session([requests.ConnectionError('injected')])
        uploader2 = self.uploader(session2)
        uploader2._retry_delays = (30,)
        uploader2.start(); self.until(lambda: uploader2.get_status()['state'] == 'RETRYING')
        start = time.monotonic(); uploader2.close()
        self.assertLess(time.monotonic() - start, 1)
        self.assertTrue(session2.closed)

    def test_latest_only_no_repeat_and_idempotent_start(self):
        session = Session([login(), Response(204)])
        uploader = self.uploader(session)
        fixed = SimpleNamespace(data=DATA)
        uploader._manager = SimpleNamespace(get_latest_frame=lambda: fixed)
        uploader.start(); uploader.start()
        self.until(lambda: uploader.get_status()['state'] == 'STREAMING')
        time.sleep(0.12)
        self.assertEqual(len(session.calls), 2)
        uploader.close(); uploader.close()

    def test_session_cleanup_on_unexpected_source_error(self):
        session = Session([])
        uploader = self.uploader(session)
        uploader._manager = SimpleNamespace(get_latest_frame=mock.Mock(side_effect=RuntimeError('injected')))
        uploader.start(); self.until(lambda: uploader.get_status()['state'] == 'ERROR')
        self.until(lambda: session.closed)

    def test_session_cleanup_failure_remains_error(self):
        session = Session([])
        session.close = mock.Mock(side_effect=RuntimeError('injected cleanup failure'))
        uploader = PointCloudUploader(self.source(), 'test', 'test-only', 'http://example.invalid', session_factory=lambda: session)
        uploader._manager = SimpleNamespace(get_latest_frame=mock.Mock(side_effect=RuntimeError('injected source failure')))
        uploader.start()
        uploader._thread.join(timeout=2)
        self.assertFalse(uploader._thread.is_alive())
        self.assertIn('cleanup failed', uploader.get_status()['error'])
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            uploader.close()
        self.assertEqual(uploader.get_status()['state'], 'ERROR')

    def test_real_http_204_reuses_connection(self):
        ports = []
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                ports.append(self.client_address[1])
                if self.path.endswith('/login'):
                    body = b'{"accessToken":"test-only-token"}'
                    self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
                else:
                    self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers()
            def log_message(self, *args): return
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            uploader = PointCloudUploader(self.source(), 'test', 'test-only', f'http://127.0.0.1:{server.server_port}')
            with requests.Session() as session:
                uploader._deliver(session, SimpleNamespace(data=DATA))
                uploader._deliver(session, SimpleNamespace(data=DATA))
            self.assertEqual(len(ports), 3)
            self.assertEqual(len(set(ports)), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


class VirtualStop:
    def __init__(self, clock, end=float('inf')):
        self.clock, self.end, self.stopped = clock, end, False
        self.on_wait = None
        self.waits = []
    def is_set(self): return self.stopped or self.clock[0] >= self.end
    def set(self): self.stopped = True
    def wait(self, delay):
        self.waits.append(delay)
        if self.on_wait: self.on_wait()
        self.clock[0] = min(self.end, self.clock[0] + max(0, delay))
        return self.is_set()


class ClockSource:
    def __init__(self, clock, period):
        self.clock, self.period, self.latest = clock, period, None
        self.available = True
        self.reads = 0
    def get_latest_frame(self):
        self.reads += 1
        if not self.available: return None
        sequence = int((self.clock[0] + 1e-9) / self.period)
        if self.latest is None or self.latest.cloud_id != sequence:
            payload = bytearray(DATA)
            struct.pack_into('<I', payload, 24, sequence)
            self.latest = SimpleNamespace(data=bytes(payload), cloud_id=sequence)
        return self.latest


class ClockSession:
    def __init__(self, clock, latency, statuses=None):
        self.clock, self.latency = clock, latency
        self.statuses = iter(statuses) if statuses else None
        self.posts = []
        self.closed = False
    def post(self, url, **kwargs):
        if url.endswith('/login'):
            self.clock[0] += 0.002
            return login()
        sequence = struct.unpack_from('<I', kwargs['data'], 24)[0]
        self.posts.append((self.clock[0], sequence))
        self.clock[0] += self.latency
        return Response(next(self.statuses) if self.statuses else 204)
    def close(self): self.closed = True


class RateLimitedClockSession(ClockSession):
    def __init__(self, clock, delays):
        super().__init__(clock, 0)
        self.delays = delays
        self.received_at = None
        self.rejected = 0
    def post(self, url, **kwargs):
        if url.endswith('/login'): return super().post(url, **kwargs)
        sequence = struct.unpack_from('<I', kwargs['data'], 24)[0]
        self.posts.append((self.clock[0], sequence))
        self.clock[0] += self.delays[(len(self.posts) - 1) % len(self.delays)]
        status = 204
        if self.received_at is not None and self.clock[0] - self.received_at < 0.05 - 1e-9:
            self.rejected += 1
            status = 429
        else:
            self.received_at = self.clock[0]
        self.clock[0] += 0.002
        return Response(status)


class UploadCadenceTests(unittest.TestCase):
    def setup_uploader(self, period=0.1093, latency=0.013, end=float('inf'), statuses=None):
        clock = [0.0]
        source = ClockSource(clock, period)
        session = ClockSession(clock, latency, statuses)
        uploader = PointCloudUploader(source, 'test', 'test-only', 'http://example.invalid',
                                     session_factory=lambda: session)
        event = VirtualStop(clock, end)
        uploader._stop = event
        return clock, source, session, uploader, event

    def test_steady_nine_hz_source_is_sent_without_post_completion_delay(self):
        clock, source, session, uploader, event = self.setup_uploader(end=30)
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            uploader._run()
        expected = int((30 - 1e-6) / source.period)
        self.assertEqual([sequence for _, sequence in session.posts], list(range(expected + 1)))
        self.assertTrue(all(b[0] - a[0] >= 0.1 - 1e-9 for a, b in zip(session.posts, session.posts[1:])))
        self.assertTrue(session.closed)
        self.assertEqual(uploader._metrics.frames, len(session.posts))

    def test_slow_requests_select_latest_with_server_guard_without_catchup_burst(self):
        clock, source, session, uploader, event = self.setup_uploader(period=0.02, latency=0.18, end=2)
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            uploader._run()
        for at, sequence in session.posts:
            self.assertEqual(sequence, int((at + 1e-9) / source.period))
        intervals = [b[0] - a[0] for a, b in zip(session.posts, session.posts[1:])]
        self.assertGreater(len(intervals), 5)
        for interval in intervals: self.assertAlmostEqual(interval, 0.23)
        self.assertEqual(len({sequence for _, sequence in session.posts}), len(session.posts))

    def test_fast_source_remains_capped_at_ten_posts_per_second(self):
        clock, source, session, uploader, event = self.setup_uploader(period=0.02, latency=0.013, end=2)
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            uploader._run()
        self.assertEqual(len(session.posts), 20)
        for a, b in zip(session.posts, session.posts[1:]):
            self.assertAlmostEqual(b[0] - a[0], 0.1)
        for at, sequence in session.posts:
            self.assertEqual(sequence, int((at + 1e-9) / source.period))

    def test_variable_upload_delays_respect_server_receive_spacing(self):
        for delays in ([0.005] * 9 + [0.06], [0.005] * 9 + [0.08], [0.09, 0.005]):
            with self.subTest(delays=delays):
                clock, source, _, uploader, event = self.setup_uploader(end=30)
                session = RateLimitedClockSession(clock, delays)
                uploader._session_factory = lambda: session
                with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
                    uploader._run()
                self.assertEqual(session.rejected, 0)
                self.assertEqual(uploader.get_status()['failures'], 0)
                self.assertEqual(uploader._metrics.frames, len(session.posts))
                self.assertGreater(len(session.posts), 190)
                for at, sequence in session.posts:
                    self.assertEqual(sequence, int((at + 1e-9) / source.period))

    def test_healthy_fast_source_remains_streaming_during_cadence_wait(self):
        clock, source, session, uploader, event = self.setup_uploader(period=0.02, end=1)
        states = []
        event.on_wait = lambda: states.append(uploader.get_status()['state'])
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            uploader._run()
        self.assertTrue(states)
        self.assertEqual(set(states), {'STREAMING'})

    def test_auth_refresh_posts_are_paced_and_reselect_after_wait(self):
        clock, source, session, uploader, event = self.setup_uploader(period=0.02, statuses=[401, 204])
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            result = uploader._deliver(session, None)
        self.assertEqual(len(session.posts), 2)
        self.assertGreaterEqual(session.posts[1][0] - session.posts[0][0], 0.1 - 1e-9)
        self.assertEqual(result.cloud_id, session.posts[-1][1])
        self.assertGreater(result.cloud_id, session.posts[0][1])
        self.assertEqual(uploader._metrics.frames, 1)
        self.assertEqual(uploader._metrics.last_id, result.cloud_id)

    def test_stop_during_cadence_wait_never_posts_or_reads_another_frame(self):
        clock, source, session, uploader, event = self.setup_uploader()
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            uploader._deliver(session, None)
            reads = source.reads
            event.on_wait = event.set
            self.assertIsNone(uploader._deliver(session, None))
        self.assertEqual(source.reads, reads)
        self.assertEqual(len(session.posts), 1)

    def test_source_stale_during_wait_does_not_send_previously_selected_frame(self):
        clock, source, session, uploader, event = self.setup_uploader()
        with mock.patch('robot.point_cloud_uploader.time.monotonic', side_effect=lambda: clock[0]):
            uploader._deliver(session, None)
            event.on_wait = lambda: setattr(source, 'available', False)
            self.assertIsNone(uploader._deliver(session, None))
        self.assertEqual(len(session.posts), 1)



if __name__ == '__main__': unittest.main()
