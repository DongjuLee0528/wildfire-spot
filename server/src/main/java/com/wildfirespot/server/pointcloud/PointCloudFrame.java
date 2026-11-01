package com.wildfirespot.server.pointcloud;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

final class PointCloudFrame {
    static final int MAX_BYTES = 144032;

    static void validate(byte[] data) {
        if (data.length < 32 || data.length > MAX_BYTES) throw new IllegalArgumentException("Invalid point-cloud size");
        ByteBuffer b = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
        if (b.get() != 'L' || b.get() != '2' || b.get() != 'P' || b.get() != 'C')
            throw new IllegalArgumentException("Invalid point-cloud magic");
        long version = Integer.toUnsignedLong(b.getInt());
        long size = Integer.toUnsignedLong(b.getInt());
        long count = Integer.toUnsignedLong(b.getInt());
        double stamp = b.getDouble();
        if (version != 1 || count > 12000 || size != count * 12L || data.length != 32L + size ||
                !Double.isFinite(stamp) || stamp < 0) throw new IllegalArgumentException("Invalid point-cloud header");
        b.position(32);
        for (long i = 0; i < count; i++) {
            double x = b.getFloat(), y = b.getFloat(), z = b.getFloat();
            double distance = x*x + y*y + z*z;
            if (!Double.isFinite(distance) || distance <= 0 || distance > 900)
                throw new IllegalArgumentException("Invalid point-cloud coordinates");
        }
    }
}
