import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RealSdkShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'linux':
            raise RuntimeError('Run only inside a network-isolated Linux container')
        active = {p.name for p in Path('/sys/class/net').iterdir()
                  if (p / 'flags').is_file() and int((p / 'flags').read_text(), 16) & 1}
        if active != {'lo'} or len(Path('/proc/net/route').read_text().splitlines()) != 1:
            raise RuntimeError('Require only active loopback and no external routes')
        cls.sdk = Path(os.environ['UNITREE_LIDAR_SDK_ROOT'])
        cls.arch = os.uname().machine
        cls.original = cls.sdk / 'lib' / cls.arch / 'libunilidar_sdk2.a'
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.build = cls.directory / 'build'
        subprocess.run(['cmake', '-S', str(ROOT), '-B', str(cls.build),
                        '-DCMAKE_BUILD_TYPE=Release', '-DUNITREE_LIDAR_SDK_ROOT=' + str(cls.sdk)], check=True)
        subprocess.run(['cmake', '--build', str(cls.build), '--parallel', '2'], check=True)
        cls.binary = cls.build / 'l2_receiver'

    def test_original_destructor_crashes_and_build_copy_destructor_returns(self):
        harness = self.directory / 'destructor.cpp'
        harness.write_text("""#include "udp_handler.h"
#include <sys/resource.h>
int main() {
    rlimit core{0, 0}; setrlimit(RLIMIT_CORE, &core);
    rlimit stack{1024 * 1024, 1024 * 1024}; setrlimit(RLIMIT_STACK, &stack);
    for (int i = 0; i < 1000; ++i) {
        UDPHandler local(0);
        UDPHandler* dynamic = new UDPHandler(0);
        delete dynamic;
    }
}
""")
        for name, library, expected in [('original', self.original, -signal.SIGSEGV),
                ('repaired', self.build / 'libunilidar_sdk2_shutdown_fixed.a', 0)]:
            with self.subTest(library=name):
                binary = self.directory / name
                subprocess.run(['g++', '-O2', '-I', str(self.sdk / 'include'), str(harness),
                                str(library), '-o', str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, expected, result.stderr)
        link = (self.build / 'CMakeFiles/l2_receiver.dir/link.txt').read_text()
        self.assertIn('libunilidar_sdk2_shutdown_fixed.a', link)
        self.assertNotIn(str(self.original), link)

    def stop_receiver(self, number):
        process = subprocess.Popen([str(self.binary), '127.0.0.1', '127.0.0.2'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            pending = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stderr, selectors.EVENT_READ)
                while b'L2 UDP initialized:' not in pending:
                    if not selector.select(5):
                        self.fail('Isolated SDK initialization did not complete')
                    chunk = os.read(process.stderr.fileno(), 4096)
                    self.assertTrue(chunk, pending.decode(errors='replace'))
                    pending.extend(chunk)
                    self.assertLess(len(pending), 8192)
            process.send_signal(number)
            output, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, bytes(pending) + error)
            self.assertEqual(output, b'')
            self.assertIn(b'SDK closeUDP complete', error)
            self.assertIn(('signal=' + str(number)).encode(), error)
        finally:
            if process.poll() is None:
                process.kill(); process.communicate()

    def test_real_sdk_receiver_sigterm_cleanup_without_sensor(self):
        self.stop_receiver(signal.SIGTERM)

    def test_real_sdk_receiver_sigint_cleanup_without_sensor(self):
        self.stop_receiver(signal.SIGINT)


if __name__ == '__main__':
    unittest.main()
