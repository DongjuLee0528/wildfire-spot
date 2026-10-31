#include "unitree_lidar_sdk.h"
#include <chrono>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>

namespace unilidar_sdk2 {
namespace {
std::string scenario() {
    const char* value = std::getenv("L2_TEST_SCENARIO");
    return value ? value : "normal";
}
class FakeReader final : public UnitreeLidarReader {
public:
    int initializeSerial(std::string, uint32_t, uint16_t, bool, float, float) override { throw std::runtime_error("Unexpected serial call"); }
    int initializeUDP(unsigned short lp, std::string li, unsigned short hp, std::string hi,
                      uint16_t scans, bool system, float low, float high) override {
        std::printf("SDK log on stdout\n");
        if (lp != 6101 || hp != 6201 || li.empty() || hi.empty() || scans != 18 || !system || low != 0 || high != 30)
            throw std::runtime_error("Unexpected UDP parameters");
        return scenario() == "init_failure" ? -1 : 0;
    }
    bool closeSerial() override { throw std::runtime_error("Unexpected serial close"); }
    bool closeUDP() override {
        std::fprintf(stderr, "FAKE_UDP_CLOSE_ATTEMPT\n");
        if (scenario().find("close_std") != std::string::npos)
            throw std::runtime_error("Injected cleanup failure");
        if (scenario().find("close_unknown") != std::string::npos) throw 7;
        if (scenario().find("close_false") != std::string::npos) return false;
        std::fprintf(stderr, "FAKE_UDP_CLOSED\n");
        return true;
    }
    int runParse() override {
        if (scenario().find("run_std") != std::string::npos)
            throw std::runtime_error("Injected parse failure");
        if (scenario().find("run_unknown") != std::string::npos) throw 9;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        return scenario() == "idle" ? 0 : LIDAR_POINT_DATA_PACKET_TYPE;
    }
    void clearBuffer() override {}
    const LidarPointDataPacket& getLidarPointDataPacket() const override { throw std::runtime_error("Unexpected packet access"); }
    const Lidar2DPointDataPacket& getLidar2DPointDataPacket() const override { throw std::runtime_error("Unexpected packet access"); }
    const LidarImuDataPacket& getLidarImuDataPacket() const override { throw std::runtime_error("Unexpected IMU access"); }
    const LidarVersionDataPacket& getLidarVersionDataPacket() const override { throw std::runtime_error("Unexpected version access"); }
    bool getPointCloud(PointCloudUnitree& cloud) const override {
        cloud.stamp = 1234.5;
        cloud.id = 42;
        cloud.ringNum = 18;
        cloud.points = {
            {1, 2, 3, 0, 0, 1}, {30, 0, 0, 0, 0, 1}, {-30, 0, 0, 0, 0, 1},
            {30.01f, 0, 0, 0, 0, 1}, {0, 0, 0, 0, 0, 1},
            {std::numeric_limits<float>::quiet_NaN(), 0, 0, 0, 0, 1},
            {0, std::numeric_limits<float>::infinity(), 0, 0, 0, 1},
            {20, 20, 20, 0, 0, 1}, {0, 0, -5, 0, 0, 1}
        };
        if (scenario() == "oversize") cloud.points.resize(12001);
        if (scenario() == "invalid_stamp") cloud.stamp = std::numeric_limits<double>::infinity();
        if (scenario() == "empty") cloud.points.clear();
        return true;
    }
    bool getImuData(LidarImuData&) const override { return false; }
    bool getVersionOfSDK(std::string&) const override { return false; }
    bool getVersionOfLidarFirmware(std::string&) const override { return false; }
    bool getVersionOfLidarHardware(std::string&) const override { return false; }
    bool getTimeDelay(double&) const override { return false; }
    bool getDirtyPercentage(float&) const override { return false; }
    void sendUserCtrlCmd(LidarUserCtrlCmd) override { throw std::runtime_error("Unexpected control command"); }
    void setLidarWorkMode(uint32_t) override { throw std::runtime_error("Unexpected mode change"); }
    void syncLidarTimeStamp() override { throw std::runtime_error("Unexpected timestamp change"); }
    void resetLidar() override { throw std::runtime_error("Unexpected reset"); }
    void stopLidarRotation() override { throw std::runtime_error("Unexpected rotation stop"); }
    void startLidarRotation() override { throw std::runtime_error("Unexpected rotation start"); }
    void setLidarIpAddressConfig(LidarIpAddressConfig) override { throw std::runtime_error("Unexpected IP change"); }
    void setLidarMacAddressConfig(LidarMacAddressConfig) override { throw std::runtime_error("Unexpected MAC change"); }
    size_t getBufferCachedSize() const override { return 0; }
    size_t getBufferReadSize() const override { return 0; }
};
}
UnitreeLidarReader* createUnitreeLidarReader() {
    static FakeReader reader;
    return scenario() == "null_reader" ? nullptr : &reader;
}
}
