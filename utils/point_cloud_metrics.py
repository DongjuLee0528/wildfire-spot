import json
import logging
import struct
import sys
import time
import uuid


logger = logging.getLogger(__name__)


def emit_line(value, *, flush=False):
    sys.stdout.write(value + '\n')
    if flush:
        sys.stdout.flush()


class PointCloudMetrics:
    def __init__(self, stage, *, clock=time.monotonic, emit=emit_line):
        self.stage = stage
        self.clock = clock
        self.emit = emit
        self.reset()

    def reset(self):
        self.session = uuid.uuid4().hex[:12]
        self.started = self.reported = self.clock()
        self.frames = self.points = self.bytes = 0
        self.first_id = self.last_id = self.last_at = None
        self.interval_count = self.interval_sum = 0
        self.interval_min = self.interval_max = None
        self.point_min = self.point_max = None
        self.id_discontinuities = self.zero_timestamps = 0
        self.finished = False

    def record(self, data):
        at = self.clock()
        _, _, _, count, stamp, cloud_id, _ = struct.unpack_from('<4sIIIdII', data)
        if self.last_at is not None and self.last_id is not None:
            interval = at - self.last_at
            self.interval_count += 1
            self.interval_sum += interval
            self.interval_min = interval if self.interval_min is None else min(self.interval_min, interval)
            self.interval_max = interval if self.interval_max is None else max(self.interval_max, interval)
            self.id_discontinuities += ((cloud_id - self.last_id) & 0xffffffff) != 1
        else:
            self.first_id = cloud_id
        self.frames += 1
        self.points += count
        self.bytes += len(data)
        self.point_min = count if self.point_min is None else min(self.point_min, count)
        self.point_max = count if self.point_max is None else max(self.point_max, count)
        self.zero_timestamps += stamp == 0
        self.last_id, self.last_at = cloud_id, at
        if at - self.reported >= 5:
            self.report(False)

    def report(self, final):
        at = self.clock()
        value = dict(stage=self.stage, session=self.session, final=final,
                     elapsed_s=round(at - self.started, 3), frames=self.frames,
                     points=self.points, bytes=self.bytes, first_id=self.first_id,
                     last_id=self.last_id, id_discontinuities=self.id_discontinuities,
                     zero_timestamps=self.zero_timestamps,
                     points_min=self.point_min, points_max=self.point_max,
                     interval_samples=self.interval_count,
                     interval_mean_ms=round(self.interval_sum * 1000 / self.interval_count, 3) if self.interval_count else None,
                     interval_min_ms=round(self.interval_min * 1000, 3) if self.interval_min is not None else None,
                     interval_max_ms=round(self.interval_max * 1000, 3) if self.interval_max is not None else None)
        try:
            self.emit('POINT_CLOUD_METRICS ' + json.dumps(value, separators=(',', ':')), flush=True)
        except Exception as error:
            logger.warning('Point-cloud metrics output failed (%s)', type(error).__name__)
        self.reported = at

    def finish(self):
        if not self.finished:
            self.finished = True
            self.report(True)
