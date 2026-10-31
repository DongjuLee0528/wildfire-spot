#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>

namespace wildfire {
constexpr float range_max_m = 30.0f;
constexpr std::size_t max_points = 12000;

inline void append_u32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
    for (unsigned shift = 0; shift < 32; shift += 8)
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
}

inline void append_float(std::vector<std::uint8_t>& bytes, float value) {
    static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
    std::uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    append_u32(bytes, bits);
}

inline void append_double(std::vector<std::uint8_t>& bytes, double value) {
    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559);
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    for (unsigned shift = 0; shift < 64; shift += 8)
        bytes.push_back(static_cast<std::uint8_t>(bits >> shift));
}

template<class Cloud>
std::vector<std::uint8_t> encode_frame(const Cloud& cloud) {
    if (!std::isfinite(cloud.stamp) || cloud.stamp < 0)
        throw std::runtime_error("Invalid point-cloud timestamp");
    if (cloud.points.size() > max_points)
        throw std::runtime_error("Point cloud exceeds 12000-point frame limit");
    std::vector<std::uint8_t> payload;
    payload.reserve(cloud.points.size() * 12);
    for (const auto& point : cloud.points) {
        const double x = point.x, y = point.y, z = point.z;
        const double distance2 = x*x + y*y + z*z;
        if (!std::isfinite(distance2) || distance2 <= 0 || distance2 > 900.0)
            continue;
        append_float(payload, point.x);
        append_float(payload, point.y);
        append_float(payload, point.z);
    }
    std::vector<std::uint8_t> frame{'L', '2', 'P', 'C'};
    frame.reserve(32 + payload.size());
    append_u32(frame, 1);
    append_u32(frame, static_cast<std::uint32_t>(payload.size()));
    append_u32(frame, static_cast<std::uint32_t>(payload.size() / 12));
    append_double(frame, cloud.stamp);
    append_u32(frame, cloud.id);
    append_u32(frame, cloud.ringNum);
    frame.insert(frame.end(), payload.begin(), payload.end());
    return frame;
}
}
