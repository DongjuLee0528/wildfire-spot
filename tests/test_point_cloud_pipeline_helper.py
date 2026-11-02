import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import os
import selectors
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'tests/point_cloud_pipeline.py'


class PipelineHelperFailureTests(unittest.TestCase):
    def setup_files(self, directory, compiler_body=''):
        directory = Path(directory)
        sdk = directory / 'sdk'
        (sdk / 'include').mkdir(parents=True)
        (sdk / 'include/unitree_lidar_sdk.h').write_text('')
        compiler = directory / 'compiler'
        compiler.write_text('#!' + sys.executable + '\n' + compiler_body)
        compiler.chmod(0o700)
        config = {'baseUrl': 'http://127.0.0.1:9', 'directory': str(directory),
                  'serial': 'unused-test-serial', 'key': 'unused-test-key'}
        return config, dict(os.environ, CXX=str(compiler), UNITREE_LIDAR_SDK_ROOT=str(sdk))

    def test_malformed_command_exits_nonzero(self):
        result = subprocess.run([sys.executable, str(HELPER)], input=b'{bad json}\n', capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(json.loads(line)['event'] == 'error' for line in result.stdout.splitlines()))

    def test_compiler_failure_preserves_bounded_diagnostic_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            config, env = self.setup_files(directory, 'import sys\nsys.stderr.write("A" * 4096 + "FINAL_DIAGNOSTIC")\nsys.exit(1)\n')
            process = subprocess.Popen([sys.executable, str(HELPER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                process.stdin.write(json.dumps(config).encode() + b'\n'); process.stdin.flush()
                reply = self.receive(process)
                process.wait(timeout=5)
                self.assertEqual(process.returncode, 1)
                self.assertEqual(reply['event'], 'error')
                self.assertIn('FINAL_DIAGNOSTIC', reply['message'])
                self.assertLess(len(reply['message']), 2200)
            finally:
                self.finish(process)

    def test_malformed_command_after_compile_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            config, env = self.setup_files(directory)
            driver = '''import sys, runpy, json, threading, subprocess, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
gate, error_seen = Path(sys.argv[3]), Path(sys.argv[4])
original_set, original_poll = threading.Event.set, subprocess.Popen.poll
armed = False
def observed_set(event):
    original_set(event)
    if isinstance(sys.exc_info()[1], json.JSONDecodeError) and threading.current_thread().name == 'pipeline-commands':
        error_seen.touch()
def gated_poll(process):
    global armed
    result = original_poll(process)
    if result == 0 and not armed:
        armed = True
        gate.touch()
        deadline = time.monotonic() + 5
        while not error_seen.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Reader-error synchronization failed')
            time.sleep(0.01)
    return result
threading.Event.set = observed_set
subprocess.Popen.poll = gated_poll
runpy.run_path(sys.argv[2], run_name='__main__')
'''
            gate, error_seen = Path(directory) / 'compiled', Path(directory) / 'reader-error'
            process = subprocess.Popen([sys.executable, '-c', driver, str(ROOT), str(HELPER), str(gate), str(error_seen)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                process.stdin.write(json.dumps(config).encode() + b'\n'); process.stdin.flush()
                deadline = time.monotonic() + 5
                while not gate.exists():
                    self.assertIsNone(process.poll(), 'Helper exited before compile gate')
                    self.assertLess(time.monotonic(), deadline, 'Compile gate timed out')
                    time.sleep(0.01)
                process.stdin.write(b'{bad json}\n'); process.stdin.flush()
                process.wait(timeout=5)
                self.assertTrue(error_seen.exists(), 'Reader error was not synchronized')
                output, diagnostic = process.stdout.read(), process.stderr.read()
                replies = [json.loads(line) for line in output.splitlines()]
                self.assertEqual(process.returncode, 1, (process.returncode, replies, diagnostic.decode()))
                self.assertTrue(any(reply['event'] == 'error' and 'JSONDecodeError' in reply['message'] for reply in replies), replies)
            finally:
                self.finish(process)

    def cleanup_failure_on_eof(self, failing):
        with tempfile.TemporaryDirectory() as directory:
            config, env = self.setup_files(directory)
            driver = '''import sys, runpy, json
from pathlib import Path
counts = {'manager': 0, 'uploader': 0}
def record(name):
    counts[name] += 1
    Path(sys.argv[4]).write_text(json.dumps(counts))
sys.path.insert(0, sys.argv[1])
import hardware.point_cloud_manager as managers
import robot.point_cloud_uploader as uploaders
class Manager:
    def __init__(self, *args, **kwargs): pass
    def start(self): pass
    def get_status(self): return {'state': 'STREAMING', 'pid': None, 'restart_count': 0}
    def close(self):
        record('manager')
        if sys.argv[3] == 'manager': raise RuntimeError('Injected manager close failure')
class Uploader:
    def __init__(self, *args, **kwargs): pass
    def start(self): pass
    def request_stop(self): pass
    def get_status(self): return {'state': 'STREAMING'}
    def close(self):
        record('uploader')
        if sys.argv[3] == 'uploader': raise RuntimeError('Injected uploader close failure')
managers.PointCloudManager = Manager
uploaders.PointCloudUploader = Uploader
runpy.run_path(sys.argv[2], run_name='__main__')
'''
            process = subprocess.Popen([sys.executable, '-c', driver, str(ROOT), str(HELPER), failing, str(Path(directory) / 'closes.json')],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                process.stdin.write(json.dumps(config).encode() + b'\n'); process.stdin.flush()
                self.assertEqual(self.receive(process)['event'], 'ready')
                process.stdin.close()
                process.wait(timeout=5)
                replies = [json.loads(line) for line in process.stdout.read().splitlines()]
                self.assertEqual(process.returncode, 1)
                self.assertTrue(any(reply['event'] == 'error' and reply['kind'] == 'CleanupFailed' for reply in replies), replies)
                self.assertFalse(any(reply['event'] == 'stopped' for reply in replies))
                self.assertEqual(json.loads((Path(directory) / 'closes.json').read_text()), {'manager': 1, 'uploader': 1})
            finally:
                self.finish(process)

    def test_manager_cleanup_failure_after_eof_is_not_success(self):
        self.cleanup_failure_on_eof('manager')

    def test_uploader_cleanup_failure_after_eof_is_not_success(self):
        self.cleanup_failure_on_eof('uploader')

    def test_real_workers_keep_periodic_and_final_metrics_out_of_json_stdout(self):
        receiver = """import os, struct, time
sequence = 0
while True:
    data = struct.pack('<4sIIIdIIfff', b'L2PC', 1, 12, 1, 1234.5, sequence, 18, 1, 2, 3)
    os.write(1, data)
    sequence += 1
    time.sleep(0.05)
"""
        compiler = "import sys\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index('-o')+1])\np.write_text(" + repr('#!' + sys.executable + '\n' + receiver) + ")\np.chmod(0o700)\n"

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body = b'{"accessToken":"fixture-only-token"}' if self.path == '/api/device-auth/login' else b''
                self.send_response(200 if body else 204)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config, env = self.setup_files(directory, compiler)
                config['baseUrl'] = 'http://127.0.0.1:' + str(server.server_port)
                process = subprocess.Popen([sys.executable, str(HELPER)], stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                try:
                    process.stdin.write(json.dumps(config).encode() + b'\n'); process.stdin.flush()
                    self.assertEqual(self.receive(process)['event'], 'ready')
                    time.sleep(5.3)
                    process.stdin.write(b'{"command":"status"}\n'); process.stdin.flush()
                    self.assertEqual(self.receive(process)['event'], 'status')
                    process.stdin.write(b'{"command":"stop"}\n'); process.stdin.flush()
                    self.assertEqual(self.receive(process)['event'], 'stopped')
                    process.wait(timeout=5)
                    self.assertEqual(process.returncode, 0)
                    self.assertEqual(process.stdout.read(), b'')
                    diagnostics = process.stderr.read().decode()
                    metrics = [json.loads(line.split(' ', 1)[1]) for line in diagnostics.splitlines()
                               if line.startswith('POINT_CLOUD_METRICS ')]
                    for stage in ('receiver_decoded', 'upload_accepted'):
                        entries = [v for v in metrics if v['stage'] == stage]
                        self.assertTrue(any(not v['final'] and v['frames'] > 0 for v in entries))
                        self.assertEqual(sum(v['final'] for v in entries), 1)
                finally:
                    self.finish(process)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def receive(self, process):
        pending = bytearray()
        end = time.monotonic() + 5
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < end:
                if not selector.select(max(0, end - time.monotonic())):
                    break
                chunk = os.read(process.stdout.fileno(), 4096)
                self.assertTrue(chunk, 'Helper ended before a reply')
                pending.extend(chunk)
                self.assertLessEqual(len(pending), 8192)
                if b'\n' in pending:
                    return json.loads(pending.partition(b'\n')[0])
        self.fail('Helper reply timed out')

    def finish(self, process):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()


if __name__ == '__main__':
    unittest.main()
