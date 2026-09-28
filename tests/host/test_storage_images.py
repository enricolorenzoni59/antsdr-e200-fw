import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[2]/'scripts/package/storage-images.py'
spec = importlib.util.spec_from_file_location('storage_images', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StorageImageTests(unittest.TestCase):
    def test_normal_boot_uses_initramfs_device_setup(self):
        args = mod.BOOTARGS.split()
        self.assertEqual([x for x in args if x.startswith("rdinit=")], ["rdinit=/init"])
        self.assertIn("panic=0", args)

    def test_iq24_opt_in_preserves_normal_boot_and_storage_policy(self):
        standard = set(mod.profile_bootargs('standard').split())
        iq24 = set(mod.profile_bootargs('iq24').split())
        self.assertEqual(standard - iq24, {'maxcpus=1'})
        self.assertEqual(iq24 - standard, {'maxcpus=2', 'industrialio_buffer_dma.cached_rx=1'})
        self.assertIn('rdinit=/init', iq24)
        with self.assertRaises(ValueError):
            mod.profile_bootargs('typo')

    def test_firmware_padding_preserves_prefix(self):
        with patch.object(mod, 'FLASH_CAPACITY', 16):
            result = mod.partition_payload(b'FIT')
        self.assertEqual(result, b'FIT' + b'\xff'*13)

    def test_exact_partition_limit(self):
        with patch.object(mod, 'FLASH_CAPACITY', 4):
            self.assertEqual(mod.partition_payload(b'1234'), b'1234')
            with self.assertRaises(ValueError):
                mod.partition_payload(b'12345')

    def test_fit_corruption_rejected(self):
        payload = b'kernel'
        props = {('/images/linux_kernel@1','data'):payload,
                 ('/images/linux_kernel@1/hash@1','algo'):b'sha256\0',
                 ('/images/linux_kernel@1/hash@1','value'):bytes(32)}
        with patch.object(mod.ram, 'fdt_properties', return_value=(set(),props,[])):
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                mod.verify_fit(b'fake',{'linux_kernel@1':payload})


if __name__ == '__main__': unittest.main()
