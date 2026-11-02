import os
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from hardware.point_cloud_manager import PointCloudManager


class PythonBridgeTests(unittest.TestCase):
    def test_cpp_frames_reach_python_and_child_is_reaped(self):
        sdk = os.environ.get('UNITREE_LIDAR_SDK_ROOT')
        if not sdk:
            self.fail('Set UNITREE_LIDAR_SDK_ROOT to the pinned official SDK directory')
        receiver = ROOT / 'hardware/l2_receiver'
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'l2_receiver_test'
            subprocess.run([
                os.environ.get('CXX') or shutil.which('c++'), '-std=c++17',
                '-Wall', '-Wextra', '-Wpedantic', '-pthread',
                '-isystem', str(Path(sdk) / 'include'), str(receiver / 'main.cpp'),
                str(receiver / 'tests/fake_sdk.cpp'), '-o', str(binary),
            ], check=True)
            manager = PointCloudManager(binary, restart_delays=())
            with mock.patch.dict(os.environ, {'L2_TEST_SCENARIO': 'normal'}):
                try:
                    manager.start()
                    deadline = time.monotonic() + 3
                    result = None
                    while time.monotonic() < deadline:
                        result = manager.get_latest_frame()
                        if result is not None:
                            break
                        time.sleep(0.01)
                    self.assertIsNotNone(result, manager.get_status())
                    self.assertEqual((result.cloud_id, result.point_count), (42, 4))
                    self.assertEqual(struct.unpack('<12f', result.data[32:]),
                                     (1, 2, 3, 30, 0, 0, -30, 0, 0, 0, 0, -5))
                    pid = manager.get_status()['pid']
                finally:
                    manager.close()
            self.assertEqual(manager.get_status()['state'], 'STOPPED')
            self.assertIsNone(manager.get_status()['pid'])
            with self.assertRaises(ChildProcessError):
                os.waitpid(pid, os.WNOHANG)


    def test_cpp_cleanup_failure_survives_requested_python_shutdown(self):
        sdk = os.environ.get('UNITREE_LIDAR_SDK_ROOT')
        if not sdk:
            self.fail('Set UNITREE_LIDAR_SDK_ROOT to the pinned official SDK directory')
        receiver = ROOT / 'hardware/l2_receiver'
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'l2_receiver_test'
            subprocess.run([
                os.environ.get('CXX') or shutil.which('c++'), '-std=c++17',
                '-Wall', '-Wextra', '-Wpedantic', '-pthread',
                '-isystem', str(Path(sdk) / 'include'), str(receiver / 'main.cpp'),
                str(receiver / 'tests/fake_sdk.cpp'), '-o', str(binary),
            ], check=True)
            manager = PointCloudManager(binary, restart_delays=())
            with mock.patch.dict(os.environ, {'L2_TEST_SCENARIO': 'close_false'}):
                try:
                    manager.start()
                    deadline = time.monotonic() + 3
                    while manager.get_latest_frame() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertIsNotNone(manager.get_latest_frame(), manager.get_status())
                    pid = manager.get_status()['pid']
                    with self.assertRaisesRegex(RuntimeError, 'SDK closeUDP failed'):
                        manager.close()
                    status = manager.get_status()
                    self.assertEqual(status['state'], 'ERROR')
                    self.assertEqual(status['last_exit_code'], 1)
                    self.assertIsNone(status['pid'])
                    self.assertIn('SDK closeUDP begin', status['error'])
                    self.assertNotIn('SDK closeUDP complete', status['error'])
                    with self.assertRaises(ChildProcessError):
                        os.waitpid(pid, os.WNOHANG)
                finally:
                    if manager.get_status()['pid'] is not None:
                        manager.close()


    def test_normal_exit_exports_initial_zero_skip_to_python_text_log(self):
        sdk = os.environ.get('UNITREE_LIDAR_SDK_ROOT')
        if not sdk:
            self.fail('Set UNITREE_LIDAR_SDK_ROOT to the pinned official SDK directory')
        receiver = ROOT / 'hardware/l2_receiver'
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'l2_receiver_test'
            subprocess.run([
                os.environ.get('CXX') or shutil.which('c++'), '-std=c++17',
                '-Wall', '-Wextra', '-Wpedantic', '-pthread',
                '-isystem', str(Path(sdk) / 'include'), str(receiver / 'main.cpp'),
                str(receiver / 'tests/fake_sdk.cpp'), '-o', str(binary),
            ], check=True)
            manager = PointCloudManager(binary, restart_delays=())
            with mock.patch.dict(os.environ, {'L2_TEST_SCENARIO': 'zero_then_valid'}), \
                 mock.patch('hardware.point_cloud_manager.emit_line') as output:
                try:
                    manager.start()
                    deadline = time.monotonic() + 3
                    while manager.get_latest_frame() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertIsNotNone(manager.get_latest_frame(), manager.get_status())
                    manager.close()
                    manager.close()
                    self.assertEqual(manager.get_status()['last_exit_code'], 0)
                    output.assert_called_once()
                    prefix, body = output.call_args.args[0].split(' ', 1)
                    report = json.loads(body)
                    self.assertEqual(prefix, 'L2_RECEIVER_EXIT')
                    self.assertEqual((report['exit_code'], report['native_result'], report['signal'],
                                      report['skipped_zero_timestamps']), (0, 0, 15, 1))
                finally:
                    if manager.get_status()['pid'] is not None:
                        manager.close()


if __name__ == '__main__':
    unittest.main()
