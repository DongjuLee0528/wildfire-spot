import json
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
