import ast
import json
import math
import os
import signal
from pathlib import Path
import struct
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from hardware.point_cloud_manager import FrameDecoder, PointCloudManager
from robot.robot_runtime_context import RobotRuntimeContext


def frame(points=((1.0, 2.0, 3.0),), stamp=1234.5, cloud_id=7):
    payload = b''.join(struct.pack('<fff', *point) for point in points)
    return struct.pack('<4sIIIdII', b'L2PC', 1, len(payload), len(points), stamp, cloud_id, 18) + payload


class DecoderTests(unittest.TestCase):
    def test_split_coalesced_and_empty_frames(self):
        decoder = FrameDecoder()
        data = frame() + frame((), cloud_id=8)
        result = []
        for start in range(0, len(data), 3):
            result.extend(decoder.feed(data[start:start + 3]))
        decoder.finish()
        self.assertEqual([item.cloud_id for item in result], [7, 8])
        self.assertEqual(result[0].data, frame())
        self.assertEqual(result[1].point_count, 0)

    def test_invalid_headers_and_oversized_count(self):
        good = bytearray(frame())
        cases = []
        for offset, replacement in [(0, b'BAD!'), (4, struct.pack('<I', 2)),
                                    (8, struct.pack('<I', 24)), (12, struct.pack('<I', 12001))]:
            data = good.copy()
            data[offset:offset + 4] = replacement
            cases.append(data)
        cases += [frame(stamp=float('nan')), frame(stamp=-1)]
        for data in cases:
            with self.subTest(data=data[:32]):
                with self.assertRaises(ValueError):
                    list(FrameDecoder().feed(data))

    def test_invalid_coordinates_and_boundary(self):
        for point in [(0, 0, 0), (30.1, 0, 0), (20, 20, 20), (math.nan, 0, 0), (math.inf, 0, 0)]:
            with self.subTest(point=point):
                with self.assertRaises(ValueError):
                    list(FrameDecoder().feed(frame((point,))))
        self.assertEqual(list(FrameDecoder().feed(frame(((30, 0, 0),))))[0].point_count, 1)

    def test_partial_eof_and_chunk_limit(self):
        decoder = FrameDecoder()
        list(decoder.feed(frame()[:-1]))
        with self.assertRaisesRegex(ValueError, 'partial'):
            decoder.finish()
        with self.assertRaisesRegex(ValueError, 'chunk'):
            list(FrameDecoder().feed(b'x' * 65537))


_SCRIPT = '''
import os, signal, struct, time
from pathlib import Path
scenario = {scenario!r}
counter = Path({counter!r})
attempt = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(attempt))
payload = struct.pack('<fff', 1, 2, 3)
def emit(sequence):
    os.write(1, struct.pack('<4sIIIdII', b'L2PC', 1, 12, 1, 1234.5, sequence, 18) + payload)
if scenario == 'exit2':
    os.write(2, b'invalid configuration')
    raise SystemExit(2)
if scenario == 'fail' or (scenario == 'recover' and attempt < 3):
    os.write(2, b'injected receiver failure')
    raise SystemExit(1)
if scenario == 'partial':
    os.write(1, b'L2PC')
    raise SystemExit(1)
if scenario == 'invalid':
    os.write(1, b'X' * 32)
    time.sleep(10)
if scenario == 'ignore_term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if scenario in ('once', 'ignore_term'):
    emit(1)
    while True:
        time.sleep(0.01)
if scenario == 'idle':
    while True:
        time.sleep(0.01)
if scenario == 'stderr_flood':
    for _ in range(100):
        os.write(2, b'z' * 4096)
sequence = 0
while True:
    sequence += 1
    emit(sequence)
    time.sleep(0.01)
'''


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.counter = Path(self.temp.name) / 'attempts'

    def manager(self, scenario='normal', **options):
        script = Path(self.temp.name) / 'receiver'
        script.write_text('#!' + sys.executable + '\n' + _SCRIPT.format(
            scenario=scenario, counter=str(self.counter)))
        script.chmod(0o700)
        settings = dict(stale_after=0.15, frame_timeout=0.5, shutdown_timeout=0.15, restart_delays=())
        settings.update(options)
        manager = PointCloudManager(script, **settings)
        self.addCleanup(manager.close)
        return manager

    def until(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail('Timed out waiting for condition')

    def test_latest_only_and_idempotent_start_close(self):
        manager = self.manager()
        manager.start()
        self.until(lambda: manager.get_latest_frame() is not None)
        pid = manager.get_status()['pid']
        manager.start()
        self.assertEqual(manager.get_status()['pid'], pid)
        self.until(lambda: manager.get_latest_frame().cloud_id >= 5)
        self.assertEqual(manager.get_latest_frame().point_count, 1)
        manager.close()
        manager.close()
        self.assertEqual(manager.get_status()['state'], 'STOPPED')
        self.assertIsNone(manager.get_status()['pid'])
        self.assertIsNone(manager.get_latest_frame())
        self.assertEqual(self.counter.read_text(), '1')
        self.assertGreaterEqual(manager._metrics.frames, 5)
        self.assertEqual(manager._metrics.frames, manager._metrics.points)
        self.assertTrue(manager._metrics.finished)

    def test_stale_frame_not_exposed_then_timeout(self):
        manager = self.manager('once', frame_timeout=3)
        manager.start()
        self.until(lambda: manager.get_latest_frame() is not None)
        manager._frame_timeout = 0.5
        self.until(lambda: manager.get_status()['state'] == 'STALE')
        self.assertIsNone(manager.get_latest_frame())
        self.until(lambda: manager.get_status()['state'] == 'ERROR')
        self.assertIn('timeout', manager.get_status()['error'])
        self.until(lambda: manager.get_status()['pid'] is None)
        self.assertIsNone(manager.get_status()['pid'])

    def test_restart_budget_and_recovery(self):
        manager = self.manager('recover', restart_delays=(0.01, 0.02))
        manager.start()
        self.until(lambda: manager.get_latest_frame() is not None)
        self.assertEqual(manager.get_status()['restart_count'], 2)
        self.assertEqual(self.counter.read_text(), '3')
        self.assertIsNone(manager.get_status()['error'])

    def test_failures_and_partial_frames_have_bounded_retries(self):
        for scenario, message in [('fail', 'injected receiver failure'), ('partial', 'partial'),
                                  ('invalid', 'magic'), ('idle', 'timeout')]:
            with self.subTest(scenario=scenario):
                if self.counter.exists():
                    self.counter.unlink()
                manager = self.manager(scenario, restart_delays=(0.01,))
                manager.start()
                self.until(lambda: manager.get_status()['state'] == 'ERROR' and
                           manager.get_status()['restart_count'] == 1 and
                           manager.get_status()['pid'] is None)
                self.assertEqual(self.counter.read_text(), '2')
                self.assertIn(message, manager.get_status()['error'])
                self.assertIsNone(manager.get_latest_frame())
                manager.close()

    def test_restart_limit_is_five(self):
        manager = self.manager('fail', restart_delays=(0,) * 5)
        manager.start()
        self.until(lambda: manager.get_status()['state'] == 'ERROR' and
                   manager.get_status()['restart_count'] == 5 and manager.get_status()['pid'] is None)
        self.assertEqual(self.counter.read_text(), '6')

    def test_cleanup_drains_final_stderr_after_stdout_eof(self):
        manager = self.manager()
        process = mock.Mock()
        process.poll.return_value = 0
        process.stderr.fileno.return_value = 999
        tail = bytearray()
        with mock.patch('hardware.point_cloud_manager.os.set_blocking'), \
             mock.patch('hardware.point_cloud_manager.os.read', side_effect=[b'x' * 5000, b'final diagnostic', b'']):
            manager._cleanup(process, tail)
        self.assertEqual(len(tail), 4096)
        self.assertTrue(tail.endswith(b'final diagnostic'))
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_cleanup_error_keeps_primary_failure_and_prevents_restart(self):
        manager = self.manager('fail', restart_delays=(0.01,))
        cleanup = manager._cleanup
        def fail_cleanup(process, stderr_tail):
            cleanup(process, stderr_tail)
            raise RuntimeError('injected cleanup failure')
        with mock.patch.object(manager, '_cleanup', side_effect=fail_cleanup):
            manager.start()
            self.until(lambda: 'cleanup failed' in (manager.get_status()['error'] or ''))
            manager._thread.join(timeout=2)
        self.assertIn('stdout closed', manager.get_status()['error'])
        self.assertIn('injected cleanup failure', manager.get_status()['error'])
        self.assertEqual(self.counter.read_text(), '1')

    def test_configuration_exit_is_not_retried(self):
        manager = self.manager('exit2', frame_timeout=3, restart_delays=(0.01,))
        manager.start()
        self.until(lambda: manager.get_status()['state'] == 'ERROR' and manager.get_status()['pid'] is None)
        self.assertEqual(self.counter.read_text(), '1')
        self.assertEqual(manager.get_status()['restart_count'], 0)
        self.assertIn('invalid configuration', manager.get_status()['error'])

    def test_missing_binary_and_invalid_settings(self):
        manager = PointCloudManager(Path(self.temp.name) / 'missing')
        manager.start()
        self.assertEqual(manager.get_status()['state'], 'ERROR')
        self.assertIn('missing', manager.get_status()['error'])
        manager.close()
        for options in [dict(local_ip='invalid'), dict(stale_after=math.nan),
                        dict(frame_timeout=1), dict(restart_delays=(0,) * 6)]:
            with self.assertRaises(ValueError):
                PointCloudManager('/missing', **options)

    def test_exec_format_error_is_permanent(self):
        manager = self.manager()
        Path(manager._command[0]).write_text('not an executable format')
        manager.start()
        self.until(lambda: manager.get_status()['state'] == 'ERROR')
        self.assertEqual(manager.get_status()['restart_count'], 0)
        self.assertIsNone(manager.get_status()['pid'])

    def test_worker_start_failure_is_reported_and_close_remains_safe(self):
        manager = self.manager()
        with mock.patch('hardware.point_cloud_manager.threading.Thread') as thread_type:
            thread_type.return_value.start.side_effect = RuntimeError('cannot create thread')
            manager.start()
        self.assertEqual(manager.get_status()['state'], 'ERROR')
        self.assertIn('cannot create thread', manager.get_status()['error'])
        self.assertIsNone(manager.get_status()['pid'])
        manager.close()

    def test_stderr_is_drained_without_blocking_frames(self):
        manager = self.manager('stderr_flood')
        manager.start()
        self.until(lambda: manager.get_latest_frame() is not None)
        self.assertEqual(manager.get_status()['state'], 'STREAMING')

    def test_hung_receiver_is_killed_and_reaped(self):
        manager = self.manager('ignore_term')
        manager.start()
        self.until(lambda: manager.get_latest_frame() is not None)
        pid = manager.get_status()['pid']
        start = time.monotonic()
        manager.close()
        self.assertLess(time.monotonic() - start, 2)
        with self.assertRaises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
        self.assertIsNone(manager.get_status()['pid'])
        self.assertEqual(manager.get_status()['state'], 'STOPPED')
        self.assertEqual(manager.get_status()['last_exit_code'], -signal.SIGKILL)

    def test_requested_shutdown_preserves_crash_or_sdk_failure_after_reaping(self):
        for code in (-signal.SIGABRT, -signal.SIGSEGV, 1):
            with self.subTest(code=code):
                manager = PointCloudManager('/not-executed')
                process = mock.Mock(pid=123, returncode=code)
                process.poll.return_value = code
                process.wait.return_value = code
                def stop(_process, _tail):
                    manager._stop.set()
                def diagnostic(_process, tail):
                    tail.extend(b'SDK closeUDP begin')
                with mock.patch('hardware.point_cloud_manager.subprocess.Popen', return_value=process) as spawn, \
                     mock.patch.object(manager, '_consume', side_effect=stop), \
                     mock.patch.object(manager, '_drain_stderr', side_effect=diagnostic):
                    manager._run_receiver()
                self.assertEqual(manager.get_status()['state'], 'ERROR')
                self.assertIsNone(manager.get_status()['pid'])
                self.assertEqual(manager.get_status()['last_exit_code'], code)
                self.assertIn('SDK closeUDP begin', manager.get_status()['error'])
                self.assertIn('exit ' + str(code), manager.get_status()['error'])
                spawn.assert_called_once()
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, 'exit ' + str(code)):
                        manager.close()
                self.assertEqual(manager.get_status()['state'], 'ERROR')

    def test_requested_shutdown_cleanup_error_cannot_be_overwritten_by_close(self):
        manager = PointCloudManager('/not-executed')
        process = mock.Mock(pid=123, returncode=0)
        def stop(_process, _tail):
            manager._stop.set()
        def fail_cleanup(_process, _tail):
            manager._pid = None
            raise RuntimeError('injected shutdown cleanup error')
        with mock.patch('hardware.point_cloud_manager.subprocess.Popen', return_value=process), \
             mock.patch.object(manager, '_consume', side_effect=stop), \
             mock.patch.object(manager, '_cleanup', side_effect=fail_cleanup):
            manager._run_receiver()
        with self.assertRaisesRegex(RuntimeError, 'injected shutdown cleanup error'):
            manager.close()
        self.assertEqual(manager.get_status()['state'], 'ERROR')

    def test_explicit_new_start_resets_prior_shutdown_error_and_exit_code(self):
        manager = self.manager()
        manager._shutdown_error = 'previous SDK shutdown failed'
        manager._last_exit_code = -signal.SIGABRT
        manager._set_state('ERROR', manager._shutdown_error)
        manager.start()
        self.until(lambda: manager.get_latest_frame() is not None)
        self.assertEqual(manager.get_status()['state'], 'STREAMING')
        self.assertIsNone(manager.get_status()['error'])
        self.assertIsNone(manager.get_status()['last_exit_code'])
        self.assertIsNone(manager._shutdown_error)
        manager.close()
        self.assertEqual(manager.get_status()['state'], 'STOPPED')

    def test_exit_diagnostic_with_no_native_summary_reports_unknown_not_zero(self):
        manager = PointCloudManager('/not-executed')
        process = mock.Mock(pid=123, returncode=-signal.SIGKILL)
        with mock.patch('hardware.point_cloud_manager.emit_line') as output:
            manager._report_exit(process, bytearray(b'partial native output'))
        report = json.loads(output.call_args.args[0].split(' ', 1)[1])
        self.assertEqual(report['exit_code'], -signal.SIGKILL)
        self.assertIsNone(report['skipped_zero_timestamps'])
        self.assertIsNone(report['native_result'])

    def test_exit_summary_output_failure_does_not_prevent_descriptor_cleanup(self):
        manager = PointCloudManager('/not-executed')
        process = mock.Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        with mock.patch.object(manager, '_drain_stderr'), \
             mock.patch('hardware.point_cloud_manager.emit_line', side_effect=OSError('injected')), \
             mock.patch('hardware.point_cloud_manager.logger.warning') as warning:
            manager._cleanup(process, bytearray())
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()
        warning.assert_called_once()
        self.assertIsNone(manager.get_status()['pid'])
        self.assertEqual(manager.get_status()['last_exit_code'], 0)

    def test_close_interrupts_restart_wait(self):
        manager = self.manager('fail', restart_delays=(10,))
        manager.start()
        self.until(lambda: manager.get_status()['state'] == 'RESTARTING')
        start = time.monotonic()
        manager.close()
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(self.counter.read_text(), '1')


class MainCleanupTests(unittest.TestCase):
    def cleanup_body(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        finalizer = next(node for node in reversed(main.body) if isinstance(node, ast.Try) and node.finalbody)
        return compile(ast.fix_missing_locations(ast.Module(body=finalizer.finalbody, type_ignores=[])),
                       '<main cleanup only>', 'exec')

    def environment(self):
        env = dict.fromkeys(('point_cloud_uploader', 'fire_detection_stop_event', 'fire_detection_thread', 'camera_control_manager',
                             '_servo_manager', '_kb_controller', 'spring_telemetry', 'keyboard_input', 'camera_vision'))
        env.update(runtime=mock.Mock(), logger=mock.Mock())
        return env

    def test_upload_stop_is_first_but_network_join_is_after_hardware(self):
        env = self.environment()
        order = []
        env['point_cloud_uploader'] = mock.Mock()
        env['point_cloud_uploader'].request_stop.side_effect = lambda: order.append('upload-stop')
        def join_upload():
            order.append('upload-join')
            raise RuntimeError('upload cleanup failed')
        env['point_cloud_uploader'].close.side_effect = join_upload
        env['runtime'].point_cloud_manager.close.side_effect = lambda: order.append('receiver')
        env['camera_control_manager'] = mock.Mock()
        env['camera_control_manager'].close.side_effect = lambda: order.append('camera')
        exec(self.cleanup_body(), env)
        self.assertEqual(order, ['upload-stop', 'receiver', 'camera', 'upload-join'])
        env['logger'].log_error.assert_called_once_with('Main.point_cloud_upload_shutdown', 'upload cleanup failed')

    def test_upload_join_is_guaranteed_when_other_cleanup_raises(self):
        env = self.environment()
        env['point_cloud_uploader'] = mock.Mock()
        env['camera_control_manager'] = mock.Mock()
        env['camera_control_manager'].close.side_effect = RuntimeError('camera failure')
        with self.assertRaisesRegex(RuntimeError, 'camera failure'):
            exec(self.cleanup_body(), env)
        env['point_cloud_uploader'].request_stop.assert_called_once()
        env['point_cloud_uploader'].close.assert_called_once()
        env['logger'].close.assert_called_once()

    def test_point_cloud_stops_before_unrelated_cleanup_failure(self):
        env = self.environment()
        env['camera_control_manager'] = mock.Mock()
        env['camera_control_manager'].close.side_effect = RuntimeError('camera cleanup failed')
        with self.assertRaisesRegex(RuntimeError, 'camera cleanup failed'):
            exec(self.cleanup_body(), env)
        env['runtime'].point_cloud_manager.close.assert_called_once()

    def test_point_cloud_cleanup_error_does_not_skip_other_cleanup(self):
        env = self.environment()
        env['runtime'].point_cloud_manager.close.side_effect = RuntimeError('lidar cleanup failed')
        exec(self.cleanup_body(), env)
        env['logger'].log_error.assert_called_once_with('Main.point_cloud_shutdown', 'lidar cleanup failed')
        env['runtime'].close.assert_called_once()


class RuntimeTests(unittest.TestCase):
    def test_runtime_owns_manager_and_closes_it(self):
        config = types.ModuleType('utils.config')
        config.L2_POINT_CLOUD_ENABLED = True
        config.L2_RECEIVER_PATH = '/fake/receiver'
        config.LIDAR_ETHERNET_HOST_IP = '192.168.1.2'
        config.LIDAR_ETHERNET_LIDAR_IP = '192.168.1.62'
        with mock.patch.dict(sys.modules, {'utils.config': config}), \
             mock.patch('hardware.point_cloud_manager.PointCloudManager') as manager_type, \
             mock.patch.object(RobotRuntimeContext, '_init_state_machine'), \
             mock.patch.object(RobotRuntimeContext, '_init_gps'), \
             mock.patch.object(RobotRuntimeContext, '_init_sensors'), \
             mock.patch.object(RobotRuntimeContext, '_init_fire_detector'):
            runtime = RobotRuntimeContext()
            manager_type.return_value.start.assert_called_once()
            self.assertIs(runtime.point_cloud_manager, manager_type.return_value)
            runtime.close()
            manager_type.return_value.close.assert_called_once()

    def test_lidar_start_failure_does_not_abort_runtime(self):
        config = types.ModuleType('utils.config')
        config.L2_POINT_CLOUD_ENABLED = True
        config.L2_RECEIVER_PATH = '/fake/receiver'
        config.LIDAR_ETHERNET_HOST_IP = '192.168.1.2'
        config.LIDAR_ETHERNET_LIDAR_IP = '192.168.1.62'
        runtime = object.__new__(RobotRuntimeContext)
        runtime.point_cloud_manager = None
        with mock.patch.dict(sys.modules, {'utils.config': config}), \
             mock.patch('hardware.point_cloud_manager.PointCloudManager', side_effect=ValueError('bad config')):
            runtime._init_point_cloud()
        self.assertIsNone(runtime.point_cloud_manager)

    def test_disabled_runtime_does_not_construct_receiver(self):
        config = types.ModuleType('utils.config')
        config.L2_POINT_CLOUD_ENABLED = False
        config.L2_RECEIVER_PATH = '/fake/receiver'
        config.LIDAR_ETHERNET_HOST_IP = '192.168.1.2'
        config.LIDAR_ETHERNET_LIDAR_IP = '192.168.1.62'
        runtime = object.__new__(RobotRuntimeContext)
        runtime.point_cloud_manager = None
        with mock.patch.dict(sys.modules, {'utils.config': config}), \
             mock.patch('hardware.point_cloud_manager.PointCloudManager') as manager_type:
            with self.assertLogs('robot.robot_runtime_context', level='INFO') as logs:
                runtime._init_point_cloud()
        self.assertTrue(any('disabled' in line for line in logs.output))
        self.assertFalse(any('failed' in line for line in logs.output))
        manager_type.assert_not_called()


if __name__ == '__main__':
    unittest.main()
