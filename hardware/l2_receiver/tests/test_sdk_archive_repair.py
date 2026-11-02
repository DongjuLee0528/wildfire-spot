import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repair_sdk_shutdown import repair_archive


class ArchiveRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sdk = Path(os.environ['UNITREE_LIDAR_SDK_ROOT'])

    def source(self, arch):
        return self.sdk / 'lib' / arch / 'libunilidar_sdk2.a'

    def test_exact_pinned_repairs_preserve_archive_size_and_original(self):
        expected = {
            'aarch64': '3b24aef10d45460dae54b5f7a6848df8962cfa5eef543795398094d1f7bdb023',
            'x86_64': 'b840dad6811c41c57ef294993f2b938c20dfac1434741bc912f4828a2b805e23',
        }
        for arch, digest in expected.items():
            with self.subTest(arch=arch):
                source = self.source(arch)
                data = source.read_bytes()
                repaired = repair_archive(data, arch)
                self.assertEqual(len(repaired), len(data))
                self.assertEqual(sum(a != b for a, b in zip(data, repaired)), 1)
                self.assertEqual(hashlib.sha256(repaired).hexdigest(), digest)
                self.assertEqual(source.read_bytes(), data)

    def test_unknown_corrupt_truncated_or_wrong_architecture_is_rejected(self):
        data = self.source('aarch64').read_bytes()
        for invalid, arch in [(b'', 'aarch64'), (data[:-1], 'aarch64'),
                              (data[:-1] + bytes([data[-1] ^ 1]), 'aarch64'),
                              (data, 'x86_64'), (data, 'armv7')]:
            with self.subTest(arch=arch, length=len(invalid)):
                with self.assertRaises(ValueError):
                    repair_archive(invalid, arch)

    def test_cli_build_copy_is_deterministic_and_original_cannot_be_output(self):
        source = self.source('aarch64')
        original = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'fixed.a'
            command = [sys.executable, str(ROOT / 'repair_sdk_shutdown.py'), str(source), str(output), 'aarch64']
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(output.read_bytes(), repair_archive(original, 'aarch64'))
            subprocess.run(command, check=True, capture_output=True)
            result = subprocess.run(command[:3] + [str(source), 'aarch64'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Output must differ', result.stderr)
            self.assertEqual(source.read_bytes(), original)

    def test_cli_unknown_input_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'unknown.a', Path(directory) / 'fixed.a'
            source.write_bytes(b'not the pinned SDK')
            output.write_bytes(b'previous output')
            result = subprocess.run([sys.executable, str(ROOT / 'repair_sdk_shutdown.py'),
                                     str(source), str(output), 'aarch64'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'refusing repair', result.stderr)
            self.assertEqual(output.read_bytes(), b'previous output')


if __name__ == '__main__':
    unittest.main()
