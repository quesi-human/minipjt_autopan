import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "esp32-usb-cam"))
from lanyard_classifier import classify_lanyard


class LanyardClassifierTest(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((240, 320, 3), 180, np.uint8)
        self.box = [60, 10, 160, 230]

    def strap(self, color, x=95):
        cv2.line(self.frame, (x, 48), (x + 7, 112), color, 3)

    def role(self):
        return classify_lanyard(self.frame, self.box)["role"]

    def test_sky_blue_strip_is_student(self):
        self.strap((235, 190, 90))
        self.assertEqual(self.role(), "student")

    def test_contrasting_black_strip_is_staff(self):
        self.strap((25, 25, 25))
        self.assertEqual(self.role(), "staff")

    def test_black_clothing_is_unknown(self):
        self.frame[:] = 25
        self.assertEqual(self.role(), "unknown")

    def test_blue_clothing_is_unknown(self):
        self.frame[:] = (235, 190, 90)
        self.assertEqual(self.role(), "unknown")

    def test_both_colors_are_ambiguous(self):
        self.strap((235, 190, 90), 90)
        self.strap((25, 25, 25), 120)
        self.assertEqual(self.role(), "unknown")

    def test_color_outside_torso_is_ignored(self):
        self.strap((235, 190, 90), 200)
        self.assertEqual(self.role(), "unknown")

    def test_distant_or_cropped_body_is_unknown(self):
        self.strap((235, 190, 90))
        for box in ([60, 10, 90, 80], [-20, 10, 160, 230]):
            with self.subTest(box=box):
                self.assertEqual(classify_lanyard(self.frame, box)["role"], "unknown")


if __name__ == "__main__":
    unittest.main()
