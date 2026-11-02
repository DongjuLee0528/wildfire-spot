let nextSession = 0;

export class PointCloudMetrics {
    constructor(stage, { now = () => performance.now(), emit = value => console.info('POINT_CLOUD_METRICS', value) } = {}) {
        this.stage = stage;
        this.now = now;
        this.emit = emit;
        this.session = `${Date.now().toString(36)}-${(++nextSession).toString(36)}`;
        this.started = this.reported = now();
        this.frames = this.points = this.bytes = this.intervalCount = this.intervalSum = 0;
        this.idDiscontinuities = this.zeroTimestamps = 0;
        this.firstId = this.lastId = this.lastAt = null;
        this.intervalMin = this.intervalMax = this.pointMin = this.pointMax = null;
        this.finished = false;
    }
    record(frame) {
        const at = this.now();
        if (this.lastAt != null) {
            const interval = at - this.lastAt;
            this.intervalCount++;
            this.intervalSum += interval;
            this.intervalMin = this.intervalMin == null ? interval : Math.min(this.intervalMin, interval);
            this.intervalMax = this.intervalMax == null ? interval : Math.max(this.intervalMax, interval);
            if (((frame.cloudId - this.lastId) >>> 0) !== 1) this.idDiscontinuities++;
        } else this.firstId = frame.cloudId;
        this.frames++;
        this.points += frame.pointCount;
        this.bytes += frame.data.byteLength;
        this.pointMin = this.pointMin == null ? frame.pointCount : Math.min(this.pointMin, frame.pointCount);
        this.pointMax = this.pointMax == null ? frame.pointCount : Math.max(this.pointMax, frame.pointCount);
        if (frame.timestamp === 0) this.zeroTimestamps++;
        this.lastId = frame.cloudId;
        this.lastAt = at;
        if (at - this.reported >= 5000) this.report(false);
    }
    report(final) {
        const value = { stage: this.stage, session: this.session, final,
            elapsed_s: (this.now() - this.started) / 1000, frames: this.frames,
            points: this.points, bytes: this.bytes, first_id: this.firstId, last_id: this.lastId,
            id_discontinuities: this.idDiscontinuities, zero_timestamps: this.zeroTimestamps,
            points_min: this.pointMin, points_max: this.pointMax, interval_samples: this.intervalCount,
            interval_mean_ms: this.intervalCount ? this.intervalSum / this.intervalCount : null,
            interval_min_ms: this.intervalMin, interval_max_ms: this.intervalMax };
        try { this.emit(value); }
        catch { console.warn('Point-cloud metrics output failed'); }
        this.reported = this.now();
    }
    finish() {
        if (!this.finished) { this.finished = true; this.report(true); }
    }
}
