"""Verify the self-test cannot pass short or failed receive commands."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'board/antsdr-e200/rootfs-overlay/usr/sbin/e200-selftest'
LOADER = importlib.machinery.SourceFileLoader('selftest', str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MODULE)


class StreamTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.tool = self.path / 'iio_readdev'
        env = patch.dict(os.environ, PATH=str(self.path) + os.pathsep + os.environ['PATH'])
        env.start()
        self.addCleanup(env.stop)

    def fake_tool(self, count, status=0):
        self.tool.write_text('#!/usr/bin/env python3\nimport sys\n'
                             f'sys.stdout.buffer.write(bytes({count}))\nraise SystemExit({status})\n')
        self.tool.chmod(0o755)

    def test_single_rx_explicitly_selects_one_pair_even_on_dual_hardware(self):
        self.assertEqual(MODULE.select_rx_channels(
            ['voltage0', 'voltage1', 'voltage2', 'voltage3'], 1),
            ['voltage0', 'voltage1'])

    def test_dual_rx_requires_both_complete_pairs(self):
        for available in (['voltage0', 'voltage1'],
                          ['voltage0', 'voltage1', 'voltage2']):
            with self.assertRaises(RuntimeError):
                MODULE.select_rx_channels(available, 2)
        self.assertEqual(len(MODULE.select_rx_channels(
            ['voltage0', 'voltage1', 'voltage2', 'voltage3'], 2)), 4)

    def test_single_rx_still_requires_both_iq_components(self):
        with self.assertRaises(RuntimeError):
            MODULE.select_rx_channels(['voltage0'], 1)

    def test_invalid_rx_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.select_rx_channels([], 0)

    def test_complete_receive_counts_bytes(self):
        self.fake_tool(16)
        result = MODULE.stream(['voltage0', 'voltage1'], 4, 1)
        self.assertEqual(result['samples_received'], 4)
        self.assertFalse(result['dma_continuity_verified'])

    def test_short_receive_cannot_pass(self):
        self.fake_tool(8)
        with self.assertRaises(RuntimeError):
            MODULE.stream(['voltage0', 'voltage1'], 4, 1)

    def test_command_error_cannot_pass_even_with_expected_bytes(self):
        self.fake_tool(16, 1)
        with self.assertRaises(RuntimeError):
            MODULE.stream(['voltage0', 'voltage1'], 4, 1)


if __name__ == '__main__':
    unittest.main()
