import json
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
from robot.point_cloud_uploader import PointCloudUploader, UploadProtocolError, start_point_cloud_uploader

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
        response = Response(204)
        session = Session([login(), response])
        uploader = self.uploader(session)
        self.assertEqual(uploader._deliver(session, SimpleNamespace(data=DATA)).data, DATA)
        self.assertTrue(response.consumed)
        self.assertFalse(session.calls[-1][1]['allow_redirects'])
        self.assertEqual(session.calls[-1][1]['data'], DATA)
        self.assertIn('Authorization', session.calls[-1][1]['headers'])

    def test_auth_refresh_uses_fresh_source_and_only_once(self):
        session = Session([login(), Response(401), login(), Response(204)])
        uploader = self.uploader(session)
        self.assertIsNotNone(uploader._deliver(session, SimpleNamespace(data=DATA)))
        self.assertEqual(len(session.calls), 4)
        session = Session([login(), Response(403), login(), Response(403)])
        uploader = self.uploader(session)
        with self.assertRaisesRegex(UploadProtocolError, 'after login'):
            uploader._deliver(session, SimpleNamespace(data=DATA))
        self.assertEqual(len(session.calls), 4)

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
        uploader.close()
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


if __name__ == '__main__': unittest.main()
