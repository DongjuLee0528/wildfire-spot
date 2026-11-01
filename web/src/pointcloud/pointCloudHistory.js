export const MAX_FRAME_POINTS = 12000;
export const MAX_HISTORY_FRAMES = 5;
export const MAX_HISTORY_POINTS = MAX_FRAME_POINTS * MAX_HISTORY_FRAMES;
export const HISTORY_WINDOW_MS = 500;

export class PointCloudHistory {
    constructor(now = () => performance.now()) {
        this.now = now;
        this.entries = [];
        this.lastIdentity = null;
    }

    clear() { this.entries = []; }

    push(frame) {
        if (!(frame.data instanceof Uint8Array) || !Number.isInteger(frame.pointCount) || frame.pointCount < 0 ||
            frame.pointCount > MAX_FRAME_POINTS || frame.data.byteLength !== 32 + frame.pointCount * 12 ||
            !Number.isInteger(frame.cloudId) || frame.cloudId < 0 || frame.cloudId > 0xffffffff ||
            !Number.isFinite(frame.timestamp) || frame.timestamp < 0)
            throw new Error('Invalid point-cloud history frame');
        const at = this.now();
        this.entries = this.entries.filter(entry => at - entry.at < HISTORY_WINDOW_MS);
        const identity = `${frame.cloudId}:${frame.timestamp}`;
        if (identity === this.lastIdentity || this.entries.some(entry => entry.identity === identity)) return;
        if (frame.pointCount === 0) this.clear();
        this.entries.push({ frame, at, identity });
        if (this.entries.length > MAX_HISTORY_FRAMES) this.entries.shift();
        this.lastIdentity = identity;
    }

    snapshot() {
        const at = this.now();
        this.entries = this.entries.filter(entry => at - entry.at < HISTORY_WINDOW_MS);
        const frames = this.entries.map(entry => entry.frame);
        return { frames, pointCount: frames.reduce((sum, frame) => sum + frame.pointCount, 0),
            latestPointCount: frames.at(-1)?.pointCount ?? 0,
            expiresAt: this.entries.length ? this.entries[0].at + HISTORY_WINDOW_MS : null };
    }
}
