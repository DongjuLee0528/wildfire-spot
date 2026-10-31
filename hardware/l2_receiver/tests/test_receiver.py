import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sdk = os.environ.get('UNITREE_LIDAR_SDK_ROOT')
        if not sdk:
            raise RuntimeError('Set UNITREE_LIDAR_SDK_ROOT to the pinned official SDK directory')
        cls.temp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temp.name) / 'l2_receiver_test'
        compiler = os.environ.get('CXX') or shutil.which('c++')
        subprocess.run([
            compiler, '-std=c++17', '-Wall', '-Wextra', '-Wpedantic', '-pthread',
            '-isystem', str(Path(sdk) / 'include'), str(ROOT / 'main.cpp'),
            str(ROOT / 'tests/fake_sdk.cpp'), '-o', str(cls.binary),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def start(self, scenario='normal', **kwargs):
        env = dict(os.environ, L2_TEST_SCENARIO=scenario)
        return subprocess.Popen([str(self.binary)], env=env, stderr=subprocess.PIPE, **kwargs)

    def test_range_filter_wire_format_and_sigterm(self):
        process = self.start(stdout=subprocess.PIPE)
        try:
            header = process.stdout.read(32)
            magic, version, size, count, stamp, sequence, rings = struct.unpack('<4sIIIdII', header)
            self.assertEqual((magic, version, size, count, stamp, sequence, rings),
                             (b'L2PC', 1, 48, 4, 1234.5, 42, 18))
            xyz = struct.unpack('<12f', process.stdout.read(size))
            self.assertEqual(xyz, (1, 2, 3, 30, 0, 0, -30, 0, 0, 0, 0, -5))
            process.send_signal(signal.SIGTERM)
            _, error = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, error)
            self.assertIn(b'SDK log on stdout', error)
            self.assertIn(b'FAKE_UDP_CLOSED', error)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_no_data_timeout(self):
        process = self.start('idle', stdout=subprocess.PIPE)
        output, error = process.communicate(timeout=8)
        self.assertEqual(output, b'')
        self.assertEqual(process.returncode, 1)
        self.assertIn(b'No complete 3D cloud', error)
        self.assertIn(b'FAKE_UDP_CLOSED', error)

    def test_invalid_clouds_and_initialization_failures(self):
        for scenario, message in [('oversize', b'frame limit'), ('invalid_stamp', b'timestamp'),
                                  ('init_failure', b'initialization failed'), ('null_reader', b'create a reader')]:
            with self.subTest(scenario=scenario):
                process = self.start(scenario, stdout=subprocess.PIPE)
                output, error = process.communicate(timeout=3)
                self.assertEqual(output, b'')
                self.assertEqual(process.returncode, 1)
                self.assertIn(message, error)
                if scenario in ('oversize', 'invalid_stamp'):
                    self.assertIn(b'FAKE_UDP_CLOSED', error)

    def test_empty_cloud_is_valid_and_sigint_closes(self):
        process = self.start('empty', stdout=subprocess.PIPE)
        header = process.stdout.read(32)
        self.assertEqual(struct.unpack('<4sIIIdII', header)[2:4], (0, 0))
        process.send_signal(signal.SIGINT)
        _, error = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 0, error)
        self.assertIn(b'FAKE_UDP_CLOSED', error)

    def test_disconnected_consumer(self):
        process = self.start(stdout=subprocess.PIPE)
        process.stdout.close()
        _, error = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 1)
        self.assertIn(b'output consumer disconnected', error)
        self.assertIn(b'FAKE_UDP_CLOSED', error)

    def test_stalled_consumer_has_bounded_exit(self):
        process = self.start(stdout=subprocess.PIPE)
        try:
            process.wait(timeout=8)
            error = process.stderr.read()
            self.assertEqual(process.returncode, 1)
            self.assertIn(b'output blocked', error)
            self.assertIn(b'FAKE_UDP_CLOSED', error)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def test_shutdown_cleanup_failures_are_reported(self):
        for scenario, message in [('close_std', b'SDK closeUDP exception: Injected cleanup failure'),
                                  ('close_unknown', b'Unknown SDK closeUDP exception'),
                                  ('close_false', b'SDK closeUDP failed')]:
            with self.subTest(scenario=scenario):
                process = self.start(scenario, stdout=subprocess.PIPE)
                try:
                    self.assertEqual(process.stdout.read(4), b'L2PC')
                    process.send_signal(signal.SIGTERM)
                    _, error = process.communicate(timeout=3)
                    self.assertEqual(process.returncode, 1, error)
                    self.assertIn(message, error)
                    self.assertEqual(error.count(b'FAKE_UDP_CLOSE_ATTEMPT'), 1)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_runtime_exceptions_still_attempt_cleanup_once(self):
        scenarios = [('run_std', b'Injected parse failure', None),
                     ('run_unknown', b'Unknown SDK/runtime exception', None),
                     ('run_std_close_unknown', b'Injected parse failure', b'Unknown SDK closeUDP exception'),
                     ('run_unknown_close_std', b'Unknown SDK/runtime exception', b'Injected cleanup failure')]
        for scenario, primary, cleanup in scenarios:
            with self.subTest(scenario=scenario):
                process = self.start(scenario, stdout=subprocess.PIPE)
                output, error = process.communicate(timeout=3)
                self.assertEqual(output, b'')
                self.assertEqual(process.returncode, 1, error)
                self.assertIn(primary, error)
                self.assertEqual(error.count(b'FAKE_UDP_CLOSE_ATTEMPT'), 1)
                if cleanup:
                    self.assertIn(cleanup, error)
                else:
                    self.assertIn(b'FAKE_UDP_CLOSED', error)

    def test_help_and_invalid_arguments_do_not_initialize_sdk(self):
        for args, code in [(['--help'], 0), (['bad', '192.168.1.62'], 2), (['extra'], 2)]:
            result = subprocess.run([str(self.binary), *args], capture_output=True, timeout=3)
            self.assertEqual(result.returncode, code)
            self.assertEqual(result.stdout, b'')
            self.assertNotIn(b'SDK log', result.stderr)


if __name__ == '__main__':
    unittest.main()
