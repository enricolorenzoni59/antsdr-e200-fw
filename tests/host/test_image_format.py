import importlib.util
from pathlib import Path
import struct
import unittest
import zlib

path = Path(__file__).resolve().parents[2] / 'scripts/package/image-format.py'
spec = importlib.util.spec_from_file_location('ram_trial', path)
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)


def make_image(payload=b'test', kind=2):
    fields = (0x27051956, 0, 1234, len(payload), 0x8000, 0x8000,
              zlib.crc32(payload), 5, 2, kind, 0, b'test')
    header = struct.pack('>7I4B32s', *fields)
    return header[:4] + struct.pack('>I', zlib.crc32(header)) + header[8:] + payload


class RamPackageTests(unittest.TestCase):
    def test_valid_kernel_and_ramdisk(self):
        self.assertEqual(ram.uimage(make_image(), 2)['payload_bytes'], 4)
        self.assertEqual(ram.uimage(make_image(kind=3), 3)['load_address'], '0x8000')

    def test_reject_corruption_and_wrong_type(self):
        good = make_image()
        for bad in (good[:10], good + b'x', good[:-1] + b'X',
                    good[:12] + b'\xff' + good[13:], make_image(kind=3)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ram.uimage(bad, 2)

    def test_staging_ranges(self):
        ram.check_ranges({name: b'x' for name in ram.ADDRESSES})
        with self.assertRaisesRegex(ValueError, 'overlap'):
            ram.check_ranges({'zynq-e200-ram.dtb': bytes(0x80001), 'uImage': b'x'})
        with self.assertRaisesRegex(ValueError, 'outside'):
            ram.check_ranges({'rootfs.cpio.uboot': FakeLargeArtifact()})


class FakeLargeArtifact:
    def __len__(self):
        return 0x10000000


if __name__ == '__main__':
    unittest.main()
