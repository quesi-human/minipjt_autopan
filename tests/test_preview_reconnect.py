import argparse
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'esp32-usb-cam'))
spec = importlib.util.spec_from_file_location('preview', ROOT/'esp32-usb-cam/web-preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class ReconnectTests(unittest.TestCase):
    def tearDown(self):
        preview.stop.clear()

    def test_retry_alternates_operating_and_boot_speed(self):
        speeds = []
        preview.stop.clear()
        preview.state['camera_reconnects'] = 0
        def failed_session(args):
            speeds.append(args.initial_baud)
            if len(speeds) == 3:
                preview.stop.set()
        with patch.object(preview, 'camera_session', failed_session), \
             patch.object(preview.stop, 'wait', return_value=False):
            preview.camera_worker(argparse.Namespace(initial_baud=115200, baud=921600))
        self.assertEqual(speeds, [115200, 921600, 115200])
        self.assertEqual(preview.state['camera_reconnects'], 2)


if __name__ == '__main__':
    unittest.main()
