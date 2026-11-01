import json
import struct
import unittest
from unittest import mock
from utils.point_cloud_metrics import PointCloudMetrics


def frame(cid, count=2, stamp=1):
    return struct.pack('<4sIIIdII', b'L2PC', 1, count * 12, count, stamp, cid, 18) + b'x' * (count * 12)


class MetricsTests(unittest.TestCase):
    def test_monotonic_counts_wrap_empty_frame_and_final_summary(self):
        at = [0]
        reports = []
        metrics = PointCloudMetrics('test', clock=lambda: at[0],
                                    emit=lambda line, **kw: reports.append(json.loads(line.split(' ', 1)[1])))
        metrics.record(frame(0xffffffff, stamp=0))
        at[0] = 0.1
        metrics.record(frame(0, count=0, stamp=1793545893))
        at[0] = 5
        metrics.record(frame(2, count=3))
        self.assertEqual(len(reports), 1)
        result = reports[0]
        self.assertEqual((result['frames'], result['points'], result['bytes']), (3, 5, 156))
        self.assertEqual(result['id_discontinuities'], 1)
        self.assertEqual(result['zero_timestamps'], 1)
        self.assertEqual(result['interval_mean_ms'], 2500)
        self.assertEqual((result['points_min'], result['points_max']), (0, 3))
        metrics.finish(); metrics.finish()
        self.assertEqual(len(reports), 2)
        self.assertTrue(reports[-1]['final'])
        metrics.reset(); metrics.finish()
        self.assertEqual(reports[-1]['frames'], 0)
        self.assertIsNone(reports[-1]['interval_mean_ms'])
        self.assertNotEqual(reports[-1]['session'], result['session'])

    def test_default_report_writes_a_complete_line_in_one_call(self):
        with mock.patch('utils.point_cloud_metrics.sys.stdout') as output:
            PointCloudMetrics('test').finish()
            output.write.assert_called_once()
            line = output.write.call_args.args[0]
            self.assertTrue(line.endswith('\n'))
            self.assertTrue(json.loads(line.split(' ', 1)[1])['final'])
            output.flush.assert_called_once()

    def test_failed_report_does_not_break_data_path(self):
        with mock.patch('utils.point_cloud_metrics.logger.warning') as warning:
            metrics = PointCloudMetrics('test', emit=mock.Mock(side_effect=OSError('injected')))
            metrics.finish()
            warning.assert_called_once()


if __name__ == '__main__':
    unittest.main()
