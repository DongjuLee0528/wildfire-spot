#include "frame.hpp"
#include "unitree_lidar_sdk.h"
#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <fcntl.h>
#include <poll.h>
#include <string>
#include <thread>
#include <unistd.h>

namespace {
volatile std::sig_atomic_t stopped = 0;
void on_signal(int) { stopped = 1; }
using Clock = std::chrono::steady_clock;

void install_signals() {
    struct sigaction action{};
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, nullptr) || sigaction(SIGTERM, &action, nullptr))
        throw std::runtime_error("Cannot install termination handlers");
    action.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &action, nullptr))
        throw std::runtime_error("Cannot ignore SIGPIPE");
}

void write_frame(int fd, const std::vector<std::uint8_t>& frame) {
    std::size_t offset = 0;
    const auto deadline = Clock::now() + std::chrono::seconds(2);
    while (offset < frame.size() && !stopped) {
        if (Clock::now() >= deadline)
            throw std::runtime_error("Point-cloud output blocked for 2 seconds");
        pollfd output{fd, POLLOUT, 0};
        const int ready = poll(&output, 1, 100);
        if (ready < 0) {
            if (errno == EINTR) continue;
            throw std::runtime_error("Cannot poll point-cloud output");
        }
        if (ready == 0) continue;
        if (output.revents & (POLLERR | POLLHUP | POLLNVAL))
            throw std::runtime_error("Point-cloud output consumer disconnected");
        const auto written = write(fd, frame.data() + offset, frame.size() - offset);
        if (written > 0) offset += static_cast<std::size_t>(written);
        else if (written < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        else throw std::runtime_error("Cannot write point-cloud frame");
    }
}

bool valid_ip(const char* text) {
    in_addr address{};
    return inet_pton(AF_INET, text, &address) == 1;
}
}

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        std::fprintf(stderr, "Usage: l2_receiver [LOCAL_IPV4 LIDAR_IPV4]\nDefaults: 192.168.1.2 192.168.1.62; binary frames on stdout\n");
        return 0;
    }
    if ((argc != 1 && argc != 3) ||
        (argc == 3 && (!valid_ip(argv[1]) || !valid_ip(argv[2])))) {
        std::fprintf(stderr, "Expected no arguments or two valid IPv4 addresses; see --help\n");
        return 2;
    }
    const char* local_ip = argc == 3 ? argv[1] : "192.168.1.2";
    const char* lidar_ip = argc == 3 ? argv[2] : "192.168.1.62";
    if (isatty(STDOUT_FILENO)) {
        std::fprintf(stderr, "Refusing binary output to a terminal; pipe or redirect stdout\n");
        return 2;
    }
    int output = -1;
    unilidar_sdk2::UnitreeLidarReader* reader = nullptr;
    bool initialized = false;
    int result = 0;
    try {
        install_signals();
        std::fflush(stdout);
        output = dup(STDOUT_FILENO);
        if (output < 0 || dup2(STDERR_FILENO, STDOUT_FILENO) < 0)
            throw std::runtime_error("Cannot separate SDK logs from binary output");
        const int flags = fcntl(output, F_GETFL);
        if (flags < 0 || fcntl(output, F_SETFL, flags | O_NONBLOCK) < 0)
            throw std::runtime_error("Cannot configure nonblocking frame output");
        reader = unilidar_sdk2::createUnitreeLidarReader();
        if (!reader) throw std::runtime_error("SDK did not create a reader");
        if (reader->initializeUDP(6101, lidar_ip, 6201, local_ip, 18, true, 0.0f,
                                  wildfire::range_max_m) != 0)
            throw std::runtime_error("L2 UDP initialization failed");
        initialized = true;
        std::fprintf(stderr, "L2 UDP initialized: %s:6101 -> %s:6201; max range 30m\n", lidar_ip, local_ip);
        auto last_cloud = Clock::now();
        unilidar_sdk2::PointCloudUnitree cloud;
        while (!stopped) {
            const int packet_type = reader->runParse();
            if (packet_type == LIDAR_POINT_DATA_PACKET_TYPE && reader->getPointCloud(cloud)) {
                const auto frame = wildfire::encode_frame(cloud);
                write_frame(output, frame);
                last_cloud = Clock::now();
            } else {
                if (Clock::now() - last_cloud > std::chrono::seconds(5))
                    throw std::runtime_error("No complete 3D cloud received for 5 seconds");
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
    } catch (const std::exception& error) {
        std::fprintf(stderr, "l2_receiver: %s\n", error.what());
        result = 1;
    } catch (...) {
        std::fprintf(stderr, "l2_receiver: Unknown SDK/runtime exception\n");
        result = 1;
    }
    if (initialized) {
        try {
            if (!reader->closeUDP()) {
                std::fprintf(stderr, "l2_receiver: SDK closeUDP failed\n");
                result = 1;
            }
        } catch (const std::exception& error) {
            std::fprintf(stderr, "l2_receiver: SDK closeUDP exception: %s\n", error.what());
            result = 1;
        } catch (...) {
            std::fprintf(stderr, "l2_receiver: Unknown SDK closeUDP exception\n");
            result = 1;
        }
    }
    if (output >= 0) close(output);
    return result;
}
