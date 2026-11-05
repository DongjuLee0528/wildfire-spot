import asyncio
from datetime import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from robot import robot_api as api
from robot.robot_api_types import RobotStatusData, RobotGpsData, RobotSensorData, FlameStatus, RobotHealthData, RobotLogsData, RobotFireStatusData
from hardware.point_cloud_manager import PointCloudFrame
from tests.test_point_cloud_manager import frame
from tests import test_person_integration as integration


class LocalDashboardTests(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(api, name, value) for name, value in {
            '_local_dashboard_enabled': True, '_point_cloud_manager': None, '_collector': None,
            '_camera_vision': None, '_camera_control_manager': None,
            '_manual_control_manager': None, '_mode_control_manager': None,
        }.items()]
        for patch in self.patches: patch.start(); self.addCleanup(patch.stop)
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)

    def collector(self):
        collector = mock.Mock()
        collector.get_status.return_value = RobotStatusData('IDLE', 'MANUAL', True, datetime(2026, 1, 1))
        collector.get_gps.return_value = RobotGpsData(37.0, 127.0, True, datetime(2026, 1, 1))
        collector.get_sensors.return_value = RobotSensorData(24.5, 40, FlameStatus(False, True, False, False), 'UNAVAILABLE')
        collector.get_health.return_value = RobotHealthData(True, False, True, False, True)
        collector.get_logs.return_value = RobotLogsData([])
        collector.get_fire_status.return_value = RobotFireStatusData('SUSPECTED_FIRE', True, False, True, False, None, None)
        api._collector = collector
        return collector

    def test_new_endpoints_are_off_by_default_and_existing_status_contract_is_unchanged(self):
        self.collector(); api._local_dashboard_enabled = False
        for path in ('dashboard', 'point-cloud/status', 'point-cloud/stream'):
            self.assertEqual(self.client.get('/robot/' + path).status_code, 404)
        status = self.client.get('/robot/status').json()
        self.assertEqual(status['mode'], 'MANUAL')
        self.assertEqual(set(status), {'state', 'mode', 'robotConnected', 'lastUpdate'})

    def test_unavailable_data_never_becomes_zero_or_healthy_defaults(self):
        self.assertEqual(self.client.get('/robot/dashboard').status_code, 503)
        collector = self.collector()
        collector.get_sensors.return_value = None
        collector.get_gps.return_value = None
        collector.get_fire_status.return_value = None
        data = self.client.get('/robot/dashboard').json()
        self.assertIsNone(data['sensors']); self.assertIsNone(data['gps']); self.assertIsNone(data['fire'])
        self.assertIsNone(data['health']['sensor']); self.assertIsNone(data['health']['camera'])
        self.assertFalse(data['health']['lidar']); self.assertEqual(data['logs'], {'logs': []})

    def test_snapshot_maps_real_contracts_and_camera_is_independent_of_pan_tilt(self):
        self.collector()
        api._camera_vision = mock.Mock()
        api._camera_vision.is_camera_available.return_value = True
        api._camera_vision.get_latest_result.return_value = {'model_available': True, 'confidence': 0.85}
        api._point_cloud_manager = mock.Mock()
        api._point_cloud_manager.get_status.return_value = {'state': 'STREAMING', 'age_seconds': 0.03}
        result = self.client.get('/robot/dashboard')
        self.assertEqual(result.status_code, 200); data = result.json()
        self.assertEqual(data['sensors']['temperature'], 24.5)
        self.assertTrue(data['sensors']['flame']['frontRight'])
        self.assertTrue(data['cameraStreamAvailable']); self.assertFalse(data['camera']['available'])
        self.assertTrue(data['health']['camera']); self.assertTrue(data['health']['lidar'])
        self.assertEqual(data['fire']['state'], 'SUSPECTED_FIRE')
        api._point_cloud_manager.get_status.return_value = {'state': 'STALE', 'age_seconds': 3}
        self.assertFalse(self.client.get('/robot/dashboard').json()['health']['lidar'])

    def test_stream_unavailable_and_runtime_error_return_503_without_creating_receiver(self):
        self.assertEqual(self.client.get('/robot/point-cloud/stream').status_code, 503)
        api._point_cloud_manager = mock.Mock()
        api._point_cloud_manager.get_latest_frame.side_effect = RuntimeError('receiver failed')
        self.assertEqual(self.client.get('/robot/point-cloud/stream').status_code, 503)
        api._point_cloud_manager.start.assert_not_called()

    def test_stream_delivers_original_binary_skips_duplicates_and_ends_when_stale(self):
        first = PointCloudFrame(1234.5, 7, 18, 1, frame(cloud_id=7))
        second = PointCloudFrame(1234.5, 8, 18, 1, frame(cloud_id=8))
        api._point_cloud_manager = mock.Mock()
        api._point_cloud_manager.get_latest_frame.side_effect = [first, first, first, second, None]
        response = self.client.get('/robot/point-cloud/stream')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/octet-stream')
        self.assertEqual(response.content, first.data + second.data)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        api._point_cloud_manager.close.assert_not_called()

    def test_disconnected_viewer_does_not_close_shared_receiver(self):
        manager = mock.Mock()
        manager.get_latest_frame.return_value = PointCloudFrame(1234.5, 1, 18, 1, frame())
        api._point_cloud_manager = manager
        request = SimpleNamespace(is_disconnected=mock.AsyncMock(return_value=True))
        async def check():
            response = await api.get_point_cloud_stream(request)
            with self.assertRaises(StopAsyncIteration): await response.body_iterator.__anext__()
        asyncio.run(check()); manager.close.assert_not_called()

    def test_control_bodies_are_forwarded_to_existing_managers_only(self):
        api._manual_control_manager = mock.Mock()
        api._manual_control_manager.send_command.return_value = {'accepted': True, 'command': 'STOP'}
        api._mode_control_manager = mock.Mock()
        api._mode_control_manager.set_mode.return_value = {'accepted': True, 'mode': 'MANUAL'}
        api._camera_control_manager = mock.Mock()
        api._camera_control_manager.camera_pan_stop.return_value = {'accepted': True}
        self.assertTrue(self.client.post('/robot/control', json={'command': 'STOP'}).json()['accepted'])
        self.assertTrue(self.client.post('/robot/mode', json={'mode': 'MANUAL'}).json()['accepted'])
        self.assertTrue(self.client.post('/robot/camera/control', json={'command': 'CAMERA_STOP'}).json()['accepted'])
        api._manual_control_manager.send_command.assert_called_once_with('STOP')
        api._mode_control_manager.set_mode.assert_called_once_with('MANUAL')
        api._camera_control_manager.camera_pan_stop.assert_called_once()

    def test_local_main_disables_all_spring_startup_even_with_env_enabled(self):
        scope, modules, _, _, runtime, _ = integration.MainPersonLifecycleTests().environment()
        scope['SPRING_TELEMETRY_ENABLED'] = True
        modules['utils.config'] = SimpleNamespace(LOCAL_DASHBOARD_ENABLED=True)
        modules['robot.spring_api_client'] = SimpleNamespace(SpringApiClient=mock.Mock(side_effect=AssertionError('Spring used')))
        modules['robot.spring_telemetry'] = SimpleNamespace(SpringTelemetry=mock.Mock(side_effect=AssertionError('Spring used')))
        modules['robot.point_cloud_uploader'] = SimpleNamespace(start_point_cloud_uploader=mock.Mock())
        with mock.patch.dict('sys.modules', modules), mock.patch('builtins.print'):
            scope['main']()
        modules['robot.point_cloud_uploader'].start_point_cloud_uploader.assert_not_called()
        configured = scope['robot_api'].configure.call_args.kwargs
        self.assertTrue(configured['local_dashboard_enabled'])
        self.assertIs(configured['point_cloud_manager'], runtime.point_cloud_manager)


    def test_external_browser_origins_cannot_send_local_controls(self):
        api._manual_control_manager = mock.Mock()
        response = self.client.post('/robot/control', json={'command': 'FORWARD'}, headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(response.status_code, 403)
        api._manual_control_manager.send_command.assert_not_called()
        api._manual_control_manager.send_command.return_value = {'accepted': True, 'command': 'STOP'}
        response = self.client.post('/robot/control', json={'command': 'STOP'}, headers={'Origin': 'http://127.0.0.1:5173'})
        self.assertEqual(response.status_code, 200)


    def test_local_server_binds_loopback_even_if_old_nas_host_is_in_environment(self):
        for enabled, expected in ((True, '127.0.0.1'), (False, '192.168.0.179')):
            scope = integration.main_functions('_start_robot_api_server')
            uvicorn = SimpleNamespace(Config=mock.Mock(), Server=mock.Mock())
            scope.update(os=os, threading=SimpleNamespace(Thread=mock.Mock()), robot_api=api)
            with mock.patch.dict('sys.modules', {'uvicorn': uvicorn, 'utils.config': SimpleNamespace(LOCAL_DASHBOARD_ENABLED=enabled)}), \
                 mock.patch.dict(os.environ, {'ROBOT_API_HOST': '192.168.0.179', 'ROBOT_API_PORT': '8000'}), \
                 mock.patch('builtins.print'):
                scope['_start_robot_api_server'](mock.Mock())
            self.assertEqual(uvicorn.Config.call_args.kwargs['host'], expected)

    def test_launcher_overrides_nas_settings_without_executing_real_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir(); (root / '.venv/bin').mkdir(parents=True)
            launcher = root / 'scripts/start-local-robot.sh'
            launcher.write_text((Path(__file__).parents[1] / 'scripts/start-local-robot.sh').read_text())
            (root / '.env.robot').write_text('SPRING_TELEMETRY_ENABLED=true\nROBOT_API_HOST=192.168.0.179\nROBOT_API_PORT=9000\n')
            executable = root / '.venv/bin/python'
            executable.write_text('#!' + sys.executable + '\nimport os,json,sys\nprint(json.dumps({"args":sys.argv[1:],"local":os.environ["LOCAL_DASHBOARD_ENABLED"],"spring":os.environ["SPRING_TELEMETRY_ENABLED"],"host":os.environ["ROBOT_API_HOST"],"port":os.environ["ROBOT_API_PORT"]}))\n')
            executable.chmod(0o700)
            completed = subprocess.run(['bash', str(launcher)], capture_output=True, text=True, timeout=5, check=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result, {'args':['-u','main.py'], 'local':'true', 'spring':'false', 'host':'127.0.0.1', 'port':'8000'})
